#!/usr/bin/env python3
"""Exercise the Workshop OS 12 media contract against a real WS350.

The default mode is read-only and validates capability/state reporting. Passing
--exercise runs the bounded speaker test, microphone activity sample, five-second
recording and local playback path. This proves runtime behavior only; hearing the
speaker, judging microphone quality, video quality, touch responsiveness and the
absence of electrical noise remain physical acceptance observations.
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
)

TERMINAL = {"Idle", "Fault"}
ACTIVE = {"Starting", "PlayingAudio", "Recording", "PlayingRecording", "PlayingVideo", "Paused", "Stopping"}


def api(client: Client, path: str, *, method: str = "GET") -> dict:
    headers = {"X-BambuHelper-Client": "1", "Accept": "application/json"}
    response = client.request(path, method=method, headers=headers, timeout=15.0)
    check(response.status in (200, 202, 409), f"{method} {path} returned HTTP {response.status}: {response.body[:200]}")
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
    check(str(payload["session"]) in TERMINAL | ACTIVE, f"unknown media session {payload['session']!r}")
    for key in ("speakerAvailable", "microphoneAvailable", "videoDecoderAvailable", "psramAvailable", "muted", "recordingAvailable"):
        check(isinstance(payload[key], bool), f"{key} must be boolean")
    for key in ("volumePercent", "microphoneLevelPercent"):
        check(isinstance(payload[key], int) and 0 <= payload[key] <= 100, f"{key} outside 0..100")
    check(isinstance(payload["psramFreeBytes"], int) and payload["psramFreeBytes"] >= 0, "invalid PSRAM byte count")
    check(isinstance(payload["audioUnderruns"], int) and payload["audioUnderruns"] >= 0, "invalid audio underrun count")
    check(isinstance(payload["droppedVideoFrames"], int) and payload["droppedVideoFrames"] >= 0, "invalid dropped-frame count")


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


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
    print(f"Target: {base_url}")
    assert_login_markup(Client(base_url))

    code = read_code()
    client = Client(base_url)
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
    check(initial["session"] != "Fault", f"media status begins in Fault: {initial['error']}")
    print("PASS  media status/capability contract")

    if not args.exercise:
        print("RUNTIME MEDIA PROBE: PASS (read-only)")
        print("Physical speaker/microphone/video acceptance was not performed.")
        return 0

    check(initial["speakerAvailable"], "--exercise requested but speaker is not available")
    speaker = api(client, "/os12/media/speaker-test", method="POST")
    validate_status(speaker)
    check(speaker["_http_status"] == 202, f"speaker test refused: {speaker['error']}")
    wait_for_session(client, {"Idle"}, 3.0)
    print("PASS  bounded non-blocking speaker-test lifecycle")

    check(initial["microphoneAvailable"], "--exercise requested but microphone is not available")
    mic = api(client, "/os12/media/microphone-sample", method="POST")
    validate_status(mic)
    check(mic["_http_status"] == 200, f"microphone sample refused: {mic['error']}")
    print(f"PASS  microphone activity sample returned {mic['microphoneLevelPercent']}%")

    check(initial["psramAvailable"], "recording requires PSRAM but device reports unavailable")
    rec = api(client, "/os12/media/record/start", method="POST")
    validate_status(rec)
    check(rec["_http_status"] == 202 and rec["session"] == "Recording", f"record start refused: {rec['error']}")
    print("STATE Recording: bounded five-second capture started")
    completed = wait_for_session(client, {"Idle"}, 7.0)
    check(completed["recordingAvailable"], "recording completed without a retained local recording")
    print("PASS  five-second PSRAM recording completed")

    play = api(client, "/os12/media/record/play", method="POST")
    validate_status(play)
    check(play["_http_status"] == 202 and play["session"] == "PlayingRecording", f"recording playback refused: {play['error']}")
    wait_for_session(client, {"Idle"}, 7.0)
    print("PASS  local recording playback completed")

    final = status(client)
    check(final["recordingAvailable"], "playback unexpectedly discarded the retained recording")
    print(f"COUNTERS underruns={final['audioUnderruns']} droppedVideoFrames={final['droppedVideoFrames']}")
    print("RUNTIME MEDIA ACCEPTANCE SUBSET: PASS")
    print("This proves API/runtime behavior only. Physical hearing, microphone quality, touch responsiveness and video remain separate acceptance observations.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    ap.add_argument("--exercise", action="store_true", help="exercise speaker, microphone and five-second record/playback")
    args = ap.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
