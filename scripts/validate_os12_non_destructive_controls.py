#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_non_destructive_controls.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_non_destructive", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load OS12 non-destructive control patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_hub() -> str:
    return '''#include "workshop_platform_bridge.h"\n\nvoid touch(bool longPress){\n  BambuState&s=displayedPrinter().state;const uint8_t slot=rotState.displayIndex;const bool paused=(s.gcodeStateId==GCODE_PAUSE);const bool active=s.printing||paused;\n  if(s.connected){requestLightCommand(slot,s.lightState!=1);setPrinterFeedback(0,"LIGHT SENT");buzzerPlay(BUZZ_CLICK);}\n  if(s.connected&&active){const bool ok=requestPrinterControlCommand(slot,paused?PRINTER_CTRL_RESUME:PRINTER_CTRL_PAUSE);if(ok){setPrinterFeedback(1,paused?"RESUME SENT":"PAUSE SENT");buzzerPlay(BUZZ_CLICK);}}\n  if(s.connected&&active&&longPress){if(requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)){setPrinterFeedback(3,"STOP SENT",1800);buzzerPlay(BUZZ_CLICK);}}\n}\n'''


def validate() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-nondestructive-") as tmp:
        repo = Path(tmp)
        (repo / "include").mkdir(parents=True)
        (repo / "src").mkdir(parents=True)
        (repo / "include/smart_home_build.h").write_text(
            "#pragma once\n#define WORKSHOP_OS_V11_28_UI13 1\n", encoding="utf-8"
        )
        (repo / "include/workshop_platform_bridge.h").write_text("#pragma once\n", encoding="utf-8")
        (repo / "src/smart_hub.cpp").write_text(synthetic_hub(), encoding="utf-8")

        patcher.apply(repo)
        patcher.apply(repo)
        text = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8")

        required = (
            "workshopPlatformDispatchPrinterCommand(slot,s.lightState!=1?",
            "workshop::platform::PrinterCommand::ChamberLightOn",
            "workshop::platform::PrinterCommand::ChamberLightOff",
            "workshop::platform::PrinterCommand::Resume",
            "workshop::platform::PrinterCommand::Pause",
            "workshop::platform::CommandResult::Accepted",
            "requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)",
            "longPress",
        )
        for needle in required:
            if needle not in text:
                fail(f"required migrated/guarded control marker missing: {needle}")

        forbidden = (
            'requestLightCommand(slot,s.lightState!=1);setPrinterFeedback(0,"LIGHT SENT");',
            'requestPrinterControlCommand(slot,paused?PRINTER_CTRL_RESUME:PRINTER_CTRL_PAUSE)',
        )
        for needle in forbidden:
            if needle in text:
                fail(f"direct non-destructive physical command survived migration: {needle}")

        if text.count("requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)") != 1:
            fail("guarded STOP must remain on the legacy path exactly once in this slice")


def main() -> int:
    validate()
    print("Workshop OS 12 non-destructive physical control migration validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
