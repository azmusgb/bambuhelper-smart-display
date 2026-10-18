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
static bool g_wsVideoStartFailed=false;
static void wsVideoStart() {{
  workshop::media::MediaService& media=workshopMediaService();
  {polish.LAUNCH_OLD}
}}
static void route() {{
  const bool directVideoViewer = true;
}}
bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {{
  if (!g_cfg.enabled) return false;
  g_wsCaptureCompose = true;
  smartHubDraw(getScreenState(), true);
{polish.CAPTURE_OLD}  if (!g_hubFrame || !g_hubFrame->getBuffer()) return false;
  if (width) *width = (uint16_t)g_hubFrame->width();
  if (height) *height = (uint16_t)g_hubFrame->height();
  return true;
}}
bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {{
  if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;
  return true;
}}
'''

LAYOUT_FIXTURE = f'''static const RowSpec kSoundAlertsRows[] = {{
  {polish.ROW_LABEL_OLD},
}};
static const PageSpec kPages[] = {{
  {{PageId::VideoTest, PageId::SoundAlerts, 2, {polish.PAGE_TITLE_OLD} "Sound", "media-video", WS_ROWS(kVideoRows)}},
}};
'''


class ViewerPolishTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "src").mkdir()
        (root / "include").mkdir()
        (root / "src/smart_hub.cpp").write_text(SMART_HUB_FIXTURE, encoding="utf-8")
        (root / "include/workshop_more_layout.hpp").write_text(LAYOUT_FIXTURE, encoding="utf-8")
        return td, root

    def read(self, root: Path) -> dict[str, str]:
        return {
            "hub": (root / "src/smart_hub.cpp").read_text(encoding="utf-8"),
            "layout": (root / "include/workshop_more_layout.hpp").read_text(encoding="utf-8"),
        }

    def test_names_the_video_page_x2d_camera(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            layout = self.read(root)["layout"]
            self.assertIn('"X2D camera", PageId::VideoTest', layout)
            self.assertIn('PageLayout::Video, "X2D camera",', layout)
            self.assertNotIn('"Video test"', layout)

    def test_refused_launch_is_audible(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            hub = self.read(root)["hub"]
            self.assertNotIn(polish.LAUNCH_OLD, hub)
            self.assertIn(polish.LAUNCH_NEW, hub)
            self.assertIn("buzzerPlay(BUZZ_ERROR)", hub)

    def test_capture_redraws_camera_frame_offscreen(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            hub = self.read(root)["hub"]
            prepare = hub[hub.index("bool smartHubCapturePrepare"):hub.index("bool smartHubCaptureRgbRow")]
            self.assertEqual(hub.count(polish.CAPTURE_MARKER), 1)
            # The camera frame goes to g_hubFrame, never the panel, and the
            # panel pointer is restored.
            self.assertLess(prepare.index("tft_ptr = g_hubFrame;"), prepare.index("workshop::media::x2dRedrawLastFrame();"))
            self.assertLess(prepare.index("workshop::media::x2dRedrawLastFrame();"), prepare.index("tft_ptr = panel;"))
            self.assertIn("g_wsPage == workshop::ui::more::PageId::VideoTest", prepare)
            self.assertLess(hub.index("bool x2dRedrawLastFrame();"), hub.index("bool smartHubCapturePrepare"))
            # The canonical g_hubFrame row reader is kept.
            self.assertIn("if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;", hub)

    def test_polish_is_idempotent(self) -> None:
        td, root = self.make_repo()
        with td:
            polish.apply(root)
            first = self.read(root)
            polish.apply(root)
            self.assertEqual(first, self.read(root))

    def test_polish_failure_is_transactional(self) -> None:
        td, root = self.make_repo()
        with td:
            hub = root / "src/smart_hub.cpp"
            hub.write_text(hub.read_text(encoding="utf-8").replace(polish.CAPTURE_OLD, ""), encoding="utf-8")
            before = self.read(root)
            with self.assertRaises(Exception):
                polish.apply(root)
            self.assertEqual(before, self.read(root))

    def test_requires_bridge_overlay_first(self) -> None:
        td, root = self.make_repo()
        with td:
            hub = root / "src/smart_hub.cpp"
            hub.write_text(hub.read_text(encoding="utf-8").replace('"x2d-bridge"', '"demo-video"'), encoding="utf-8")
            with self.assertRaises(Exception):
                polish.apply(root)


if __name__ == "__main__":
    unittest.main()
