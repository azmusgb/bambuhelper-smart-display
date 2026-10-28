#!/usr/bin/env python3
"""Expose the Bambu Studio X2D camera as a bounded LAN-only JPEG endpoint.

The bridge intentionally keeps Bambu authentication/session material local to the
Mac. It launches Bambu Studio's existing ``bambu_source`` helper, decodes the raw
H.264 stream with the installed FFmpeg, scales it (320 px wide by default), and retains only
the latest complete JPEG in memory. The WS350 polls a fixed endpoint such as:

    http://<mac-lan-ip>:8091/x2d/frame.jpg

Or, with ``--rtsp-url-file`` (for an always-on Linux box such as a Raspberry Pi),
FFmpeg reads the printer's own LAN stream, ``rtsps://bblp:<access code>@<printer>:322/streaming/live/1``,
which needs "LAN Only Liveview" turned on at the printer. No Studio, no cloud.
The URL file holds the access code, so it must be readable by its owner only.

No Bambu URL, access code, UID, or printer identifier is returned by the HTTP
server. This is an experimental physical-test bridge, not a public Internet
service. Bind it only on a trusted LAN/VPN.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import ssl
import struct
from typing import Optional
from urllib.parse import quote, urlsplit

DEFAULT_CAMERA_ROOT = Path.home() / "Library/Application Support/BambuStudio/cameratools"
DEFAULT_PLUGIN_ROOT = Path.home() / "Library/Application Support/BambuStudio/plugins"
DEFAULT_URL_FILE = DEFAULT_CAMERA_ROOT / "url.txt"
MAX_JPEG_BYTES = 384 * 1024
# A pipeline that has exited, or produced no frame for this long, is restarted.
STALL_SECONDS = 15.0
RESTART_BACKOFF_SECONDS = (2.0, 5.0, 15.0, 30.0, 60.0)


_CREDENTIALS = re.compile(rb"(rtsps?://)[^/@\s]*@")


def redact(line: bytes) -> bytes:
    """FFmpeg names its input in errors; never let the access code reach a log."""
    return _CREDENTIALS.sub(rb"\1***@", line)


def _forward_redacted(stream) -> None:
    for line in iter(stream.readline, b""):
        sys.stderr.buffer.write(redact(line))
        sys.stderr.flush()


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
        rtsp_url_file: Optional[Path] = None,
        latest_detect: Optional[LatestFrame] = None,
        detect_fps: int = 1,
    ) -> None:
        self.latest = latest
        self.latest_detect = latest_detect
        self.detect_fps = detect_fps
        self.camera_root = camera_root
        self.plugin_root = plugin_root
        self.url_file = url_file
        self.ffmpeg = ffmpeg
        self.fps = fps
        self.width = width
        self.rtsp_url_file = rtsp_url_file
        self._is_p1s = False
        self._p1s_sock: Optional[socket.socket] = None
        self.source: Optional[subprocess.Popen[bytes]] = None
        self.encoder: Optional[subprocess.Popen[bytes]] = None
        self._detect_r: Optional[int] = None
        self._detect_w: Optional[int] = None
        self.thread: Optional[threading.Thread] = None
        self.detect_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_error: Optional[str] = None
        self.restarts = 0

    def rtsp_url(self) -> str:
        """The printer's LAN stream URL from --rtsp-url-file (owner-only, rtsps://, rtsp://, or bambu://)."""
        assert self.rtsp_url_file is not None
        path = self.rtsp_url_file
        if not path.is_file():
            raise RuntimeError(f"missing RTSP URL file: {path}")
        if path.stat().st_mode & 0o077:
            raise RuntimeError(f"{path} must be readable by its owner only (chmod 600): it holds the access code")
        url = path.read_text(encoding="utf-8").strip()
        if not url.startswith(("rtsps://", "rtsp://", "bambu://")) or any(c.isspace() for c in url):
            raise RuntimeError(f"{path} must hold one rtsps:// or bambu:// URL")
        return url

    def validate(self) -> None:
        if self.fps < 1 or self.fps > 10:
            raise RuntimeError("--fps must be between 1 and 10")
        if self.width < 160 or self.width > 480 or self.width % 2:
            raise RuntimeError("--width must be an even value from 160 through 480")
        if self.rtsp_url_file is not None:
            self.rtsp_url()
            return
        source = self.camera_root / "bambu_source"
        dylib = self.plugin_root / "libBambuSource.dylib"
        for path, label in (
            (source, "bambu_source"),
            (dylib, "libBambuSource.dylib"),
            (self.url_file, "Bambu camera url.txt"),
        ):
            if not path.is_file():
                raise RuntimeError(f"missing {label}: {path}")

    def encoder_args(self, input_args: list[str], detect_pipe: Optional[int] = None) -> list[str]:
        if detect_pipe is None or self.latest_detect is None:
            return [
                self.ffmpeg, "-hide_banner", "-loglevel", "warning", *input_args, "-an",
                "-vf", f"fps={self.fps},scale={self.width}:-2:flags=fast_bilinear",
                "-c:v", "mjpeg", "-q:v", "5", "-f", "image2pipe", "pipe:1",
            ]
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "warning", *input_args, "-an",
            "-filter_complex",
            f"[0:v]split=2[v_disp][v_det];"
            f"[v_disp]fps={self.fps},scale={self.width}:-2:flags=fast_bilinear[out_disp];"
            f"[v_det]fps={self.detect_fps},crop=in_h:in_h:(in_w*0.16):0,scale=416:416:flags=fast_bilinear[out_det]",
            "-map", "[out_disp]", "-c:v", "mjpeg", "-q:v", "5", "-f", "image2pipe", "pipe:1",
            "-map", "[out_det]", "-c:v", "mjpeg", "-q:v", "5", "-f", "image2pipe", f"pipe:{detect_pipe}",
        ]

    def _read_p1s_frames(self) -> None:
        parsed = urlsplit(self.rtsp_url())
        host = parsed.hostname or "10.0.0.136"
        port = parsed.port or 6000
        user = parsed.username or "bblp"
        password = parsed.password or ""

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        payload = struct.pack("<IIII", 0x40, 0x3000, 0, 0)
        payload += user.encode("ascii").ljust(32, b"\x00")
        payload += password.encode("ascii").ljust(32, b"\x00")

        buffer = bytearray()
        while not self.stop_event.is_set():
            sock = None
            try:
                raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw.settimeout(10.0)
                sock = ctx.wrap_socket(raw, server_hostname=host)
                self._p1s_sock = sock
                sock.connect((host, port))
                sock.sendall(payload)
                while not self.stop_event.is_set():
                    chunk = sock.recv(32 * 1024)
                    if not chunk:
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
                                buffer.clear()
                            break
                        end += 2
                        frame = bytes(buffer[:end])
                        del buffer[:end]
                        self.latest.update(frame)
            except Exception as exc:
                self.last_error = f"P1S port 6000: {exc}"
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
                self._p1s_sock = None
            if not self.stop_event.is_set():
                time.sleep(3)

    def start(self) -> None:
        self.validate()
        self.stop_event = threading.Event()
        detect_pipe = None
        pass_fds = ()
        if self.latest_detect is not None:
            self._detect_r, self._detect_w = os.pipe()
            detect_pipe = self._detect_w
            pass_fds = (self._detect_w,)

        if self.rtsp_url_file is not None:
            url = self.rtsp_url()
            parsed = urlsplit(url)
            if parsed.port == 6000 or parsed.scheme in ("bambu", "tls"):
                if self._detect_w is not None:
                    os.close(self._detect_w)
                    self._detect_w = None
                if self._detect_r is not None:
                    os.close(self._detect_r)
                    self._detect_r = None
                self._is_p1s = True
                self.source = None
                self.encoder = None
                self.thread = threading.Thread(target=self._read_p1s_frames, name="x2d-p1s-reader", daemon=True)
                self.thread.start()
                return

            # One FFmpeg reads the printer's stream over TCP (the printer's certificate is self-signed).
            self.source = None
            self.encoder = subprocess.Popen(
                self.encoder_args(["-rtsp_transport", "tcp", "-timeout", "10000000", "-i", self.rtsp_url()], detect_pipe=detect_pipe),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=pass_fds,
                bufsize=0,
            )
            if self._detect_w is not None:
                os.close(self._detect_w)
                self._detect_w = None
            threading.Thread(target=_forward_redacted, args=(self.encoder.stderr,), name="x2d-ffmpeg-log", daemon=True).start()
            self.thread = threading.Thread(target=self._read_frames, name="x2d-jpeg-reader", daemon=True)
            self.thread.start()
            if self.latest_detect is not None and self._detect_r is not None:
                self.detect_thread = threading.Thread(target=self._read_detect_frames, name="x2d-detect-reader", daemon=True)
                self.detect_thread.start()
            return
        source_path = self.camera_root / "bambu_source"
        encoded_path = quote(str(self.url_file.resolve()), safe="/")
        camera_uri = f"bambu:///camera/{encoded_path}"

        source_cmd = [str(source_path), camera_uri]
        ffmpeg_cmd = self.encoder_args(["-fflags", "+genpts", "-f", "h264", "-r", "30", "-i", "pipe:0"], detect_pipe=detect_pipe)

        self.source = subprocess.Popen(
            source_cmd,
            cwd=self.plugin_root,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
        )
        if self.source.stdout is None:
            if self._detect_w is not None:
                os.close(self._detect_w)
                self._detect_w = None
            if self._detect_r is not None:
                os.close(self._detect_r)
                self._detect_r = None
            raise RuntimeError("bambu_source stdout pipe unavailable")

        self.encoder = subprocess.Popen(
            ffmpeg_cmd,
            stdin=self.source.stdout,
            stdout=subprocess.PIPE,
            stderr=None,
            pass_fds=pass_fds,
            bufsize=0,
        )
        self.source.stdout.close()
        if self._detect_w is not None:
            os.close(self._detect_w)
            self._detect_w = None
        if self.encoder.stdout is None:
            if self._detect_r is not None:
                os.close(self._detect_r)
                self._detect_r = None
            raise RuntimeError("FFmpeg stdout pipe unavailable")

        self.thread = threading.Thread(target=self._read_frames, name="x2d-jpeg-reader", daemon=True)
        self.thread.start()
        if self.latest_detect is not None and self._detect_r is not None:
            self.detect_thread = threading.Thread(target=self._read_detect_frames, name="x2d-detect-reader", daemon=True)
            self.detect_thread.start()

    def _read_detect_frames(self) -> None:
        if self._detect_r is None:
            return
        fd = self._detect_r
        buffer = bytearray()
        try:
            while not self.stop_event.is_set():
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
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
                            buffer.clear()
                        break
                    end += 2
                    frame = bytes(buffer[:end])
                    del buffer[:end]
                    if self.latest_detect is not None:
                        self.latest_detect.update(frame)
        except Exception:
            pass
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
            if self._detect_r == fd:
                self._detect_r = None

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
        if self._detect_r is not None:
            try:
                os.close(self._detect_r)
            except Exception:
                pass
            self._detect_r = None
        if self._detect_w is not None:
            try:
                os.close(self._detect_w)
            except Exception:
                pass
            self._detect_w = None
        if self._p1s_sock is not None:
            try:
                self._p1s_sock.close()
            except Exception:
                pass
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
        if self.detect_thread is not None:
            self.detect_thread.join(timeout=1)

    def running(self) -> bool:
        """True while both processes (or socket thread) and the frame reader are alive."""
        if self._is_p1s:
            return self.thread is not None and self.thread.is_alive()
        return (
            (self.rtsp_url_file is not None or (self.source is not None and self.source.poll() is None))
            and self.encoder is not None and self.encoder.poll() is None
            and self.thread is not None and self.thread.is_alive()
        )


