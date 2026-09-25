#!/usr/bin/env python3
"""Route physical Light + Pause/Resume through the Workshop OS 12 command facade.

STOP deliberately remains on the existing long-press guarded path in this
slice. The migration is intentionally narrow: it changes physical Printer
control dispatch only and preserves all existing feedback/UX behavior.
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




LIGHT_PATTERN = re.compile(
    r"requestLightCommand\(\s*slot\s*,\s*s\.lightState\s*!=\s*1\s*\)\s*;"
)
LIGHT_NEW = (
    'const workshop::platform::CommandResult os12LightResult=workshopPlatformDispatchPrinterCommand('
    'slot,s.lightState!=1?workshop::platform::PrinterCommand::ChamberLightOn:'
    'workshop::platform::PrinterCommand::ChamberLightOff,false);'
    'if(os12LightResult==workshop::platform::CommandResult::Accepted)'
)

PAUSE_PATTERN = re.compile(
    r"requestPrinterControlCommand\(\s*slot\s*,\s*paused\s*\?\s*PRINTER_CTRL_RESUME\s*:\s*PRINTER_CTRL_PAUSE\s*\)"
)
PAUSE_NEW = (
    '(workshopPlatformDispatchPrinterCommand('
    'slot,paused?workshop::platform::PrinterCommand::Resume:workshop::platform::PrinterCommand::Pause,false)'
    '==workshop::platform::CommandResult::Accepted)'
)

STOP_PATTERN = re.compile(
    r"requestPrinterControlCommand\(\s*slot\s*,\s*PRINTER_CTRL_STOP\s*\)"
)


def replace_regex_once(text: str, pattern: re.Pattern[str], new: str, label: str) -> str:
    # Idempotence: a migrated source no longer contains the direct transport call.
    matches = list(pattern.finditer(text))
    if not matches:
        if new in text:
            return text
        raise PatchError(f"{label}: expected one source anchor, found 0")
    if len(matches) != 1:
        raise PatchError(f"{label}: expected one source anchor, found {len(matches)}")
    return pattern.sub(new, text, count=1)


def apply(repo: Path) -> None:
    marker = repo / "include" / "smart_home_build.h"
    hub_path = repo / "src" / "smart_hub.cpp"
    if not marker.is_file() or not hub_path.is_file():
        raise PatchError("OS12 control migration requires reconstructed UI13 source")
    if "#define WORKSHOP_OS_V11_28_UI13 1" not in marker.read_text(encoding="utf-8"):
        raise PatchError("OS12 control migration requires v11.28 UI13")
    if not (repo / "include" / "workshop_platform_bridge.h").is_file():
        raise PatchError("OS12 platform bridge must be installed first")

    text = hub_path.read_text(encoding="utf-8")
    if '#include "workshop_platform_bridge.h"' not in text:
        raise PatchError("smart_hub.cpp must include the OS12 platform bridge")
    if len(STOP_PATTERN.findall(text)) != 1:
        raise PatchError("guarded legacy STOP path must exist exactly once before migration")

    # Light is a void legacy call. Replace only that call + semicolon with a
    # preflighted result and a one-statement `if`, so the already-existing next
    # feedback statement executes only when the OS12 facade accepted the command.
    text = replace_regex_once(text, LIGHT_PATTERN, LIGHT_NEW, "physical light command")

    # Pause/Resume already feeds a boolean `ok` in the mature UI. Replace only
    # the expression, preserving the existing feedback/buzzer block verbatim.
    text = replace_regex_once(text, PAUSE_PATTERN, PAUSE_NEW, "physical pause/resume command")

    # This slice must not absorb STOP. Keeping this assertion in the patcher
    # prevents an accidental broad replacement from weakening the release gate.
    if len(STOP_PATTERN.findall(text)) != 1:
        raise PatchError("guarded legacy STOP path must remain exactly once")
    if "longPress" not in text:
        raise PatchError("physical STOP long-press guard missing")

    hub_path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 non-destructive physical controls migrated; guarded STOP preserved")


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
