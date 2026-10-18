#!/usr/bin/env python3
"""Polish the reconstructed WS350 X2D viewer after the bridge overlay.

This follow-up overlay is intentionally reconstruction-only. It keeps the
canonical media backend transport-agnostic while applying the physical-device
fixes proven during X2D testing:

- avoid redundant full-panel refresh requests from static viewer chrome,
- make Back an ordinary navigation action and hand display ownership back to
  Media before stopping the video session,
- present X2D Camera as a first-class Media feature, with visible feedback
  when an on-device start is refused,
- make /hub/frame.ppm capture ordinary pages from g_hubFrame and the X2D
  viewer from the root framebuffer it renders into directly.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError, replace_cpp_function


LAUNCH_FLAG_ANCHOR = "\nstatic void drawOs12Media() {\n"
LAUNCH_FLAG = "\nstatic bool gOs12X2dLaunchFailed=false;  // Last on-device X2D start was refused.\n"

LAUNCH_OLD = 'if(!media.playMjpeg("x2d-bridge",millis()))g_ui12SettingsView=10;'
LAUNCH_NEW = (
    'if(media.playMjpeg("x2d-bridge",millis())){gOs12X2dLaunchFailed=false;}'
    'else{g_ui12SettingsView=10;gOs12X2dLaunchFailed=true;buzzerPlay(BUZZ_ERROR);}'
)

MEDIA_ROW_OLD = 'hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Active":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"),m.capabilities.videoDecoderAvailable?"Tap row to open X2D camera":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));'
MEDIA_ROW_MARKER = 'hubUi13InfoRow(hubUi13RowRect(2),"X2D Camera",'
MEDIA_ROW_NEW = (
    MEDIA_ROW_MARKER
    + 'm.runtime.session==workshop::media::SessionState::Paused?"Paused":(videoPlaying?"Live":(gOs12X2dLaunchFailed?"Not started":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"))),'
    + 'gOs12X2dLaunchFailed?"Check Wi-Fi and the Mac bridge":(m.capabilities.videoDecoderAvailable?"Tap to view live printer camera":"Camera unavailable"),'
    + 'videoPlaying?C10_GREEN:(gOs12X2dLaunchFailed?C10_ORANGE:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED)));'
)

VIEWER_STATE_OLD = """  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;\n  const bool videoActive=m.runtime.session==workshop::media::SessionState::PlayingVideo||paused;\n"""
VIEWER_STATE_NEW = VIEWER_STATE_OLD + """\n  // Camera frames dirty the root framebuffer themselves. Viewer chrome only\n  // needs another full-panel refresh when its state actually changes.\n  const bool controlsChanged = !gOs12VideoViewerPrimed || g_dirty;\n"""

VIEWER_ACTION_OLD = """  hubV1125Action(hubUi13ActionRect(),paused?\"Resume\":\"Pause\",C10_ACCENT,true,false);\n  hubMarkFrameDirty();g_dirty=false;\n"""
VIEWER_ACTION_NEW = """  hubV1125Action(hubUi13ActionRect(),paused?\"Resume\":\"Pause\",C10_ACCENT,true,false);\n  if (controlsChanged) {\n    // The X2D viewer renders into the root framebuffer, not g_hubFrame.\n    markFrameDirty();\n  }\n  g_dirty=false;\n"""

BACK_OLD = """        if(hubUi13BackRect().contains(x,y)){\n          if(state!=workshop::media::SessionState::Idle)media.stop(millis());\n          gOs12VideoViewerPrimed=false;\n          g_ui12SettingsView=10;\n          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;\n        }\n"""
BACK_NEW = """        if(hubUi13BackRect().contains(x,y)){\n          // Transfer display ownership back to Media before stopping the\n          // session so no intermediate idle-video frame can be committed.\n          g_ui12SettingsView=10;\n          gOs12VideoViewerPrimed=false;\n          g_hubFramePrimed=false;\n          if(state!=workshop::media::SessionState::Idle)media.stop(millis());\n          buzzerPlay(BUZZ_CLICK);\n          g_dirty=true;\n          return true;\n        }\n"""

OLD_TITLE = 'uiDrawFit("Video Viewer",OS12V_INSET,9,'
NEW_TITLE = 'uiDrawFit("X2D Camera",OS12V_INSET,9,'
OLD_BACK_HINT = '"Stop & Back returns to Media"'
NEW_BACK_HINT = '"Back returns to Media"'
OLD_BACK = 'hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);'
NEW_BACK = 'hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);'

