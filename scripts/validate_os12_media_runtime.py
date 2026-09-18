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
        "VideoSource",
        "renderDemoFrame",
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
        'kDemoVideoSource[] = "demo-video"',
        'kPrinterCameraSource[] = "printer-camera"',
        "VideoSource::Demo",
        "VideoSource::PrinterCamera",
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
    if 'std::strcmp(source, kDemoVideoSource) == 0' not in backend:
        raise SystemExit("FAIL: built-in WS350 demo video source missing")
    if 'std::strcmp(source, kPrinterCameraSource) == 0' not in backend:
        raise SystemExit("FAIL: printer camera must remain an explicit source, not the video authority")
    if "caps.videoDecoderAvailable = caps.psramAvailable;" not in backend:
        raise SystemExit("FAIL: WS350 video capability must be device-owned and PSRAM-gated")
    if "cameraService();" not in backend or "renderLatestCameraFrame(millis());" not in backend:
        raise SystemExit("FAIL: MJPEG playback is not poll-driven")
    if "WiFiClient" in backend or "HTTPClient" in backend:
        raise SystemExit("FAIL: media backend created a second network transport authority")

    if 'if (videoLastFrameId_ == 0U)' not in backend:
        raise SystemExit("FAIL: demo video must initialize its static scene exactly once per session")
    if 'tft.fillRect(previousX, previousY, 56, 56, TFT_BLACK);' not in backend:
        raise SystemExit("FAIL: demo video must use bounded dirty-region motion updates")

    print("PASS: reconstructed OS12 media runtime has bounded recording/playback, device-owned demo video, and source-scoped printer camera rendering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
