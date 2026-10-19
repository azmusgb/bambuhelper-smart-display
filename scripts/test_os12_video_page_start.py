#!/usr/bin/env python3
"""Host test for the Video test page start rule (no device needed).

Since 12.1.3 (#169) opening the Video test page (/hub/show page=media-video)
starts the built-in demo video by itself, so a second
POST /os12/media/video/start is refused with 409 Busy. Older builds open the
page Idle and need the POST.

A loopback fake WS350 implements both behaviours with the firmware's
requireIdle() rule. start_video_after_page_open() must:
* treat an already-playing page as the start ("page") and send no start POST;
* POST start exactly once when the page opened Idle ("api");
* fail closed when the page leaves the session in any other state;
and pause, resume and stop must still work after either path. The acceptance
scripts that open media-video must go through the helper, not POST start
straight after showing the page.
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import accept_os12_portal_runtime as portal  # noqa: E402

os.environ.pop(portal.COOKIE_JAR_ENV, None)
import accept_os12_media_runtime as media  # noqa: E402


class Fake(http.server.BaseHTTPRequestHandler):
    mode = "page-autostart"  # or "page-idle", "page-paused"
    session = ["Idle"]
    error = ["None"]
    seen: list[tuple[str, str]] = []

    def log_message(self, *a):
        pass

    def _status(self, code=200):
        body = {
            "session": self.session[0], "error": self.error[0],
            "speakerAvailable": True, "microphoneAvailable": True,
            "videoDecoderAvailable": True, "psramAvailable": True,
            "psramFreeBytes": 4_000_000, "volumePercent": 60, "muted": False,
            "microphoneLevelPercent": 0, "recordingAvailable": False,
            "audioUnderruns": 0, "droppedVideoFrames": 0,
        }
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _play(self) -> bool:
        # MediaService::playMjpeg -> requireIdle(): Busy unless Idle.
        if self.session[0] != "Idle":
            self.error[0] = "Busy"
            return False
        self.session[0] = "PlayingVideo"
        self.error[0] = "None"
        return True

    def do_GET(self):
        self.seen.append(("GET", self.path))
        if self.path == "/os12/media/status":
            return self._status()
        self._status(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        self.seen.append(("POST", self.path))
        if self.path == "/hub/show":
            page = form.get("page", [""])[0]
            if page == "media-video":
                if self.mode == "page-autostart":
                    self._play()  # wsOpen -> wsVideoStart
                elif self.mode == "page-paused":
                    self.session[0] = "Paused"
            elif self.session[0] in ("PlayingVideo", "Paused"):
                self.session[0] = "Idle"  # wsLeavePage -> wsVideoStop
            return self._status()
        if self.path == "/os12/media/video/start":
            return self._status(202 if self._play() else 409)
        if self.path == "/os12/media/video/pause":
            ok = self.session[0] == "PlayingVideo"
            if ok:
                self.session[0] = "Paused"
            return self._status(200 if ok else 409)
        if self.path == "/os12/media/video/resume":
            ok = self.session[0] == "Paused"
            if ok:
                self.session[0] = "PlayingVideo"
            return self._status(200 if ok else 409)
        if self.path == "/os12/media/stop":
            self.session[0] = "Idle"
            return self._status()
        self._status(404)


def reset(mode: str) -> None:
    Fake.mode = mode
    Fake.session[0] = "Idle"
    Fake.error[0] = "None"
    Fake.seen.clear()


def open_video_page(client: portal.Client) -> None:
    response = client.request("/hub/show", method="POST", form={"page": "media-video"})
    assert response.status == 200, response.status


def start_posts() -> int:
    return sum(1 for m, p in Fake.seen if m == "POST" and p == "/os12/media/video/start")


def run_lifecycle(client: portal.Client) -> None:
    pause = media.api(client, "/os12/media/video/pause", method="POST")
    assert pause["_http_status"] == 200 and pause["session"] == "Paused", pause
    resume = media.api(client, "/os12/media/video/resume", method="POST")
    assert resume["_http_status"] == 200 and resume["session"] == "PlayingVideo", resume
    stop = media.api(client, "/os12/media/stop", method="POST")
    assert stop["_http_status"] == 200 and stop["session"] == "Idle", stop
    final = media.status(client)
    assert final["session"] == "Idle" and final["error"] == "None", final


def check_scripts_use_helper() -> None:
    for name in ("accept_os12_unattended.py", "accept_os12_media_physical.py", "test_os12_video_viewer.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        assert "start_video_after_page_open(client)" in text, f"{name} does not use start_video_after_page_open"
        assert '"/os12/media/video/start"' not in text, f"{name} still POSTs video start after opening media-video"
    unattended = (HERE / "accept_os12_unattended.py").read_text(encoding="utf-8")
    assert 'evidence["media"]["videoStartedBy"]' in unattended
    physical = (HERE / "accept_os12_media_physical.py").read_text(encoding="utf-8")
    assert '"videoStartedBy": None' in physical and 'evidence["videoStartedBy"]' in physical


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    client = portal.Client(base)
    try:
        # The fake matches the device failure seen on 12.3.5: a naive start
        # after opening the auto-starting page is refused with Busy.
        reset("page-autostart")
        open_video_page(client)
        naive = media.api(client, "/os12/media/video/start", method="POST")
        assert naive["_http_status"] == 409 and naive["error"] == "Busy", naive

        # Page starts the video itself (12.1.3 and later).
        reset("page-autostart")
        open_video_page(client)
        payload, started_by = media.start_video_after_page_open(client)
        assert started_by == "page" and payload["session"] == "PlayingVideo", (started_by, payload)
        assert start_posts() == 0, Fake.seen
        run_lifecycle(client)

        # Page opens Idle (earlier builds): the helper POSTs start once.
        reset("page-idle")
        open_video_page(client)
        payload, started_by = media.start_video_after_page_open(client)
        assert started_by == "api" and payload["_http_status"] == 202, (started_by, payload)
        assert payload["session"] == "PlayingVideo", payload
        assert start_posts() == 1, Fake.seen
        run_lifecycle(client)

        # Any other state after opening the page fails closed.
        reset("page-paused")
        open_video_page(client)
        try:
            media.start_video_after_page_open(client)
        except portal.AcceptanceError as exc:
            assert "expected PlayingVideo or Idle" in str(exc), exc
            assert start_posts() == 0, Fake.seen
        else:
            raise SystemExit("FAIL: helper accepted a Paused session after opening Video test")

        check_scripts_use_helper()
    finally:
        server.shutdown()
    print("PASS: Video test acceptance accepts the page's own start, POSTs start only when the page opens Idle, "
          "and keeps pause/resume/stop checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
