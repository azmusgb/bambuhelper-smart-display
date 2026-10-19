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

MORE_HANDOFF = "  if(cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM||cur==SCREEN_HUB_CUSTOM)return wsMoreTouch(x,y,longPress);\n"
TABS_HANDOFF = (MORE_HANDOFF
                + "  // Home, Printer and Workshop own their touch too (tab bar included).\n"
                + "  if(cur==SCREEN_HUB_HOME)return wtHomeTouch(x,y);\n")

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
    print("Workshop OS 12.3 tabs installed: Home")


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