def needs_restart(pipeline: CameraPipeline, latest: LatestFrame, started: float, now: float) -> Optional[str]:
    """Why the pipeline should be restarted, or None while it is healthy."""
    if not pipeline.running():
        return "camera pipeline exited"
    _, _, age = latest.snapshot()
    if now - started < STALL_SECONDS:
        return None
    if age is None or age > STALL_SECONDS:
        return f"no camera frame for {STALL_SECONDS:.0f} s"
    return None


def supervise(pipeline: CameraPipeline, latest: LatestFrame, stop: threading.Event) -> None:
    """Restart the camera pipeline when it exits or stalls.

    The printer only streams while Bambu Studio's live view is open, and
    bambu_source exits when the tunnel closes. Restarting re-reads url.txt, so
    reopening the live view in Studio is enough to bring frames back.
    """
    started = time.monotonic()
    failures = 0
    while not stop.wait(1.0):
        now = time.monotonic()
        reason = needs_restart(pipeline, latest, started, now)
        if reason is None:
            if latest.snapshot()[2] is not None and now - started >= STALL_SECONDS:
                failures = 0
            continue
        delay = RESTART_BACKOFF_SECONDS[min(failures, len(RESTART_BACKOFF_SECONDS) - 1)]
        sys.stderr.write(f"[bridge] {reason}; restarting in {delay:.0f} s\n")
        pipeline.stop()
        if stop.wait(delay):
            return
        failures += 1
        try:
            pipeline.start()
            pipeline.restarts += 1
        except Exception as exc:  # url.txt missing while Studio is closed, etc.
            pipeline.last_error = str(exc)
        started = time.monotonic()


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        latest: LatestFrame,
        pipeline: CameraPipeline,
        latest_detect: Optional[LatestFrame] = None,
    ):
        super().__init__(address, BridgeHandler)
        self.latest = latest
        self.latest_detect = latest_detect
        self.pipeline = pipeline
        self.started_monotonic = time.monotonic()


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer
    # Headers and body go out as separate writes. With Nagle on, the body waits
    # for the client's ACK of the headers, and the ESP32's delayed ACK turned
    # each ~25 ms fetch into ~340 ms (about 2.5 fps on the WS350).
    disable_nagle_algorithm = True

    def log_request(self, code: object = "-", size: object = "-") -> None:
        # The WS350 polls about 5 times a second; log only non-200 responses so
        # a long-running (launchd) bridge log stays small.
        if str(getattr(code, "value", code)) != "200":
            super().log_request(code, size)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[bridge-http] " + (fmt % args) + "\n")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/x2d/frame.jpg":
            self._frame(self.server.latest)
            return
        if path == "/x2d/detect.jpg":
            self._frame(self.server.latest_detect or self.server.latest)
            return
        if path == "/x2d/health.json":
            self._health()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _frame(self, target: LatestFrame) -> None:
        frame, sequence, age = target.snapshot()
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
        det_frame, det_seq, det_age = (
            self.server.latest_detect.snapshot() if self.server.latest_detect else (None, 0, None)
        )
        source = getattr(self.server.pipeline, "source", None)
        encoder = getattr(self.server.pipeline, "encoder", None)
        source_rc = source.poll() if source else None
        ffmpeg_rc = encoder.poll() if encoder else None
        payload = {
            "ok": bool(frame is not None and age is not None and age <= 3.0 and source_rc is None and ffmpeg_rc is None),
            "frameSequence": sequence,
            "frameAgeMs": None if age is None else round(age * 1000),
            "frameBytes": 0 if frame is None else len(frame),
            "detectSequence": det_seq,
            "detectAgeMs": None if det_age is None else round(det_age * 1000),
            "detectBytes": 0 if det_frame is None else len(det_frame),
            "sourceRunning": source_rc is None,
            "ffmpegRunning": ffmpeg_rc is None,
            "uptimeSeconds": round(time.monotonic() - self.server.started_monotonic),
            "lastError": getattr(self.server.pipeline, "last_error", None),
            "pipelineRestarts": getattr(self.server.pipeline, "restarts", 0),
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
    parser.add_argument("--width", type=int, default=384, help="JPEG width, even 160-480; default 384 (fills the WS350 12.3.9+ camera page)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable; default PATH ffmpeg")
    parser.add_argument("--camera-root", type=Path, default=DEFAULT_CAMERA_ROOT)
    parser.add_argument("--plugin-root", type=Path, default=DEFAULT_PLUGIN_ROOT)
    parser.add_argument("--url-file", type=Path, default=DEFAULT_URL_FILE)
    parser.add_argument("--rtsp-url-file", type=Path, default=None,
                        help="read the printer's LAN stream (rtsps://bblp:<code>@<ip>:322/streaming/live/1) from this "
                             "owner-only file instead of Bambu Studio's helper")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    latest = LatestFrame()
    latest_detect = LatestFrame()
    pipeline = CameraPipeline(
        latest=latest,
        camera_root=args.camera_root.expanduser(),
        plugin_root=args.plugin_root.expanduser(),
        url_file=args.url_file.expanduser(),
        ffmpeg=args.ffmpeg,
        fps=args.fps,
        width=args.width,
        rtsp_url_file=args.rtsp_url_file.expanduser() if args.rtsp_url_file else None,
        latest_detect=latest_detect,
    )
    pipeline.start()
    server = BridgeServer((args.bind, args.port), latest, pipeline, latest_detect=latest_detect)

    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    supervisor = threading.Thread(
        target=supervise, args=(pipeline, latest, stop_requested), name="x2d-supervisor", daemon=True
    )
    supervisor.start()

    print(f"X2D JPEG bridge listening on http://{args.bind}:{args.port}/x2d/frame.jpg")
    print(f"Failure detection crop: http://{args.bind}:{args.port}/x2d/detect.jpg")
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
