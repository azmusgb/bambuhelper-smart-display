#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);args=ap.parse_args()
    hub=Path(args.repo).resolve()/"src/smart_hub.cpp"
    if not hub.is_file(): raise SystemExit(f"FAIL: missing {hub}")
    text=hub.read_text(encoding="utf-8")
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
        'Video',
        'PSRAM',
        'Hardware not detected',
        'Decoder is not advertised yet',
    ):
        if needle not in text: raise SystemExit(f"FAIL: media UI missing {needle!r}")
    for forbidden in ('matchSpoolByColor','matchSpoolByMaterial','resolveSpool'):
        if forbidden in text: raise SystemExit(f"FAIL: media UI introduced forbidden inventory inference {forbidden}")
    print('PASS: OS12 media touchscreen UI is capability-scoped and explicit about unavailable features')
    return 0

if __name__=='__main__': raise SystemExit(main())
