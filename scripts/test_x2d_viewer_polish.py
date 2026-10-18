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


SMART_HUB_FIXTURE = f'''static bool g_dirty=false;
static bool g_hubFramePrimed=false;
static int g_ui12SettingsView=10;

static void drawOs12Media() {{
  const auto& m=workshopMediaSnapshot();
  const bool videoPlaying=false;
  {polish.MEDIA_ROW_OLD}
}}

static bool gOs12VideoViewerPrimed=false;

static void drawOs12VideoViewer() {{
{polish.VIEWER_STATE_OLD}
  if(!videoActive) {{
    hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);
    return;
  }}
  if(!gOs12VideoViewerPrimed) {{
    uiDrawFit("Video Viewer",OS12V_INSET,9,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_TEXT,TFT_BLACK);
    uiDrawFit("Stop & Back returns to Media",OS12V_INSET,50,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    gOs12VideoViewerPrimed=true;
  }}
  hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);
{polish.VIEWER_ACTION_OLD}}}
static bool touch() {{
  workshop::media::MediaService& media=workshopMediaService();
  const workshop::media::SessionState state=media.snapshot().runtime.session;
{polish.BACK_OLD}
  {polish.LAUNCH_OLD}
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

class ViewerPolishTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "src"
        src.mkdir()
        (src / "smart_hub.cpp").write_text(SMART_HUB_FIXTURE, encoding="utf-8")
        return td, root

    def test_polish_installs_proven_viewer_and_capture_fixes(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            hub = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")

            self.assertIn('"X2D Camera"', hub)
            self.assertIn("const bool controlsChanged", hub)
            self.assertNotIn('"Stop & Back"', hub)
            self.assertNotIn("Stop & Back returns", hub)
            self.assertIn(polish.NEW_BACK_HINT, hub)
            self.assertGreaterEqual(hub.count('"Back",C10_ACCENT,true,false'), 2)
            self.assertIn("Transfer display ownership back to Media", hub)

    def test_refused_launch_is_visible_on_media_row(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            hub = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            self.assertNotIn(polish.LAUNCH_OLD, hub)
            self.assertIn(polish.LAUNCH_NEW, hub)
            self.assertIn("buzzerPlay(BUZZ_ERROR)", hub)
            # Declared before the Media renderer that reads it.
            self.assertLess(hub.index("static bool gOs12X2dLaunchFailed=false;"), hub.index("static void drawOs12Media()"))
            self.assertIn('"Check Wi-Fi and the Mac bridge"', hub)

    def test_capture_recomposes_viewer_offscreen(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            hub = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
            prepare = hub[hub.index("bool smartHubCapturePrepare"):hub.index("bool smartHubCaptureRgbRow")]
            self.assertEqual(hub.count(polish.CAPTURE_MARKER), 1)
            self.assertIn("screen == SCREEN_HUB_MORE && g_ui12SettingsView == 12", prepare)
            # Viewer chrome and the last camera frame go to g_hubFrame, never the panel,
            # and every piece of borrowed state is restored.
            self.assertLess(prepare.index("tft_ptr = g_hubFrame;"), prepare.index("drawOs12VideoViewer();"))
            self.assertLess(prepare.index("workshop::media::x2dRedrawLastFrame();"), prepare.index("tft_ptr = panel;"))
            for restored in ("gOs12VideoViewerPrimed = primed;", "g_dirty = dirty;"):
                self.assertIn(restored, prepare)
            self.assertIn("bool x2dRedrawLastFrame();", hub)
            # The canonical g_hubFrame row reader is kept.
            self.assertIn("if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;", hub)

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

    def test_polish_failure_is_transactional(self) -> None:
        td, root = self.make_repo()
        with td:
            hub = root / "src/smart_hub.cpp"
            hub.write_text(hub.read_text(encoding="utf-8").replace(polish.BACK_OLD, ""), encoding="utf-8")
            before = {
                p.name: p.read_text(encoding="utf-8")
                for p in (root / "src").iterdir()
            }
            with self.assertRaises(Exception):
                polish.apply(root)
            after = {
                p.name: p.read_text(encoding="utf-8")
                for p in (root / "src").iterdir()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
