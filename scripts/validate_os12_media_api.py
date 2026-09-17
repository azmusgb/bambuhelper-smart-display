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
        'Cache-Control',
        'no-store',
    ):
        if needle not in text:
            raise SystemExit(f"FAIL: media API missing {needle!r}")

    for forbidden in (
        'SECURE_POST("/os12/media/play-url"',
        'server.arg("url")',
        'server.arg("source")',
        'server.arg("duration")',
        'server.on("/os12/media/',
    ):
        if forbidden in text:
            raise SystemExit(f"FAIL: media API contains forbidden surface {forbidden!r}")

    print("PASS: OS12 media API is authenticated, source-free and fixes recording to the bounded five-second contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
