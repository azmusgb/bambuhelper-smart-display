#!/usr/bin/env python3
"""Focused tests for the reconstructed-source X2D viewer polish overlay."""
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


polish = load_module(
    "x2d_viewer_polish",
    ROOT / "apply_workshop_os12_x2d_viewer_polish.py",
)


SMART_HUB_FIXTURE = f'''static bool gOs12VideoViewerPrimed=false;
static bool g_dirty=false;
static bool g_hubFramePrimed=false;
static int g_ui12SettingsView=10;
static void drawMedia() {{
  const auto& m=workshopMediaSnapshot();
  const bool videoPlaying=false;
  {polish.MEDIA_ROW_OLD}
}}
static void drawOs12VideoViewer() {{
{polish.VIEWER_STATE_OLD}
  if(!videoActive) return;
  if(!gOs12VideoViewerPrimed) {{
    uiDrawFit("Video Viewer",OS12V_INSET,9,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_TEXT,TFT_BLACK);
    gOs12VideoViewerPrimed=true;
  }}
  hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);
{polish.VIEWER_ACTION_OLD}}}
static bool touch() {{
  workshop::media::MediaService& media=workshopMediaService();
  const workshop::media::SessionState state=media.snapshot().runtime.session;
{polish.BACK_OLD}
  if(media.playMjpeg("x2d-bridge",millis())) return true;
  return false;
}}
static void route() {{
  const bool directVideoViewer = true;
}}
bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {{
  if (!g_cfg.enabled) return false;
  smartHubDraw(getScreenState(), true);
  if (!g_hubFrame || !g_hubFrame->getBuffer()) return false;
  if (width) *width = (uint16_t)g_hubFrame->width();
  if (height) *height = (uint16_t)g_hubFrame->height();
  return true;
}}
bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {{
  if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;
  return true;
}}
'''

BACKEND_FIXTURE = f'''static const char kX2dBridgeSource[] = "x2d-bridge";
void renderX2dBridgeFrame(uint32_t nowMs) {{
  const int16_t viewportH = 270;
  const int16_t x = 0;
  const int16_t y = 0;
{polish.BACKEND_CLEAR}}}
'''

DISPLAY_FIXTURE = '''static FakeSprite _frame_sprite;
void flushFrame() {}
// Pass-through hook for any future board-level rotation constraints. All four
'''


class ViewerPolishTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "src"
        src.mkdir()
        (src / "ws350_media_backend.cpp").write_text(BACKEND_FIXTURE, encoding="utf-8")
        (src / "smart_hub.cpp").write_text(SMART_HUB_FIXTURE, encoding="utf-8")
        (src / "display_ui.cpp").write_text(DISPLAY_FIXTURE, encoding="utf-8")
        return td, root

    def test_polish_installs_proven_viewer_and_capture_fixes(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            backend = (root / "src/ws350_media_backend.cpp").read_text(encoding="utf-8")
            hub = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            display = (root / "src/display_ui.cpp").read_text(encoding="utf-8")

            self.assertNotIn("tft.fillRect(0, 0, tft.width(), viewportH, TFT_BLACK);", backend)
            self.assertIn("exact 480x270 viewport", backend)
            self.assertIn('"X2D Camera"', hub)
            self.assertIn("const bool controlsChanged", hub)
            self.assertNotIn('"Stop & Back"', hub)
            self.assertIn("Transfer display ownership back to Media", hub)
            self.assertIn("return displayCapturePrepare(width, height);", hub)
            self.assertIn("return displayCaptureRgbRow(y, out, outLen);", hub)
            self.assertIn("bool displayCapturePrepare", display)
            self.assertIn("_frame_sprite.readPixel", display)

    def test_polish_is_idempotent_for_partially_patched_physical_candidate(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            first = {
                p.name: p.read_text(encoding="utf-8")
                for p in (root / "src").iterdir()
            }
            polish.apply(root)
            second = {
                p.name: p.read_text(encoding="utf-8")
                for p in (root / "src").iterdir()
            }
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
