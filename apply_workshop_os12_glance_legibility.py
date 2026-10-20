#!/usr/bin/env python3
"""Workshop OS 12.3.9: WS350 glanceability and legibility.

The drawing changes live in the design-system sources that the More and tabs
layers install (firmware/platform/ui/more_layout.hpp, tabs_layout.hpp,
more_pages.cppfrag, tabs_pages.cppfrag). This layer runs last in the
touchscreen chain, after apply_workshop_os12_review_hardening.py, and wires
in the parts that live outside those files.

- Printer > Camera has no control row in 12.3.9: the picture runs from the
  header to the tab bar (more::cameraVideoRect) and Pause/Resume is a header
  button. The media backend sizes every frame to the page's video area, so
  ws350VideoArea() asks the hub whether the page is in camera mode
  (smartHubCameraViewActive). The demo video test keeps its control row.

What the design-system sources change (validated by
scripts/validate_os12_glance_legibility.py):
- Home and Printer > Status while printing: the percentage in the 48 px
  numeric font, time left (19 px) and "Done 9:09 AM" (14 px) beside it, one
  layout for both cards (tabs::printCardLayout, host-tested).
- One done-at time for Home, Printer and the calm screen, fixed when the
  printer's estimate changes (tabs::doneAtEpoch, host-tested).
- Row values, stepper values, reasons, button labels and toasts in 14 px when
  they fit (10 px before); the calm status line in 19 px when it fits.
- Disabled-row reasons in the muted colour instead of amber; "Not set up" on
  Home's filament row; an off switch keeps a visible track; "No smart plug";
  "35°C".
"""
from __future__ import annotations

import argparse
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_GLANCE_LEGIBILITY 1"
REVIEW_MARKER = "#define WORKSHOP_OS12_REVIEW_HARDENING 1"

AREA_OLD = """static void ws350VideoArea(int16_t& x, int16_t& y, int16_t& w, int16_t& h) {
  const workshop::ui::more::Rect r = workshop::ui::more::videoRect(
      workshop::ui::more::makeScreen(tft.width(), tft.height()), workshop::ui::more::PageId::VideoTest);
  x = r.x; y = r.y; w = r.w; h = r.h;
}
"""
AREA_NEW = """// 12.3.9: Printer > Camera has no control row, so its picture area runs to
// the tab bar; the hub says which layout is on screen.
static void ws350VideoArea(int16_t& x, int16_t& y, int16_t& w, int16_t& h) {
  const workshop::ui::more::Rect r = workshop::ui::more::videoRect(
      workshop::ui::more::makeScreen(tft.width(), tft.height()), workshop::ui::more::PageId::VideoTest,
      ::smartHubCameraViewActive());
  x = r.x; y = r.y; w = r.w; h = r.h;
}
"""

# Declared at file scope: the backend's functions live in workshop::media.
DECL_ANCHOR = '#include "workshop_more_layout.hpp"\n'
DECL_NEW = DECL_ANCHOR + """
// 12.3.9: whether the video page is shown as Printer > Camera (smart_hub.cpp).
extern bool smartHubCameraViewActive();
"""

HUB_ANCHOR = "bool smartHubShowPage(const char* pageName) {\n"
HUB_NEW = """// 12.3.9: whether the video page is shown as Printer > Camera (no control
// row; the media backend sizes the picture to more::cameraVideoRect).
bool smartHubCameraViewActive() { return wsCameraView(g_wsPage); }

""" + HUB_ANCHOR


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if REVIEW_MARKER not in build:
        raise PatchError("the 12.3.9 layer runs after apply_workshop_os12_review_hardening.py")
    if BUILD_MARKER in build:
        raise PatchError("the 12.3.9 layer is already applied")
    hub_path = repo / "src" / "smart_hub.cpp"
    backend_path = repo / "src" / "ws350_media_backend.cpp"
    hub = load(hub_path)
    backend = load(backend_path)
    for needle, label in (
        ("static bool wsCameraView(wsm::PageId id)", "12.3.9 More pages (more_pages.cppfrag)"),
        ("static void wtDrawRunningPrint(const wtl::PrintCardLayout& L, const WtPrint& w)", "12.3.9 tab pages (tabs_pages.cppfrag)"),
    ):
        if needle not in hub:
            raise PatchError(f"smart_hub.cpp lacks the {label}")
    hub = replace_once(hub, HUB_ANCHOR, HUB_NEW, "camera view query")
    backend = replace_once(backend, DECL_ANCHOR, DECL_NEW, "camera view declaration")
    backend = replace_once(backend, AREA_OLD, AREA_NEW, "camera video area")
    hub_path.write_text(hub, encoding="utf-8")
    backend_path.write_text(backend, encoding="utf-8")
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.3.9 glance and legibility installed: big print percentage, one done-at time, "
          "14 px values and toasts, muted not-set-up reasons, camera picture to the tab bar")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
