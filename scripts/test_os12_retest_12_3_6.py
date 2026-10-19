#!/usr/bin/env python3
"""Offline test of scripts/accept_os12_retest_12_3_6.py (no device needed).

A loopback fake WS350 answers the catalog, view, frame, identity and media
routes the re-test uses, with the 12.3.6 media status fields. The test runs
the whole re-test with scripted answers and checks that:
* it asks exactly the 12.3.5 failures again: controlsComfortable on the nine
  failed views, home's hierarchyClear, touchResponsiveness, and the four
  audio, microphone and recorder questions; nothing else;
* the media steps open media-lab (Sound & Alerts on its media rows);
* the objective checks pass on a healthy fake and fail when the fake drops
  audio (short clip, long wall time) or power-cycles the codec at idle;
* it refuses to run against the wrong source SHA.
"""
from __future__ import annotations

import builtins
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import accept_os12_portal_runtime as portal  # noqa: E402

os.environ.pop(portal.COOKIE_JAR_ENV, None)
import accept_os12_media_physical as media_physical  # noqa: E402
import accept_os12_retest_12_3_6 as retest  # noqa: E402

SHA = "a" * 40
CATALOG = [
    {"id": "home", "label": "Home", "group": "Primary"},
    {"id": "printer", "label": "Printer", "group": "Primary"},
    {"id": "printer-ams", "label": "Printer AMS", "group": "Primary"},
    {"id": "printer-control", "label": "Printer Control", "group": "Primary"},
    {"id": "workshop", "label": "Workshop", "group": "Primary"},
    {"id": "settings-printer-power", "label": "Printer & Power", "group": "More"},
    {"id": "hardware-auto-off", "label": "Auto power-off", "group": "More - sub-page"},
    {"id": "settings-sounds", "label": "Sound & Alerts", "group": "More"},
    {"id": "media-video", "label": "Video test", "group": "More - sub-page"},
    {"id": "system-update", "label": "Updates & About", "group": "More"},
    {"id": "system-diagnostics", "label": "Device health", "group": "More - sub-page"},
]
PPM = b"P6\n480 320\n255\n" + bytes(480 * 320 * 3)


