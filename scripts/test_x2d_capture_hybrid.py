#!/usr/bin/env python3
"""Focused tests for X2D hybrid framebuffer evidence capture."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hybrid = load_module(
    "x2d_capture_hybrid",
    ROOT / "apply_workshop_os12_x2d_capture_hybrid.py",
)

FIXTURE = r'''extern bool displayCapturePrepare(uint16_t* width, uint16_t* height);
extern bool displayCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen);
static bool directVideoViewer = false;
static int g_ui12SettingsView = 10;
static FakeSprite* g_hubFrame = nullptr;
static int16_t g_hubFrameW = 480;
static int16_t g_hubFrameH = 320;
static Config g_cfg;
static ScreenState getScreenState();
static void smartHubDraw(ScreenState, bool);
#define SCREEN_HUB_MORE 3

bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {
  if (!g_cfg.enabled) return false;
  smartHubDraw(getScreenState(), true);
  return displayCapturePrepare(width, height);
}

bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {
  return displayCaptureRgbRow(y, out, outLen);
}
'''


class HybridCaptureTests(unittest.TestCase):
    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "src"
        src.mkdir()
        (src / "smart_hub.cpp").write_text(FIXTURE, encoding="utf-8")
        return td, root

    def test_hybrid_capture_preserves_hub_sprite_for_ordinary_pages(self):
        td, root = self.make_repo()
        with td:
            hybrid.apply(root)
            text = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            self.assertIn(hybrid.CAPTURE_MARKER, text)
            self.assertIn("screen == SCREEN_HUB_MORE && g_ui12SettingsView == 12", text)
            self.assertIn("return displayCapturePrepare(width, height);", text)
            self.assertIn("g_hubFrameW <= 0 || g_hubFrameH <= 0", text)
            self.assertIn("return displayCaptureRgbRow(y, out, outLen);", text)
            self.assertIn("g_hubFrame->readPixel", text)

    def test_hybrid_capture_is_idempotent(self):
        td, root = self.make_repo()
        with td:
            hybrid.apply(root)
            first = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            hybrid.apply(root)
            second = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
