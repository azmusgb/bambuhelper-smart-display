#!/usr/bin/env python3
"""Migrate Home + Printer status reads to the Workshop OS 12 normalized state facade.

This is intentionally read-only. Rich Bambu telemetry (job name, AMS, alerts,
remaining time, light state) remains sourced from the existing Bambu runtime
until those fields have their own normalized contracts. Control dispatch is not
migrated in this slice.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




INCLUDE = '#include "workshop_platform_bridge.h"\n'
HOME_OLD = (
    '  (void)full; const int16_t W=tft.width(); const bool configured=isAnyPrinterConfigured(); '
    'const PrinterSlot* p=configured?&displayedPrinter():nullptr; const BambuState* s=p?&p->state:nullptr;\n'
)
HOME_NEW = (
    '  (void)full; const int16_t W=tft.width(); '
    'const bool configured=workshopPlatformState().configuredPrinterCount>0; '
    'const PrinterSlot* p=configured?&displayedPrinter():nullptr; const BambuState* s=p?&p->state:nullptr;\n'
)
HOME_STATE_OLD = (
    '  const bool paused=s&&s->gcodeStateId==GCODE_PAUSE; const bool printing=s&&s->printing; '
    'const bool online=s&&s->connected; const bool wifi=WiFi.status()==WL_CONNECTED; '
    'const bool alert=s&&uiHmsCount(*s)>0;\n'
)
HOME_STATE_NEW = (
    '  const uint8_t os12Slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0; '
    'const bool paused=configured&&workshopPlatformPrinterPaused(os12Slot); '
    'const bool printing=configured&&workshopPlatformPrinterPrinting(os12Slot); '
    'const bool online=configured&&workshopPlatformPrinterOnline(os12Slot); '
    'const bool wifi=workshopPlatformWifiOnline(); const bool alert=s&&uiHmsCount(*s)>0;\n'
)
PRINTER_CONFIG_OLD = '  if(!isAnyPrinterConfigured()){'
PRINTER_CONFIG_NEW = '  if(workshopPlatformState().configuredPrinterCount==0){'
# UI13 product-finish intentionally changed disconnected printer status from red
# to warning orange. Match the final reconstructed UI13 source, not the older
# UI11 fragment, and preserve that semantic color in the normalized replacement.
PRINTER_STATE_OLD = (
    '  const PrinterSlot& p=displayedPrinter();const BambuState& s=p.state;'
    'const bool paused=s.gcodeStateId==GCODE_PAUSE;const bool active=s.printing||paused;'
    'const uint16_t sc=!s.connected?C10_ORANGE:(paused?C10_ORANGE:(s.printing?C10_ACCENT:C10_GREEN));'
    'const char* state=!s.connected?"Offline":(paused?"Paused":(s.printing?"Printing":"Ready"));\n'
)
PRINTER_STATE_NEW = (
    '  const PrinterSlot& p=displayedPrinter();const BambuState& s=p.state;'
    'const uint8_t os12Slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;'
    'const bool paused=workshopPlatformPrinterPaused(os12Slot);'
    'const bool printing=workshopPlatformPrinterPrinting(os12Slot);'
    'const bool active=workshopPlatformPrinterActive(os12Slot);'
    'const bool online=workshopPlatformPrinterOnline(os12Slot);'
    'const uint16_t sc=!online?C10_ORANGE:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN));'
    'const char* state=!online?"Offline":(paused?"Paused":(printing?"Printing":"Ready"));\n'
)


def apply(repo: Path) -> None:
    marker = repo / "include" / "smart_home_build.h"
    hub_path = repo / "src" / "smart_hub.cpp"
    if not marker.is_file() or not hub_path.is_file():
        raise PatchError("OS12 UI read migration requires reconstructed UI13 source")
    if "#define WORKSHOP_OS_V11_28_UI13 1" not in marker.read_text(encoding="utf-8"):
        raise PatchError("OS12 UI read migration requires v11.28 UI13")
    if not (repo / "include" / "workshop_platform_bridge.h").is_file():
        raise PatchError("OS12 platform bridge must be installed before UI read migration")

    text = hub_path.read_text(encoding="utf-8")
    if INCLUDE not in text:
        first_include = text.find("#include ")
        if first_include < 0:
            raise PatchError("smart_hub.cpp has no include anchor")
        text = text[:first_include] + INCLUDE + text[first_include:]

    text = replace_once(text, HOME_OLD, HOME_NEW, "Home configured read")
    text = replace_once(text, HOME_STATE_OLD, HOME_STATE_NEW, "Home normalized status reads")
    text = replace_once(text, PRINTER_CONFIG_OLD, PRINTER_CONFIG_NEW, "Printer configured read")
    text = replace_once(text, PRINTER_STATE_OLD, PRINTER_STATE_NEW, "Printer normalized status reads")

    if text.count(INCLUDE.strip()) != 1:
        raise PatchError("workshop_platform_bridge include must exist exactly once in smart_hub.cpp")
    hub_path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 Home + Printer status reads migrated to normalized facade")


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
