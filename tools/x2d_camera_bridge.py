#!/usr/bin/env python3
"""Expose the Bambu Studio X2D camera as a bounded LAN-only JPEG endpoint.

The bridge intentionally keeps Bambu authentication/session material local to the
Mac. It launches Bambu Studio's existing ``bambu_source`` helper, decodes the raw
H.264 stream with the installed FFmpeg, scales it to 480x270, and retains only
the latest complete JPEG in memory. The WS350 polls a fixed endpoint such as:

    http://<mac-lan-ip>:8091/x2d/frame.jpg

No Bambu URL, access code, UID, or printer identifier is returned by the HTTP
server. This is an experimental physical-test bridge, not a public Internet
service. Bind it only on a trusted LAN/VPN.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import quote

DEFAULT_CAMERA_ROOT = Path.home() / "Library/Application Support/BambuStudio/cameratools"
DEFAULT_PLUGIN_ROOT = Path.home() / "Library/Application Support/BambuStudio/plugins"
DEFAULT_URL_FILE = DEFAULT_CAMERA_ROOT / "url.txt"
MAX_JPEG_BYTES = 384 * 1024


class LatestFrame:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[bytes] = None
        self._sequence = 0
        self._updated_monotonic = 0.0

    def update(self, frame: bytes) -> None:
        if len(frame) < 4 or len(frame) > MAX_JPEG_BYTES:
            return
        if not (frame.startswith(b"\xff\xd8") and frame.endswith(b"\xff\xd9")):
            return
        with self._lock:
            self._frame = frame
            self._sequence += 1
            self._updated_monotonic = time.monotonic()

    def snapshot(self) -> tuple[Optional[bytes], int, Optional[float]]:
        with self._lock:
            age = None
            if self._updated_monotonic:
                age = max(0.0, time.monotonic() - self._updated_monotonic)
            return self._frame, self._sequence, age


class CameraPipeline:
    def __init__(
        self,
        latest: LatestFrame,
        camera_root: Path,
        plugin_root: Path,
        url_file: Path,
        ffmpeg: str,
        fps: int,
        width: int,
    ) -> None:
        self.latest = latest
        self.camera_root = camera_root
        self.plugin_root = plugin_root
        self.url_file = url_file
        self.ffmpeg = ffmpeg
        self.fps = fps
        self.width = width
        self.source: Optional[subprocess.Popen[bytes]] = None
        self.encoder: Optional[subprocess.Popen[bytes]] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_error: Optional[str] = None

    def validate(self) -> None:
        source = self.camera_root / "bambu_source"
        dylib = self.plugin_root / "libBambuSource.dylib"
        for path, label in (
            (source, "bambu_source"),
            (dylib, "libBambuSource.dylib"),
            (self.url_file, "Bambu camera url.txt"),
        ):
            if not path.is_file():
                raise RuntimeError(f"missing {label}: {path}")
        if self.fps < 1 or self.fps > 10:
            raise RuntimeError("--fps must be between 1 and 10")
        if self.width < 160 or self.width > 480 or self.width % 2:
            raise RuntimeError("--width must be an even value from 160 through 480")

    def start(self) -> None:
        self.validate()
        source_path = self.camera_root / "bambu_source"
        encoded_path = quote(str(self.url_file.resolve()), safe="/")
        camera_uri = f"bambu:///camera/{encoded_path}"

        source_cmd = [str(source_path), camera_uri]
        ffmpeg_cmd = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "+genpts",
            "-f",
            "h264",
            "-r",
            "30",
            "-i",
            "pipe:0",
            "-an",
            "-vf",
            f"fps={self.fps},scale={self.width}:-2:flags=fast_bilinear",
            "-c:v",
            "mjpeg",
            "-q:v",
            "5",
            "-f",
            "image2pipe",
            "pipe:1",
        ]

        self.source = subprocess.Popen(
            source_cmd,
            cwd=self.plugin_root,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
        )
        if self.source.stdout is None:
            raise RuntimeError("bambu_source stdout pipe unavailable")

        self.encoder = subprocess.Popen(
            ffmpeg_cmd,
            stdin=self.source.stdout,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
        )
        self.source.stdout.close()
        if self.encoder.stdout is None:
            raise RuntimeError("FFmpeg stdout pipe unavailable")

        self.thread = threading.Thread(target=self._read_frames, name="x2d-jpeg-reader", daemon=True)
        self.thread.start()

    def _read_frames(self) -> None:
        assert self.encoder is not None and self.encoder.stdout is not None
        buffer = bytearray()
        try:
            while not self.stop_event.is_set():
                chunk = self.encoder.stdout.read(64 * 1024)
                if not chunk:
                    rc = self.encoder.poll()
                    if rc is not None and rc != 0:
                        self.last_error = f"FFmpeg exited with status {rc}"
                    break
                buffer.extend(chunk)

                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start < 0:
                        if len(buffer) > 2:
                            del buffer[:-2]
                        break
                    if start > 0:
                        del buffer[:start]
                    end = buffer.find(b"\xff\xd9", 2)
                    if end < 0:
                        if len(buffer) > MAX_JPEG_BYTES:
                            self.last_error = "JPEG frame exceeded bridge safety limit"
                            buffer.clear()
                        break
                    end += 2
                    frame = bytes(buffer[:end])
                    del buffer[:end]
                    self.latest.update(frame)
        except Exception as exc:  # Keep health endpoint useful after a pipeline fault.
            self.last_error = str(exc)

    def stop(self) -> None:
        self.stop_event.set()
        for process in (self.encoder, self.source):
            if process is not None and process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 2.0
        for process in (self.encoder, self.source):
            if process is None:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        if self.thread is not None:
            self.thread.join(timeout=1)


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], latest: LatestFrame, pipeline: CameraPipeline):
        super().__init__(address, BridgeHandler)
        self.latest = latest
        self.pipeline = pipeline
        self.started_monotonic = time.monotonic()


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer
    # Headers and body go out as separate writes. With Nagle on, the body waits
    # for the client's ACK of the headers, and the ESP32's delayed ACK turned
    # each ~25 ms fetch into ~340 ms (about 2.5 fps on the WS350).
    disable_nagle_algorithm = True

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[bridge-http] " + (fmt % args) + "\n")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] == "/x2d/frame.jpg":
            self._frame()
            return
        if self.path.split("?", 1)[0] == "/x2d/health.json":
            self._health()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _frame(self) -> None:
        frame, sequence, age = self.server.latest.snapshot()
        if frame is None or age is None or age > 3.0:
            self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Frame-Sequence", str(sequence))
        self.end_headers()
        try:
            self.wfile.write(frame)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _health(self) -> None:
        frame, sequence, age = self.server.latest.snapshot()
        source_rc = self.server.pipeline.source.poll() if self.server.pipeline.source else None
        ffmpeg_rc = self.server.pipeline.encoder.poll() if self.server.pipeline.encoder else None
        payload = {
            "ok": bool(frame is not None and age is not None and age <= 3.0 and source_rc is None and ffmpeg_rc is None),
            "frameSequence": sequence,
            "frameAgeMs": None if age is None else round(age * 1000),
            "frameBytes": 0 if frame is None else len(frame),
            "sourceRunning": source_rc is None,
            "ffmpegRunning": ffmpeg_rc is None,
            "uptimeSeconds": round(time.monotonic() - self.server.started_monotonic),
            "lastError": self.server.pipeline.last_error,
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(HTTPStatus.OK if payload["ok"] else HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bambu X2D -> WS350 latest-JPEG bridge")
    parser.add_argument("--bind", default="0.0.0.0", help="HTTP bind address; default 0.0.0.0")
    parser.add_argument("--port", type=int, default=8091, help="HTTP port; default 8091")
    parser.add_argument("--fps", type=int, default=5, help="JPEG production rate, 1-10; default 5")
    parser.add_argument("--width", type=int, default=320, help="JPEG width, even 160-480; default 320 (the WS350 viewer size)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable; default PATH ffmpeg")
    parser.add_argument("--camera-root", type=Path, default=DEFAULT_CAMERA_ROOT)
    parser.add_argument("--plugin-root", type=Path, default=DEFAULT_PLUGIN_ROOT)
    parser.add_argument("--url-file", type=Path, default=DEFAULT_URL_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    latest = LatestFrame()
    pipeline = CameraPipeline(
        latest=latest,
        camera_root=args.camera_root.expanduser(),
        plugin_root=args.plugin_root.expanduser(),
        url_file=args.url_file.expanduser(),
        ffmpeg=args.ffmpeg,
        fps=args.fps,
        width=args.width,
    )
    pipeline.start()
    server = BridgeServer((args.bind, args.port), latest, pipeline)

    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print(f"X2D JPEG bridge listening on http://{args.bind}:{args.port}/x2d/frame.jpg")
    print("Health: /x2d/health.json")
    print("LAN/VPN only; do not port-forward this service to the public Internet.")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        pipeline.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
