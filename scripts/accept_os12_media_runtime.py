#!/usr/bin/env python3
"""Exercise Workshop OS 12 media against a real WS350.

Read-only mode validates the API contract. --exercise runs an operator-observable
speaker + microphone + record/playback diagnostic. On an interactive terminal it
shows a live microphone meter, gives audible-test countdowns, and asks the operator
what was actually heard. --exercise-video similarly makes the video lifecycle
operator-observable.

This script deliberately distinguishes runtime truth from human physical evidence.
A successful API lifecycle is never reported as proof that the speaker was audible,
the microphone responded, or video motion was visible.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    assert_code_free_portal,
    check,
)

TERMINAL = {"Idle", "Fault"}
ACTIVE = {
    "Starting", "PlayingAudio", "Recording", "PlayingRecording",
    "PlayingVideo", "Paused", "Stopping",
}


def api(client: Client, path: str, *, method: str = "GET") -> dict:
    headers = {"X-BambuHelper-Client": "1", "Accept": "application/json"}
    response = client.request(path, method=method, headers=headers, timeout=15.0)
    check(
        response.status in (200, 202, 409),
        f"{method} {path} returned HTTP {response.status}: {response.body[:200]}",
    )
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{method} {path} did not return JSON") from exc
    check(isinstance(payload, dict), f"{method} {path} returned non-object JSON")
    payload["_http_status"] = response.status
    return payload


def validate_status(payload: dict) -> None:
    required = (
        "session", "error", "speakerAvailable", "microphoneAvailable",
        "videoDecoderAvailable", "psramAvailable", "psramFreeBytes",
        "volumePercent", "muted", "microphoneLevelPercent",
        "recordingAvailable", "audioUnderruns", "droppedVideoFrames",
    )
    missing = [key for key in required if key not in payload]
    check(not missing, f"media status missing fields: {', '.join(missing)}")
    check(str(payload["session"]) in TERMINAL | ACTIVE,
          f"unknown media session {payload['session']!r}")
    for key in (
        "speakerAvailable", "microphoneAvailable", "videoDecoderAvailable",
        "psramAvailable", "muted", "recordingAvailable",
    ):
        check(isinstance(payload[key], bool), f"{key} must be boolean")
    for key in ("volumePercent", "microphoneLevelPercent"):
        check(isinstance(payload[key], int) and 0 <= payload[key] <= 100,
              f"{key} outside 0..100")
    check(isinstance(payload["psramFreeBytes"], int) and payload["psramFreeBytes"] >= 0,
          "invalid PSRAM byte count")
    check(isinstance(payload["audioUnderruns"], int) and payload["audioUnderruns"] >= 0,
          "invalid audio underrun count")
    check(isinstance(payload["droppedVideoFrames"], int) and payload["droppedVideoFrames"] >= 0,
          "invalid dropped-frame count")


def status(client: Client) -> dict:
    payload = api(client, "/os12/media/status")
    validate_status(payload)
    return payload


def wait_for_session(client: Client, wanted: set[str], timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        payload = status(client)
        session = str(payload["session"])
        if session != last:
            print(f"STATE {session}: error={payload['error']}")
            last = session
        if session == "Fault":
            raise AcceptanceError(f"media entered Fault: {payload['error']}")
        if session in wanted:
            return payload
        time.sleep(0.10)
    raise AcceptanceError(f"timed out waiting for media session in {sorted(wanted)}")


def ask(prompt: str) -> bool | None:
    while True:
        value = input(f"{prompt} [y/n/u]: ").strip().lower()
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        if value in ("u", "unknown", "unsure", "?"):
            return None
        print("Please answer y, n, or u (unknown/unsure).")


def meter(level: int, width: int = 30) -> str:
    level = max(0, min(100, int(level)))
    filled = round(width * level / 100)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {level:3d}%"


def diagnostics_line(payload: dict) -> str:
    return (
        f"codecReady={payload.get('audioCodecReady')} "
        f"i2sReady={payload.get('audioI2sReady')} "
        f"pipelineRunning={payload.get('audioPipelineRunning')} "
        f"ampEnabled={payload.get('audioAmpEnabled')} "
        f"freq={payload.get('audioCurrentFrequency')} "
        f"targetGain={payload.get('audioTargetGain')} "
        f"currentGain={payload.get('audioCurrentGain')} "
        f"volume={payload.get('volumePercent')}% muted={payload.get('muted')}"
    )


def exercise_speaker(client: Client, interactive: bool) -> bool | None:
    initial = status(client)
    check(initial["speakerAvailable"], "--exercise requested but speaker is not available")
    print("\n=== SPEAKER — AUDIBLE TEST ===")
    print(
        "Listen at the WS350. Three short diagnostic tones will play. "
        "The test is intentionally repeated so a 180 ms pulse cannot be missed."
    )
    print("PRECHECK " + diagnostics_line(initial))
    if initial.get("muted"):
        print("WARNING: runtime reports the speaker MUTED. An inaudible result is expected.")
    if int(initial.get("volumePercent", 0)) < 30:
        print("WARNING: runtime reports low speaker volume.")

    observed_active = None
    for idx in range(1, 4):
        if interactive:
            print(f"Tone {idx}/3 in 1 second...")
            time.sleep(1.0)
        speaker = api(client, "/os12/media/speaker-test", method="POST")
        validate_status(speaker)
        check(speaker["_http_status"] == 202, f"speaker test refused: {speaker['error']}")
        time.sleep(0.08)
        diag = status(client)
        observed_active = diag
        print(f"TONE {idx}/3  " + diagnostics_line(diag))
        # Current firmware has a short bounded diagnostic pulse. Wait for Idle
        # before issuing the next one rather than colliding with Busy.
        wait_for_session(client, {"Idle"}, 2.0)
        time.sleep(0.25)

    print("PASS  speaker diagnostic lifecycle executed three times")
    if not interactive:
        return None

    heard = ask("Did you clearly hear at least one diagnostic tone from the WS350?")
    if heard is False:
        print("PHYSICAL FAIL: speaker lifecycle ran, but no audible output was confirmed.")
        if observed_active:
            print("LAST ACTIVE DIAGNOSTICS: " + diagnostics_line(observed_active))
    elif heard is True:
        print("PHYSICAL PASS: audible speaker output confirmed.")
    else:
        print("PHYSICAL PENDING: speaker audibility was not confirmed.")
    return heard


def sample_mic(client: Client) -> dict:
    payload = api(client, "/os12/media/microphone-sample", method="POST")
    validate_status(payload)
    check(payload["_http_status"] == 200, f"microphone sample refused: {payload['error']}")
    return payload


def exercise_microphone(client: Client, interactive: bool) -> tuple[bool | None, dict]:
    initial = status(client)
    check(initial["microphoneAvailable"], "--exercise requested but microphone is not available")
    print("\n=== MICROPHONE — LIVE RESPONSE TEST ===")

    baseline_levels: list[int] = []
    baseline_peaks: list[int] = []
    print("Baseline: stay quiet for ~2 seconds...")
    for _ in range(5):
        p = sample_mic(client)
        baseline_levels.append(int(p.get("microphoneLevelPercent", 0)))
        baseline_peaks.append(int(p.get("microphoneLastPeak", 0) or 0))
        print("\rBASELINE " + meter(baseline_levels[-1]), end="", flush=True)
        time.sleep(0.10)
    print()

    baseline_level = sum(baseline_levels) / len(baseline_levels)
    baseline_peak = max(baseline_peaks) if baseline_peaks else 0

    live_levels: list[int] = []
    live_peaks: list[int] = []
    if interactive:
        print("Now speak, clap, or tap near the WS350 microphone for ~6 seconds.")
        print("You should see the meter react in real time.")
        end = time.monotonic() + 6.0
        while time.monotonic() < end:
            p = sample_mic(client)
            level = int(p.get("microphoneLevelPercent", 0))
            peak = int(p.get("microphoneLastPeak", 0) or 0)
            live_levels.append(level)
            live_peaks.append(peak)
            print("\rLIVE     " + meter(level), end="", flush=True)
            time.sleep(0.05)
        print()
    else:
        for _ in range(3):
            p = sample_mic(client)
            live_levels.append(int(p.get("microphoneLevelPercent", 0)))
            live_peaks.append(int(p.get("microphoneLastPeak", 0) or 0))

    max_level = max(live_levels) if live_levels else 0
    max_peak = max(live_peaks) if live_peaks else 0
    delta = max_level - baseline_level

    print(
        f"MIC SUMMARY baseline={baseline_level:.1f}% max={max_level}% delta={delta:.1f}pp "
        f"baselinePeak={baseline_peak} maxPeak={max_peak}"
    )
    last = status(client)
    print(
        "MIC DIAGNOSTICS "
        f"bytes={last.get('microphoneLastBytes')} "
        f"samples={last.get('microphoneLastSamples')} "
        f"nonzero={last.get('microphoneLastNonZeroSamples')} "
        f"peak={last.get('microphoneLastPeak')}"
    )

    if not interactive:
        return None, {
            "baselineLevel": baseline_level,
            "maxLevel": max_level,
            "delta": delta,
            "baselinePeak": baseline_peak,
            "maxPeak": max_peak,
        }

    responded = ask("Did the live meter clearly respond when you made sound near the microphone?")
    if responded is False:
        print("PHYSICAL FAIL: microphone response was not confirmed.")
    elif responded is True:
        print("PHYSICAL PASS: microphone response confirmed.")
    else:
        print("PHYSICAL PENDING: microphone response was not confirmed.")
    return responded, {
        "baselineLevel": baseline_level,
        "maxLevel": max_level,
        "delta": delta,
        "baselinePeak": baseline_peak,
        "maxPeak": max_peak,
    }


def exercise_record_playback(client: Client, interactive: bool) -> bool | None:
    initial = status(client)
    check(initial["psramAvailable"], "recording requires PSRAM but device reports unavailable")
    print("\n=== MICROPHONE + SPEAKER — END-TO-END RECORD/PLAYBACK ===")
    if interactive:
        input("Press Enter, then clearly say: 'Workshop OS microphone test one two three' ... ")

    rec = api(client, "/os12/media/record/start", method="POST")
    validate_status(rec)
    check(rec["_http_status"] == 202 and rec["session"] == "Recording",
          f"record start refused: {rec['error']}")
    print("RECORDING for five seconds...")
    # Give the operator a visible countdown while the backend captures.
    for remaining in range(5, 0, -1):
        print(f"  {remaining}...")
        time.sleep(0.8)
    completed = wait_for_session(client, {"Idle"}, 3.0)
    check(completed["recordingAvailable"],
          "recording completed without a retained local recording")
    print("PASS  five-second PSRAM recording completed")

    if interactive:
        input("Press Enter to play the recording through the WS350 speaker. Listen for your phrase... ")
    play = api(client, "/os12/media/record/play", method="POST")
    validate_status(play)
    check(play["_http_status"] == 202 and play["session"] == "PlayingRecording",
          f"recording playback refused: {play['error']}")
    wait_for_session(client, {"Idle"}, 8.0)
    print("PASS  local recording playback lifecycle completed")

    if not interactive:
        return None
    heard = ask("Did you clearly hear your recorded phrase from the WS350 speaker?")
    if heard is False:
        print("PHYSICAL FAIL: end-to-end microphone/record/playback was not audible.")
    elif heard is True:
        print("PHYSICAL PASS: end-to-end record/playback confirmed.")
    else:
        print("PHYSICAL PENDING: record/playback quality was not confirmed.")
    return heard


def exercise_audio(client: Client, initial: dict, interactive: bool = False) -> dict:
    # Keep the legacy function name because physical acceptance imports helpers
    # from this module. The initial snapshot remains a validated precondition.
    check(initial["speakerAvailable"], "--exercise requested but speaker is not available")
    check(initial["microphoneAvailable"], "--exercise requested but microphone is not available")
    speaker = exercise_speaker(client, interactive)
    mic, mic_metrics = exercise_microphone(client, interactive)
    playback = exercise_record_playback(client, interactive)
    return {
        "speakerAudible": speaker,
        "microphoneResponsive": mic,
        "recordingPlaybackAudible": playback,
        "microphoneMetrics": mic_metrics,
    }


def exercise_video(client: Client, initial: dict, interactive: bool = False) -> bool | None:
    check(initial["videoDecoderAvailable"],
          "--exercise-video requested but video capability is unavailable")
    check(initial["psramAvailable"],
          "--exercise-video requested but PSRAM is unavailable")

    print("\n=== VIDEO — MOTION / PAUSE / RESUME TEST ===")
    start = api(client, "/os12/media/video/start", method="POST")
    validate_status(start)
    check(
        start["_http_status"] == 202 and start["session"] == "PlayingVideo",
        "video start refused: " + str(start["error"]) +
        " (built-in WS350 demo source must be available)",
    )
    print("STATE PlayingVideo: built-in WS350 demo video started")
    if interactive:
        print("Look at the WS350: the demo object/progress indicator should be moving.")
        time.sleep(3.0)
    else:
        time.sleep(2.0)

    live = status(client)
    check(live["session"] == "PlayingVideo",
          f"video did not remain active: {live['session']}")

    pause = api(client, "/os12/media/video/pause", method="POST")
    validate_status(pause)
    check(pause["_http_status"] == 200 and pause["session"] == "Paused",
          f"video pause refused: {pause['error']}")
    print("STATE Paused: video paused")
    if interactive:
        print("Confirm visually that motion stops for ~2 seconds...")
        time.sleep(2.0)
    else:
        time.sleep(0.5)

    resume = api(client, "/os12/media/video/resume", method="POST")
    validate_status(resume)
    check(resume["_http_status"] == 200 and resume["session"] == "PlayingVideo",
          f"video resume refused: {resume['error']}")
    print("STATE PlayingVideo: video resumed")
    if interactive:
        print("Confirm visually that motion resumes...")
        time.sleep(2.0)
    else:
        time.sleep(0.5)

    stop = api(client, "/os12/media/stop", method="POST")
    validate_status(stop)
    check(stop["_http_status"] == 200 and stop["session"] == "Idle",
          f"video stop refused: {stop['error']}")
    print("PASS  bounded WS350 demo-video start/pause/resume/stop lifecycle")

    if not interactive:
        return None
    visible = ask("Did you see clear motion, a visible pause, and motion resume on the WS350?")
    if visible is False:
        print("PHYSICAL FAIL: video lifecycle ran but visible motion/pause/resume was not confirmed.")
    elif visible is True:
        print("PHYSICAL PASS: video motion/pause/resume confirmed.")
    else:
        print("PHYSICAL PENDING: video behavior was not confirmed.")
    return visible


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")),
          "--base-url must start with http:// or https://")
    print(f"Target: {base_url}")
    client = Client(base_url)
    assert_code_free_portal(client)
    print("PASS  code-free local portal contract")

    initial = status(client)
    print(
        "CAPABILITIES "
        f"speaker={initial['speakerAvailable']} "
        f"microphone={initial['microphoneAvailable']} "
        f"video={initial['videoDecoderAvailable']} "
        f"psram={initial['psramAvailable']} ({initial['psramFreeBytes']} bytes free)"
    )
    check(initial["session"] != "Fault",
          f"media status begins in Fault: {initial['error']}")
    print("PASS  media status/capability contract")

    if not args.exercise and not args.exercise_video:
        print("RUNTIME MEDIA PROBE: PASS (read-only)")
        print("Physical media acceptance was not performed.")
        return 0

    interactive = sys.stdin.isatty() and not args.non_interactive
    if interactive:
        print("\nINTERACTIVE MODE: ON")
        print("This run will ask what you actually hear/see; runtime PASS cannot override a physical FAIL.")
    else:
        print("\nINTERACTIVE MODE: OFF — runtime lifecycle only")

    observations: dict[str, object] = {}
    if args.exercise:
        observations.update(exercise_audio(client, initial, interactive))
    if args.exercise_video:
        idle = status(client)
        check(idle["session"] == "Idle",
              f"video exercise requires Idle media service, got {idle['session']}")
        observations["videoVisible"] = exercise_video(client, idle, interactive)

    final = status(client)
    check(final["session"] == "Idle",
          f"media exercise did not finish Idle: {final['session']}")
    if args.exercise:
        check(final["recordingAvailable"],
              "playback unexpectedly discarded the retained recording")
    print(
        f"\nCOUNTERS underruns={final['audioUnderruns']} "
        f"droppedVideoFrames={final['droppedVideoFrames']}"
    )
    print("RUNTIME MEDIA ACCEPTANCE SUBSET: PASS")

    if interactive:
        physical_keys = (
            "speakerAudible",
            "microphoneResponsive",
            "recordingPlaybackAudible",
            "videoVisible",
        )
        values = [observations.get(k) for k in physical_keys if k in observations]
        if any(v is False for v in values):
            print("INTERACTIVE MEDIA PHYSICAL OBSERVATION: FAIL")
            print("Runtime behavior passed, but at least one human-observable media function failed.")
            return 2
        if any(v is None for v in values):
            print("INTERACTIVE MEDIA PHYSICAL OBSERVATION: PENDING")
            return 3
        print("INTERACTIVE MEDIA PHYSICAL OBSERVATION: PASS")

    print(
        "Runtime and physical observations are reported separately. "
        "This command does not promote the firmware to accepted/stable."
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base-url",
        default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
    )
    ap.add_argument(
        "--exercise",
        action="store_true",
        help="exercise speaker, live microphone response, and five-second record/playback",
    )
    ap.add_argument(
        "--exercise-video",
        action="store_true",
        help="exercise built-in WS350 demo-video start/pause/resume/stop",
    )
    ap.add_argument(
        "--non-interactive",
        action="store_true",
        help="disable operator prompts/meters and perform runtime lifecycle checks only",
    )
    args = ap.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
