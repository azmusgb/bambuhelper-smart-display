#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def require(path: Path, needles: list[str]) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path}")
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"FAIL: {path}: missing {needle!r}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    main_cpp = require(repo / "src/main.cpp", [
        '#include "workshop_media_runtime.h"',
        "workshopMediaBegin();",
        "workshopMediaPoll();",
    ])
    if main_cpp.count("workshopMediaBegin();") != 1:
        raise SystemExit("FAIL: workshopMediaBegin must appear exactly once")
    if main_cpp.count("workshopMediaPoll();") != 1:
        raise SystemExit("FAIL: workshopMediaPoll must appear exactly once")

    require(repo / "include/media_service.h", [
        "class MediaService",
        "class HardwareBackend",
        "videoDecoderAvailable",
        "psramAvailable",
    ])
    require(repo / "include/ws350_media_backend.h", ["class Ws350MediaBackend"])
    require(repo / "include/workshop_media_runtime.h", ["workshopMediaSnapshot"])
    require(repo / "src/media_service.cpp", ["MediaError::Busy", "MediaError::OutOfMemory"])
    backend = require(repo / "src/ws350_media_backend.cpp", [
        "BOARD_HAS_ES8311_AUDIO",
        "BOARD_HAS_MICROPHONE",
        "buzzerBackendSetVolume",
        "buzzerBackendMicLevel",
        "videoDecoderAvailable = false",
    ])
    require(repo / "src/workshop_media_runtime.cpp", ["gMediaService", "gMediaBackend"])

    # Safety: do not claim video or recording support until a real bounded backend
    # is present and validated. These false returns are intentional for this slice.
    if "bool Ws350MediaBackend::beginRecording" not in backend or "return false;" not in backend:
        raise SystemExit("FAIL: bounded recording must remain fail-closed until implemented")
    if "bool Ws350MediaBackend::beginMjpeg" not in backend:
        raise SystemExit("FAIL: MJPEG capability boundary missing")

    print("PASS: reconstructed OS12 media runtime/lifecycle boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
