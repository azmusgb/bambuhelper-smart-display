#!/usr/bin/env python3
"""Soak the WS350 X2D viewer: media status at 1 Hz, a framebuffer capture every
10 s, pause/resume every 60 s. Ends early, with the touch counters, if the video
session stops on its own.

Development evidence only. Needs the portal session in WORKSHOP_OS_COOKIE_JAR
and a running Mac bridge. Keep hands off the display: a tap on Back or a tab
leaves the viewer, which stops the video by design and is reported as a stop.

    python3 scripts/soak_x2d_viewer.py --minutes 30
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request

from accept_os12_portal_runtime import Client

VIDEO_STATES = ("PlayingVideo", "Paused")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    parser.add_argument("--no-captures", action="store_true",
                        help="skip framebuffer captures (each stalls drawing for ~5 s)")
    args = parser.parse_args()
    c = Client(args.url)

    def api(path: str, method: str = "GET", timeout: float = 20):
        t = time.monotonic()
        r = c.request(path, method=method, headers={"Accept": "application/json"}, timeout=timeout)
        return r, (time.monotonic() - t) * 1000

    def touch() -> str:
        rs = json.loads(api("/recovery/status")[0].body)
        return f"touchPresses={rs.get('touchPresses')} readFailures={rs.get('touchReadFailures')}"

    events: list[tuple[int, str]] = []
    lat: list[float] = []
    psram: list[int] = []
    samples: list[tuple[float, object, object]] = []
    toggles = {"pause": [], "resume": []}
    reboots = frames_ok = frames_fail = 0
    last_up = prev = None

    r, _ = api("/os12/media/video/start-x2d-bridge", "POST")
    print("start:", r.status, json.loads(r.body).get("session"), flush=True)
    t0 = time.monotonic()
    events.append((0, "baseline " + touch()))
    next_frame, next_toggle = t0 + 10, t0 + 60
    while time.monotonic() - t0 < args.minutes * 60:
        tick = time.monotonic()
        at = round(tick - t0)
        try:
            r, ms = api("/os12/media/status", timeout=10)
            d = json.loads(r.body)
            lat.append(ms)
            up = d.get("deviceUptimeMs")
            if isinstance(up, int) and isinstance(last_up, int) and up < last_up:
                reboots += 1
                events.append((at, "REBOOT"))
            last_up = up
            if d.get("psramFreeBytes"):
                psram.append(d["psramFreeBytes"])
            session = d.get("session")
            samples.append((tick - t0, d.get("videoFramesRendered"), session))
            if prev and session not in VIDEO_STATES:
                events.append((at, f"session {prev} -> {session} error={d.get('error')}; " + touch()))
                print("video session ended:", session, flush=True)
                break
            prev = session
        except Exception as exc:  # noqa: BLE001 - every failure is evidence
            events.append((at, f"status {type(exc).__name__}: {str(exc)[:70]}"))
        if not args.no_captures and tick >= next_frame:
            next_frame += 10
            try:
                with c.opener.open(urllib.request.Request(args.url + "/hub/frame.ppm"), timeout=20) as resp:
                    resp.read()
                frames_ok += 1
            except Exception as exc:  # noqa: BLE001
                frames_fail += 1
                events.append((at, f"capture {type(exc).__name__}"))
        if tick >= next_toggle:
            next_toggle += 60
            for action in ("pause", "resume"):
                try:
                    r, ms = api(f"/os12/media/video/{action}", "POST")
                    toggles[action].append(ms)
                    if r.status != 200:
                        events.append((at, f"{action} HTTP {r.status}"))
                except Exception as exc:  # noqa: BLE001
                    events.append((at, f"{action} {type(exc).__name__}: {str(exc)[:70]}"))
                time.sleep(3)
        time.sleep(max(0, 1 - (time.monotonic() - tick)))

    r, _ = api("/os12/media/stop", "POST")
    fps = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(samples, samples[60:])
           if isinstance(a[1], int) and isinstance(b[1], int) and b[1] >= a[1] and a[2] == b[2] == "PlayingVideo"]
    q = sorted(lat) or [0.0]
    print(json.dumps({
        "minutesRun": round((time.monotonic() - t0) / 60, 1), "reboots": reboots,
        "statusMs": {"n": len(lat), "p50": round(statistics.median(q)), "p95": round(q[int(len(q) * .95)]), "max": round(q[-1])},
        "captures": {"ok": frames_ok, "fail": frames_fail},
        "pauseMsMax": round(max(toggles["pause"] or [0])), "resumeMsMax": round(max(toggles["resume"] or [0])),
        "fpsPerMinute": {"min": round(min(fps), 2), "median": round(statistics.median(fps), 2)} if fps else None,
        "psramFree": {"min": min(psram), "max": max(psram)} if psram else None,
    }, indent=1), flush=True)
    for at, what in events:
        print(f"{at:5d}s {what}", flush=True)
    return 1 if reboots or any("session" in w or "HTTP" in w for _, w in events) else 0


if __name__ == "__main__":
    raise SystemExit(main())
