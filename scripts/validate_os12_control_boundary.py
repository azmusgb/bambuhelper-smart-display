#!/usr/bin/env python3
"""Fail closed if migrated physical printer controls bypass the OS12 facade."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


DIRECT_PATTERNS = {
    "light": re.compile(r"requestLightCommand\(\s*slot\s*,"),
    "pause/resume": re.compile(
        r"requestPrinterControlCommand\(\s*slot\s*,\s*paused\s*\?\s*PRINTER_CTRL_RESUME\s*:\s*PRINTER_CTRL_PAUSE\s*\)"
    ),
    "stop": re.compile(r"requestPrinterControlCommand\(\s*slot\s*,\s*PRINTER_CTRL_STOP\s*\)"),
}

REQUIRED = (
    "workshop::platform::PrinterCommand::ChamberLightOn",
    "workshop::platform::PrinterCommand::ChamberLightOff",
    "workshop::platform::PrinterCommand::Pause",
    "workshop::platform::PrinterCommand::Resume",
    "workshop::platform::PrinterCommand::Stop",
    "workshopPlatformDispatchPrinterCommand",
    "longPress",
)


def validate(repo: Path) -> None:
    hub = repo / "src" / "smart_hub.cpp"
    if not hub.is_file():
        raise SystemExit("FAIL: reconstructed smart_hub.cpp not found")
    text = hub.read_text(encoding="utf-8")

    for label, pattern in DIRECT_PATTERNS.items():
        if pattern.search(text):
            raise SystemExit(f"FAIL: direct physical {label} transport call survived OS12 migration")

    for marker in REQUIRED:
        if marker not in text:
            raise SystemExit(f"FAIL: required OS12 control-boundary marker missing: {marker}")

    if text.count("workshop::platform::PrinterCommand::Stop") != 1:
        raise SystemExit("FAIL: guarded physical Stop must dispatch through OS12 exactly once")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    validate(Path(args.repo).resolve())
    print("Workshop OS 12 physical control boundary validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