DISPLAY_CAPTURE_MARKER = "bool displayCapturePrepare(uint16_t* width, uint16_t* height)"
DISPLAY_CAPTURE_INSERT_ANCHOR = "// Pass-through hook for any future board-level rotation constraints."
DISPLAY_CAPTURE_CODE = r'''
// Root-framebuffer capture for physical/UI evidence. The X2D viewer bypasses
// the Smart Hub g_hubFrame compositor and decodes straight into this sprite,
// which is exactly what flushFrame() sends to the LCD.
bool displayCapturePrepare(uint16_t* width, uint16_t* height) {
#if PANEL_REQUIRES_AXS_FRAME_SPRITE
  if (!_frame_sprite.getBuffer()) return false;
  if (width) *width = static_cast<uint16_t>(_frame_sprite.width());
  if (height) *height = static_cast<uint16_t>(_frame_sprite.height());
  return true;
#else
  (void)width;
  (void)height;
  return false;
#endif
}

bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {
#if PANEL_REQUIRES_AXS_FRAME_SPRITE
  if (!out || !_frame_sprite.getBuffer()) return false;
  const uint16_t w = static_cast<uint16_t>(_frame_sprite.width());
  const uint16_t h = static_cast<uint16_t>(_frame_sprite.height());
  if (y >= h || outLen < static_cast<size_t>(w) * 3U) return false;

  for (uint16_t x = 0; x < w; ++x) {
    const uint16_t c = _frame_sprite.readPixel(static_cast<int16_t>(x), static_cast<int16_t>(y));
    const uint8_t r5 = static_cast<uint8_t>((c >> 11) & 0x1FU);
    const uint8_t g6 = static_cast<uint8_t>((c >> 5) & 0x3FU);
    const uint8_t b5 = static_cast<uint8_t>(c & 0x1FU);
    out[static_cast<size_t>(x) * 3U + 0U] = static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
    out[static_cast<size_t>(x) * 3U + 1U] = static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
    out[static_cast<size_t>(x) * 3U + 2U] = static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
  }
  return true;
#else
  (void)y;
  (void)out;
  (void)outLen;
  return false;
#endif
}

'''

CAPTURE_MARKER = "static bool gX2dCaptureFromRoot = false;"
CAPTURE_PREPARE = r'''extern bool displayCapturePrepare(uint16_t* width, uint16_t* height);
extern bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen);

static bool gX2dCaptureFromRoot = false;

bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {
  if (!g_cfg.enabled) return false;

  const ScreenState screen = getScreenState();
  gX2dCaptureFromRoot =
      screen == SCREEN_HUB_MORE && g_ui12SettingsView == 12;

  // Force the requested view to be fully composed before streaming evidence.
  // The X2D viewer bypasses g_hubFrame; ordinary Hub pages do not.
  smartHubDraw(screen, true);

  if (gX2dCaptureFromRoot) {
    return displayCapturePrepare(width, height);
  }

  if (!g_hubFrame || !g_hubFrame->getBuffer() ||
      g_hubFrameW <= 0 || g_hubFrameH <= 0) {
    return false;
  }
  if (width) *width = static_cast<uint16_t>(g_hubFrameW);
  if (height) *height = static_cast<uint16_t>(g_hubFrameH);
  return true;
}
'''

CAPTURE_ROW = r'''bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {
  if (gX2dCaptureFromRoot) {
    return displayCaptureRgbRow(y, out, outLen);
  }

  if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;
  if (y >= static_cast<uint16_t>(g_hubFrameH)) return false;
  const size_t need = static_cast<size_t>(g_hubFrameW) * 3U;
  if (outLen < need) return false;

  for (int16_t x = 0; x < g_hubFrameW; ++x) {
    const uint16_t c = g_hubFrame->readPixel(x, static_cast<int16_t>(y));
    const uint8_t r5 = static_cast<uint8_t>((c >> 11) & 0x1FU);
    const uint8_t g6 = static_cast<uint8_t>((c >> 5) & 0x3FU);
    const uint8_t b5 = static_cast<uint8_t>(c & 0x1FU);
    out[static_cast<size_t>(x) * 3U + 0U] = static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
    out[static_cast<size_t>(x) * 3U + 1U] = static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
    out[static_cast<size_t>(x) * 3U + 2U] = static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
  }
  return true;
}
'''


