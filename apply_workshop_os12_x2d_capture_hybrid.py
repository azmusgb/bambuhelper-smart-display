#!/usr/bin/env python3
"""Use the correct framebuffer source for WS350 evidence capture.

Ordinary Smart Hub pages are composed in g_hubFrame and that capture path is
already proven on hardware. The X2D viewer deliberately bypasses g_hubFrame and
renders into the root framebuffer. This follow-up overlay therefore captures
ordinary pages from g_hubFrame and only switches to the root framebuffer while
the dedicated media-video viewer owns the display.
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


CAPTURE_MARKER = "static bool gX2dCaptureFromRoot = false;"

CAPTURE_PREPARE = r'''static bool gX2dCaptureFromRoot = false;

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
    smart_hub = repo / "src/smart_hub.cpp"
    if not smart_hub.is_file():
        raise PatchError(f"missing reconstructed source: {smart_hub}")

    hub = smart_hub.read_text(encoding="utf-8")
    if CAPTURE_MARKER in hub:
        print("Workshop OS 12 X2D hybrid framebuffer capture already installed")
        return

    required = (
        "extern bool displayCapturePrepare(uint16_t* width, uint16_t* height);",
        "extern bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen);",
        "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height)",
        "bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen)",
        "directVideoViewer",
    )
    for needle in required:
        if needle not in hub:
            raise PatchError(f"viewer polish prerequisite missing: {needle}")

    staged = replace_cpp_function(
        hub,
        "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height)",
        CAPTURE_PREPARE,
        "capture prepare",
    )
    staged = replace_cpp_function(
        staged,
        "bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen)",
        CAPTURE_ROW,
        "capture row",
    )

    checks = (
        CAPTURE_MARKER,
        "screen == SCREEN_HUB_MORE && g_ui12SettingsView == 12",
        "return displayCapturePrepare(width, height);",
        "g_hubFrameW <= 0 || g_hubFrameH <= 0",
        "return displayCaptureRgbRow(y, out, outLen);",
        "g_hubFrame->readPixel",
    )
    for needle in checks:
        if needle not in staged:
            raise PatchError(f"hybrid capture invariant missing: {needle}")

    smart_hub.write_text(staged, encoding="utf-8")
    print("Workshop OS 12 X2D hybrid framebuffer capture installed")
    print("Ordinary Hub pages use g_hubFrame; media-video uses the root framebuffer")


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
