#!/usr/bin/env python3
"""WS350 Home, Printer and Workshop tabs on the More design system (12.3.x).

Owning patch for the three main tabs. It runs last, after
apply_workshop_os12_more_overhaul.py, whose layout, row drawing and pages it
builds on, and owns whole functions rather than editing lines inside them.

- ``firmware/platform/ui/tabs_layout.hpp`` (views, items and geometry) is
  installed as ``include/workshop_tabs_layout.hpp``; the host test
  tests/workshop_os12_tabs_layout_smoke.cpp checks it in both orientations.
- ``firmware/platform/ui/tabs_pages.cppfrag`` (drawing, live values and touch)
  is inserted at the end of smart_hub.cpp's anonymous namespace, after the
  More pages.
- 12.3.0, Home: drawHome hands Home to the new page; Home's touch goes through
  the shared hit test, and the old invisible Home zones (hubHomeRect) are
  deleted.
- 12.3.1, Printer: drawPrinter hands Status, AMS and Control to the new
  page and Printer's touch goes through the shared hit test. Stop keeps its
  hold guard (longPress, confirmation flag) and is sent only for a hold that
  started on the Stop button and stayed on it; the hold progress is drawn
  over the new button. The 12.0 Printer rectangles and widgets are deleted.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, replace_cpp_function  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_TABS_OVERHAUL 1"
MORE_MARKER = "#define WORKSHOP_OS12_MORE_OVERHAUL 1"
LAYOUT_SOURCE = Path("firmware") / "platform" / "ui" / "tabs_layout.hpp"
LAYOUT_TARGET = Path("include") / "workshop_tabs_layout.hpp"
PAGES_SOURCE = Path("firmware") / "platform" / "ui" / "tabs_pages.cppfrag"

OLD_INCLUDE = '#include "workshop_more_layout.hpp"\n'
NEW_INCLUDE = '#include "workshop_more_layout.hpp"\n#include "workshop_tabs_layout.hpp"\n#include "hms_lookup.h"\n'

NAMESPACE_END = "\n} // namespace\n"

DRAW_HOME_SIGNATURE = "static void drawHome(bool full)"
DRAW_HOME = """static void wtDrawHome(bool full);
static void drawHome(bool full) {
  wtDrawHome(full);
}
"""

# The 12.0 Home zones did not match the cards they sat on.
HOME_RECT_SIGNATURE = "static HubRect hubHomeRect(uint8_t i)"

DRAW_PRINTER_SIGNATURE = "static void drawPrinter(bool full)"
DRAW_PRINTER = """static void wtDrawPrinter(bool full);
static void drawPrinter(bool full) {
  wtDrawPrinter(full);
}
"""

# 12.0 Printer geometry and widgets, replaced by the shared layout.
REPLACED_PRINTER = (
    "static HubRect hubPrinterActionRect(uint8_t i)",
    "static HubRect hubV1125PrinterModeRect(uint8_t i)",
    "static void hubV1125ModeTabs()",
    "static void hubV1125TelemetryColumn(const HubRect& r,const BambuState& s)",
    "static void hubV1125AmsSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index)",
)

OLD_PRINTER_TOUCH_START = "  if(cur==SCREEN_HUB_PRINTER){\n    for(uint8_t i=0;i<3;i++)if(hubV1125PrinterModeRect(i).contains(x,y))"
OLD_PRINTER_TOUCH_END = "  if(cur==SCREEN_HUB_WORKSHOP){"

HOLD_PRINTER_OLD = """  }else if(getScreenState()==SCREEN_HUB_PRINTER && g_printerMode==HUB_PRINTER_CONTROL && isAnyPrinterConfigured() && hubPrinterActionRect(3).contains(x,y)){
    BambuState& s=displayedPrinter().state;const bool paused=s.gcodeStateId==GCODE_PAUSE;
    if(s.connected&&(s.printing||paused)){HubRect r=hubPrinterActionRect(3);kind=3;bx=r.x;by=r.y;bw=r.w;bh=r.h;label="Keep Holding";}else{lastKind=0;lastSegments=255;return;}
  }else{"""
HOLD_PRINTER_NEW = """  }else if(getScreenState()==SCREEN_HUB_PRINTER){
    // Every sample of the press goes to the Stop tracker: Stop counts only
    // for a hold that started on the Stop button and never left it.
    wsm::Rect stop;
    if(wtStopHoldTrack(x,y,stop)){kind=3;bx=stop.x;by=stop.y;bw=stop.w;bh=stop.h;label="Keep holding";}else{lastKind=0;lastSegments=255;return;}
  }else{"""
HOLD_DRAW_OLD = "  if(kind==3)hubV1125Action(hr(bx,by,bw,bh),label,W25_DANGER,true,true);else hubRc2ButtonRef(bx,by,bw,bh,label,UI_ORANGE,true);\n"
HOLD_DRAW_NEW = ("  if(kind==3){wtDrawStopHold(wsm::makeRect(bx,by,bw,bh),segments);hubMarkFrameDirty();return;}\n"
                 "  hubRc2ButtonRef(bx,by,bw,bh,label,UI_ORANGE,true);\n")

MORE_HANDOFF = "  if(cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM||cur==SCREEN_HUB_CUSTOM)return wsMoreTouch(x,y,longPress);\n"
TABS_HANDOFF = (MORE_HANDOFF
                + "  // Home, Printer and Workshop own their touch too (tab bar included).\n"
                + "  if(cur==SCREEN_HUB_HOME)return wtHomeTouch(x,y);\n"
                + "  if(cur==SCREEN_HUB_PRINTER)return wtPrinterTouch(x,y,longPress);\n")

OLD_HOME_TOUCH = """  if(cur==SCREEN_HUB_HOME){
    if(g_ambientActive){g_ambientActive=false;g_dirty=true;return true;}
    if(hubHomeRect(0).contains(x,y)){setPage(SCREEN_HUB_WORKSHOP);return true;}
    if(hubHomeRect(1).contains(x,y)){setPage(SCREEN_HUB_PRINTER);return true;}
    if(hubHomeRect(2).contains(x,y)||hubHomeRect(3).contains(x,y)||hubHomeRect(4).contains(x,y)){wsOpen(wsm::PageId::Root);return true;}
    return true;
  }
"""


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def remove_span(text: str, start: str, end: str, label: str) -> str:
    """Delete from `start` up to (not including) `end`."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise PatchError(f"{label}: anchors not unique ({text.count(start)}, {text.count(end)})")
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + text[b:]


def install_layout(repo: Path, source_root: Path) -> None:
    source = source_root / LAYOUT_SOURCE
    if not source.is_file():
        raise PatchError(f"missing {source}")
    target = repo / LAYOUT_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def patch_smart_hub(repo: Path, source_root: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    fragment = load(source_root / PAGES_SOURCE)
    if "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)" not in text:
        raise PatchError("the tabs overhaul needs the More pages in smart_hub.cpp")
    text = replace_once(text, OLD_INCLUDE, NEW_INCLUDE, "layout include")
    text = replace_cpp_function(text, DRAW_HOME_SIGNATURE, DRAW_HOME, "drawHome")
    text = replace_cpp_function(text, HOME_RECT_SIGNATURE, "", "old Home zones")
    text = replace_cpp_function(text, DRAW_PRINTER_SIGNATURE, DRAW_PRINTER, "drawPrinter")
    text = remove_span(text, OLD_PRINTER_TOUCH_START, OLD_PRINTER_TOUCH_END, "old Printer touch")
    text = replace_once(text, HOLD_PRINTER_OLD, HOLD_PRINTER_NEW, "Stop hold tracking")
    text = replace_once(text, HOLD_DRAW_OLD, HOLD_DRAW_NEW, "Stop hold progress")
    for signature in REPLACED_PRINTER:
        text = replace_cpp_function(text, signature, "", f"replaced {signature}")
    text = replace_once(text, NAMESPACE_END, "\n" + fragment.rstrip() + "\n" + NAMESPACE_END, "tab pages")
    text = replace_once(text, MORE_HANDOFF, TABS_HANDOFF, "tab touch hand-off")
    text = replace_once(text, OLD_HOME_TOUCH, "", "old Home touch")
    path.write_text(text, encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if MORE_MARKER not in build:
        raise PatchError("the tabs overhaul runs after apply_workshop_os12_more_overhaul.py")
    if BUILD_MARKER in build:
        raise PatchError("the tabs overhaul is already applied")
    install_layout(repo, source_root)
    patch_smart_hub(repo, source_root)
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.3 tabs installed: Home, Printer")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
