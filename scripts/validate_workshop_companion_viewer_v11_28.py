#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"v11.28 Companion Viewer validation failed: {message}")


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
    header = (root / "src/companion_web.h").read_text(encoding="utf-8")
    companion = (root / "src/companion_web.cpp").read_text(encoding="utf-8")
    display = (root / "src/display_ui.cpp").read_text(encoding="utf-8")

    for marker in [
        'SMART_HOME_VERSION "v11.28"',
        'SMART_HOME_PROFILE "companion-viewer"',
        'Smart Home v11.28 Physical Companion Viewer RC1',
        'Workshop OS v11.28 Physical Companion Viewer RC1',
    ]:
        need(build, marker, "candidate identity")

    for marker in [
        "companionWebViewerActive()",
        "companionWebViewerDeactivate()",
        "uint16_t* width, uint16_t* height",
    ]:
        need(header, marker, "viewer API")

    for marker in [
        'server.on("/companion/capture/show", HTTP_POST, handleCompanionCaptureShow)',
        "securityAuthorize(server, true)",
        "g_captureViewerActive = true",
        "setScreenState(SCREEN_CAMERA)",
        'server.arg("w")',
        'server.arg("h")',
        "requestedWidth < 1 || requestedWidth > 480",
        "requestedHeight < 1 || requestedHeight > 480",
        'cap["width"]',
        'cap["height"]',
        'cap["viewer"]',
        "Show on Waveshare",
        "uploadCaptureBlob(blob,width,height)",
    ]:
        need(companion, marker, "explicit phone-photo viewer contract")

    # Uploading a photo must never itself steal the physical display.
    upload_start = companion.find("void handleCompanionCaptureUpload")
    show_start = companion.find("void handleCompanionCaptureShow")
    if upload_start >= 0 and show_start > upload_start:
        upload_slice = companion[upload_start:show_start]
        forbid(upload_slice, "setScreenState(SCREEN_CAMERA)", "automatic screen takeover during upload")

    for marker in [
        '#include "companion_web.h"',
        "if (companionWebViewerActive())",
        "companionWebGetLatestCapture(&phoneBuf, &phoneLen, &captureId, &srcW, &srcH)",
        "tft.drawJpg(phoneBuf, (uint32_t)phoneLen",
        "PHONE PHOTO  |  TAP TO EXIT",
        "cameraGetLatestFrame(",
        "companionWebViewerDeactivate()",
    ]:
        need(display, marker, "physical viewer/chamber-camera coexistence")

    for forbidden in ["LittleFS", "SPIFFS", "FFat", "Preferences", "putBytes(", "writeFile("]:
        forbid(companion, forbidden, "phone-capture flash persistence")

    print("Workshop OS v11.28 Physical Companion Viewer contracts: PASS")
    print("Phone photo display takeover: EXPLICIT ONLY")
    print("JPEG renderer length: EXPLICIT UINT32")
    print("Normal chamber-camera fallback: PRESERVED")
    print("Phone capture persistence: VOLATILE PSRAM ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
