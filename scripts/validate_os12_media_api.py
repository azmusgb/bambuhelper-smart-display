#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    web = Path(args.repo).resolve() / "src/web_server.cpp"
    if not web.is_file():
        raise SystemExit(f"FAIL: missing {web}")
    text = web.read_text(encoding="utf-8")

    for needle in (
        '#include "workshop_media_runtime.h"',
        'sendWorkshopMediaStatus',
        'workshopMediaSnapshot()',
        'workshopMediaService()',
        'SECURE_GET("/os12/media/status"',
        'SECURE_POST("/os12/media/speaker-test"',
        'SECURE_POST("/os12/media/microphone-sample"',
        'SECURE_POST("/os12/media/record/start"',
        'SECURE_POST("/os12/media/record/stop"',
        'SECURE_POST("/os12/media/record/play"',
        'SECURE_POST("/os12/media/stop"',
        'startRecording(5000U, millis())',
        'stopRecording(millis())',
        'playRecording(millis())',
        'doc["recordingAvailable"]',
        'doc["videoDecoderAvailable"]',
        'doc["microphoneLevelPercent"]',
        'doc["deviceUptimeMs"]',
        'doc["printerConfigured"]',
        'doc["printerCameraObserved"]',
        'doc["printerLiveviewPreview"]',
        'doc["printerRtspEnabled"]',
        'doc["printerCameraResolution"]',
        'Cache-Control',
        'no-store',
    ):
        if needle not in text:
            raise SystemExit(f"FAIL: media API missing {needle!r}")

    # Existing non-media maintenance routes may legitimately contain a URL or
    # source argument. The media boundary itself must never accept either, so
    # scope source-safety checks to the injected media handler block and media
    # route registrations rather than rejecting unrelated legacy code.
    handler_start = text.find("// Workshop OS 12 media diagnostics API")
    handler_end = text.find("\nvoid initWebServer()", handler_start)
    if handler_start < 0 or handler_end < 0:
        raise SystemExit("FAIL: media handler block missing")
    media_handlers = text[handler_start:handler_end]

    init_start = text.find("void initWebServer() {")
    init_end = text.find("\nvoid handleWebServer()", init_start)
    if init_start < 0 or init_end < 0:
        raise SystemExit("FAIL: web route-registration block missing")
    registration = text[init_start:init_end]
    media_registration = "\n".join(
        line for line in registration.splitlines() if "/os12/media/" in line
    )

    for forbidden in (
        'server.arg("url")',
        'server.arg("source")',
        'server.arg("duration")',
        'play-url',
    ):
        if forbidden in media_handlers or forbidden in media_registration:
            raise SystemExit(f"FAIL: media API contains forbidden surface {forbidden!r}")
    if 'server.on("/os12/media/' in registration:
        raise SystemExit("FAIL: media mutations bypass authenticated SECURE routes")

    if 'playMjpeg("demo-video", millis())' not in media_handlers:
        raise SystemExit("FAIL: media API video start must use the built-in WS350 demo source")

    print("PASS: OS12 media API is authenticated, source-free and starts the built-in WS350 video demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
