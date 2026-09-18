#!/usr/bin/env python3
"""Exercise the Workshop OS 12 media contract against a real WS350.

Default mode is read-only. --exercise runs speaker, microphone and bounded
record/playback. --exercise-video runs the built-in WS350 demo-video lifecycle. These are runtime checks only; hearing/seeing media quality and
touch responsiveness remain physical acceptance observations.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import time

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    assert_login_markup,
    check,
    login,
    normalized_code,
    protected_root_is_open,
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


def read_code() -> str:
    raw = os.environ.get("WORKSHOP_OS_PORTAL_CODE")
    if not raw:
        raw = getpass.getpass("Current portal code shown on WS350 System screen: ")
    code = normalized_code(raw)
    raw = ""
    return code


def exercise_audio(client: Client, initial: dict) -> None:
    check(initial["speakerAvailable"], "--exercise requested but speaker is not available")
    speaker = api(client, "/os12/media/speaker-test", method="POST")
    validate_status(speaker)
    check(speaker["_http_status"] == 202, f"speaker test refused: {speaker['error']}")
    wait_for_session(client, {"Idle"}, 3.0)
    print("PASS  bounded non-blocking speaker-test lifecycle")
    speaker_diag = status(client)
    print(
        "SPEAKER DIAG "
        f"codecReady={speaker_diag.get('audioCodecReady')} "
        f"i2sReady={speaker_diag.get('audioI2sReady')} "
        f"pipelineRunning={speaker_diag.get('audioPipelineRunning')} "
        f"writeBytes={speaker_diag.get('audioLastWriteBytes')} "
        f"peak={speaker_diag.get('audioLastPeak')} "
        f"freq={speaker_diag.get('audioCurrentFrequency')}"
    )

    check(initial["microphoneAvailable"],
          "--exercise requested but microphone is not available")
    mic = api(client, "/os12/media/microphone-sample", method="POST")
    validate_status(mic)
    check(mic["_http_status"] == 200,
          f"microphone sample refused: {mic['error']}")
    print(f"PASS  microphone activity sample returned {mic['microphoneLevelPercent']}%")
    print(
        "AUDIO DIAG "
        f"codecReady={mic.get('audioCodecReady')} "
        f"i2sReady={mic.get('audioI2sReady')} "
        f"pipelineRunning={mic.get('audioPipelineRunning')} "
        f"bytes={mic.get('microphoneLastBytes')} "
        f"samples={mic.get('microphoneLastSamples')} "
        f"nonzero={mic.get('microphoneLastNonZeroSamples')} "
        f"peak={mic.get('microphoneLastPeak')}"
    )

    check(initial["psramAvailable"],
          "recording requires PSRAM but device reports unavailable")
    rec = api(client, "/os12/media/record/start", method="POST")
    validate_status(rec)
    check(rec["_http_status"] == 202 and rec["session"] == "Recording",
          f"record start refused: {rec['error']}")
    print("STATE Recording: bounded five-second capture started")
    completed = wait_for_session(client, {"Idle"}, 7.0)
    check(completed["recordingAvailable"],
          "recording completed without a retained local recording")
    print("PASS  five-second PSRAM recording completed")

    play = api(client, "/os12/media/record/play", method="POST")
    validate_status(play)
    check(play["_http_status"] == 202 and play["session"] == "PlayingRecording",
          f"recording playback refused: {play['error']}")
    wait_for_session(client, {"Idle"}, 7.0)
    print("PASS  local recording playback completed")


def exercise_video(client: Client, initial: dict) -> None:
    check(initial["videoDecoderAvailable"],
          "--exercise-video requested but video capability is unavailable")
    check(initial["psramAvailable"],
          "--exercise-video requested but PSRAM is unavailable")

    start = api(client, "/os12/media/video/start", method="POST")
    validate_status(start)
    check(
        start["_http_status"] == 202 and start["session"] == "PlayingVideo",
        "video start refused: " + str(start["error"]) +
        " (built-in WS350 demo source must be available)",
    )
    print("STATE PlayingVideo: built-in WS350 demo video started")

    time.sleep(2.0)
    live = status(client)
    check(live["session"] == "PlayingVideo",
          f"video did not remain active: {live['session']}")

    pause = api(client, "/os12/media/video/pause", method="POST")
    validate_status(pause)
    check(pause["_http_status"] == 200 and pause["session"] == "Paused",
          f"video pause refused: {pause['error']}")
    print("STATE Paused: video paused")
    time.sleep(0.5)

    resume = api(client, "/os12/media/video/resume", method="POST")
    validate_status(resume)
    check(resume["_http_status"] == 200 and resume["session"] == "PlayingVideo",
          f"video resume refused: {resume['error']}")
    print("STATE PlayingVideo: video resumed")
    time.sleep(0.5)

    stop = api(client, "/os12/media/stop", method="POST")
    validate_status(stop)
    check(stop["_http_status"] == 200 and stop["session"] == "Idle",
          f"video stop refused: {stop['error']}")
    print("PASS  bounded WS350 demo-video start/pause/resume/stop lifecycle")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")),
          "--base-url must start with http:// or https://")
    print(f"Target: {base_url}")
    assert_login_markup(Client(base_url))

    client = Client(base_url)
    if protected_root_is_open(client):
        print("DEV OPEN  portal/session code bypass is active for this physical-test build")
    else:
        code = read_code()
        login(client, code, "media acceptance session")
        code = ""

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

    if args.exercise:
        exercise_audio(client, initial)
    if args.exercise_video:
        idle = status(client)
        check(idle["session"] == "Idle",
              f"video exercise requires Idle media service, got {idle['session']}")
        exercise_video(client, idle)

    final = status(client)
    check(final["session"] == "Idle",
          f"media exercise did not finish Idle: {final['session']}")
    if args.exercise:
        check(final["recordingAvailable"],
              "playback unexpectedly discarded the retained recording")
    print(
        f"COUNTERS underruns={final['audioUnderruns']} "
        f"droppedVideoFrames={final['droppedVideoFrames']}"
    )
    print("RUNTIME MEDIA ACCEPTANCE SUBSET: PASS")
    print(
        "This proves API/runtime behavior only. Speaker quality, microphone quality, "
        "visible video motion/pause, touch responsiveness and printer-health observations "
        "remain physical acceptance checks."
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
        help="exercise speaker, microphone and five-second record/playback",
    )
    ap.add_argument(
        "--exercise-video",
        action="store_true",
        help="exercise built-in WS350 demo-video start/pause/resume/stop",
    )
    args = ap.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
