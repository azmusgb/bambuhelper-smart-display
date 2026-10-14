#!/usr/bin/env python3
"""Regression test for async X2D overlay on the real OS12 ownership stop block."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_module("x2d_async_base", ROOT / "apply_workshop_os12_x2d_async_fetch.py")
COMPAT = load_module("x2d_async_compat", ROOT / "apply_workshop_os12_x2d_async_fetch_compat.py")
TESTS = load_module("x2d_async_tests", ROOT / "scripts/test_x2d_async_fetch.py")


def ownership_fixture() -> str:
    legacy = "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n"
    ownership = (
        "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) {\n"
        "    cameraStop();\n"
        "    cameraSetMediaOwned(false);\n"
        "  }\n"
    )
    source = TESTS.fixture_source()
    assert legacy in source
    return source.replace(legacy, ownership, 1)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src").mkdir(parents=True)
        backend = repo / "src/ws350_media_backend.cpp"
        backend.write_text(ownership_fixture(), encoding="utf-8")

        COMPAT.apply(repo)
        text = backend.read_text(encoding="utf-8")

        assert BASE.ASYNC_MARKER in text
        assert COMPAT.OWNERSHIP_STOP in text
        assert COMPAT.X2D_STOP in text
        assert text.count("x2dStopFetchSession();") == 2  # helper definition + stop call

        render_start = text.index("void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs)")
        stop_start = text.index("bool Ws350MediaBackend::stopMedia()", render_start)
        renderer = text[render_start:stop_start]
        assert "HTTPClient" not in renderer
        assert "http.GET" not in renderer
        assert "getStreamPtr" not in renderer

        once = text
        COMPAT.apply(repo)
        twice = backend.read_text(encoding="utf-8")
        assert once == twice

    print("X2D async ownership-stop compatibility test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
