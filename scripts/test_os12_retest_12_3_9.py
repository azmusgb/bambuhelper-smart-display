#!/usr/bin/env python3
"""Offline test of scripts/accept_os12_retest_12_3_9.py (no device needed).

A loopback fake WS350 answers the catalog, view, frame, identity and media
routes the re-test uses. The test runs the whole re-test with scripted
answers and checks that:
* it opens exactly the views 12.3.9 changed (Home, Printer, AMS, Printer >
  Camera, Display, Printer & Power, Auto power-off, Updates & About), prints a
  "Try:" hint for each, and asks only the 12.3.9 questions plus the calm
  screen and touch-speed questions;
* it stops the camera after the Camera view (media left Idle);
* "u" on the calm screen alone still passes (it may not come on), any other
  "u" is pending and any "n" fails;
* it refuses to run against the wrong source SHA.
"""
from __future__ import annotations

import builtins
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import accept_os12_portal_runtime as portal  # noqa: E402

os.environ.pop(portal.COOKIE_JAR_ENV, None)
import accept_os12_retest_12_3_9 as retest  # noqa: E402

SHA = "c" * 40
CATALOG = [
    {"id": "home", "label": "Home", "group": "Primary"},
    {"id": "printer", "label": "Printer", "group": "Primary"},
    {"id": "printer-ams", "label": "Printer AMS", "group": "Primary"},
    {"id": "printer-control", "label": "Printer Control", "group": "Primary"},
    {"id": "workshop", "label": "Workshop", "group": "Primary"},
    {"id": "settings-printer-power", "label": "Printer & Power", "group": "More"},
    {"id": "hardware-auto-off", "label": "Auto power-off", "group": "More - sub-page"},
    {"id": "settings-display", "label": "Display", "group": "More"},
    {"id": "media-video", "label": "Video test", "group": "More - sub-page"},
    {"id": "system-update", "label": "Updates & About", "group": "More"},
]
PPM = b"P6\n480 320\n255\n" + bytes(480 * 320 * 3)


