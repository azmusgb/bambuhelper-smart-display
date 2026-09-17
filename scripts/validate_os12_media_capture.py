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
            "captureScratch",
            "memcpy(gOs12RecordingData + used, captureScratch, bytesRead)",
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

    for forbidden in (
        "gOs12CapturePauseRequested",
        "gOs12CaptureTxPaused",
        "os12PauseAudioTxForCapture",
        "vTaskDelete(task)",
    ):
        if forbidden in source:
            raise SystemExit(f"FAIL: recording path retained unsafe task-handoff marker {forbidden}")

    direct_psram_read = "i2s_read((i2s_port_t)AUDIO_I2S_PORT,\n                                  gOs12RecordingData + used"
    if direct_psram_read in source:
        raise SystemExit("FAIL: I2S RX must not write directly into the PSRAM recording buffer")

    begin = source.find("bool buzzerBackendMicRecordBegin")
    stop_tone = source.find("buzzerBackendStop();", begin)
    activate = source.find("gOs12RecordingActive = true;", begin)
    if begin < 0 or stop_tone < 0 or activate < 0 or stop_tone > activate:
        raise SystemExit("FAIL: recording must keep ES8311 task alive but silence TX before activation")

    print("PASS: OS12 microphone capture is PSRAM-bounded, poll-driven, keeps I2S clocks alive, and stages RX through internal RAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
