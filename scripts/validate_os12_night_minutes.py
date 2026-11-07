#!/usr/bin/env python3
"""Check the reconstructed tree keeps the night-mode schedule in minutes (apply_workshop_os12_night_minutes.py)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: night-mode minutes: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    root = Path(args.source_root).resolve()

    def read(rel: str) -> str:
        path = repo / rel
        if not path.is_file():
            fail(f"missing {rel}")
        return path.read_text(encoding="utf-8")

    header = (root / "firmware/platform/ui/night_time.hpp").read_text(encoding="utf-8")
    if read("include/workshop_night_time.hpp") != header:
        fail("include/workshop_night_time.hpp is not firmware/platform/ui/night_time.hpp")

    # No code reads or writes the old whole-hour fields; only the migration and the older-export / older-page paths name hours.
    for rel in ("src/settings.h", "src/settings.cpp", "src/display_ui.cpp", "src/smart_hub.cpp", "src/web_template.cpp", "src/web_server.cpp"):
        text = read(rel)
        if re.search(r"\bnight(?:Start|End)Hour\b", text.replace('dp["nightStartHour"]', "").replace('dp["nightEndHour"]', "")):
            fail(f"{rel} still uses nightStartHour / nightEndHour")
    settings = read("src/settings.cpp")
    for needle in ('"dp_nstartm"', '"dp_nendm"', "wnight::resolveStored", 'prefs.putUShort("dp_nstartm"', 'prefs.putUShort("dp_nendm"'):
        if needle not in settings:
            fail(f"settings.cpp lacks {needle}")
    if "wnight::isNight(" not in read("src/display_ui.cpp"):
        fail("display_ui.cpp does not test the schedule in minutes")
    web = read("src/web_server.cpp")
    for needle in ('server.hasArg("nstartm")', 'server.hasArg("nendm")', 'server.hasArg("nstart")', 'server.hasArg("nend")',
                   'dp["nightStartMin"] = dpSettings.nightStartMin', 'dp["nightEndMin"] = dpSettings.nightEndMin', "wnight::importTime("):
        if needle not in web:
            fail(f"web_server.cpp lacks {needle}")
    if "wnight::kOptionCount" not in read("src/web_template.cpp"):
        fail("web_template.cpp does not list the 96 times")
    js = read("web/app.js")
    if "p.append('nstartm'" not in js or "p.append('nendm'" not in js or "p.append('nstart'," in js:
        fail("the Display form does not post nstartm / nendm")
    hub = read("src/smart_hub.cpp")
    for needle in ("wnight::indexOf(dpSettings.nightStartMin)", "wnight::indexOf(dpSettings.nightEndMin)", "wnight::kOptionCount"):
        if needle not in hub:
            fail(f"smart_hub.cpp lacks {needle}")
    print("PASS: night-mode schedule kept in minutes: 96 options, hour migration, portal form and export, midnight-safe test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
