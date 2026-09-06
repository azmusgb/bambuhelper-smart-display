#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(msg: str) -> None:
    raise SystemExit(f"v11.30 Unified Web + Companion validation failed: {msg}")


def need(body: str, needle: str, label: str) -> None:
    if needle not in body:
        fail(f"missing {label}: {needle}")


def forbid(body: str, needle: str, label: str) -> None:
    if needle in body:
        fail(f"forbidden {label}: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    root = Path(ap.parse_args().repo).resolve()

    build = (root / "include/smart_home_build.h").read_text(encoding="utf-8")
    app = (root / "web/app.js").read_text(encoding="utf-8")
    companion = (root / "src/companion_web.cpp").read_text(encoding="utf-8")
    security = (root / "src/security_manager.cpp").read_text(encoding="utf-8")

    for marker in [
        'SMART_HOME_VERSION "v11.30"',
        'SMART_HOME_PROFILE "unified-web-companion"',
        'Smart Home v11.30 Unified Web + Companion RC1',
        '#define WORKSHOP_OS_ACCEPTANCE_OPEN_LAN 1',
        'Workshop OS v11.30 Unified Web + Companion RC1',
    ]:
        need(build, marker, "candidate identity / inherited acceptance mode")

    for marker in [
        'Workshop OS v11.30 Unified Web + Companion UX',
        'v1130UnifiedRail',
        'v1130-mobile-dock',
        'v1130Attention',
        'Open Companion',
        "ca.href='/companion'",
        "dca.href='/companion'",
        "fetch('/companion/state?slot=0&_='+Date.now()",
        'window.v1130PauseLiveRail=function(value)',
        'v1130PauseLiveRail(true)',
        "xhr.addEventListener('loadend'",
        "document.hidden?7000:3200",
    ]:
        need(app, marker, "standard web unified UX")

    # The standard portal's supplemental state poll must explicitly stand down
    # during OTA so it cannot contend with the ESP32's long upload connection.
    stop = app.find('stopPolling();')
    pause = app.find('v1130PauseLiveRail(true)', stop)
    xhr = app.find('var xhr = new XMLHttpRequest();', stop)
    if stop < 0 or pause < stop or xhr < pause:
        fail("OTA live-rail pause ordering is not stopPolling -> pause -> XHR")

    for marker in [
        'v11.30 Companion refinement',
        'v1130CompanionNav',
        'v1130CompanionEnhance',
        'Overview', 'Controls', 'Photo', 'System',
        'v1130AttentionCard',
        'Getting workshop state',
        'Print paused',
        'Waveshare online · printer offline',
        'Workshop ready',
        'Unified Web + Companion · v11.30 candidate',
    ]:
        need(companion, marker, "Companion refinement")

    # Companion enhancement reuses the existing one-second state/UI loop via
    # DOM state. It must not add a second /companion/state poll of its own.
    enhance_at = companion.find('<script id="v1130CompanionEnhance">')
    if enhance_at < 0:
        fail("Companion enhancement script boundary missing")
    enhance = companion[enhance_at:]
    forbid(enhance, "fetch('/companion/state", "duplicate Companion network poll")
    forbid(enhance, 'fetchJson(', "duplicate Companion network poll")

    # v11.28 explicit photo control and volatile capture remain first-class.
    for marker in [
        'server.on("/companion/capture/show", HTTP_POST',
        'Show on Waveshare',
        'cap["viewer"]',
        'g_capturePublishedWidth',
        'g_capturePublishedHeight',
        'MALLOC_CAP_SPIRAM',
    ]:
        need(companion, marker, "inherited physical Companion viewer")
    for forbidden in ['LittleFS', 'SPIFFS', 'FFat', 'Preferences', 'putBytes(', 'writeFile(']:
        forbid(companion, forbidden, "photo flash persistence")

    # v11.29 security posture must survive the visual/UX-only delta.
    for marker in [
        'if (!isAPMode()) return true;',
        'if (mutating && !sameOrigin(server))',
        'uri == "/settings/export" || uri == "/debug"',
        'recoverySafeModeActive()',
    ]:
        need(security, marker, "v11.29 security boundary")

    print("Workshop OS v11.30 Unified Web + Companion contracts: PASS")
    print("Standard web live status rail: PRESENT")
    print("Standard web mobile bottom dock: PRESENT")
    print("Full web -> Companion handoff: FIRST-CLASS")
    print("Supplemental full-web live poll: 3.2s visible / 7s hidden")
    print("Supplemental live poll during OTA: PAUSED")
    print("Companion attention summary: DOM-DERIVED / NO EXTRA STATE POLL")
    print("Companion jump navigation: OVERVIEW_CONTROLS_PHOTO_SYSTEM")
    print("v11.28 explicit physical photo viewer: PRESERVED")
    print("v11.29 WS350 Acceptance Open LAN boundary: PRESERVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
