#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/platform/media/media_service.h"
SOURCE = ROOT / "firmware/platform/media/media_service.cpp"
BACKEND_H = ROOT / "firmware/platform/media/ws350_media_backend.h"
BACKEND_CPP = ROOT / "firmware/platform/media/ws350_media_backend.cpp"
RUNTIME_H = ROOT / "firmware/platform/media/workshop_media_runtime.h"
RUNTIME_CPP = ROOT / "firmware/platform/media/workshop_media_runtime.cpp"
TEST = ROOT / "tests/workshop_os12_media_smoke.cpp"
PATCHER = ROOT / "apply_workshop_os12_media_runtime.py"


def require(path: Path, needles: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"FAIL: {path}: missing {needle!r}")


def forbid(path: Path, needles: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"FAIL: {path}: forbidden {needle!r}")


def main() -> int:
    require(HEADER, [
        "class MediaService",
        "class HardwareBackend",
        "PlayingAudio",
        "Recording",
        "PlayingRecording",
        "PlayingVideo",
        "Paused",
        "speakerAvailable",
        "microphoneAvailable",
        "videoDecoderAvailable",
        "psramAvailable",
        "recordingAvailable",
        "isSessionActive() const",
        "hasRecording() const",
        "audioUnderruns",
        "droppedVideoFrames",
    ])
    forbid(HEADER, ["namespace workshop::media"])
    require(SOURCE, [
        "requireIdle()",
        "MediaError::Busy",
        "MediaError::OutOfMemory",
        "beginRecording",
        "playRecording",
        "refreshBackendFacts",
        "backend_->hasRecording()",
        "backend_->isSessionActive()",
        "beginMjpeg",
        "pauseVideo",
        "stopMedia",
    ])
    require(BACKEND_H, [
        "class Ws350MediaBackend",
        "HardwareBackend",
        "recordingPlaybackRequested_",
        "videoLastFrameId_",
        "videoLastRenderAtMs_",
        "renderLatestCameraFrame",
        "isSessionActive() const override",
        "hasRecording() const override",
    ])
    require(BACKEND_CPP, [
        "BOARD_HAS_ES8311_AUDIO",
        "BOARD_HAS_MICROPHONE",
        "buzzerBackendSetVolume",
        "buzzerBackendMicLevel",
        "buzzerBackendMicRecordBegin",
        "buzzerBackendMicRecordPoll",
        "buzzerBackendMicPlaybackBegin",
        "buzzerBackendMicPlaybackPoll",
        "buzzerBackendMicHasRecording",
        "psramFound()",
        'kPrinterCameraSource[] = "printer-camera"',
        "cameraCanStreamDisplayedPrinter()",
        "cameraBegin()",
        "cameraGetLatestFrame",
        "tft.drawJpg",
        "kVideoFrameIntervalMs = 125U",
        "videoDecoderAvailable = caps.psramAvailable",
    ])
    forbid(BACKEND_CPP, [
        "WiFiClient",
        "HTTPClient",
        "setInsecure",
        "server.arg",
    ])
    require(RUNTIME_H, ["workshopMediaBegin", "workshopMediaPoll", "workshopMediaSnapshot"])
    require(RUNTIME_CPP, ["gMediaService", "gMediaBackend", "millis()"])
    require(PATCHER, [
        "WORKSHOP_OS_RELEASE_VERSION",
        "buzzerBackendSetVolume",
        "workshopMediaBegin();",
        "workshopMediaPoll();",
    ])
    require(TEST, [
        'assert(!media.playMjpeg("clip.mjpg"',
        "MediaError::Busy",
        "MediaError::OutOfMemory",
        "SessionState::Fault",
        "recordingAvailable",
        "isSessionActive() const override",
        "hasRecording() const override",
    ])

    with tempfile.TemporaryDirectory(prefix="os12-media-") as td:
        binary = Path(td) / "media-smoke"
        cmd = [
            "c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(SOURCE), str(TEST), "-o", str(binary),
        ]
        subprocess.run(cmd, check=True, cwd=ROOT)
        subprocess.run([str(binary)], check=True, cwd=ROOT)

    print("PASS: OS12 media service, async recording lifecycle, bounded fixed-source MJPEG boundary and C++11 contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
