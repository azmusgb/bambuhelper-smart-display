#!/usr/bin/env python3
"""Interactive physical acceptance for Workshop OS 12 media on a real WS350.

This helper drives bounded media diagnostics, asks the operator to confirm
physical observations, and writes an evidence bundle. It never stores the portal
code and it cannot promote the firmware or mark the whole OS stable.

Evidence is written even when a runtime AcceptanceError aborts the sequence, so
failed physical runs remain auditable rather than disappearing before final save.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    assert_login_markup,
    check,
    login,
    protected_root_is_open,
)
from accept_os12_media_runtime import (
    api,
    exercise_video,
    read_code,
    status,
    validate_status,
    wait_for_session,
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


def public_status(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def write_evidence(destination: Path, evidence: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def show_native_media_view(client: Client, view: str) -> None:
    routes = {
        "media": "/os12/media/acceptance/show-media",
        "lab": "/os12/media/acceptance/show-lab",
    }
    check(view in routes, f"unknown native media acceptance view: {view}")
    payload = api(client, routes[view], method="POST")
    validate_status(payload)
    check(payload["_http_status"] == 200,
          f"device refused native {view} view navigation")
    label = "Media" if view == "media" else "Media Lab"
    print(f"DEVICE VIEW {label}: native touchscreen view selected")
    time.sleep(0.45)


def exercise_audio_visible(client: Client, initial: dict) -> None:
    show_native_media_view(client, "media")

    check(initial["speakerAvailable"], "speaker is not available")
    speaker = api(client, "/os12/media/speaker-test", method="POST")
    validate_status(speaker)
    check(speaker["_http_status"] == 202,
          f"speaker test refused: {speaker['error']}")
    wait_for_session(client, {"Idle"}, 3.0)
    print("PASS  bounded speaker-test lifecycle while native Media view is visible")

    check(initial["microphoneAvailable"], "microphone is not available")
    mic = api(client, "/os12/media/microphone-sample", method="POST")
    validate_status(mic)
    check(mic["_http_status"] == 200,
          f"microphone sample refused: {mic['error']}")
    print(
        "PASS  microphone sample while native Media view is visible: "
        f"{mic['microphoneLevelPercent']}%"
    )

    show_native_media_view(client, "lab")
    check(initial["psramAvailable"], "recording requires PSRAM")
    rec = api(client, "/os12/media/record/start", method="POST")
    validate_status(rec)
    check(rec["_http_status"] == 202 and rec["session"] == "Recording",
          f"record start refused: {rec['error']}")
    print("STATE Recording: native Media Lab visible; bounded five-second capture started")
    completed = wait_for_session(client, {"Idle"}, 7.0)
    check(completed["recordingAvailable"],
          "recording completed without a retained local recording")
    print("PASS  five-second PSRAM recording completed")

    play = api(client, "/os12/media/record/play", method="POST")
    validate_status(play)
    check(play["_http_status"] == 202 and play["session"] == "PlayingRecording",
          f"recording playback refused: {play['error']}")
    wait_for_session(client, {"Idle"}, 7.0)
    print("PASS  local recording playback completed while native Media Lab is visible")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")),
          "--base-url must start with http:// or https://")

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    destination = output_path(args.output, stamp)
    evidence = {
        "schemaVersion": 2,
        "kind": "workshop-os12-media-physical-acceptance",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base_url).hostname,
        "runtimeIdentity": None,
        "initialMediaStatus": None,
        "finalMediaStatus": None,
        "observations": {},
        "runtimeIdleAndClean": False,
        "passed": False,
        "completed": False,
        "failure": None,
        "portalMode": "unknown",
        "scope": "media physical acceptance only; not whole-device stable acceptance",
    }

    client = Client(base_url)
    initial = None
    final = None
    observations: dict[str, bool] = evidence["observations"]

    try:
        assert_login_markup(client)
        if protected_root_is_open(client):
            evidence["portalMode"] = "temporary-open-lan"
            print("DEV OPEN  portal/session code bypass is active for this physical-test build")
        else:
            evidence["portalMode"] = "portal-code"
            code = read_code()
            login(client, code, "physical media acceptance session")
            code = ""

        identity = update_identity(client)
        evidence["runtimeIdentity"] = identity

        initial = status(client)
        evidence["initialMediaStatus"] = public_status(initial)
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
        exercise_audio_visible(client, initial)

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
        show_native_media_view(client, "lab")
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
        evidence["finalMediaStatus"] = public_status(final)
        runtime_ok = final["session"] == "Idle" and final["error"] == "None"
        evidence["runtimeIdleAndClean"] = runtime_ok
        evidence["completed"] = True

        all_observations = all(observations.values())
        passed = runtime_ok and all_observations
        evidence["passed"] = passed
        write_evidence(destination, evidence)

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

    except AcceptanceError as exc:
        evidence["failure"] = str(exc)
        try:
            final = status(client)
        except Exception as status_exc:
            evidence["finalStatusCaptureError"] = str(status_exc)
        else:
            evidence["finalMediaStatus"] = public_status(final)
            evidence["runtimeIdleAndClean"] = (
                final["session"] == "Idle" and final["error"] == "None"
            )
        write_evidence(destination, evidence)
        print(f"\nEvidence: {destination}")
        print(f"FAIL: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        evidence["failure"] = "operator_aborted"
        evidence["finalStatusCaptureSkipped"] = True
        write_evidence(destination, evidence)
        print(f"\nEvidence: {destination}")
        print("PHYSICAL MEDIA ACCEPTANCE: ABORTED")
        return 130


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
