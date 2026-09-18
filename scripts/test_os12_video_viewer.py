#!/usr/bin/env python3
"""Video-only physical test for the dedicated OS12 Camera Viewer."""
from __future__ import annotations

import argparse
import os
import time

from accept_os12_portal_runtime import Client, AcceptanceError, check
from accept_os12_media_runtime import api, status, validate_status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    ap.add_argument("--seconds", type=int, default=30)
    args = ap.parse_args()

    client = Client(args.base_url.rstrip("/"))

    show = client.request(
        "/hub/show",
        method="POST",
        form={"page": "media-video"},
        headers={"X-BambuHelper-Client": "1", "Accept": "application/json,text/plain,*/*"},
        timeout=10.0,
    )
    check(show.status == 200, f"Camera Viewer navigation returned HTTP {show.status}")
    print("DEVICE VIEW Camera Viewer: opened")

    initial = status(client)
    check(initial["session"] == "Idle", f"video test must start Idle, got {initial['session']}")

    start = api(client, "/os12/media/video/start", method="POST")
    validate_status(start)
    check(
        start["_http_status"] == 202 and start["session"] == "PlayingVideo",
        "video start refused: " + str(start["error"]),
    )
    print("STATE PlayingVideo: runtime session entered")
    print(f"WATCH THE PHYSICAL WS350 FOR {args.seconds} SECONDS")

    for second in range(1, max(1, args.seconds) + 1):
        time.sleep(1)
        current = status(client)
        if second % 5 == 0 or second == args.seconds:
            print(
                f"{second:2d}s session={current['session']} "
                f"error={current['error']} "
                f"dropped={current['droppedVideoFrames']} "
                f"psram={current['psramFreeBytes']}"
            )

    stop = api(client, "/os12/media/stop", method="POST")
    validate_status(stop)
    check(stop["_http_status"] == 200 and stop["session"] == "Idle",
          f"video stop refused: {stop['error']}")
    print("STATE Idle: video stopped")
    print("This test proves runtime state only; visible camera motion must be observed physically.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