class Fake(http.server.BaseHTTPRequestHandler):
    state: dict = {}
    shown: list[str] = []

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
        s = self.state
        # Timed sessions end on their own, like the firmware.
        if s["session"] != "Idle" and time.monotonic() >= s["until"]:
            if s["session"] == "Recording":
                s["recordingAvailable"] = True
            s["session"] = "Idle"
        body = {
            "session": s["session"], "error": "None",
            "speakerAvailable": True, "microphoneAvailable": True,
            "videoDecoderAvailable": True, "psramAvailable": True,
            "psramFreeBytes": 7_000_000, "volumePercent": 70, "muted": False,
            "microphoneLevelPercent": s["level"], "microphoneLastPeak": s["peak"],
            "recordingAvailable": s["recordingAvailable"], "audioUnderruns": 0, "droppedVideoFrames": 0,
            "audioCodecReady": s["codecReady"], "audioI2sReady": True, "audioPipelineRunning": s["codecReady"],
            "audioAmpEnabled": True, "audioCurrentFrequency": 1047 if s["session"] == "PlayingAudio" else 0,
            "audioTargetGain": 256, "audioCurrentGain": 256, "audioIdleQuiet": s["quiet"],
            "recordingBytes": s["recBytes"], "recordingTargetBytes": 320000, "recordingWallMs": s["recWall"],
            "recordingRxShortReads": 0, "playbackSlot": 1, "playbackDcOffset": -12, "playbackGainQ8": 1024,
        }
        self._json(body, code)

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
            return self._json({"runningVersion": "12.3.6", "runningSourceCommit": SHA})
        if self.path == "/os12/media/status":
            return self._media()
        self._json({}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        s = self.state
        if self.path == "/hub/show":
            page = form.get("page", [""])[0]
            self.shown.append(page)
            ok = page in {v["id"] for v in CATALOG} or page == "media-lab"
            if page == "media-video":
                s["session"], s["until"] = "PlayingVideo", time.monotonic() + 3600
            return self._json({"status": "ok"} if ok else {"status": "error"}, 200 if ok else 400)
        if self.path == "/os12/media/speaker-test":
            s["session"], s["until"] = "PlayingAudio", time.monotonic() + 0.4
            return self._media(202)
        if self.path == "/os12/media/microphone-sample":
            s["samples"] += 1
            s["peak"] = 100 if s["samples"] == 1 else 4000
            s["level"] = 23 if s["samples"] == 1 else 70
            return self._media(200)
        if self.path == "/os12/media/record/start":
            s["session"], s["until"] = "Recording", time.monotonic() + 0.3
            return self._media(202)
        if self.path == "/os12/media/record/play":
            s["session"], s["until"] = "PlayingRecording", time.monotonic() + 0.3
            return self._media(202)
        if self.path == "/os12/media/stop":
            s["session"] = "Idle"
            return self._media(200)
        self._json({}, 404)


def reset(**over) -> None:
    Fake.state = {
        "session": "Idle", "until": 0.0, "level": 0, "peak": 0, "samples": 0,
        "recordingAvailable": False, "codecReady": True, "quiet": True,
        "recBytes": 320000, "recWall": 5016,
    }
    Fake.state.update(over)
    Fake.shown.clear()


def run_retest(base: str, answer: str = "y", sha: str = SHA) -> tuple[int, dict, list[str]]:
    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return answer if prompt.endswith("[y/n/u]: ") else ""

    real_input, real_sleep = builtins.input, time.sleep
    builtins.input = fake_input
    time.sleep = lambda s: real_sleep(min(s, 0.35))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "retest.json"
            sys.argv = ["accept_os12_retest_12_3_6.py", "--base-url", base, "--expect-source-sha", sha,
                        "--output", str(out)]
            code = retest.main()
            evidence = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    finally:
        builtins.input, time.sleep = real_input, real_sleep
    return code, evidence, prompts


def main() -> int:
    retest.establish_portal_session = lambda client: "session-required"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        # Healthy 12.3.6 fake, every answer yes: PASS.
        reset()
        code, ev, prompts = run_retest(base)
        assert code == 0, (code, ev.get("failed"), ev.get("unknown"), ev.get("failure"))
        assert ev["passed"] is True and ev["completed"] is True
        questions = [p for p in prompts if p.endswith("[y/n/u]: ")]
        failed_views = [v for v, _ in retest.TOUCH_VIEWS]
        assert failed_views == ["home", "printer", "printer-ams", "workshop", "settings-printer-power",
                                "hardware-auto-off", "media-video", "system-update", "system-diagnostics"]
        # 9 comfort + home hierarchy + responsiveness + 4 audio = 15 questions, nothing else.
        assert len(questions) == 15, questions
        assert sum("comfortably finger-sized" in q for q in questions) == 9
        assert sum("information hierarchy" in q for q in questions) == 1
        assert sum("remain responsive across the full walk" in q for q in questions) == 1
        assert set(ev["observations"]) == {"microphone_level_responds", "native_media_lab_view_visible",
                                           "recording_intelligible", "audio_no_obvious_noise_or_instability"}
        assert set(ev["questions"]) == set(ev["observations"])
        assert ev["questions"]["microphone_level_responds"] == media_physical.QUESTIONS["microphone_level_responds"]
        for vid in failed_views:
            assert ev["views"][vid]["frame"]["width"] == 480, vid
        # The device-UI wording is unchanged from the 12.3.5 walk.
        ui_source = (HERE / "accept_os12_device_ui_physical.py").read_text(encoding="utf-8")
        assert 'f"Are visible controls on {label} comfortably finger-sized and clearly enabled/disabled?"' in ui_source
        assert retest.UI_COMFORT.format(label="X") == \
            "Are visible controls on X comfortably finger-sized and clearly enabled/disabled?"
        # Media steps open Sound & Alerts on its media rows.
        assert Fake.shown.count("media-lab") == 2, Fake.shown
        assert ev["recorderDiagnostics"]["recordingComplete"] is True
        assert ev["recorderDiagnostics"]["recordingNoDrops"] is True
        assert ev["idleWithoutPowerCycle"] is True and ev["microphonePeakIncreased"] is True

        # Dropped audio (short clip, long wall time) fails even with all "yes".
        reset(recBytes=250000, recWall=6400)
        code, ev, _ = run_retest(base)
        assert code == 1 and "objective.recordingComplete" in ev["failed"] and "objective.recordingNoDrops" in ev["failed"], ev["failed"]

        # Codec powered down at idle (the 12.3.5 behaviour) fails.
        reset(codecReady=False, quiet=False)
        code, ev, _ = run_retest(base)
        assert code == 1 and "objective.idleWithoutPowerCycle" in ev["failed"], ev["failed"]

        # A "no" anywhere fails.
        reset()
        code, ev, _ = run_retest(base, answer="n")
        assert code == 1 and "touchResponsiveness" in ev["failed"] and "recording_intelligible" in ev["failed"]

        # Wrong firmware: refused before any question.
        reset()
        code, ev, prompts = run_retest(base, sha="b" * 40)
        assert code == 1 and "does not match --expect-source-sha" in (ev.get("failure") or ""), ev.get("failure")
        assert not [p for p in prompts if p.endswith("[y/n/u]: ")]
    finally:
        server.shutdown()
    print("PASS: the 12.3.6 re-test asks exactly the 12.3.5 failures again, opens media-lab, and fails on "
          "dropped audio, codec power cycling or any 'no'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
