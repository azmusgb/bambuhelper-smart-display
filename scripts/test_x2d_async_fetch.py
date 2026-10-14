#!/usr/bin/env python3
"""Focused tests for the reconstructed-source X2D async fetch overlay."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PATCHER_PATH = ROOT / "apply_workshop_os12_x2d_async_fetch.py"
SPEC = importlib.util.spec_from_file_location("x2d_async_fetch", PATCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)


def fixture_source() -> str:
    return (
        '#include "ws350_media_backend.h"\n'
        '#include <cstring>\n'
        + PATCHER.ESP32_INCLUDE_OLD
        + '#define WORKSHOP_X2D_BRIDGE_URL "http://10.0.0.16:8091/x2d/frame.jpg"\n'
        + 'static const char kX2dBridgeSource[] = "x2d-bridge";\n'
        + 'static const uint32_t kVideoFrameIntervalMs = 200U;\n'
        + 'static const uint32_t kBridgeConnectTimeoutMs = 350U;\n'
        + 'static const uint32_t kBridgeReadTimeoutMs = 900U;\n'
        + 'static const size_t kBridgeMaxFrameBytes = 384U * 1024U;\n'
        + 'static const int16_t kBridgeCameraWidth = 480;\n'
        + PATCHER.ASYNC_INSERT_ANCHOR
        + '\n'
        + 'bool Ws350MediaBackend::beginMjpeg(const char* source) {\n'
        + '  if (false) {\n'
        + PATCHER.BEGIN_X2D_OLD
        + '    return false;\n'
        + '  }\n'
        + '  return next == VideoSource::X2dBridge;\n'
        + '}\n\n'
        + 'bool Ws350MediaBackend::pauseVideo(bool paused) {\n'
        + '  if (!videoRequested_) return false;\n'
        + '  videoPaused_ = paused;\n'
        + '  return true;\n'
        + '}\n\n'
        + 'void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs) {\n'
        + '  HTTPClient http;\n'
        + '  const int status = http.GET();\n'
        + '  WiFiClient* stream = http.getStreamPtr();\n'
        + '  (void)status; (void)stream; (void)nowMs;\n'
        + '  // The bridge already produces the exact 480x270 viewport. Avoid a\n'
        + '  tft.drawJpg(frame, static_cast<uint32_t>(received), x, y);\n'
        + '}\n\n'
        + 'bool Ws350MediaBackend::stopMedia() {\n'
        + '  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n'
        + '  videoRequested_ = false;\n'
        + '  return true;\n'
        + '}\n'
    )


def test_apply_moves_network_off_renderer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src").mkdir(parents=True)
        backend = repo / "src/ws350_media_backend.cpp"
        backend.write_text(fixture_source(), encoding="utf-8")

        PATCHER.apply(repo)
        text = backend.read_text(encoding="utf-8")

        assert PATCHER.ASYNC_MARKER in text
        assert "xTaskCreatePinnedToCore(" in text
        assert '"x2d-fetch"' in text
        assert "x2dBeginFetchSession()" in text
        assert "x2dStopFetchSession();" in text
        assert "x2dSetFetchEnabled(!paused, false);" in text
        assert "generation == gX2dFetchGeneration" in text
        assert "std::memcpy(gX2dPublishedFrame, gX2dFetchBuffer, received);" in text

        render_start = text.index("void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs)")
        stop_start = text.index("bool Ws350MediaBackend::stopMedia()", render_start)
        renderer = text[render_start:stop_start]
        assert "HTTPClient" not in renderer
        assert "http.GET" not in renderer
        assert "getStreamPtr" not in renderer
        assert "tft.drawJpg(gX2dPublishedFrame" in renderer

        # Applying twice must be safe and must not create another worker.
        once = text
        PATCHER.apply(repo)
        twice = backend.read_text(encoding="utf-8")
        assert once == twice
        assert twice.count(PATCHER.ASYNC_MARKER) == 1


def test_missing_polish_is_transactional() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src").mkdir(parents=True)
        backend = repo / "src/ws350_media_backend.cpp"
        original = fixture_source().replace(
            "The bridge already produces the exact 480x270 viewport",
            "unpolished renderer",
        )
        backend.write_text(original, encoding="utf-8")

        try:
            PATCHER.apply(repo)
        except Exception:
            pass
        else:
            raise AssertionError("patcher should reject a pre-polish renderer")

        assert backend.read_text(encoding="utf-8") == original


def main() -> int:
    test_apply_moves_network_off_renderer()
    test_missing_polish_is_transactional()
    print("X2D async fetch overlay tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