def replace_once_or_verified(text: str, old: str, new: str, marker: str, label: str) -> str:
    if marker in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_all_or_verified(text: str, old: str, new: str, allowed: tuple[int, ...], label: str) -> str:
    count = text.count(old)
    if count:
        if count not in allowed:
            raise PatchError(f"{label}: expected {allowed} anchors, found {count}")
        return text.replace(old, new)
    if new not in text:
        raise PatchError(f"{label}: neither old nor polished text found")
    return text


def patch_smart_hub(hub: str) -> str:
    if 'media.playMjpeg("x2d-bridge",millis())' not in hub or "directVideoViewer" not in hub:
        raise PatchError("X2D bridge overlay must be applied before viewer polish")
    if "smartHubCapturePrepare" not in hub or "smartHubCaptureRgbRow" not in hub:
        raise PatchError("visual capture support must be reconstructed before X2D viewer polish")

    hub = replace_once_or_verified(hub, LAUNCH_FLAG_ANCHOR, LAUNCH_FLAG + LAUNCH_FLAG_ANCHOR[1:],
                                   "static bool gOs12X2dLaunchFailed", "launch failure flag")
    hub = replace_once_or_verified(hub, LAUNCH_OLD, LAUNCH_NEW, "gOs12X2dLaunchFailed=true;", "launch failure feedback")
    hub = replace_once_or_verified(hub, MEDIA_ROW_OLD, MEDIA_ROW_NEW, MEDIA_ROW_MARKER, "Media camera row")
    hub = replace_once_or_verified(hub, VIEWER_STATE_OLD, VIEWER_STATE_NEW, "const bool controlsChanged", "viewer refresh state")
    hub = replace_all_or_verified(hub, OLD_TITLE, NEW_TITLE, (1,), "active viewer title")
    hub = replace_all_or_verified(hub, OLD_BACK_HINT, NEW_BACK_HINT, (1,), "active viewer Back hint")
    # The reconstructed UI renders Stop & Back in both the inactive and active
    # viewer branches. Both are ordinary navigation and both must be neutral.
    hub = replace_all_or_verified(hub, OLD_BACK, NEW_BACK, (1, 2), "viewer Back action")
    hub = replace_once_or_verified(hub, VIEWER_ACTION_OLD, VIEWER_ACTION_NEW, "if (controlsChanged)", "viewer redundant refresh")
    hub = replace_once_or_verified(hub, BACK_OLD, BACK_NEW, "Transfer display ownership back to Media", "viewer Back handoff")

    if CAPTURE_MARKER not in hub:
        hub = replace_cpp_function(hub, "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height)",
                                   CAPTURE_PREPARE, "Smart Hub capture prepare")
        hub = replace_cpp_function(hub, "bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen)",
                                   CAPTURE_ROW, "Smart Hub capture row")

    if OLD_BACK in hub:
        raise PatchError("smart_hub.cpp: destructive Stop & Back action remains after polish")
    return hub


def patch_display(display: str) -> str:
    if DISPLAY_CAPTURE_MARKER in display:
        return display
    count = display.count(DISPLAY_CAPTURE_INSERT_ANCHOR)
    if count != 1:
        raise PatchError(f"root framebuffer capture insertion: expected one anchor, found {count}")
    return display.replace(DISPLAY_CAPTURE_INSERT_ANCHOR, DISPLAY_CAPTURE_CODE + DISPLAY_CAPTURE_INSERT_ANCHOR, 1)


def apply(repo: Path) -> None:
    smart_hub = repo / "src/smart_hub.cpp"
    display_ui = repo / "src/display_ui.cpp"
    for path in (smart_hub, display_ui):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")

    # Stage every transformation in memory. Only write after all anchors
    # validate so a late mismatch cannot leave a half-patched candidate behind.
    hub = patch_smart_hub(smart_hub.read_text(encoding="utf-8"))
    display = patch_display(display_ui.read_text(encoding="utf-8"))

    smart_hub.write_text(hub, encoding="utf-8")
    display_ui.write_text(display, encoding="utf-8")

    print("Workshop OS 12 X2D viewer polish installed")
    print("Framebuffer capture: ordinary Hub pages use g_hubFrame; the X2D viewer uses the root framebuffer")


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
