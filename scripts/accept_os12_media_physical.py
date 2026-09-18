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
    read_code,
    status,
    validate_status,
    wait_for_session,
)


def observation(prompt: str) -> bool | None:
    """Return True/False/Unknown without forcing uncertain physical evidence."""
    while True:
        answer = input(f"{prompt} [y/n/u]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        if answer in ("u", "unknown", "unsure", "?"):
            return None
        print("Please answer y, n, or u (unknown/unsure).")


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


def native_view_catalog(client: Client) -> list[dict]:
    response = client.request(
        "/hub/views",
        headers={"X-BambuHelper-Client": "1", "Accept": "application/json"},
        timeout=10.0,
    )
    check(response.status == 200,
          f"GET /hub/views returned HTTP {response.status}")
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("native view catalog did not return JSON") from exc
    views = payload.get("views")
    check(isinstance(views, list) and views,
          "native view catalog contains no views")
    return views


def resolve_native_media_view(client: Client, view: str) -> tuple[str, str]:
    wanted = {
        "media": ("media", "media"),
        "lab": ("media-lab", "media lab"),
        "video": ("media-video", "camera viewer"),
    }
    check(view in wanted, f"unknown native media acceptance view: {view}")
    preferred_id, preferred_label = wanted[view]
    views = native_view_catalog(client)

    for item in views:
        view_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if view_id.lower() == preferred_id or label.lower() == preferred_label:
            fallback = {"media": "Media", "lab": "Media Lab", "video": "Camera Viewer"}[view]
            return view_id, label or fallback

    available = ", ".join(
        str(item.get("id", "")).strip()
        for item in views
        if item.get("id")
    )
    raise AcceptanceError(
        f"native {view} view is absent from /hub/views; available ids: {available}"
    )


def show_native_media_view(
    client: Client,
    view: str,
    navigation_log: list[dict],
) -> None:
    view_id, label = resolve_native_media_view(client, view)
    response = client.request(
        "/hub/show",
        method="POST",
        form={"page": view_id},
        headers={"X-BambuHelper-Client": "1", "Accept": "application/json,text/plain,*/*"},
        timeout=10.0,
    )
    accepted = response.status == 200
    navigation_log.append({
        "requestedView": view,
        "catalogViewId": view_id,
        "catalogLabel": label,
        "httpStatus": response.status,
        "accepted": accepted,
        "route": "/hub/show",
    })
    check(accepted,
          f"native view router refused {label} ({view_id}) with HTTP {response.status}")
    print(f"DEVICE VIEW {label}: canonical /hub/show navigation accepted ({view_id})")
    time.sleep(0.45)


def exercise_audio_visible(
    client: Client,
    initial: dict,
    navigation_log: list[dict],
    observations: dict[str, bool | None],
) -> None:
    show_native_media_view(client, "media", navigation_log)
    observations["native_media_view_visible"] = observation(
        "Did the native Media screen appear on the WS350?"
    )

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

    show_native_media_view(client, "lab", navigation_log)
    observations["native_media_lab_view_visible"] = observation(
        "Did the native Media Lab screen appear on the WS350?"
    )
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
        "schemaVersion": 4,
        "kind": "workshop-os12-media-physical-acceptance",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base_url).hostname,
        "runtimeIdentity": None,
        "initialMediaStatus": None,
        "finalMediaStatus": None,
        "observations": {},
        "navigationObservations": [],
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
    observations: dict[str, bool | None] = evidence["observations"]
    navigation_log: list[dict] = evidence["navigationObservations"]

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
        exercise_audio_visible(client, initial, navigation_log, observations)

        observations["speaker_tone_clean"] = observation(
            "Did you hear the diagnostic speaker tone clearly without obvious distortion?"
        )
        observations["microphone_level_responds"] = observation(
            "Did the microphone level respond when you made sound near the device?"
        )
        observations["recording_intelligible"] = observation(
            "Was the five-second microphone recording intelligible during playback?"
        )
        observations["audio_no_obvious_noise_or_instability"] = observation(
            "Did audio/recording complete without obvious electrical noise, reboot, hang, or UI freeze?"
        )

        print("\nVIDEO\n-----")
        show_native_media_view(client, "video", navigation_log)
        observations["native_camera_viewer_visible"] = observation(
            "Did the dedicated Camera Viewer screen appear on the WS350?"
        )

        idle = status(client)
        check(idle["session"] == "Idle",
              f"video physical check requires Idle media service, got {idle['session']}")
        start = api(client, "/os12/media/video/start", method="POST")
        validate_status(start)
        check(
            start["_http_status"] == 202 and start["session"] == "PlayingVideo",
            "video start refused: " + str(start["error"]) +
            " (displayed printer must expose a streamable local camera)",
        )
        print(
            "STATE PlayingVideo: runtime session entered. "
            "This proves the command/state transition only, not visible video."
        )
        time.sleep(1.5)
        observations["video_visible_motion"] = observation(
            "While the session is PlayingVideo, can you actually see live camera motion on the WS350?"
        )

        pause = api(client, "/os12/media/video/pause", method="POST")
        validate_status(pause)
        check(pause["_http_status"] == 200 and pause["session"] == "Paused",
              f"video pause refused: {pause['error']}")
        print("STATE Paused: runtime pause accepted")
        observations["video_pause_visible"] = observation(
            "Did the visible camera image freeze when Pause was issued?"
        )

        resume = api(client, "/os12/media/video/resume", method="POST")
        validate_status(resume)
        check(resume["_http_status"] == 200 and resume["session"] == "PlayingVideo",
              f"video resume refused: {resume['error']}")
        print("STATE PlayingVideo: runtime resume accepted")
        time.sleep(1.0)
        observations["video_resume_visible"] = observation(
            "Did visible live camera motion resume on the WS350?"
        )
        observations["touch_responsive_during_video"] = observation(
            "Did touchscreen interaction remain responsive while video was active?"
        )
        observations["printer_telemetry_continued"] = observation(
            "Did printer telemetry continue updating while/after media use?"
        )

        stop = api(client, "/os12/media/stop", method="POST")
        validate_status(stop)
        check(stop["_http_status"] == 200 and stop["session"] == "Idle",
              f"video stop refused: {stop['error']}")
        print("STATE Idle: video runtime stopped")

        observations["printer_controls_healthy"] = observation(
            "Did normal non-destructive printer controls remain usable after media use?"
        )
        observations["device_network_healthy"] = observation(
            "Is the WS350 still reachable on the LAN after stopping media?"
        )
        observations["no_reboot_or_watchdog"] = observation(
            "Did the device avoid unexpected reboot, watchdog reset, or recovery entry?"
        )

        final = status(client)
        evidence["finalMediaStatus"] = public_status(final)
        runtime_ok = final["session"] == "Idle" and final["error"] == "None"
        evidence["runtimeIdleAndClean"] = runtime_ok
        evidence["completed"] = True

        all_observations = bool(observations) and all(
            value is True for value in observations.values()
        )
        passed = runtime_ok and all_observations
        evidence["passed"] = passed
        write_evidence(destination, evidence)

        print(f"\nEvidence: {destination}")
        if passed:
            print("PHYSICAL MEDIA ACCEPTANCE: PASS")
            print("Scope is media only. This does not promote Workshop OS to accepted or stable.")
            return 0

        failed = [name for name, value in observations.items() if value is False]
        unknown = [name for name, value in observations.items() if value is None]
        if not runtime_ok:
            failed.append("final_runtime_idle_and_clean")
        print("PHYSICAL MEDIA ACCEPTANCE: FAIL / PENDING")
        if failed:
            print("Failed observations: " + ", ".join(failed))
        if unknown:
            print("Unknown observations: " + ", ".join(unknown))
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
