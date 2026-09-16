#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_ui_state_reads.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_ui_reads", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load OS12 UI read patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_hub() -> str:
    return '''#include "smart_hub.h"\n\nstatic void drawHome(bool full) {\n  (void)full; const int16_t W=tft.width(); const bool configured=isAnyPrinterConfigured(); const PrinterSlot* p=configured?&displayedPrinter():nullptr; const BambuState* s=p?&p->state:nullptr;\n  const bool paused=s&&s->gcodeStateId==GCODE_PAUSE; const bool printing=s&&s->printing; const bool online=s&&s->connected; const bool wifi=WiFi.status()==WL_CONNECTED; const bool alert=s&&uiHmsCount(*s)>0;\n}\n\nstatic void drawPrinter(bool full) {\n  if(!isAnyPrinterConfigured()){return;}\n  const PrinterSlot& p=displayedPrinter();const BambuState& s=p.state;const bool paused=s.gcodeStateId==GCODE_PAUSE;const bool active=s.printing||paused;const uint16_t sc=!s.connected?C10_RED:(paused?C10_ORANGE:(s.printing?C10_ACCENT:C10_GREEN));const char* state=!s.connected?"Offline":(paused?"Paused":(s.printing?"Printing":"Ready"));\n  (void)full;(void)W;(void)wifi;(void)sc;(void)state;(void)active;\n}\n'''


def validate_patcher() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-ui-reads-") as tmp:
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
            'workshopPlatformState().configuredPrinterCount>0',
            'workshopPlatformPrinterPaused(os12Slot)',
            'workshopPlatformPrinterPrinting(os12Slot)',
            'workshopPlatformPrinterOnline(os12Slot)',
            'workshopPlatformPrinterActive(os12Slot)',
            'workshopPlatformWifiOnline()',
        )
        for needle in required:
            if needle not in text:
                fail(f"patched UI missing normalized read: {needle}")

        forbidden = (
            'const bool configured=isAnyPrinterConfigured()',
            'const bool online=s&&s->connected',
            'const bool wifi=WiFi.status()==WL_CONNECTED',
            'const bool paused=s.gcodeStateId==GCODE_PAUSE;const bool active=s.printing||paused;',
        )
        for needle in forbidden:
            if needle in text:
                fail(f"legacy UI read survived migration: {needle}")

        if text.count('#include "workshop_platform_bridge.h"') != 1:
            fail("smart_hub bridge include is not idempotent")

        # Deliberately preserved in this slice: richer telemetry and command code
        # still use the existing Bambu runtime until separately normalized.
        if "displayedPrinter()" not in text or "BambuState" not in text:
            fail("migration overreached and removed legacy rich-telemetry access")


def main() -> int:
    validate_patcher()
    print("Workshop OS 12 Home + Printer normalized read migration validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
