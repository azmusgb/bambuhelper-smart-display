#!/usr/bin/env python3
"""Focused tests for the experimental X2D -> WS350 JPEG bridge."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
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


bridge = load_module("x2d_camera_bridge", ROOT / "tools/x2d_camera_bridge.py")
patch = load_module("x2d_bridge_patch", ROOT / "apply_workshop_os12_x2d_bridge_camera.py")


LEGACY_STOP = "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n"


def prepare_reconstructed_backend(canonical_cpp: Path, destination: Path, ownership_stop: bool = True) -> None:
    """Reproduce the shared-camera-ownership state that precedes the X2D overlay."""
    text = canonical_cpp.read_text(encoding="utf-8")
    if ownership_stop:
        if text.count(LEGACY_STOP) != 1:
            raise RuntimeError("expected one canonical PrinterCamera stop line")
        text = text.replace(LEGACY_STOP, patch.STOP_ANCHORS[0], 1)

    old = """  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraBegin();
    if (!cameraActive()) return false;
    next = VideoSource::PrinterCamera;
  } else {
"""

    new = """  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraSetMediaOwned(true);
    cameraBegin();
    if (!cameraActive()) {
      cameraSetMediaOwned(false);
      return false;
    }
    next = VideoSource::PrinterCamera;
  } else {
"""

    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one canonical printer-camera branch, found {count}")

    destination.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_smart_hub_fixture(path: Path) -> None:
    path.write_text(
        'static int g_ui12SettingsView = 10;\n'
        'static void fixtureMedia() {\n'
        f'  const char* mediaHint = {patch.SMART_HUB_MEDIA_HINT_ANCHOR};\n'
        f'  {patch.SMART_HUB_DEMO_START_ANCHOR}\n'
        f'  const char* idleHint = {patch.SMART_HUB_IDLE_HINT_ANCHOR};\n'
        f'  const char* activeHint = {patch.SMART_HUB_ACTIVE_HINT_ANCHOR};\n'
        '}\n'
        'static void fixtureDraw(int screen) {\n'
        + patch.SMART_HUB_COMPOSITOR_ANCHOR
        + '}\n',
        encoding="utf-8",
    )


class LatestFrameTests(unittest.TestCase):
    def test_accepts_complete_jpeg(self) -> None:
        latest = bridge.LatestFrame()
        payload = b"\xff\xd8hello\xff\xd9"
        latest.update(payload)
        frame, sequence, age = latest.snapshot()
        self.assertEqual(frame, payload)
        self.assertEqual(sequence, 1)
        self.assertIsNotNone(age)

    def test_rejects_incomplete_jpeg(self) -> None:
        latest = bridge.LatestFrame()
        latest.update(b"not-a-jpeg")
        frame, sequence, age = latest.snapshot()
        self.assertIsNone(frame)
        self.assertEqual(sequence, 0)
        self.assertIsNone(age)

    def test_rejects_oversized_frame(self) -> None:
        latest = bridge.LatestFrame()
        payload = b"\xff\xd8" + (b"x" * bridge.MAX_JPEG_BYTES) + b"\xff\xd9"
        latest.update(payload)
        frame, sequence, _ = latest.snapshot()
        self.assertIsNone(frame)
        self.assertEqual(sequence, 0)


class BridgeUrlTests(unittest.TestCase):
    def test_accepts_private_literal_ip_and_fixed_path(self) -> None:
        self.assertEqual(
            patch.validate_bridge_url("http://10.0.0.16:8091/x2d/frame.jpg"),
            "http://10.0.0.16:8091/x2d/frame.jpg",
        )

    def test_rejects_public_ip(self) -> None:
        with self.assertRaises(patch.PatchError):
            patch.validate_bridge_url("http://8.8.8.8:8091/x2d/frame.jpg")

    def test_rejects_credentials_query_and_wrong_path(self) -> None:
        bad = (
            "http://user:pass@10.0.0.16:8091/x2d/frame.jpg",
            "http://10.0.0.16:8091/x2d/frame.jpg?token=secret",
            "http://10.0.0.16:8091/arbitrary.jpg",
        )
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(patch.PatchError):
                patch.validate_bridge_url(raw)


WEB_FIXTURE = (
    'static void sendWorkshopMediaStatus(int code = 200) {}\n'
    'static void handleWorkshopMediaVideoStart() {}\n'
    'static void handleWorkshopMediaVideoPause() {}\n'
    'void initWebServer() {\n'
    '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
    '}\n'
)
CONFIGURED = "http://10.0.0.16:8091/x2d/frame.jpg"


def make_repo(root: Path, ownership_stop: bool = True) -> None:
    (root / "src").mkdir()
    (root / "include").mkdir()
    prepare_reconstructed_backend(
        ROOT / "firmware/platform/media/ws350_media_backend.cpp",
        root / "src/ws350_media_backend.cpp",
        ownership_stop,
    )
    shutil.copyfile(ROOT / "firmware/platform/media/ws350_media_backend.h", root / "include/ws350_media_backend.h")
    (root / "src/web_server.cpp").write_text(WEB_FIXTURE, encoding="utf-8")
    write_smart_hub_fixture(root / "src/smart_hub.cpp")


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


def function_body(text: str, signature: str) -> str:
    start = text.index(signature)
    end = text.index("\n}\n", start)
    return text[start:end]


class AsyncWorkerTests(unittest.TestCase):
    def apply_fixture(self, ownership_stop: bool = True) -> str:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            make_repo(repo, ownership_stop)
            patch.apply(repo, CONFIGURED)
            return (repo / "src/ws350_media_backend.cpp").read_text(encoding="utf-8")

    def test_network_io_runs_only_on_worker(self) -> None:
        text = self.apply_fixture()
        self.assertEqual(text.count(patch.ASYNC_MARKER), 1)
        self.assertIn('xTaskCreatePinnedToCore(x2dFetchWorker, "x2d-fetch"', text)
        self.assertIn("#include <freertos/semphr.h>", text)
        renderer = function_body(text, "void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs)")
        for forbidden in ("HTTPClient", "http.GET", "getStreamPtr", "fillRect"):
            self.assertNotIn(forbidden, renderer)
        self.assertIn("tft.drawJpg(gX2dDisplayFrame", renderer)
        self.assertIn("gX2dDisplayBytes = frameBytes;", renderer)
        # The viewport fits the frame's real JPEG size, so the bridge may send viewer-sized frames.
        self.assertIn("x2dViewportOrigin(gX2dDisplayFrame, frameBytes, &x, &y)", renderer)
        self.assertIn("static bool x2dJpegSize(", text)
        # Evidence capture redraws the last frame offscreen; defined on every board.
        self.assertIn("bool x2dRedrawLastFrame() {", text)
        # The decode happens after the lock is released.
        self.assertLess(renderer.index("xSemaphoreGive"), renderer.index("tft.drawJpg"))

    def test_generation_is_revalidated_under_the_lock(self) -> None:
        text = self.apply_fixture()
        worker = function_body(text, "static void x2dFetchWorker(void*)")
        take = worker.index("xSemaphoreTake(gX2dFrameMutex")
        check = worker.index("generation == gX2dFetchGeneration")
        give = worker.index("xSemaphoreGive(gX2dFrameMutex)")
        self.assertLess(take, check)
        self.assertLess(check, give)
        setter = function_body(text, "static void x2dSetFetchEnabled(bool enabled, bool clearPublished)")
        self.assertLess(setter.index("xSemaphoreTake"), setter.index("++gX2dFetchGeneration"))
        self.assertLess(setter.index("gX2dPublishedBytes = 0U"), setter.index("xSemaphoreGive"))

    def test_session_lifecycle_gates_worker(self) -> None:
        text = self.apply_fixture()
        self.assertIn("if (!x2dBeginFetchSession()) return false;", text)
        pause = function_body(text, "bool Ws350MediaBackend::pauseVideo(bool paused)")
        self.assertIn("x2dSetFetchEnabled(!paused, true);", pause)
        stop = function_body(text, "bool Ws350MediaBackend::stopMedia()")
        self.assertIn(patch.STOP_ANCHORS[0] + patch.STOP_ADDITION, stop)

    def test_legacy_stop_form_is_accepted(self) -> None:
        text = self.apply_fixture(ownership_stop=False)
        self.assertIn(patch.STOP_ANCHORS[1] + patch.STOP_ADDITION, text)
        self.assertEqual(text.count("x2dStopFetchSession();"), 1)


class PatchIntegrationTests(unittest.TestCase):
    def test_overlay_patches_reconstructed_copy_not_canonical_assets(self) -> None:
        canonical_cpp = ROOT / "firmware/platform/media/ws350_media_backend.cpp"
        canonical_h = ROOT / "firmware/platform/media/ws350_media_backend.h"
        before_cpp = canonical_cpp.read_text(encoding="utf-8")
        before_h = canonical_h.read_text(encoding="utf-8")
        self.assertNotIn("HTTPClient", before_cpp)
        self.assertNotIn("kX2dBridgeSource", before_cpp)
        self.assertNotIn("X2dBridge", before_h)

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src"
            include = repo / "include"
            src.mkdir()
            include.mkdir()
            backend = src / "ws350_media_backend.cpp"
            backend_h = include / "ws350_media_backend.h"
            web = src / "web_server.cpp"
            smart_hub = src / "smart_hub.cpp"
            prepare_reconstructed_backend(canonical_cpp, backend)
            shutil.copyfile(canonical_h, backend_h)
            web.write_text(
                'static void sendWorkshopMediaStatus(int code = 200) {}\n'
                'static void handleWorkshopMediaVideoStart() {}\n'
                'static void handleWorkshopMediaVideoPause() {}\n'
                'void initWebServer() {\n'
                '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
                '}\n',
                encoding="utf-8",
            )
            write_smart_hub_fixture(smart_hub)

            configured = "http://10.0.0.16:8091/x2d/frame.jpg"
            patch.apply(repo, configured)

            backend_text = backend.read_text(encoding="utf-8")
            header_text = backend_h.read_text(encoding="utf-8")
            web_text = web.read_text(encoding="utf-8")
            smart_hub_text = smart_hub.read_text(encoding="utf-8")
            self.assertIn(f'#define WORKSHOP_X2D_BRIDGE_URL "{configured}"', backend_text)
            self.assertIn("#include <HTTPClient.h>", backend_text)
            self.assertIn('kX2dBridgeSource[] = "x2d-bridge"', backend_text)
            self.assertIn("renderX2dBridgeFrame", backend_text)
            self.assertIn("X2dBridge", header_text)
            self.assertIn('media.playMjpeg("x2d-bridge", millis())', web_text)
            self.assertIn('smartHubShowPage("media-video")', web_text)
            self.assertIn(
                'SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);',
                web_text,
            )
            self.assertNotIn('server.on("/os12/media/video/start-x2d-bridge"', web_text)
            self.assertIn(patch.SMART_HUB_X2D_START_REPLACEMENT, smart_hub_text)
            self.assertIn(patch.SMART_HUB_MEDIA_HINT_REPLACEMENT, smart_hub_text)
            self.assertIn(patch.SMART_HUB_ACTIVE_HINT_REPLACEMENT, smart_hub_text)
            self.assertIn("directVideoViewer", smart_hub_text)
            self.assertIn("const bool buffered = !directVideoViewer && hubEnsureFrame();", smart_hub_text)
            self.assertNotIn(patch.SMART_HUB_DEMO_START_ANCHOR, smart_hub_text)

        self.assertEqual(canonical_cpp.read_text(encoding="utf-8"), before_cpp)
        self.assertEqual(canonical_h.read_text(encoding="utf-8"), before_h)

    def test_overlay_refuses_double_application(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            make_repo(repo)
            patch.apply(repo, CONFIGURED)
            before = snapshot(repo)
            with self.assertRaises(patch.PatchError):
                patch.apply(repo, CONFIGURED)
            self.assertEqual(snapshot(repo), before)

    def test_late_anchor_failure_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            make_repo(repo)
            hub = repo / "src/smart_hub.cpp"
            hub.write_text(hub.read_text(encoding="utf-8").replace(patch.SMART_HUB_COMPOSITOR_ANCHOR, ""), encoding="utf-8")
            before = snapshot(repo)
            with self.assertRaises(patch.PatchError):
                patch.apply(repo, CONFIGURED)
            self.assertEqual(snapshot(repo), before)


if __name__ == "__main__":
    unittest.main()
