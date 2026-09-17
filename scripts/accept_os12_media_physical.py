#!/usr/bin/env python3
"""Interactive physical acceptance for Workshop OS 12 media on a real WS350.

This helper drives the bounded media diagnostics, asks the operator to confirm
physical observations, and writes an evidence bundle. It never stores the portal
code and it cannot promote the firmware or mark the whole OS stable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    assert_login_markup,
    check,
    login,
)
from accept_os12_media_runtime import (
    api,
    exercise_audio,
    exercise_video,
    read_code,
    status,
)


def yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def update_identity(client: Client) -> dict:
    response = client.request(
        "/os12/update/status",
        headers={"X-BambuHelper-Client": "1", "Accept": "application/json"},
        timeout=10.0,
    )
    check(response.status == 200,
          f"GET /os12/update/status returned HTTP {response.status}")
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("update status did not return JSON") from exc
    for key in ("runningVersion", "runningSourceCommit"):
        check(isinstance(payload.get(key), str) and payload[key],
              f"update status missing {key}")
    return {
        "runningVersion": payload["runningVersion"],
        "runningSourceCommit": payload["runningSourceCommit"],
    }


def output_path(arg: str | None, stamp: str) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return (
        Path.home()
        / "Downloads"
        / f"workshop-os12-media-physical-{stamp}.json"
    )


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")),
          "--base-url must start with http:// or https://")
    assert_login_markup(Client(base_url))

    code = read_code()
    client = Client(base_url)
    login(client, code, "physical media acceptance session")
    code = ""

    identity = update_identity(client)
    initial = status(client)
    check(initial["session"] == "Idle",
          f"physical acceptance must start Idle, got {initial['session']}")
    for key in (
        "speakerAvailable", "microphoneAvailable",
        "videoDecoderAvailable", "psramAvailable",
    ):
        check(initial[key], f"required media capability is unavailable: {key}")

    print(
        "Running: "
        f"{identity['runningVersion']} @ {identity['runningSourceCommit']}"
    )
    print("\nAUDIO / MICROPHONE\n------------------")
    exercise_audio(client, initial)

    observations: dict[str, bool] = {}
    observations["speaker_tone_clean"] = yes_no(
        "Did you hear the diagnostic speaker tone clearly without obvious distortion?"
    )
    observations["microphone_level_responds"] = yes_no(
        "Did the microphone level respond when you made sound near the device?"
    )
    observations["recording_intelligible"] = yes_no(
        "Was the five-second microphone recording intelligible during playback?"
    )
    observations["audio_no_obvious_noise_or_instability"] = yes_no(
        "Did audio/recording complete without obvious electrical noise, reboot, hang, or UI freeze?"
    )

    print("\nVIDEO\n-----")
    exercise_video(client, status(client))
    observations["video_visible_motion"] = yes_no(
        "Did the displayed-printer camera visibly update during video playback?"
    )
    observations["video_pause_resume_visible"] = yes_no(
        "Did Pause visibly freeze the image and Resume continue live motion?"
    )
    observations["touch_responsive_during_video"] = yes_no(
        "Did touchscreen interaction remain responsive while video was active?"
    )
    observations["printer_telemetry_continued"] = yes_no(
        "Did printer telemetry continue updating during/after media use?"
    )
    observations["printer_controls_healthy"] = yes_no(
        "Did normal non-destructive printer controls remain usable after media use?"
    )
    observations["device_network_healthy"] = yes_no(
        "Is the WS350 still reachable on the LAN after stopping media?"
    )
    observations["no_reboot_or_watchdog"] = yes_no(
        "Did the device avoid unexpected reboot, watchdog reset, or recovery entry?"
    )

    final = status(client)
    runtime_ok = final["session"] == "Idle" and final["error"] == "None"
    all_observations = all(observations.values())
    passed = runtime_ok and all_observations

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    evidence = {
        "schemaVersion": 1,
        "kind": "workshop-os12-media-physical-acceptance",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base_url).hostname,
        "runtimeIdentity": identity,
        "initialMediaStatus": {k: v for k, v in initial.items() if not k.startswith("_")},
        "finalMediaStatus": {k: v for k, v in final.items() if not k.startswith("_")},
        "observations": observations,
        "runtimeIdleAndClean": runtime_ok,
        "passed": passed,
        "scope": "media physical acceptance only; not whole-device stable acceptance",
    }
    destination = output_path(args.output, stamp)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"\nEvidence: {destination}")
    if passed:
        print("PHYSICAL MEDIA ACCEPTANCE: PASS")
        print("Scope is media only. This does not promote Workshop OS to accepted or stable.")
        return 0

    failed = [name for name, ok in observations.items() if not ok]
    if not runtime_ok:
        failed.append("final_runtime_idle_and_clean")
    print("PHYSICAL MEDIA ACCEPTANCE: FAIL / PENDING")
    print("Failed observations: " + ", ".join(failed))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
    )
    parser.add_argument(
        "--output",
        help="optional evidence JSON path; defaults to ~/Downloads",
    )
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
