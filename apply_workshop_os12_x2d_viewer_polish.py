#!/usr/bin/env python3
"""Polish the reconstructed WS350 X2D viewer after the bridge overlay.

This follow-up overlay is intentionally reconstruction-only. It keeps the
canonical media backend transport-agnostic while applying the physical-device
fixes proven during X2D testing.

Since Workshop OS 12.1.3 the viewer is the More area's Video test page
(Sound & Alerts > Video test). It already has a header with Back, a
Pause/Resume row and the tab bar, Back hands display ownership back to the
frame buffer before stopping the session, and the chrome is only redrawn when
it changes. This overlay:

- names the row and page "X2D camera",
- makes a refused on-device start audible (the page already says so),
- makes /hub/frame.ppm capture the camera frame. The viewer draws straight to
  the panel, which is not readable on the WS350, so the capture composes the
  page into the idle g_hubFrame sprite and then redraws the last decoded
  camera frame into it.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError


ROW_LABEL_OLD = '{RowId::VideoTestNav, RowKind::Nav, "Video test", PageId::VideoTest}'
ROW_LABEL_NEW = '{RowId::VideoTestNav, RowKind::Nav, "X2D camera", PageId::VideoTest}'
PAGE_TITLE_OLD = 'PageLayout::Video, "Video test",'
PAGE_TITLE_NEW = 'PageLayout::Video, "X2D camera",'

LAUNCH_OLD = 'if(!media.playMjpeg("x2d-bridge",millis()))g_wsVideoStartFailed=true;'
LAUNCH_NEW = 'if(!media.playMjpeg("x2d-bridge",millis())){g_wsVideoStartFailed=true;buzzerPlay(BUZZ_ERROR);}'

CAPTURE_MARKER = "Redraw the last X2D camera frame into the capture"
CAPTURE_OLD = """  g_wsCaptureCompose = false;
  g_wsVideoChromeDrawn = false;
"""
CAPTURE_NEW = """  g_wsCaptureCompose = false;
  g_wsVideoChromeDrawn = false;
  if (getScreenState() == SCREEN_HUB_MORE && g_wsPage == workshop::ui::more::PageId::VideoTest &&
      g_hubFrame && g_hubFrame->getBuffer()) {
    // Redraw the last X2D camera frame into the capture (g_hubFrame only;
    // the physical panel is not touched).
    lgfx::LovyanGFX* const panel = tft_ptr;
    tft_ptr = g_hubFrame;
    workshop::media::x2dRedrawLastFrame();
    tft_ptr = panel;
    g_hubFramePrimed = false;
  }
"""
# 12.3.7 Printer > Camera: on this build the camera is the Mac bridge.
CAMERA_SOURCE_OLD = 'static const char kWsCameraSource[] = "printer-camera";'
CAMERA_SOURCE_NEW = 'static const char kWsCameraSource[] = "x2d-bridge";'
CAMERA_HINT_OLD = '"The printer needs LAN mode and its access code."'
CAMERA_HINT_NEW = '"Open the X2D Live View in Bambu Studio on the Mac."'

CAPTURE_DECLARATION = "namespace workshop { namespace media { bool x2dRedrawLastFrame(); } }\n\n"
CAPTURE_SIGNATURE = "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {"


def replace_once_or_verified(text: str, old: str, new: str, marker: str, label: str) -> str:
    if marker in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_smart_hub(hub: str) -> str:
    if 'media.playMjpeg("x2d-bridge",millis())' not in hub or "directVideoViewer" not in hub:
        raise PatchError("X2D bridge overlay must be applied before viewer polish")
    if "smartHubCapturePrepare" not in hub or "smartHubCaptureRgbRow" not in hub:
        raise PatchError("visual capture support must be reconstructed before X2D viewer polish")
    hub = replace_once_or_verified(hub, LAUNCH_OLD, LAUNCH_NEW, "buzzerPlay(BUZZ_ERROR);}", "launch failure feedback")
    if "g_wsCameraMode" in hub:  # trees with Printer > Camera (12.3.7+)
        hub = replace_once_or_verified(hub, CAMERA_SOURCE_OLD, CAMERA_SOURCE_NEW, CAMERA_SOURCE_NEW, "camera source")
        hub = replace_once_or_verified(hub, CAMERA_HINT_OLD, CAMERA_HINT_NEW, CAMERA_HINT_NEW, "camera hint")
    hub = replace_once_or_verified(hub, CAPTURE_OLD, CAPTURE_NEW, CAPTURE_MARKER, "capture camera frame")
    hub = replace_once_or_verified(hub, CAPTURE_SIGNATURE, CAPTURE_DECLARATION + CAPTURE_SIGNATURE,
                                   "bool x2dRedrawLastFrame();", "capture frame declaration")
    return hub


def patch_layout(layout: str) -> str:
    layout = replace_once_or_verified(layout, ROW_LABEL_OLD, ROW_LABEL_NEW, ROW_LABEL_NEW, "Video test row label")
    layout = replace_once_or_verified(layout, PAGE_TITLE_OLD, PAGE_TITLE_NEW, PAGE_TITLE_NEW, "Video test page title")
    return layout


def apply(repo: Path) -> None:
    smart_hub = repo / "src/smart_hub.cpp"
    layout = repo / "include/workshop_more_layout.hpp"
    for path in (smart_hub, layout):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")

    # Every transformation is staged in memory; files are written only after
    # all anchors validate so a late mismatch cannot leave a half-patched tree.
    hub_text = patch_smart_hub(smart_hub.read_text(encoding="utf-8"))
    layout_text = patch_layout(layout.read_text(encoding="utf-8"))
    smart_hub.write_text(hub_text, encoding="utf-8")
    layout.write_text(layout_text, encoding="utf-8")

    print("Workshop OS 12 X2D viewer polish installed")
    print("Framebuffer capture redraws the last X2D camera frame into g_hubFrame")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
