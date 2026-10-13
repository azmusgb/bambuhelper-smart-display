#!/usr/bin/env python3
"""Polish the reconstructed WS350 X2D viewer after the bridge overlay.

This follow-up overlay is intentionally reconstruction-only. It keeps the
canonical media backend transport-agnostic while applying the physical-device
fixes proven during X2D testing:

- do not clear the 480x270 camera viewport to black before every JPEG decode,
- avoid redundant full-panel refresh requests from static viewer chrome,
- make Back an ordinary navigation action and hand display ownership back to
  Media before stopping the video session,
- present X2D Camera as a first-class Media feature,
- make /hub/frame.ppm read the root framebuffer so captures include direct
  video rendering rather than a stale Smart Hub backing sprite.
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


BACKEND_CLEAR = """  tft.fillRect(0, 0, tft.width(), viewportH, TFT_BLACK);\n  tft.drawJpg(frame, static_cast<uint32_t>(received), x, y);\n"""
BACKEND_DRAW = """  // The bridge already produces the exact 480x270 viewport. Avoid a\n  // separate black clear: a panel flush between clear and decode exposes a\n  // visible black frame even though the JPEG itself is healthy.\n  tft.drawJpg(frame, static_cast<uint32_t>(received), x, y);\n"""

MEDIA_ROW_OLD = 'hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Active":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"),m.capabilities.videoDecoderAvailable?"Tap row to open X2D camera":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));'
MEDIA_ROW_NEW = 'hubUi13InfoRow(hubUi13RowRect(2),"X2D Camera",m.runtime.session==workshop::media::SessionState::Paused?"Paused":(videoPlaying?"Live":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable")),m.capabilities.videoDecoderAvailable?"Tap to view live printer camera":"Camera unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));'

VIEWER_STATE_OLD = """  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;\n  const bool videoActive=m.runtime.session==workshop::media::SessionState::PlayingVideo||paused;\n"""
VIEWER_STATE_NEW = VIEWER_STATE_OLD + """\n  // Camera frames dirty the root framebuffer themselves. Viewer chrome only\n  // needs another full-panel refresh when its state actually changes.\n  const bool controlsChanged = !gOs12VideoViewerPrimed || g_dirty;\n"""

VIEWER_ACTION_OLD = """  hubV1125Action(hubUi13ActionRect(),paused?\"Resume\":\"Pause\",C10_ACCENT,true,false);\n  hubMarkFrameDirty();g_dirty=false;\n"""
VIEWER_ACTION_NEW = """  hubV1125Action(hubUi13ActionRect(),paused?\"Resume\":\"Pause\",C10_ACCENT,true,false);\n  if (controlsChanged) {\n    // The X2D viewer renders into the root framebuffer, not g_hubFrame.\n    markFrameDirty();\n  }\n  g_dirty=false;\n"""

BACK_OLD = """        if(hubUi13BackRect().contains(x,y)){\n          if(state!=workshop::media::SessionState::Idle)media.stop(millis());\n          gOs12VideoViewerPrimed=false;\n          g_ui12SettingsView=10;\n          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;\n        }\n"""
BACK_NEW = """        if(hubUi13BackRect().contains(x,y)){\n          // Transfer display ownership back to Media before stopping the\n          // session so no intermediate idle-video frame can be committed.\n          g_ui12SettingsView=10;\n          gOs12VideoViewerPrimed=false;\n          g_hubFramePrimed=false;\n          if(state!=workshop::media::SessionState::Idle)media.stop(millis());\n          buzzerPlay(BUZZ_CLICK);\n          g_dirty=true;\n          return true;\n        }\n"""

DISPLAY_CAPTURE_MARKER = "bool displayCapturePrepare(uint16_t* width, uint16_t* height)"
DISPLAY_CAPTURE_INSERT_ANCHOR = "// Pass-through hook for any future board-level rotation constraints."
DISPLAY_CAPTURE_CODE = r'''
// Root-framebuffer capture for physical/UI evidence. The WS350 Smart Hub uses
// a second backing sprite for ordinary pages, but direct video deliberately
// bypasses that compositor. Capture the root sprite so /hub/frame.ppm matches
// the actual frame that flushFrame() sends to the LCD for both cases.
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

SMART_CAPTURE_PREPARE = r'''extern bool displayCapturePrepare(uint16_t* width, uint16_t* height);
extern bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen);

bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {
  if (!g_cfg.enabled) return false;
  // Compose ordinary Hub pages into the root framebuffer first. Direct video
  // already owns that root framebuffer, so the same capture path works there.
  smartHubDraw(getScreenState(), true);
  return displayCapturePrepare(width, height);
}
'''

SMART_CAPTURE_ROW = r'''bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {
  return displayCaptureRgbRow(y, out, outLen);
}
'''


def replace_once_or_verified(text: str, old: str, new: str, marker: str, label: str) -> str:
    if marker in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_cpp_function(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise PatchError(f"{label}: function signature missing")
    brace = text.find("{", start + len(signature))
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    i = brace
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\r":
                    end += 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return text[:start] + replacement + text[end:]
        i += 1
    raise PatchError(f"{label}: closing brace missing")


def apply(repo: Path) -> None:
    backend = repo / "src/ws350_media_backend.cpp"
    smart_hub = repo / "src/smart_hub.cpp"
    display_ui = repo / "src/display_ui.cpp"
    for path in (backend, smart_hub, display_ui):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")

    # Stage every transformation in memory. Only write after all anchors and
    # final invariants validate so a late mismatch cannot leave a half-patched
    # physical candidate behind.
    backend_text = backend.read_text(encoding="utf-8")
    hub = smart_hub.read_text(encoding="utf-8")
    display = display_ui.read_text(encoding="utf-8")

    if "kX2dBridgeSource" not in backend_text or "renderX2dBridgeFrame" not in backend_text:
        raise PatchError("apply the X2D bridge overlay before viewer polish")
    backend_text = replace_once_or_verified(
        backend_text,
        BACKEND_CLEAR,
        BACKEND_DRAW,
        "The bridge already produces the exact 480x270 viewport",
        "X2D per-frame black clear",
    )

    if 'media.playMjpeg("x2d-bridge",millis())' not in hub or "directVideoViewer" not in hub:
        raise PatchError("X2D on-device viewer overlay must be present before polish")

    hub = replace_once_or_verified(
        hub,
        MEDIA_ROW_OLD,
        MEDIA_ROW_NEW,
        'hubUi13InfoRow(hubUi13RowRect(2),"X2D Camera",m.runtime.session==',
        "Media camera row",
    )
    hub = replace_once_or_verified(
        hub, VIEWER_STATE_OLD, VIEWER_STATE_NEW, "const bool controlsChanged", "viewer refresh state"
    )

    old_title = 'uiDrawFit("Video Viewer",OS12V_INSET,9,'
    new_title = 'uiDrawFit("X2D Camera",OS12V_INSET,9,'
    if old_title in hub:
        if hub.count(old_title) != 1:
            raise PatchError(f"active viewer title: expected one anchor, found {hub.count(old_title)}")
        hub = hub.replace(old_title, new_title, 1)
    elif new_title not in hub:
        raise PatchError("active viewer title: neither old nor polished title found")

    # Current reconstructed UI renders the same Stop & Back action in both the
    # inactive and active viewer branches. Both are ordinary navigation and both
    # must be neutral. Older fixtures had only one occurrence, so accept 1 or 2.
    old_back = 'hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);'
    new_back = 'hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);'
    old_back_count = hub.count(old_back)
    if old_back_count:
        if old_back_count not in (1, 2):
            raise PatchError(f"viewer Back action: expected one or two anchors, found {old_back_count}")
        hub = hub.replace(old_back, new_back)
    elif new_back not in hub:
        raise PatchError("viewer Back action: neither old nor polished action found")

    hub = replace_once_or_verified(
        hub, VIEWER_ACTION_OLD, VIEWER_ACTION_NEW, "if (controlsChanged)", "viewer redundant refresh"
    )
    hub = replace_once_or_verified(
        hub, BACK_OLD, BACK_NEW, "Transfer display ownership back to Media", "viewer Back handoff"
    )

    if "smartHubCapturePrepare" not in hub or "smartHubCaptureRgbRow" not in hub:
        raise PatchError("visual capture support must be reconstructed before X2D viewer polish")
    if "return displayCapturePrepare(width, height);" not in hub:
        hub = replace_cpp_function(
            hub,
            "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height)",
            SMART_CAPTURE_PREPARE,
            "Smart Hub capture prepare",
        )
    if "return displayCaptureRgbRow(y, out, outLen);" not in hub:
        hub = replace_cpp_function(
            hub,
            "bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen)",
            SMART_CAPTURE_ROW,
            "Smart Hub capture row",
        )

    if DISPLAY_CAPTURE_MARKER not in display:
        count = display.count(DISPLAY_CAPTURE_INSERT_ANCHOR)
        if count != 1:
            raise PatchError(f"root framebuffer capture insertion: expected one anchor, found {count}")
        display = display.replace(
            DISPLAY_CAPTURE_INSERT_ANCHOR,
            DISPLAY_CAPTURE_CODE + DISPLAY_CAPTURE_INSERT_ANCHOR,
            1,
        )

    checks = {
        "ws350_media_backend.cpp": (
            backend_text,
            [
                "The bridge already produces the exact 480x270 viewport",
                "tft.drawJpg(frame, static_cast<uint32_t>(received), x, y);",
            ],
        ),
        "smart_hub.cpp": (
            hub,
            [
                'hubUi13InfoRow(hubUi13RowRect(2),"X2D Camera",m.runtime.session==',
                new_title,
                "const bool controlsChanged",
                "Transfer display ownership back to Media",
                "return displayCapturePrepare(width, height);",
                "return displayCaptureRgbRow(y, out, outLen);",
            ],
        ),
        "display_ui.cpp": (
            display,
            [
                DISPLAY_CAPTURE_MARKER,
                "bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen)",
                "_frame_sprite.readPixel",
            ],
        ),
    }
    for name, (body, needles) in checks.items():
        for needle in needles:
            if needle not in body:
                raise PatchError(f"{name}: missing required marker {needle!r}")

    if old_back in hub:
        raise PatchError("smart_hub.cpp: destructive Stop & Back action remains after polish")

    backend.write_text(backend_text, encoding="utf-8")
    smart_hub.write_text(hub, encoding="utf-8")
    display_ui.write_text(display, encoding="utf-8")

    print("Workshop OS 12 X2D viewer polish installed")
    print("Root framebuffer capture enabled for direct-video screenshots")


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
