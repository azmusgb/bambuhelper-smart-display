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
            "gOs12CaptureKeepAlive",
            "if (!gOs12CaptureKeepAlive) shutdownAudio();",
            "captureScratch",
            "memcpy(gOs12RecordingData + used, captureScratch, bytesRead)",
            "gOs12PlaybackPosition < gOs12RecordingBytes",
            "if (gOs12PlaybackActive) gIdleStartMs = millis();",
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
    pin = source.find("gOs12CaptureKeepAlive = true;", begin)
    refresh = source.find("gIdleStartMs = millis();", pin)
    stop_tone = source.find("buzzerBackendStop();", begin)
    activate = source.find("gOs12RecordingActive = true;", begin)
    if begin < 0 or pin < 0 or refresh < 0 or stop_tone < 0 or activate < 0:
        raise SystemExit("FAIL: recording I2S lifetime pin sequence is incomplete")
    if not (begin < pin < refresh < stop_tone < activate):
        raise SystemExit("FAIL: I2S lifetime must be pinned before TX silence and recording activation")

    poll = source.find("bool buzzerBackendMicRecordPoll")
    poll_refresh = source.find("gIdleStartMs = millis();", poll)
    poll_read = source.find("i2s_read((i2s_port_t)AUDIO_I2S_PORT", poll)
    if poll < 0 or poll_refresh < 0 or poll_read < 0 or poll_refresh > poll_read:
        raise SystemExit("FAIL: recording poll must refresh audio lifetime before I2S RX")

    finish = source.find("void os12FinishRecording")
    release = source.find("gOs12CaptureKeepAlive = false;", finish)
    if finish < 0 or release < 0:
        raise SystemExit("FAIL: recording completion must release I2S lifetime pin")

    playback_begin = source.find("bool buzzerBackendMicPlaybackBegin")
    playback_pin = source.find("gOs12CaptureKeepAlive = true;", playback_begin)
    playback_refresh = source.find("gIdleStartMs = millis();", playback_pin)
    playback_stop_tone = source.find("buzzerBackendStop();", playback_begin)
    playback_activate = source.find("gOs12PlaybackActive = true;", playback_begin)
    if min(playback_begin, playback_pin, playback_refresh, playback_stop_tone, playback_activate) < 0:
        raise SystemExit("FAIL: playback I2S lifetime pin sequence is incomplete")
    if not (playback_begin < playback_pin < playback_refresh < playback_stop_tone < playback_activate):
        raise SystemExit("FAIL: playback must pin I2S lifetime before TX silence and activation")

    playback_poll = source.find("bool buzzerBackendMicPlaybackPoll")
    playback_poll_refresh = source.find("if (gOs12PlaybackActive) gIdleStartMs = millis();", playback_poll)
    if playback_poll < 0 or playback_poll_refresh < 0:
        raise SystemExit("FAIL: playback poll must refresh audio lifetime while active")

    playback_loop = source.find("if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes)")
    playback_complete = source.find("gOs12PlaybackActive = false;\n        gOs12CaptureKeepAlive = false;", playback_loop)
    if playback_loop < 0 or playback_complete < 0:
        raise SystemExit("FAIL: audio task must release playback lifetime pin when retained audio drains")

    playback_stop = source.find("void buzzerBackendMicPlaybackStop()")
    stop_release = source.find("gOs12CaptureKeepAlive = false;", playback_stop)
    if playback_stop < 0 or stop_release < 0:
        raise SystemExit("FAIL: explicit playback stop must release I2S lifetime pin")

    print("PASS: OS12 microphone capture/playback is PSRAM-bounded, poll-driven, pins I2S lifetime during RX/TX, and stages RX through internal RAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())