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
        "videoLastFrameId_",
        "renderLatestCameraFrame",
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
        'kPrinterCameraSource[] = "printer-camera"',
        "cameraCanStreamDisplayedPrinter()",
        "cameraBegin()",
        "cameraGetLatestFrame",
        "tft.drawJpg",
        "videoDecoderAvailable = caps.psramAvailable",
    ])
    require(repo / "src/workshop_media_runtime.cpp", ["gMediaService", "gMediaBackend"])

    if "bool Ws350MediaBackend::beginRecording" not in backend:
        raise SystemExit("FAIL: bounded recording backend missing")
    if "recordingRequested_ = buzzerBackendMicRecordBegin(maxDurationMs);" not in backend:
        raise SystemExit("FAIL: recording does not route through the bounded microphone backend")
    if 'std::strcmp(source, kPrinterCameraSource) != 0' not in backend:
        raise SystemExit("FAIL: MJPEG source must be constrained to the existing printer-camera authority")
    if "cameraService();" not in backend or "renderLatestCameraFrame(millis());" not in backend:
        raise SystemExit("FAIL: MJPEG playback is not poll-driven")
    if "WiFiClient" in backend or "HTTPClient" in backend:
        raise SystemExit("FAIL: media backend created a second network transport authority")

    print("PASS: reconstructed OS12 media runtime has bounded recording/playback and fixed-source MJPEG rendering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
