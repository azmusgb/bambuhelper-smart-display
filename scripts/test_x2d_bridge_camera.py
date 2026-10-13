#!/usr/bin/env python3
"""Focused tests for the experimental X2D -> WS350 JPEG bridge."""
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


bridge = load_module("x2d_camera_bridge", ROOT / "tools/x2d_camera_bridge.py")
patch = load_module("x2d_bridge_patch", ROOT / "apply_workshop_os12_x2d_bridge_camera.py")


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


class PatchIntegrationTests(unittest.TestCase):
    def test_patch_keeps_source_fixed_and_route_authenticated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src"
            src.mkdir()
            backend = src / "ws350_media_backend.cpp"
            web = src / "web_server.cpp"
            backend.write_text(
                '#define WORKSHOP_X2D_BRIDGE_URL ""\n'
                'static const char kX2dBridgeSource[] = "x2d-bridge";\n'
                'void renderX2dBridgeFrame() {}\n',
                encoding="utf-8",
            )
            web.write_text(
                'static void sendWorkshopMediaStatus(int code = 200) {}\n'
                'static void handleWorkshopMediaVideoStart() {}\n'
                'static void handleWorkshopMediaVideoPause() {}\n'
                'void initWebServer() {\n'
                '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
                '}\n',
                encoding="utf-8",
            )

            configured = "http://10.0.0.16:8091/x2d/frame.jpg"
            patch.apply(repo, configured)

            backend_text = backend.read_text(encoding="utf-8")
            web_text = web.read_text(encoding="utf-8")
            self.assertIn(f'#define WORKSHOP_X2D_BRIDGE_URL "{configured}"', backend_text)
            self.assertIn('media.playMjpeg("x2d-bridge", millis())', web_text)
            self.assertIn(
                'SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);',
                web_text,
            )
            self.assertNotIn('server.on("/os12/media/video/start-x2d-bridge"', web_text)


if __name__ == "__main__":
    unittest.main()