class Fake(http.server.BaseHTTPRequestHandler):
    state: dict = {}
    shown: list[str] = []
    posts: list[str] = []

    def log_message(self, *a):
        pass

    def _json(self, body: dict, code: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _media(self, code: int = 200) -> None:
        self._json({
            "session": self.state["session"], "error": "None",
            "speakerAvailable": True, "microphoneAvailable": True, "videoDecoderAvailable": True,
            "psramAvailable": True, "psramFreeBytes": 7_000_000, "volumePercent": 70, "muted": False,
            "microphoneLevelPercent": 0, "recordingAvailable": False, "audioUnderruns": 0, "droppedVideoFrames": 0,
        }, code)

    def do_GET(self):
        if self.path == "/hub/views":
            return self._json({"version": 3, "views": CATALOG})
        if self.path == "/hub/frame.ppm":
            self.send_response(200)
            self.send_header("Content-Type", "image/x-portable-pixmap")
            self.send_header("Content-Length", str(len(PPM)))
            self.end_headers()
            self.wfile.write(PPM)
            return
        if self.path == "/os12/update/status":
            return self._json({"runningVersion": "12.3.9", "runningSourceCommit": SHA})
        if self.path == "/os12/media/status":
            return self._media()
        self._json({}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        self.posts.append(self.path)
        if self.path == "/hub/show":
            page = form.get("page", [""])[0]
            self.shown.append(page)
            # printer-camera is a /hub/show id, not a catalog view (12.3.7).
            ok = page in {v["id"] for v in CATALOG} or page == "printer-camera"
            if page == "printer-camera":
                self.state["session"] = "PlayingVideo"
            return self._json({"status": "ok"} if ok else {"status": "error"}, 200 if ok else 400)
        if self.path == "/os12/media/stop":
            self.state["session"] = "Idle"
            return self._media(200)
        self._json({}, 404)


def reset() -> None:
    Fake.state = {"session": "Idle"}
    Fake.shown.clear()
    Fake.posts.clear()


def run_retest(base: str, answers, sha: str = SHA) -> tuple[int, dict, list[str], str]:
    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        if not prompt.endswith("[y/n/u]: "):
            return ""
        return answers(prompt)

    real_input = builtins.input
    builtins.input = fake_input
    out = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "retest.json"
            sys.argv = ["accept_os12_retest_12_3_9.py", "--base-url", base, "--expect-source-sha", sha, "--output", str(dest)]
            with redirect_stdout(out):
                code = retest.main()
            evidence = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {}
    finally:
        builtins.input = real_input
    return code, evidence, prompts, out.getvalue()


def main() -> int:
    retest.establish_portal_session = lambda client: "session-required"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    want_views = ["home", "printer", "printer-ams", "printer-camera", "settings-display", "settings-printer-power",
                  "hardware-auto-off", "system-update"]
    try:
        # Every answer yes: PASS, exactly the changed views and questions.
        reset()
        code, ev, prompts, out = run_retest(base, lambda p: "y")
        assert code == 0, (code, ev.get("failed"), ev.get("unknown"), ev.get("failure"))
        assert ev["passed"] is True and ev["completed"] is True
        assert [v for v, _, _, _ in retest.CHANGED_VIEWS] == want_views
        assert Fake.shown == want_views, Fake.shown
        questions = [p for p in prompts if p.endswith("[y/n/u]: ")]
        per_view = sum(len(q) for _, _, _, q in retest.CHANGED_VIEWS)
        assert len(questions) == per_view + 2, (len(questions), per_view)
        assert out.count("  Try: ") == len(want_views) + 1, out.count("  Try: ")
        assert set(ev["views"]) == set(want_views)
        assert ev["views"]["printer-camera"]["label"] == "Printer > Camera"
        for vid in want_views:
            assert ev["views"][vid]["frame"]["width"] == 480, vid
        assert set(ev["answers"]) == {"calmStatusReadable", "touchResponsiveness"}
        # The camera is stopped right after its view.
        assert Fake.state["session"] == "Idle"
        cam = Fake.posts.index("/os12/media/stop")
        assert Fake.posts[cam - 1] == "/hub/show"
        # Nothing that sends a printer command, and nothing about audio.
        for q in questions:
            assert "microphone" not in q.lower() and "recording" not in q.lower(), q
        assert not [p for p in Fake.posts if p not in ("/hub/show", "/os12/media/stop")], Fake.posts

        # "u" on the calm screen only: still PASS.
        reset()
        code, ev, _, _ = run_retest(base, lambda p: "u" if "calm idle screen" in p else "y")
        assert code == 0 and ev["passed"] is True, ev.get("unknown")

        # Any other "u" is pending.
        reset()
        code, ev, _, _ = run_retest(base, lambda p: "u" if "camera picture" in p else "y")
        assert code == 1 and ev["unknown"] == ["printer-camera.cameraLarger"], ev.get("unknown")

        # A "no" fails and names the item.
        reset()
        code, ev, _, _ = run_retest(base, lambda p: "n" if "done-at time is the same" in p or "same as on Home" in p else "y")
        assert code == 1 and ev["failed"] == ["printer.doneAtConsistent"], ev.get("failed")

        # Wrong firmware: refused before any question.
        reset()
        code, ev, prompts, _ = run_retest(base, lambda p: "y", sha="d" * 40)
        assert code == 1 and "does not match --expect-source-sha" in (ev.get("failure") or ""), ev.get("failure")
        assert not [p for p in prompts if p.endswith("[y/n/u]: ")]
    finally:
        server.shutdown()
    print("PASS: the 12.3.9 re-test opens only the changed views, gives a Try: hint for each, asks only about the "
          "12.3.9 changes, stops the camera, and fails on any 'no'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
