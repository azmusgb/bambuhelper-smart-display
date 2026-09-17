#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/platform/media/media_service.h"
SOURCE = ROOT / "firmware/platform/media/media_service.cpp"
TEST = ROOT / "tests/workshop_os12_media_smoke.cpp"


def require(path: Path, needles: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"FAIL: {path}: missing {needle!r}")


def main() -> int:
    require(HEADER, [
        "class MediaService",
        "class HardwareBackend",
        "PlayingAudio",
        "Recording",
        "PlayingVideo",
        "Paused",
        "speakerAvailable",
        "microphoneAvailable",
        "videoDecoderAvailable",
        "psramAvailable",
        "audioUnderruns",
        "droppedVideoFrames",
    ])
    require(SOURCE, [
        "requireIdle()",
        "MediaError::Busy",
        "MediaError::OutOfMemory",
        "beginRecording",
        "beginMjpeg",
        "pauseVideo",
        "stopMedia",
    ])
    require(TEST, [
        "assert(!media.playMjpeg(\"clip.mjpg\", 4))",
        "MediaError::Busy",
        "MediaError::OutOfMemory",
        "SessionState::Fault",
    ])

    with tempfile.TemporaryDirectory(prefix="os12-media-") as td:
        binary = Path(td) / "media-smoke"
        cmd = [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(SOURCE), str(TEST), "-o", str(binary),
        ]
        subprocess.run(cmd, check=True, cwd=ROOT)
        subprocess.run([str(binary)], check=True, cwd=ROOT)

    print("PASS: OS12 media service state/policy smoke tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
