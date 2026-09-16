#!/usr/bin/env python3
"""Route physical Light + Pause/Resume through the Workshop OS 12 command facade.

STOP deliberately remains on the existing long-press guarded path in this
slice. The migration is intentionally narrow: it changes physical Printer
control dispatch only and preserves all existing feedback/UX behavior.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


LIGHT_OLD = 'requestLightCommand(slot,s.lightState!=1);setPrinterFeedback(0,"LIGHT SENT");'
LIGHT_NEW = (
    'const workshop::platform::CommandResult os12LightResult=workshopPlatformDispatchPrinterCommand('
    'slot,s.lightState!=1?workshop::platform::PrinterCommand::ChamberLightOn:'
    'workshop::platform::PrinterCommand::ChamberLightOff,false);'
    'if(os12LightResult==workshop::platform::CommandResult::Accepted)'
    'setPrinterFeedback(0,"LIGHT SENT");'
)

PAUSE_OLD = (
    'const bool ok=requestPrinterControlCommand(slot,paused?PRINTER_CTRL_RESUME:PRINTER_CTRL_PAUSE);'
    'if(ok){setPrinterFeedback(1,paused?"RESUME SENT":"PAUSE SENT");buzzerPlay(BUZZ_CLICK);}'
)
PAUSE_NEW = (
    'const workshop::platform::CommandResult os12PrintResult=workshopPlatformDispatchPrinterCommand('
    'slot,paused?workshop::platform::PrinterCommand::Resume:workshop::platform::PrinterCommand::Pause,false);'
    'if(os12PrintResult==workshop::platform::CommandResult::Accepted)'
    '{setPrinterFeedback(1,paused?"RESUME SENT":"PAUSE SENT");buzzerPlay(BUZZ_CLICK);}'
)

STOP_MARKER = 'requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)


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
    if STOP_MARKER not in text:
        raise PatchError("guarded legacy STOP path missing before non-destructive migration")

    text = replace_once(text, LIGHT_OLD, LIGHT_NEW, "physical light command")
    text = replace_once(text, PAUSE_OLD, PAUSE_NEW, "physical pause/resume command")

    # This slice must not absorb STOP. Keeping this assertion in the patcher
    # prevents an accidental broad replacement from weakening the release gate.
    if text.count(STOP_MARKER) != 1:
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
