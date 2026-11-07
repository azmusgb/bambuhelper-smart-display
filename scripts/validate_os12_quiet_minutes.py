#!/usr/bin/env python3
"""Check the reconstructed tree keeps quiet hours as an explicit on/off and two times in minutes (apply_workshop_os12_quiet_minutes.py)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: quiet hours: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    def read(rel: str) -> str:
        path = repo / rel
        if not path.is_file():
            fail(f"missing {rel}")
        return path.read_text(encoding="utf-8")

    # Nothing reads or writes the old hour fields; only the migration, an older page and an older export name hours.
    for rel in ("src/settings.h", "src/settings.cpp", "src/buzzer.cpp", "src/smart_hub.cpp", "src/web_template.cpp", "src/web_server.cpp"):
        if re.search(r"\bquiet(?:Start|End)Hour\b", read(rel)):
            fail(f"{rel} still uses quietStartHour / quietEndHour")
    settings = read("src/settings.cpp")
    for needle in ('"buz_qon"', '"buz_qsm"', '"buz_qem"', "wnight::resolveQuiet", 'prefs.putBool("buz_qon"', 'prefs.putUShort("buz_qsm"', 'prefs.putUShort("buz_qem"'):
        if needle not in settings:
            fail(f"settings.cpp lacks {needle}")
    if "wnight::quietNow(" not in read("src/buzzer.cpp"):
        fail("buzzer.cpp does not test quiet hours in minutes")
    web = read("src/web_server.cpp")
    for needle in ('server.hasArg("buzqon")', 'server.hasArg("buzqsm")', 'server.hasArg("buzqem")', 'server.hasArg("buzqs")', 'server.hasArg("buzqe")',
                   'server.hasArg("quietOn")', 'server.hasArg("quietStartMin")', 'server.hasArg("quietEndMin")', 'server.hasArg("quietStart")',
                   'server.hasArg("quietEnd")', 'buz["quietEnabled"] = buzzerSettings.quietEnabled', 'doc["quietEnabled"] = buzzerSettings.quietEnabled',
                   "wnight::importQuiet("):
        if needle not in web:
            fail(f"web_server.cpp lacks {needle}")
    if "BUZ_QS_OPTS" not in read("src/web_template.cpp") or "%BUZ_QS_OPTS%" not in read("include/web_pages.h"):
        fail("the Sound card does not list the quiet-hours times")
    js = read("web/app.js")
    for needle in ("p.append('buzqon'", "p.append('buzqem'", "p.append('quietOn'", "p.append('quietEndMin'"):
        if needle not in js:
            fail(f"app.js lacks {needle}")
    if "p.append('buzqs'," in js or "p.append('quietStart'," in js:
        fail("app.js still posts quiet hours as whole hours")
    hub = read("src/smart_hub.cpp")
    for needle in ("wnight::quietIndex(", "wnight::chooseQuietStart(", "buzzerSettings.quietEnabled"):
        if needle not in hub:
            fail(f"smart_hub.cpp lacks {needle}")
    print("PASS: quiet hours kept as an explicit on/off and two times in minutes; portal, export and touchscreen agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
