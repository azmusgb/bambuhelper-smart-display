#!/usr/bin/env python3
"""Re-test only what the 12.3.5 physical acceptance failed, on a 12.3.6 WS350.

The owner's 12.3.5 walk (evidence-sensory/device-ui.json and media.json)
answered "no" to:
- controlsComfortable on home, printer, printer-ams, workshop,
  settings-printer-power, hardware-auto-off, media-video, system-update and
  system-diagnostics, and touchResponsiveness overall (home's hierarchyClear
  was left unanswered);
- audio_no_obvious_noise_or_instability, microphone_level_responds,
  recording_intelligible and native_media_lab_view_visible.

This script asks exactly those questions again, with the same wording as
accept_os12_device_ui_physical.py for the touch part and the 12.3.6 wording
of accept_os12_media_physical.py for the audio part (whose helpers it reuses),
and prints what to try on each view first. It also records the 12.3.6
objective audio checks: the clip is complete and took no longer than 5.3 s
(no dropped audio), playback used the microphone slot with a bounded gain,
and the codec stayed powered and muted at idle (no power-cycle pops).

  python3 scripts/accept_os12_retest_12_3_6.py --expect-source-sha <40-hex>
  (add --skip-touch or --skip-audio to run one half)

It never stores the portal code and does not promote anything.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from accept_os12_device_ui_physical import catalog, frame_probe, observation, show
from accept_os12_media_physical import (
    AcceptanceError,
    Client,
    ask,
    check,
    public_status,
    run_microphone_diagnostic,
    run_recorder_diagnostic,
    run_speaker_diagnostic,
    show_native_media_view,
    update_identity,
    write_evidence,
)
from accept_os12_media_runtime import api, status, validate_status, wait_for_session
from accept_os12_portal_runtime import establish_portal_session

HEX40 = re.compile(r"^[0-9a-f]{40}$")

# The views whose controlsComfortable was "no" on 12.3.5, and what to try.
TOUCH_VIEWS = (
    ("home", "Tap the print card (opens Printer) and the Filament row (opens Workshop); "
             "the temperatures are read-only and now drawn flat."),
    ("printer", "Tap Status / AMS / Control. The status card, temperatures and Layer row are "
                "read-only and drawn flat."),
    ("printer-ams", "AMS trays are read-only: drawn flat, the tray in use has a blue bar. Tap the "
                    "segment buttons."),
    ("workshop", "Tap Timer Start, the - / + of Timer length, and Filament inventory."),
    ("settings-printer-power", "Disabled rows (no smart plug) are flat with an empty switch outline; "
                               "toggle Bed cooldown alert and step Cooldown at."),
    ("hardware-auto-off", "Every row is disabled until a smart plug is set up: they should read as "
                          "not available (flat, no -/+, empty switch)."),
    ("media-video", "Tap Pause and Resume; the button outlines as soon as your finger lands."),
    ("system-update", "Tap Check now and the Test builds switch (Cancel the dialog); Version and "
                      "Date & time are read-only and flat."),
    ("system-diagnostics", "All rows are read-only and drawn flat; only Back is a control."),
)

UI_COMFORT = "Are visible controls on {label} comfortably finger-sized and clearly enabled/disabled?"
UI_HIERARCHY = "Is the information hierarchy/state on {label} immediately understandable?"
UI_RESPONSIVE = "Did touch remain responsive across the full walk with no perceptible interaction starvation?"

TOUCH_HINT = (
    "On every view: a control outlines in blue the moment your finger lands, and the page "
    "updates right after you lift. Taps just above the tab bar do nothing (4 px guard band)."
)


def output_path(arg: str | None, stamp: str) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return Path.home() / "Downloads" / f"workshop-os12-retest-12.3.6-{stamp}.json"


def run_touch(client: Client, evidence: dict) -> None:
    views = catalog(client)
    by_id = {str(v.get("id", "")): v for v in views}
    missing = [vid for vid, _ in TOUCH_VIEWS if vid not in by_id]
    check(not missing, "required native views missing: " + ", ".join(missing))
    print("\nTOUCH COMFORT (views that failed on 12.3.5)\n" + TOUCH_HINT + "\n")
    for view_id, hint in TOUCH_VIEWS:
        label = str(by_id[view_id].get("label") or view_id)
        print(f"VIEW {label} ({view_id})")
        show(client, view_id)
        record: dict = {"label": label, "frame": frame_probe(client), "controlsComfortable": None}
        print(f"  Try: {hint}")
        prompt = UI_COMFORT.format(label=label)
        record["questions"] = {"controlsComfortable": prompt}
        if view_id == "home":
            # Left unanswered on 12.3.5.
            record["questions"]["hierarchyClear"] = UI_HIERARCHY.format(label=label)
            record["hierarchyClear"] = observation(record["questions"]["hierarchyClear"])
        record["controlsComfortable"] = observation(prompt)
        evidence["views"][view_id] = record
        if view_id == "media-video":
            # Opening Video test starts the demo video; leave media Idle.
            stop = api(client, "/os12/media/stop", method="POST")
            validate_status(stop)
    evidence["touchResponsiveness"] = observation(UI_RESPONSIVE)


def run_audio(client: Client, evidence: dict) -> None:
    observations = evidence["observations"]
    questions = evidence["questions"]
    initial = status(client)
    evidence["initialMediaStatus"] = public_status(initial)
    check(initial["session"] == "Idle", f"audio re-test must start Idle, got {initial['session']}")
    print("\nAUDIO / MICROPHONE / RECORDER (failed on 12.3.5)")
    show_native_media_view(client, "media", evidence["navigationObservations"])
    evidence["speakerActiveDiagnostics"] = run_speaker_diagnostic(client, initial)
    mic = run_microphone_diagnostic(client, initial)
    evidence["microphone"] = mic
    if isinstance(mic["baselinePeak"], int) and isinstance(mic["stimulatedPeak"], int):
        evidence["microphonePeakIncreased"] = mic["stimulatedPeak"] > mic["baselinePeak"]
    ask(observations, "microphone_level_responds", questions)

    show_native_media_view(client, "lab", evidence["navigationObservations"])
    ask(observations, "native_media_lab_view_visible", questions)
    evidence["recorderDiagnostics"] = run_recorder_diagnostic(client, initial)
    ask(observations, "recording_intelligible", questions)

    # 12.3.6: after the idle timeout (1.5 s) the codec stays powered with its
    # DAC muted instead of being reset and powered down (the pops).
    time.sleep(2.2)
    idle = status(client)
    evidence["idleAudio"] = {
        "audioPipelineRunning": idle.get("audioPipelineRunning"),
        "audioCodecReady": idle.get("audioCodecReady"),
        "audioIdleQuiet": idle.get("audioIdleQuiet"),
    }
    evidence["idleWithoutPowerCycle"] = (
        idle.get("audioPipelineRunning") is True and idle.get("audioCodecReady") is True
        and idle.get("audioIdleQuiet") is True
    )
    print("IDLE AUDIO " + json.dumps(evidence["idleAudio"]))
    ask(observations, "audio_no_obvious_noise_or_instability", questions)
    final = wait_for_session(client, {"Idle"}, 3.0)
    evidence["finalMediaStatus"] = public_status(final)


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
    check(HEX40.fullmatch(args.expect_source_sha) is not None,
          "--expect-source-sha must be exactly 40 lowercase hex characters")
    check(not (args.skip_touch and args.skip_audio), "nothing to do with both --skip-touch and --skip-audio")
    now = datetime.now(timezone.utc)
    dest = output_path(args.output, now.strftime("%Y%m%d-%H%M%S"))
    evidence: dict = {
        "schemaVersion": 1,
        "kind": "workshop-os12-12.3.6-retest-of-12.3.5-failures",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base).hostname,
        "expectedSourceSha": args.expect_source_sha,
        "runtimeIdentity": None,
        "portalMode": "unknown",
        "views": {},
        "touchResponsiveness": None,
        "observations": {},
        "questions": {},
        "navigationObservations": [],
        "initialMediaStatus": None,
        "finalMediaStatus": None,
        "speakerActiveDiagnostics": None,
        "microphone": None,
        "microphonePeakIncreased": None,
        "recorderDiagnostics": None,
        "idleAudio": None,
        "idleWithoutPowerCycle": None,
        "ranTouch": not args.skip_touch,
        "ranAudio": not args.skip_audio,
        "passed": False,
        "completed": False,
        "failure": None,
        "scope": "re-test of the 12.3.5 physical failures only; not whole-device acceptance",
    }
    client = Client(base)
    try:
        evidence["portalMode"] = establish_portal_session(client)
        identity = update_identity(client)
        evidence["runtimeIdentity"] = identity
        check(identity["runningSourceCommit"] == args.expect_source_sha,
              "runtime source SHA does not match --expect-source-sha; refusing to record "
              "a re-test against the wrong firmware candidate")
        print(f"Running: {identity['runningVersion']} @ {identity['runningSourceCommit']}")
        if not args.skip_touch:
            run_touch(client, evidence)
        if not args.skip_audio:
            run_audio(client, evidence)
        evidence["completed"] = True
    except (AcceptanceError, KeyboardInterrupt, EOFError) as exc:
        evidence["failure"] = "operator_aborted" if isinstance(exc, (KeyboardInterrupt, EOFError)) else str(exc)
        write_evidence(dest, evidence)
        print(f"\nEvidence: {dest}\nFAIL: {evidence['failure']}")
        return 130 if evidence["failure"] == "operator_aborted" else 1

    failed, unknown = [], []
    answers: list[tuple[str, bool | None]] = []
    for vid, rec in evidence["views"].items():
        answers.append((f"{vid}.controlsComfortable", rec["controlsComfortable"]))
        if "hierarchyClear" in rec:
            answers.append((f"{vid}.hierarchyClear", rec["hierarchyClear"]))
    if not args.skip_touch:
        answers.append(("touchResponsiveness", evidence["touchResponsiveness"]))
    for key, value in evidence["observations"].items():
        answers.append((key, value))
    if not args.skip_audio:
        rec = evidence["recorderDiagnostics"] or {}
        answers.append(("objective.recordingComplete", rec.get("recordingComplete")))
        answers.append(("objective.recordingNoDrops", rec.get("recordingNoDrops")))
        answers.append(("objective.idleWithoutPowerCycle", evidence["idleWithoutPowerCycle"]))
        answers.append(("objective.microphonePeakIncreased", evidence["microphonePeakIncreased"]))
    for name, value in answers:
        if value is False:
            failed.append(name)
        elif value is None:
            unknown.append(name)
    evidence["passed"] = not failed and not unknown
    evidence["failed"] = failed
    evidence["unknown"] = unknown
    write_evidence(dest, evidence)
    print(f"\nEvidence: {dest}")
    if evidence["passed"]:
        print("12.3.6 RE-TEST OF THE 12.3.5 FAILURES: PASS")
        print("Scope: the failed items only. Whole-device acceptance and promotion are separate.")
        return 0
    print("12.3.6 RE-TEST OF THE 12.3.5 FAILURES: FAIL / PENDING")
    if failed:
        print("Failed: " + ", ".join(failed))
    if unknown:
        print("Unknown: " + ", ".join(unknown))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    ap.add_argument("--expect-source-sha", required=True,
                    help="exact 40-character source SHA of the installed 12.3.6 CI candidate")
    ap.add_argument("--output", help="evidence JSON path; defaults to ~/Downloads")
    ap.add_argument("--skip-touch", action="store_true", help="only the audio, microphone and recorder part")
    ap.add_argument("--skip-audio", action="store_true", help="only the touch comfort part")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
