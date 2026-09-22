#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_guarded_stop.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_guarded_stop", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load OS12 guarded STOP patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_hub() -> str:
    return '''#include "workshop_platform_bridge.h"\n\nvoid touch(bool longPress){\n  BambuState&s=displayedPrinter().state;const uint8_t slot=rotState.displayIndex;const bool paused=(s.gcodeStateId==GCODE_PAUSE);const bool active=s.printing||paused;\n  if(s.connected&&active&&longPress){if(requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)){setPrinterFeedback(3,"STOP SENT",1800);buzzerPlay(BUZZ_CLICK);}}\n}\n'''


def prepare_repo(root: Path, hub: str) -> None:
    (root / "include").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "include/smart_home_build.h").write_text(
        "#pragma once\n#define WORKSHOP_OS_V11_28_UI13 1\n", encoding="utf-8"
    )
    (root / "include/workshop_platform_bridge.h").write_text("#pragma once\n", encoding="utf-8")
    (root / "src/smart_hub.cpp").write_text(hub, encoding="utf-8")


def validate() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-stop-") as tmp:
        repo = Path(tmp)
        prepare_repo(repo, synthetic_hub())

        patcher.apply(repo)
        patcher.apply(repo)
        text = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8")

        required = (
            "longPress",
            "workshopPlatformDispatchPrinterCommand(slot,workshop::platform::PrinterCommand::Stop,true)",
            "workshop::platform::CommandResult::Accepted",
            'setPrinterFeedback(3,"STOP SENT",1800)',
        )
        for needle in required:
            if needle not in text:
                fail(f"required guarded STOP marker missing: {needle}")

        if "requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)" in text:
            fail("legacy direct STOP transport call survived migration")
        if text.count("workshop::platform::PrinterCommand::Stop") != 1:
            fail("OS12 STOP dispatch must exist exactly once in physical UI")

    # Fail closed if the mature long-press guard disappears.
    with tempfile.TemporaryDirectory(prefix="os12-stop-no-guard-") as tmp:
        repo = Path(tmp)
        prepare_repo(
            repo,
            '#include "workshop_platform_bridge.h"\nvoid touch(){requestPrinterControlCommand(slot,PRINTER_CTRL_STOP);}\n',
        )
        try:
            patcher.apply(repo)
        except patcher.PatchError:
            pass
        else:
            fail("STOP migration accepted source without longPress guard")


def main() -> int:
    validate()
    print("Workshop OS 12 guarded STOP migration validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
