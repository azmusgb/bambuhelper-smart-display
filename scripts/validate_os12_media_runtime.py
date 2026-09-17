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
        "recordingAvailable",
        "isSessionActive() const",
        "hasRecording() const",
    ])
    require(repo / "include/ws350_media_backend.h", [
        "class Ws350MediaBackend",
        "recordingPlaybackRequested_",
    ])
    require(repo / "include/workshop_media_runtime.h", ["workshopMediaSnapshot"])
    require(repo / "src/media_service.cpp", [
        "MediaError::Busy",
        "MediaError::OutOfMemory",
        "refreshBackendFacts",
    ])
    backend = require(repo / "src/ws350_media_backend.cpp", [
        "BOARD_HAS_ES8311_AUDIO",
        "BOARD_HAS_MICROPHONE",
        "buzzerBackendSetVolume",
        "buzzerBackendMicLevel",
        "buzzerBackendMicRecordBegin",
        "buzzerBackendMicRecordPoll",
        "buzzerBackendMicRecordStop",
        "buzzerBackendMicPlaybackBegin",
        "buzzerBackendMicPlaybackPoll",
        "buzzerBackendMicHasRecording",
        "videoDecoderAvailable = false",
    ])
    require(repo / "src/workshop_media_runtime.cpp", ["gMediaService", "gMediaBackend"])

    # Recording is now implemented only through the bounded ES8311/PSRAM path.
    # Video remains fail-closed until a real bounded MJPEG decoder is installed.
    if "bool Ws350MediaBackend::beginRecording" not in backend:
        raise SystemExit("FAIL: bounded recording backend missing")
    if "recordingRequested_ = buzzerBackendMicRecordBegin(maxDurationMs);" not in backend:
        raise SystemExit("FAIL: recording does not route through the bounded microphone backend")
    if "bool Ws350MediaBackend::beginMjpeg" not in backend or "videoRequested_ = false;" not in backend:
        raise SystemExit("FAIL: MJPEG capability must remain fail-closed")

    print("PASS: reconstructed OS12 media runtime has bounded recording/playback and fail-closed video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
