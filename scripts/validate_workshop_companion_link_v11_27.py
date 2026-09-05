#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise ValidationError(f"missing {label}: {token}")


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise ValidationError(f"forbidden {label}: {token}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    root = Path(args.repo)

    build = (root / "include/smart_home_build.h").read_text(encoding="utf-8")
    header = (root / "src/companion_web.h").read_text(encoding="utf-8")
    source = (root / "src/companion_web.cpp").read_text(encoding="utf-8")
    security = (root / "src/security_manager.cpp").read_text(encoding="utf-8")
    web = (root / "src/web_server.cpp").read_text(encoding="utf-8")
    ble = (root / "src/workshop_companion_ble.cpp").read_text(encoding="utf-8")

    for token in [
        'SMART_HOME_VERSION "v11.27"',
        'SMART_HOME_PROFILE "companion-link"',
        'Smart Home v11.27 Companion Link RC1',
        'Workshop OS v11.27 Companion Link RC1',
    ]:
        need(build, token, "v11.27 identity")

    for token in [
        'server.on("/companion/state", HTTP_GET, handleCompanionState);',
        'server.on("/companion/capture", HTTP_POST, handleCompanionCaptureComplete, handleCompanionCaptureUpload);',
        'server.on("/companion/capture/clear", HTTP_POST, handleCompanionCaptureClear);',
        'securityAuthorize(server, false)',
        'securityAuthorize(server, true)',
        'doc["protocol"] = 2',
        'doc["transport"] = "wifi-web"',
        'doc["printer"]',
        'doc["power"]',
        'doc["device"]',
        'doc["capture"]',
        'printer["remainingMinutes"]',
        'printer["lightState"]',
        'pwr["watts"]',
        'dev["heapKb"]',
        'dev["psramFreeKb"]',
        'notePhoneSeen(slot)',
    ]:
        need(source, token, "state envelope")

    for token in [
        'kCaptureMaxBytes = 256U * 1024U',
        'MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT',
        'CAPTURE_UPLOAD_TOO_LARGE',
        'CAPTURE_UPLOAD_INVALID_JPEG',
        'upload.type != "image/jpeg"',
        'g_captureInflight[0] != 0xFF',
        'g_captureInflight[1] != 0xD8',
        'g_captureInflight[g_captureInflightLen - 2] != 0xFF',
        'g_captureInflight[g_captureInflightLen - 1] != 0xD9',
        'clearPublishedCapture()',
        'companionWebGetLatestCapture',
        'companionWebClearCapture',
    ]:
        need(source + header, token, "volatile capture transport")

    for token in [
        "fetchJson('/companion/state?slot=",
        "form.append('capture',blob,'capture.jpg')",
        "maxDim=480",
        "canvas.toBlob",
        "250*1024",
        "suppressPowerClickUntil",
        "POWER OFF DURING PRINT",
        "command('/printer/control'",
        "command('/light/set'",
        "post('/printer/power'",
        "Workshop Companion Link · v11.27 candidate",
        "No phone photo stored on the Waveshare.",
    ]:
        need(source, token, "mobile Companion behavior")

    # v11.27 replaces the v11.26 three-request refresh loop with one state GET.
    for token in [
        "Promise.all([fetchJson('/status?slot=",
        "fetchJson('/printer/power/status?slot=",
        "setInterval(heartbeat",
        "heartTimer=",
    ]:
        forbid(source, token, "legacy multi-request polling")

    # Captures are RAM-only. Never write phone photos to persistent storage.
    for token in [
        'LittleFS',
        'SPIFFS',
        'FFat',
        'fopen(',
        'Preferences',
        'putBytes(',
        'writeFile(',
    ]:
        forbid(source, token, "capture persistence")

    # The Companion remains a session-authenticated same-origin surface.
    for token in ['return cookieMatches(server);', 'if (mutating && !sameOrigin(server))']:
        need(security, token, "inherited portal/session boundary")
    for token in [
        'WORKSHOP_OS_TEMP_LAN_OPEN',
        'if (!isAPMode()) return true;',
        'TEMPORARY TRUSTED-LAN MODE',
        'sendHeader("Location", server.arg("next"))',
    ]:
        forbid(build + security + web + source, token, "auth/open-redirect bypass")

    # BLE stays orchestration-only even as web gains the authenticated payload plane.
    need(ble, 'g_phoneConnected || companionWebPhoneConnected()', "unified BLE/web presence")
    for token in [
        'requestPrinterControlCommand',
        'requestLightCommand',
        'tasmotaSetPower',
        'portalCode',
        'sessionCookie',
        'Set-Cookie',
    ]:
        forbid(ble, token, "BLE authority/secret leak")

    # Companion web must not smuggle long-lived credentials into its embedded page.
    for token in ['access_code', 'accessCode', 'wifiPassword', 'portalCode', 'BHSESSION=']:
        forbid(source, token, "embedded credential")

    # Extract the embedded HTML and syntax-check the exact JavaScript shipped in firmware.
    match = re.search(r'const char kCompanionHtml\[\] PROGMEM = R"COMPANION\((.*?)\)COMPANION";', source, re.S)
    if not match:
        raise ValidationError("embedded Companion HTML not found")
    html = match.group(1)
    script = re.search(r'<script>\s*(.*?)\s*</script>', html, re.S)
    if not script:
        raise ValidationError("embedded Companion JavaScript not found")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script.group(1))
        js_path = fh.name
    result = subprocess.run(["node", "--check", js_path], capture_output=True, text=True)
    Path(js_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise ValidationError("embedded Companion JavaScript failed node --check:\n" + result.stderr)

    print("Workshop Companion Link v11.27 contract: PASS")
    print("state_transport=SINGLE_AUTHENTICATED_ENVELOPE")
    print("capture_transport=JPEG_TO_VOLATILE_PSRAM")
    print("capture_max_bytes=262144")
    print("capture_persistence=ABSENT")
    print("ble_authority=ORCHESTRATION_ONLY")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"V11.27 COMPANION LINK FAILED: {exc}")
        raise SystemExit(1)
