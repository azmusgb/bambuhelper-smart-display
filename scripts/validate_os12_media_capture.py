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
            "gOs12CapturePauseRequested",
            "gOs12CaptureTxPaused",
            "os12PauseAudioTxForCapture",
            "os12ResumeAudioTaskAfterCapture",
            "vTaskDelay(pdMS_TO_TICKS(1))",
            "gOs12PlaybackPosition < gOs12RecordingBytes",
            "i2s_read",
        ),
    )

    if "buzzerBackendMicEcho" not in header:
        raise SystemExit("FAIL: legacy mic primitive unexpectedly missing; donor continuity lost")
    if "while (gOs12RecordingActive" in source:
        raise SystemExit("FAIL: capture backend contains an unbounded active-recording loop")
    if "vTaskDelete(task)" in source:
        raise SystemExit("FAIL: capture must not force-delete the live ES8311 task")

    capture_api = source[source.find("bool buzzerBackendMicRecordBegin"):]
    if "delay(" in capture_api:
        raise SystemExit("FAIL: OS12 capture API must not add delay-based recording")

    pause_request = source.find("gOs12CapturePauseRequested = true;", source.find("bool os12PauseAudioTxForCapture"))
    pause_ack = source.find("while (!gOs12CaptureTxPaused", pause_request)
    activate = source.find("gOs12RecordingActive = true;", source.find("bool buzzerBackendMicRecordBegin"))
    if pause_request < 0 or pause_ack < 0 or activate < 0:
        raise SystemExit("FAIL: capture pause/ack handoff is incomplete")

    task_loop = source.find("if (gOs12CapturePauseRequested)")
    ack_set = source.find("gOs12CaptureTxPaused = true;", task_loop)
    ack_clear = source.find("gOs12CaptureTxPaused = false;", ack_set)
    if task_loop < 0 or ack_set < 0 or ack_clear < 0:
        raise SystemExit("FAIL: ES8311 task must cooperatively acknowledge capture pause and resume")

    if "if (gOs12RecordingActive || gOs12CapturePauseRequested) os12FinishRecording();" not in source:
        raise SystemExit("FAIL: explicit recording stop must release capture ownership")

    print("PASS: OS12 microphone capture is PSRAM-bounded, poll-driven and uses cooperative single-owner I2S handoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
