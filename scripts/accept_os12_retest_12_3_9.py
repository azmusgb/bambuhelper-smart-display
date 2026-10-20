#!/usr/bin/env python3
"""Re-test only what 12.3.9 changed on the WS350 touchscreen.

12.3.9 (glance and legibility, from the 12.3.8 UX critique) changes:
- Home and Printer > Status while printing: the percentage in a 48 px font,
  time left and "Done <time>" beside it; one done-at time on every screen;
- row values, stepper values, button labels and toasts in 14 px (10 px
  before); the calm idle status line in 19 px;
- "not set up" reasons drawn grey instead of amber; Home's filament row says
  "Not set up"; an off switch keeps a visible outline; "No smart plug";
  "35°C";
- Printer > Camera: no control row, the picture runs to the tab bar, and
  Pause/Resume is a button at the top right.

This script opens each changed view, says what to try ("Try:"), and asks one
or two yes/no questions per change, judged from where the owner normally
stands beside the printer. Nothing else is asked. It records the answers,
the running firmware identity and a frame probe per view.

  python3 scripts/accept_os12_retest_12_3_9.py --expect-source-sha <40-hex>

Best run while a print is running (the Home and Printer questions are about
the print status); answer "u" where a view cannot show the change. It never
stores the portal code and does not promote anything.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from accept_os12_device_ui_physical import catalog, frame_probe, observation, show
from accept_os12_media_physical import AcceptanceError, Client, check, update_identity, write_evidence
from accept_os12_media_runtime import api, validate_status
from accept_os12_portal_runtime import establish_portal_session

HEX40 = re.compile(r"^[0-9a-f]{40}$")

STAND = "From where you normally stand beside the printer (arm's length), "

# (view id, label when the view is not in /hub/views, what to try, questions).
# Each question is (key, text). Only what 12.3.9 changed is asked.
CHANGED_VIEWS = (
    ("home", None,
     "With a print running: the big number on the left is the percentage; to its right, time left "
     "and 'Done <time>'. The Filament row says 'Not set up' in grey if inventory is not connected.",
     (("printStatusReadable", STAND + "can you read the percentage, the time left and the done-at time on Home "
                              "without stepping closer?"),
      ("notSetUpCalm", "Does an unconnected Filament row now read as 'not set up' rather than as a warning?"))),
    ("printer", None,
     "Same layout as Home; 'Printing' is no longer repeated under the header. Compare the 'Done' time "
     "with Home's, then wait a minute: it should not change unless the printer's estimate does.",
     (("printStatusReadable", STAND + "can you read the percentage, the time left and the done-at time on "
                              "Printer > Status?"),
      ("doneAtConsistent", "Is the done-at time the same as on Home, and does it hold still?"))),
    ("printer-ams", None,
     "Tray types (for example 'PLA') and 'In use' are in the larger type now.",
     (("valuesReadable", STAND + "can you read the tray types and 'In use'?"),)),
    ("printer-camera", "Printer > Camera",
     "The picture now runs from the header to the tab bar. Tap Pause at the top right, then Resume, "
     "then Back (returns to Printer).",
     (("cameraLarger", "Is the camera picture clearly bigger, with nothing below it but the tab bar?"),
      ("cameraPause", "Do Pause and Resume at the top right work, and does Back return to Printer?"))),
    ("settings-display", None,
     "Values such as '25%', 'Screen off' and 'Show clock' are in the larger type. Step Brightness "
     "with - and + and watch the value.",
     (("valuesReadable", STAND + "can you read the values next to the - and + buttons?"),)),
    ("settings-printer-power", None,
     "Bed cooldown alert: an off switch now has a visible outline. 'Cooldown at' says '35°C'. Rows "
     "that need a smart plug say why in grey, not amber.",
     (("offSwitchLooksLikeSwitch", "Does an off switch still look like a switch (an outlined track, not a grey dot)?"),
      ("valuesReadable", STAND + "can you read the values, including the °C on Cooldown at?"))),
    ("hardware-auto-off", None,
     "Every row needs a smart plug: the reason is now grey, not amber. Tap any row: the reason "
     "replaces the title at the top for a moment, in the larger type.",
     (("notSetUpCalm", "Does the page read as 'not set up yet' rather than as a list of warnings?"),
      ("toastReadable", "Is the message at the top easy to read and noticeable?"))),
    ("system-update", None,
     "'Check now' and the version and date values are in the larger type. Test builds (off) shows "
     "an outlined switch. Cancel any dialog.",
     (("valuesReadable", STAND + "can you read the values and the Check now button?"),)),
)

CALM_QUESTION = ("calmStatusReadable",
                 "If the calm idle screen came on during this walk: is its status line (for example "
                 "'Printing 42% · done 6:42 PM') easy to read? Answer u if you did not see it.")
RESPONSIVE_QUESTION = ("touchResponsiveness",
                       "Did touch stay as quick as on 12.3.8 across this walk (no slower taps or redraws)?")

HINT = ("Only what 12.3.9 changed is asked. Stand where you normally stand beside the printer; "
        "answer y, n, or u (not sure / could not see it).")


def output_path(arg: str | None, stamp: str) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return Path.home() / "Downloads" / f"workshop-os12-retest-12.3.9-{stamp}.json"


def run_views(client: Client, evidence: dict) -> None:
    views = catalog(client)
    by_id = {str(v.get("id", "")): v for v in views}
    missing = [vid for vid, label, _, _ in CHANGED_VIEWS if label is None and vid not in by_id]
    check(not missing, "required native views missing: " + ", ".join(missing))
    print("\n12.3.9 CHANGES\n" + HINT + "\n")
    for view_id, fallback, hint, questions in CHANGED_VIEWS:
        label = str((by_id.get(view_id) or {}).get("label") or fallback or view_id)
        print(f"VIEW {label} ({view_id})")
        show(client, view_id)
        record: dict = {"label": label, "frame": frame_probe(client), "questions": {}, "answers": {}}
        print(f"  Try: {hint}")
        for key, text in questions:
            record["questions"][key] = text
            record["answers"][key] = observation(text)
        evidence["views"][view_id] = record
        if view_id == "printer-camera":
            # Opening Printer > Camera starts the camera; leave media Idle.
            validate_status(api(client, "/os12/media/stop", method="POST"))
    print("\nCALM IDLE SCREEN")
    print("  Try: it appears after the display goes idle with More > Display > Calm idle screen on.")
    evidence["questions"][CALM_QUESTION[0]] = CALM_QUESTION[1]
    evidence["answers"][CALM_QUESTION[0]] = observation(CALM_QUESTION[1])
    evidence["questions"][RESPONSIVE_QUESTION[0]] = RESPONSIVE_QUESTION[1]
    evidence["answers"][RESPONSIVE_QUESTION[0]] = observation(RESPONSIVE_QUESTION[1])


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
    check(HEX40.fullmatch(args.expect_source_sha) is not None,
          "--expect-source-sha must be exactly 40 lowercase hex characters")
    now = datetime.now(timezone.utc)
    dest = output_path(args.output, now.strftime("%Y%m%d-%H%M%S"))
    evidence: dict = {
        "schemaVersion": 1,
        "kind": "workshop-os12-12.3.9-retest-of-glance-legibility-changes",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base).hostname,
        "expectedSourceSha": args.expect_source_sha,
        "runtimeIdentity": None,
        "portalMode": "unknown",
        "views": {},
        "questions": {},
        "answers": {},
        "passed": False,
        "completed": False,
        "failure": None,
        "scope": "re-test of the 12.3.9 touchscreen changes only; not whole-device acceptance",
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
        run_views(client, evidence)
        evidence["completed"] = True
    except (AcceptanceError, KeyboardInterrupt, EOFError) as exc:
        evidence["failure"] = "operator_aborted" if isinstance(exc, (KeyboardInterrupt, EOFError)) else str(exc)
        write_evidence(dest, evidence)
        print(f"\nEvidence: {dest}\nFAIL: {evidence['failure']}")
        return 130 if evidence["failure"] == "operator_aborted" else 1

    failed, unknown = [], []
    answers: list[tuple[str, bool | None]] = []
    for vid, rec in evidence["views"].items():
        answers.extend((f"{vid}.{key}", value) for key, value in rec["answers"].items())
    answers.extend(evidence["answers"].items())
    for name, value in answers:
        if value is False:
            failed.append(name)
        elif value is None and name != CALM_QUESTION[0]:
            # The calm screen may not come on during a short walk; "u" there is not a gap.
            unknown.append(name)
    evidence["passed"] = not failed and not unknown
    evidence["failed"] = failed
    evidence["unknown"] = unknown
    write_evidence(dest, evidence)
    print(f"\nEvidence: {dest}")
    if evidence["passed"]:
        print("12.3.9 RE-TEST OF THE GLANCE AND LEGIBILITY CHANGES: PASS")
        print("Scope: the 12.3.9 changes only. Whole-device acceptance and promotion are separate.")
        return 0
    print("12.3.9 RE-TEST OF THE GLANCE AND LEGIBILITY CHANGES: FAIL / PENDING")
    if failed:
        print("Failed: " + ", ".join(failed))
    if unknown:
        print("Unknown: " + ", ".join(unknown))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    ap.add_argument("--expect-source-sha", required=True,
                    help="exact 40-character source SHA of the installed 12.3.9 CI candidate")
    ap.add_argument("--output", help="evidence JSON path; defaults to ~/Downloads")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
