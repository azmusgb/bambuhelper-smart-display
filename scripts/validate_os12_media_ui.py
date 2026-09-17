#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    hub = Path(args.repo).resolve() / "src/smart_hub.cpp"
    if not hub.is_file():
        raise SystemExit(f"FAIL: missing {hub}")
    text = hub.read_text(encoding="utf-8")
    for needle in (
        '#include "workshop_media_runtime.h"',
        'static void drawOs12Media()',
        'static void drawOs12MediaLab()',
        'g_ui12SettingsView==10',
        'g_ui12SettingsView==11',
        'workshopMediaSnapshot()',
        'workshopMediaService()',
        'Speaker Volume',
        'Speaker Test',
        'Microphone',
        'Recording',
        'Playback',
        '5 sec max',
        'recordingAvailable',
        'startRecording(5000U,millis())',
        'stopRecording(millis())',
        'playRecording(millis())',
        'Video',
        'Displayed printer camera',
        'playMjpeg("printer-camera",millis())',
        'Tap anywhere to stop',
        'Hardware not detected',
    ):
        if needle not in text:
            raise SystemExit(f"FAIL: media UI missing {needle!r}")
    if 'delay(120)' in text:
        raise SystemExit("FAIL: media speaker test must not block the touchscreen with delay(120)")
    for forbidden in ('matchSpoolByColor', 'matchSpoolByMaterial', 'resolveSpool'):
        if forbidden in text:
            raise SystemExit(f"FAIL: media UI introduced forbidden inventory inference {forbidden}")
    print('PASS: OS12 media touchscreen UI exposes non-blocking speaker/mic, bounded record/playback and fixed-source MJPEG video')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
