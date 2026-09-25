#!/usr/bin/env python3
"""Route the physical guarded STOP control through the Workshop OS 12 command facade.

This migration is intentionally narrow. It preserves the mature UI13 long-press
interaction and feedback behavior while moving destructive-command eligibility
and transport dispatch behind the OS12 facade.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError




LEGACY_STOP_PATTERN = re.compile(
    r"requestPrinterControlCommand\(\s*slot\s*,\s*PRINTER_CTRL_STOP\s*\)"
)
OS12_STOP = (
    "workshopPlatformDispatchPrinterCommand("
    "slot,workshop::platform::PrinterCommand::Stop,true)"
    "==workshop::platform::CommandResult::Accepted"
)


def apply(repo: Path) -> None:
    marker = repo / "include" / "smart_home_build.h"
    hub_path = repo / "src" / "smart_hub.cpp"
    bridge = repo / "include" / "workshop_platform_bridge.h"

    if not marker.is_file() or not hub_path.is_file():
        raise PatchError("OS12 guarded STOP migration requires reconstructed UI13 source")
    if "#define WORKSHOP_OS_V11_28_UI13 1" not in marker.read_text(encoding="utf-8"):
        raise PatchError("OS12 guarded STOP migration requires v11.28 UI13")
    if not bridge.is_file():
        raise PatchError("OS12 platform bridge must be installed first")

    text = hub_path.read_text(encoding="utf-8")
    if '#include "workshop_platform_bridge.h"' not in text:
        raise PatchError("smart_hub.cpp must include the OS12 platform bridge")

    legacy_matches = list(LEGACY_STOP_PATTERN.finditer(text))
    if not legacy_matches:
        if text.count(OS12_STOP) == 1:
            return
        raise PatchError("guarded STOP: expected one legacy source anchor, found 0")
    if len(legacy_matches) != 1:
        raise PatchError(f"guarded STOP: expected one legacy source anchor, found {len(legacy_matches)}")

    # The current accepted UX contract requires a long-press before STOP can be
    # dispatched. The facade receives `true` only because this replacement stays
    # inside that already-established guarded branch.
    if "longPress" not in text:
        raise PatchError("physical STOP long-press guard missing")

    text = LEGACY_STOP_PATTERN.sub(OS12_STOP, text, count=1)

    if LEGACY_STOP_PATTERN.search(text):
        raise PatchError("legacy physical STOP transport call survived migration")
    if text.count(OS12_STOP) != 1:
        raise PatchError("OS12 guarded STOP dispatch must exist exactly once")
    if "longPress" not in text:
        raise PatchError("physical STOP long-press guard was lost during migration")

    hub_path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 guarded STOP migrated; existing long-press UX preserved")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
