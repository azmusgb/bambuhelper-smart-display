#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def require(path: Path, needles: tuple[str, ...]) -> str:
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

    header = require(
        repo / "src/buzzer_backend.h",
        (
            "buzzerBackendMicRecordBegin",
            "buzzerBackendMicRecordPoll",
            "buzzerBackendMicRecordStop",
            "buzzerBackendMicHasRecording",
            "buzzerBackendMicPlaybackBegin",
            "buzzerBackendMicPlaybackPoll",
            "buzzerBackendMicPlaybackStop",
        ),
    )
    source = require(
        repo / "src/buzzer_backend_es8311.cpp",
        (
            "MALLOC_CAP_SPIRAM",
            "kOs12RecordMaxMs = 5000U",
            "kOs12CaptureBurstBytes = 1024U",
            "kOs12CaptureBurstsPerPoll = 2U",
            "gOs12RecordingData",
            "gOs12PlaybackActive",
            "gOs12CaptureOwnsAudioTask",
            "os12SuspendAudioTaskForCapture",
            "os12ResumeAudioTaskAfterCapture",
            "vTaskDelete(task)",
            "gOs12PlaybackPosition < gOs12RecordingBytes",
            "i2s_read",
        ),
    )

    if "buzzerBackendMicEcho" not in header:
        raise SystemExit("FAIL: legacy mic primitive unexpectedly missing; donor continuity lost")
    if "while (gOs12RecordingActive" in source:
        raise SystemExit("FAIL: capture backend contains an unbounded active-recording loop")
    capture_api = source[source.find("bool buzzerBackendMicRecordBegin"):]
    if "delay(" in capture_api:
        raise SystemExit("FAIL: OS12 capture API must not add delay-based recording")

    suspend = source.find("os12SuspendAudioTaskForCapture();", source.find("bool buzzerBackendMicRecordBegin"))
    activate = source.find("gOs12RecordingActive = true;", source.find("bool buzzerBackendMicRecordBegin"))
    if suspend < 0 or activate < 0 or suspend > activate:
        raise SystemExit("FAIL: ES8311 TX task must be suspended before recording becomes active")

    if "if (gOs12RecordingActive || gOs12CaptureOwnsAudioTask) os12FinishRecording();" not in source:
        raise SystemExit("FAIL: explicit recording stop must restore normal ES8311 task ownership")

    print("PASS: OS12 microphone capture is PSRAM-bounded, poll-driven and exclusively owns I2S RX during recording")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
