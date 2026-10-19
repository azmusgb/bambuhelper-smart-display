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
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    establish_portal_session,
    check,
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")

from accept_os12_media_runtime import (
    api,
    start_video_after_page_open,
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
        headers={"Accept": "application/json"},
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
        headers={"Accept": "application/json"},
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


# Since 12.1 there is no Media or Recorder screen: Speaker test, Microphone and
# Recorder are rows on Sound & Alerts, below the fold at the top of the page.
# Since 12.3.6 /hub/show page=media-lab opens Sound & Alerts scrolled to those
# rows, so the "media" and "lab" steps request it (12.3.5 showed the top of
# the page, and the owner answered "no" to the Recorder and live-level
# questions because the rows were off screen).
MEDIA_ROWS_PAGE = "media-lab"


def resolve_native_media_view(client: Client, view: str) -> tuple[str, str, str]:
    """(catalog id, label, /hub/show page) for a media acceptance step."""
    wanted = {
        "media": ("settings-sounds", "sound & alerts", MEDIA_ROWS_PAGE),
        "lab": ("settings-sounds", "sound & alerts", MEDIA_ROWS_PAGE),
        "video": ("media-video", "video test", "media-video"),
    }
    check(view in wanted, f"unknown native media acceptance view: {view}")
    preferred_id, preferred_label, page = wanted[view]
    views = native_view_catalog(client)

    for item in views:
        view_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if view_id.lower() == preferred_id or label.lower() == preferred_label:
            fallback = {"media": "Sound & Alerts", "lab": "Sound & Alerts", "video": "Video test"}[view]
            return view_id, label or fallback, page if page != preferred_id else view_id

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
    view_id, label, page = resolve_native_media_view(client, view)
    response = client.request(
        "/hub/show",
        method="POST",
        form={"page": page},
        headers={"Accept": "application/json,text/plain,*/*"},
        timeout=10.0,
    )
    accepted = response.status == 200
    navigation_log.append({
        "requestedView": view,
        "catalogViewId": view_id,
        "catalogLabel": label,
        "shownPage": page,
        "httpStatus": response.status,
        "accepted": accepted,
        "route": "/hub/show",
    })
    check(accepted,
          f"native view router refused {label} ({page}) with HTTP {response.status}")
    print(f"DEVICE VIEW {label}: canonical /hub/show navigation accepted ({page})")
    time.sleep(0.45)


# Exact wording of every recorded question, so evidence says what "no" meant.
QUESTIONS = {
    "native_media_view_visible":
        "Is Sound & Alerts on the WS350, showing the Speaker test, Microphone and Recorder rows?",
    "native_media_lab_view_visible":
        "Is Sound & Alerts still showing the Recorder row (Record and Play buttons)? "
        "Since 12.1 the Recorder is a row there, not a screen of its own.",
    "speaker_tone_clean":
        "Did you hear the diagnostic speaker tone clearly without obvious distortion?",
    "microphone_level_responds":
        "Did the Microphone row's level bar on the WS350 move with your sound?",
    "recording_intelligible":
        "Was the five-second microphone recording intelligible during playback?",
    "audio_no_obvious_noise_or_instability":
        "Did audio/recording complete without obvious electrical noise (pops, clicks, hum or hiss), "
        "reboot, hang, or UI freeze?",
}


def ask(observations: dict, key: str, questions: dict | None = None) -> bool | None:
    prompt = QUESTIONS[key]
    if questions is not None:
        questions[key] = prompt
    observations[key] = observation(prompt)
    return observations[key]


def run_speaker_diagnostic(client: Client, initial: dict) -> dict:
    """Bounded 1.2 s 1047 Hz tone; returns the active-state diagnostics."""
    check(initial["speakerAvailable"], "speaker is not available")
    speaker = api(client, "/os12/media/speaker-test", method="POST")
    validate_status(speaker)
    check(speaker["_http_status"] == 202,
          f"speaker test refused: {speaker['error']}")
    time.sleep(0.15)
    speaker_active = status(client)
    check(speaker_active["session"] == "PlayingAudio",
          f"speaker diagnostic did not remain active long enough to sample: {speaker_active['session']}")
    diag = {
        "codecReady": speaker_active.get("audioCodecReady"),
        "i2sReady": speaker_active.get("audioI2sReady"),
        "pipelineRunning": speaker_active.get("audioPipelineRunning"),
        "ampEnabled": speaker_active.get("audioAmpEnabled"),
        "frequency": speaker_active.get("audioCurrentFrequency"),
        "targetGain": speaker_active.get("audioTargetGain"),
        "currentGain": speaker_active.get("audioCurrentGain"),
    }
    print(
        "SPEAKER ACTIVE "
        f"codecReady={diag['codecReady']} i2sReady={diag['i2sReady']} "
        f"pipelineRunning={diag['pipelineRunning']} ampEnabled={diag['ampEnabled']} "
        f"freq={diag['frequency']} targetGain={diag['targetGain']} currentGain={diag['currentGain']}"
    )
    wait_for_session(client, {"Idle"}, 3.0)
    print("PASS  bounded speaker-test lifecycle while Sound & Alerts is visible")
    return diag


def run_microphone_diagnostic(client: Client, initial: dict, samples: int = 8, interval: float = 0.3) -> dict:
    """Baseline sample, then samples while the operator keeps making sound.

    12.3.5 asked for the sound *before* Enter and sampled after it, when the
    sound was over. Now the operator presses Enter first and keeps talking or
    clapping while the samples run; every sample also restarts the live meter
    on the Microphone row, so the operator watches it move.
    """
    check(initial["microphoneAvailable"], "microphone is not available")
    mic = api(client, "/os12/media/microphone-sample", method="POST")
    validate_status(mic)
    check(mic["_http_status"] == 200,
          f"microphone sample refused: {mic['error']}")
    baseline_peak = mic.get("microphoneLastPeak")
    print(
        "PASS  microphone baseline sample (quiet room): "
        f"{mic['microphoneLevelPercent']}% peak={baseline_peak}"
    )
    input(
        "Press Enter, then keep talking or clapping close to the WS350 for about "
        f"{samples * interval:.0f} seconds while you watch the Microphone row's level bar: "
    )
    peaks: list[int] = []
    levels: list[int] = []
    for _ in range(samples):
        stimulated = api(client, "/os12/media/microphone-sample", method="POST")
        validate_status(stimulated)
        check(stimulated["_http_status"] == 200,
              f"stimulated microphone sample refused: {stimulated['error']}")
        if isinstance(stimulated.get("microphoneLastPeak"), int):
            peaks.append(stimulated["microphoneLastPeak"])
        if isinstance(stimulated.get("microphoneLevelPercent"), int):
            levels.append(stimulated["microphoneLevelPercent"])
        time.sleep(interval)
    stimulated_peak = max(peaks) if peaks else None
    stimulated_level = max(levels) if levels else None
    print(
        "MIC RESPONSE "
        f"baselinePeak={baseline_peak} stimulatedPeak={stimulated_peak} "
        f"stimulatedLevel={stimulated_level}%"
    )
    return {
        "baselinePeak": baseline_peak,
        "baselineLevel": mic.get("microphoneLevelPercent"),
        "stimulatedPeak": stimulated_peak,
        "stimulatedLevel": stimulated_level,
        "stimulatedPeaks": peaks,
        "stimulatedLevels": levels,
    }


RECORDING_KEYS = (
    "recordingBytes", "recordingTargetBytes", "recordingWallMs", "recordingRxShortReads",
    "playbackSlot", "playbackDcOffset", "playbackGainQ8",
)


def run_recorder_diagnostic(client: Client, initial: dict) -> dict:
    """Five-second recording, then playback; returns the recorder diagnostics."""
    check(initial["psramAvailable"], "recording requires PSRAM")
    input("Press Enter, then speak a sentence near the WS350 for the next five seconds: ")
    rec = api(client, "/os12/media/record/start", method="POST")
    validate_status(rec)
    check(rec["_http_status"] == 202 and rec["session"] == "Recording",
          f"record start refused: {rec['error']}")
    print("STATE Recording: bounded five-second capture started (keep speaking)")
    completed = wait_for_session(client, {"Idle"}, 8.0)
    check(completed["recordingAvailable"],
          "recording completed without a retained local recording")
    print("PASS  five-second PSRAM recording completed")

    play = api(client, "/os12/media/record/play", method="POST")
    validate_status(play)
    check(play["_http_status"] == 202 and play["session"] == "PlayingRecording",
          f"recording playback refused: {play['error']}")
    played = wait_for_session(client, {"Idle"}, 8.0)
    print("PASS  local recording playback completed while Sound & Alerts is visible")
    diag = {key: played.get(key) for key in RECORDING_KEYS}
    target = diag.get("recordingTargetBytes")
    got = diag.get("recordingBytes")
    if isinstance(target, int) and isinstance(got, int):
        diag["recordingComplete"] = target > 0 and got == target
    wall = diag.get("recordingWallMs")
    if isinstance(wall, int):
        # A 5 s clip that took clearly longer than 5 s of wall time lost audio.
        diag["recordingNoDrops"] = 0 < wall <= 5300
    print("RECORDER " + " ".join(f"{k}={v}" for k, v in diag.items()))
    return diag


def exercise_audio_visible(
    client: Client,
    initial: dict,
    navigation_log: list[dict],
    observations: dict[str, bool | None],
    questions: dict | None = None,
) -> None:
    show_native_media_view(client, "media", navigation_log)
    ask(observations, "native_media_view_visible", questions)

    observations["_speaker_active_diag"] = run_speaker_diagnostic(client, initial)
    mic = run_microphone_diagnostic(client, initial)
    observations["_mic_baseline_peak"] = mic["baselinePeak"]
    observations["_mic_stimulated_peak"] = mic["stimulatedPeak"]

    show_native_media_view(client, "lab", navigation_log)
    ask(observations, "native_media_lab_view_visible", questions)
    observations["_recorder_diag"] = run_recorder_diagnostic(client, initial)


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")),
          "--base-url must start with http:// or https://")
    check(HEX40.fullmatch(args.expect_source_sha) is not None,
          "--expect-source-sha must be exactly 40 lowercase hex characters")

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    destination = output_path(args.output, stamp)
    evidence = {
        "schemaVersion": 6,
        "kind": "workshop-os12-media-physical-acceptance",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base_url).hostname,
        "expectedSourceSha": args.expect_source_sha,
        "runtimeIdentity": None,
        "initialMediaStatus": None,
        "finalMediaStatus": None,
        "observations": {},
        "questions": {},
        "navigationObservations": [],
        "runtimeIdleAndClean": False,
        "runtimeUptimeStartMs": None,
        "runtimeUptimeEndMs": None,
        "runtimeUptimeMonotonic": None,
        "runtimeObservationConflict": False,
        "microphoneBaselinePeak": None,
        "microphoneStimulatedPeak": None,
        "microphonePeakIncreased": None,
        "speakerActiveDiagnostics": None,
        "recorderDiagnostics": None,
        "videoStartedBy": None,
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
        evidence["portalMode"] = establish_portal_session(client)
        print("PASS  signed-in local portal contract")

        identity = update_identity(client)
        evidence["runtimeIdentity"] = identity
        check(
            identity["runningSourceCommit"] == args.expect_source_sha,
            "runtime source SHA does not match --expect-source-sha; refusing to record "
            "physical acceptance against the wrong firmware candidate",
        )
        print(f"PASS  exact runtime source identity: {args.expect_source_sha}")

        initial = status(client)
        evidence["initialMediaStatus"] = public_status(initial)
        evidence["runtimeUptimeStartMs"] = initial.get("deviceUptimeMs")
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
        exercise_audio_visible(client, initial, navigation_log, observations, evidence["questions"])
        evidence["speakerActiveDiagnostics"] = observations.pop("_speaker_active_diag", None)
        evidence["recorderDiagnostics"] = observations.pop("_recorder_diag", None)
        baseline_peak = observations.pop("_mic_baseline_peak", None)
        stimulated_peak = observations.pop("_mic_stimulated_peak", None)
        evidence["microphoneBaselinePeak"] = baseline_peak
        evidence["microphoneStimulatedPeak"] = stimulated_peak
        if isinstance(baseline_peak, int) and isinstance(stimulated_peak, int):
            evidence["microphonePeakIncreased"] = stimulated_peak > baseline_peak

        for key in ("speaker_tone_clean", "microphone_level_responds",
                    "recording_intelligible", "audio_no_obvious_noise_or_instability"):
            ask(observations, key, evidence["questions"])

        print("\nVIDEO\n-----")
        show_native_media_view(client, "video", navigation_log)
        observations["native_camera_viewer_visible"] = observation(
            "Did the dedicated Video Viewer screen appear on the WS350?"
        )

        # Since 12.1.3 the page starts the video itself; older builds open Idle.
        _, evidence["videoStartedBy"] = start_video_after_page_open(client)
        print(
            "STATE PlayingVideo: runtime session entered. "
            "This proves the command/state transition only, not visible video."
        )
        time.sleep(1.5)
        observations["video_visible_motion"] = observation(
            "While the session is PlayingVideo, can you see the built-in WS350 demo motion?"
        )

        pause = api(client, "/os12/media/video/pause", method="POST")
        validate_status(pause)
        check(pause["_http_status"] == 200 and pause["session"] == "Paused",
              f"video pause refused: {pause['error']}")
        print("STATE Paused: runtime pause accepted")
        observations["video_pause_visible"] = observation(
            "Did the visible demo motion freeze when Pause was issued?"
        )

        resume = api(client, "/os12/media/video/resume", method="POST")
        validate_status(resume)
        check(resume["_http_status"] == 200 and resume["session"] == "PlayingVideo",
              f"video resume refused: {resume['error']}")
        print("STATE PlayingVideo: runtime resume accepted")
        time.sleep(1.0)
        observations["video_resume_visible"] = observation(
            "Did visible demo motion resume on the WS350?"
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
            "Did the WS350 stay running continuously with no reboot, watchdog reset, or recovery screen?"
        )

        final = status(client)
        evidence["runtimeUptimeEndMs"] = final.get("deviceUptimeMs")
        start_uptime = evidence["runtimeUptimeStartMs"]
        end_uptime = evidence["runtimeUptimeEndMs"]
        if isinstance(start_uptime, int) and isinstance(end_uptime, int):
            evidence["runtimeUptimeMonotonic"] = end_uptime >= start_uptime
            if observations["no_reboot_or_watchdog"] is not None:
                deterministic_no_reboot = evidence["runtimeUptimeMonotonic"]
                evidence["runtimeObservationConflict"] = (
                    bool(observations["no_reboot_or_watchdog"]) != deterministic_no_reboot
                )
        evidence["finalMediaStatus"] = public_status(final)
        runtime_ok = final["session"] == "Idle" and final["error"] == "None"
        evidence["runtimeIdleAndClean"] = runtime_ok
        evidence["completed"] = True
        if evidence["runtimeUptimeMonotonic"] is not None:
            print(
                "UPTIME "
                f"start={evidence['runtimeUptimeStartMs']}ms "
                f"end={evidence['runtimeUptimeEndMs']}ms "
                f"monotonic={evidence['runtimeUptimeMonotonic']}"
            )
        if evidence["runtimeObservationConflict"]:
            print(
                "EVIDENCE CONFLICT: operator reboot/watchdog observation disagrees "
                "with monotonic device uptime; physical acceptance remains pending."
            )

        all_observations = bool(observations) and all(
            value is True for value in observations.values()
        )
        passed = runtime_ok and all_observations and not evidence["runtimeObservationConflict"]
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
        "--expect-source-sha",
        required=True,
        help="exact 40-character source SHA of the CI physical candidate",
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
