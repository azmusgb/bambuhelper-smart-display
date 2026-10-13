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
            shutil.copyfile(canonical_cpp, backend)
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

            configured = "http://10.0.0.16:8091/x2d/frame.jpg"
            patch.apply(repo, configured)

            backend_text = backend.read_text(encoding="utf-8")
            header_text = backend_h.read_text(encoding="utf-8")
            web_text = web.read_text(encoding="utf-8")
            self.assertIn(f'#define WORKSHOP_X2D_BRIDGE_URL "{configured}"', backend_text)
            self.assertIn("#include <HTTPClient.h>", backend_text)
            self.assertIn('kX2dBridgeSource[] = "x2d-bridge"', backend_text)
            self.assertIn("renderX2dBridgeFrame", backend_text)
            self.assertIn("X2dBridge", header_text)
            self.assertIn('media.playMjpeg("x2d-bridge", millis())', web_text)
            self.assertIn(
                'SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);',
                web_text,
            )
            self.assertNotIn('server.on("/os12/media/video/start-x2d-bridge"', web_text)

        self.assertEqual(canonical_cpp.read_text(encoding="utf-8"), before_cpp)
        self.assertEqual(canonical_h.read_text(encoding="utf-8"), before_h)

    def test_overlay_refuses_double_application(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src"
            include = repo / "include"
            src.mkdir()
            include.mkdir()
            shutil.copyfile(ROOT / "firmware/platform/media/ws350_media_backend.cpp", src / "ws350_media_backend.cpp")
            shutil.copyfile(ROOT / "firmware/platform/media/ws350_media_backend.h", include / "ws350_media_backend.h")
            (src / "web_server.cpp").write_text(
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
            with self.assertRaises(patch.PatchError):
                patch.apply(repo, configured)


if __name__ == "__main__":
    unittest.main()
