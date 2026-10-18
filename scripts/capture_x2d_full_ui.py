#!/usr/bin/env python3
"""Unattended WS350 UI + X2D camera screenshot and lifecycle capture.

This development evidence runner captures every non-sensitive /hub/views entry,
then exercises the fixed X2D bridge through start, live sampling, pause, resume,
stop/Media recovery, and repeated reopen cycles. It writes PPM + PNG frames,
JSON evidence, an HTML contact sheet, and a ZIP bundle suitable for visual
review.

The runner intentionally does not claim physical LCD acceptance. Framebuffer
captures can detect stale compositing, blank/black frames, routing mistakes and
many transition defects, but cannot prove that the panel itself never exposes a
sub-frame artifact between flushes.
"""
from __future__ import annotations

import argparse
import binascii
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import sys
import time
import zlib

from accept_os12_media_physical import update_identity
from accept_os12_media_runtime import api, status, validate_status, wait_for_session
from accept_os12_portal_runtime import AcceptanceError, Client, establish_portal_session, check
from accept_os12_unattended import catalog, frame_bytes, parse_ppm, pixel_difference_ratio, show

WIDTH = 480
HEIGHT = 320
VIDEO_HEIGHT = 270
LIVE_SAMPLE_INTERVAL = 0.22
STATIC_SETTLE_INTERVAL = 0.08
STATIC_SETTLE_ATTEMPTS = 8
STATIC_SETTLE_THRESHOLD = 0.008
NEAR_BLACK = 12
BLANK_BLACK_RATIO = 0.985


def png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    scan = bytearray()
    row = width * 3
    for y in range(height):
        scan.append(0)
        scan.extend(rgb[y * row : (y + 1) * row])
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    out += chunk(b"IDAT", zlib.compress(bytes(scan), 9))
    out += chunk(b"IEND", b"")
    return bytes(out)


def frame_metrics(body: bytes) -> dict:
    width, height, pixels = parse_ppm(body)
    check((width, height) == (WIDTH, HEIGHT), f"expected {WIDTH}x{HEIGHT}, got {width}x{height}")
    total = WIDTH * VIDEO_HEIGHT
    black = 0
    luma_sum = 0.0
    min_luma = 255.0
    max_luma = 0.0
    for y in range(VIDEO_HEIGHT):
        row = y * WIDTH
        for x in range(WIDTH):
            off = (row + x) * 3
            r, g, b = pixels[off], pixels[off + 1], pixels[off + 2]
            if r <= NEAR_BLACK and g <= NEAR_BLACK and b <= NEAR_BLACK:
                black += 1
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            luma_sum += luma
            min_luma = min(min_luma, luma)
            max_luma = max(max_luma, luma)
    return {
        "sha256": hashlib.sha256(body).hexdigest(),
        "width": width,
        "height": height,
        "videoViewport": {
            "height": VIDEO_HEIGHT,
            "nearBlackRatio": round(black / total, 6),
            "meanLuma": round(luma_sum / total, 3),
            "lumaSpan": round(max_luma - min_luma, 3),
            "blankSuspect": (black / total) >= BLANK_BLACK_RATIO,
        },
    }


def capture_settled(client: Client) -> tuple[bytes, dict]:
    previous: bytes | None = None
    observations: list[dict] = []
    last = b""
    for attempt in range(1, STATIC_SETTLE_ATTEMPTS + 1):
        last = frame_bytes(client)
        diff = None if previous is None else pixel_difference_ratio(previous, last)
        observations.append({"attempt": attempt, "differenceFromPrevious": None if diff is None else round(diff, 8), "sha256": hashlib.sha256(last).hexdigest()})
        if previous is not None and diff is not None and diff <= STATIC_SETTLE_THRESHOLD:
            return last, {"stable": True, "attempts": attempt, "finalDifferenceRatio": round(diff, 8), "observations": observations}
        previous = last
        time.sleep(STATIC_SETTLE_INTERVAL)
    return last, {"stable": False, "attempts": STATIC_SETTLE_ATTEMPTS, "finalDifferenceRatio": observations[-1]["differenceFromPrevious"], "observations": observations}


def wait_for_live_frame(client: Client, timeout: float = 12.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        last = status(client)
        validate_status(last)
        if last.get("session") == "PlayingVideo" and isinstance(last.get("videoFramesRendered"), int) and last["videoFramesRendered"] > 0:
            return last
        time.sleep(0.12)
    raise AcceptanceError(f"X2D live frame did not arrive within {timeout:.1f}s; last={last}")


def ensure_idle(client: Client) -> None:
    current = status(client)
    validate_status(current)
    if current.get("session") != "Idle":
        stopped = api(client, "/os12/media/stop", method="POST")
        validate_status(stopped)
        check(stopped.get("_http_status") == 200, "could not stop stale media session")
        wait_for_session(client, {"Idle"}, 4.0)


def write_contact_sheet(out_dir: Path, captures: list[dict]) -> None:
    cards = []
    for item in captures:
        cards.append(f'<article><h2>{html.escape(item["label"])}</h2><img src="{html.escape(item["png"])}" loading="lazy"><p>{html.escape(item.get("detail", ""))}</p></article>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>WS350 X2D UI capture</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#111;color:#eee;margin:24px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:22px}}article{{background:#1b1b1b;padding:14px;border-radius:12px}}h2{{font-size:16px;margin:0 0 10px}}img{{width:100%;border-radius:8px;background:#000}}p{{color:#aaa;font-size:12px;overflow-wrap:anywhere}}</style></head><body><h1>WS350 X2D UI capture</h1><main>{''.join(cards)}</main></body></html>"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    client = Client(base_url)
    establish_portal_session(client)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else Path.home() / "Downloads" / f"ws350-x2d-full-ui-{stamp}"
    ppm_dir, png_dir, state_dir = out_dir / "ppm", out_dir / "png", out_dir / "state"
    ppm_dir.mkdir(parents=True, exist_ok=False)
    png_dir.mkdir(parents=True, exist_ok=False)
    state_dir.mkdir(parents=True, exist_ok=False)

    identity = update_identity(client)
    views = catalog(client)
    captures: list[dict] = []
    report: dict = {"schemaVersion": 1, "kind": "ws350-x2d-full-ui-development-evidence", "recordedAt": datetime.now(timezone.utc).isoformat(), "baseUrl": base_url, "runtimeIdentity": identity, "catalogCount": len(views), "staticViews": [], "x2d": {"liveSamples": [], "pauseSamples": [], "resumeSamples": [], "exitSamples": [], "reopenCycles": []}, "warnings": [], "automatedChecksPassed": False, "physicalPanelAcceptance": None, "failure": None}
    sequence = 0

    def save(body: bytes, label: str, detail: str = "") -> dict:
        nonlocal sequence
        sequence += 1
        width, height, rgb = parse_ppm(body)
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label.lower()).strip("-")
        stem = f"{sequence:03d}-{safe}"
        ppm, png = ppm_dir / f"{stem}.ppm", png_dir / f"{stem}.png"
        ppm.write_bytes(body); png.write_bytes(png_bytes(width, height, rgb))
        item = {"index": sequence, "label": label, "detail": detail, "ppm": str(ppm.relative_to(out_dir)), "png": str(png.relative_to(out_dir)), "metrics": frame_metrics(body), "capturedAt": datetime.now(timezone.utc).isoformat()}
        captures.append(item); return item

    failure: Exception | None = None
    try:
        ensure_idle(client)
        print(f"Output: {out_dir}")
        print(f"Runtime source: {identity.get('runningSourceCommit')}")
        print("\nCAPTURING ALL NON-SENSITIVE CATALOG VIEWS")
        for view in views:
            view_id = str(view.get("id", "")).strip()
            if not view_id: continue
            sensitivity = view.get("sensitive")
            if sensitivity not in (None, False, "", 0):
                report["staticViews"].append({"id": view_id, "skipped": True, "reason": "sensitive", "sensitivity": sensitivity})
                print(f"SKIP  {view_id:28s} sensitive={sensitivity}"); continue
            show(client, view_id)
            body, settle = capture_settled(client)
            item = save(body, f"view-{view_id}", f"{view.get('group')} / {view.get('label')}")
            report["staticViews"].append({"id": view_id, "label": view.get("label"), "group": view.get("group"), "settle": settle, "capture": item})
            print(f"{'PASS' if settle['stable'] else 'WARN':4s}  {view_id:28s} {item['metrics']['sha256'][:12]}...")

        print("\nX2D CAMERA LIFECYCLE")
        ensure_idle(client)
        try: show(client, "media")
        except AcceptanceError: pass
        report["x2d"]["mediaReady"] = save(frame_bytes(client), "x2d-media-ready", "Media before X2D start")
        started = api(client, "/os12/media/video/start-x2d-bridge", method="POST"); validate_status(started)
        check(started.get("_http_status") == 202 and started.get("session") == "PlayingVideo", f"X2D start refused: HTTP {started.get('_http_status')} error={started.get('error')}")
        live_ready = wait_for_live_frame(client, args.live_start_timeout)
        report["x2d"]["startStatus"] = {k: v for k, v in live_ready.items() if not str(k).startswith("_")}

        live_bodies, live_statuses = [], []
        for i in range(args.live_samples):
            body = frame_bytes(client); current = status(client); validate_status(current)
            item = save(body, f"x2d-live-{i+1:02d}", f"live sample {i+1}/{args.live_samples}")
            item["status"] = {"session": current.get("session"), "videoFramesRendered": current.get("videoFramesRendered"), "videoLastFrameId": current.get("videoLastFrameId"), "videoNoFramePolls": current.get("videoNoFramePolls")}
            report["x2d"]["liveSamples"].append(item); live_bodies.append(body); live_statuses.append(current); time.sleep(LIVE_SAMPLE_INTERVAL)
        live_diffs = [pixel_difference_ratio(a, b) for a, b in zip(live_bodies, live_bodies[1:])]
        live_blank = [item["metrics"]["videoViewport"]["blankSuspect"] for item in report["x2d"]["liveSamples"]]
        frame_counts = [s.get("videoFramesRendered") for s in live_statuses if isinstance(s.get("videoFramesRendered"), int)]
        live_advanced = len(frame_counts) >= 2 and frame_counts[-1] > frame_counts[0]
        check(live_advanced, "X2D renderer counters did not advance during live sampling")
        if any(live_blank): report["warnings"].append("one or more X2D live framebuffer samples were almost entirely black")
        report["x2d"]["liveAnalysis"] = {"consecutiveDifferenceRatios": [round(v, 8) for v in live_diffs], "medianDifferenceRatio": round(statistics.median(live_diffs), 8) if live_diffs else 0.0, "blankSuspectCount": sum(bool(v) for v in live_blank), "rendererCountersAdvanced": live_advanced}
        print(f"PASS  live: samples={args.live_samples} rendered={frame_counts[0] if frame_counts else '?'}->{frame_counts[-1] if frame_counts else '?'} blankSuspects={sum(live_blank)}")

        paused = api(client, "/os12/media/video/pause", method="POST"); validate_status(paused)
        check(paused.get("_http_status") == 200 and paused.get("session") == "Paused", "X2D pause failed"); time.sleep(0.30)
        pause_bodies, pause_counts = [], []
        for i in range(4):
            body = frame_bytes(client); current = status(client); validate_status(current)
            item = save(body, f"x2d-paused-{i+1:02d}", "paused"); report["x2d"]["pauseSamples"].append(item); pause_bodies.append(body)
            if isinstance(current.get("videoFramesRendered"), int): pause_counts.append(current["videoFramesRendered"])
            time.sleep(0.20)
        pause_diffs = [pixel_difference_ratio(a, b) for a, b in zip(pause_bodies, pause_bodies[1:])]
        pause_counter_stable = not pause_counts or max(pause_counts) == min(pause_counts)
        check(pause_counter_stable, "X2D renderer counter advanced while paused")
        report["x2d"]["pauseAnalysis"] = {"consecutiveDifferenceRatios": [round(v, 8) for v in pause_diffs], "rendererCounterStable": pause_counter_stable}; print("PASS  pause: renderer counter stable")

        resumed = api(client, "/os12/media/video/resume", method="POST"); validate_status(resumed)
        check(resumed.get("_http_status") == 200 and resumed.get("session") == "PlayingVideo", "X2D resume failed"); wait_for_live_frame(client, args.live_start_timeout)
        resume_counts = []
        for i in range(6):
            body = frame_bytes(client); current = status(client); validate_status(current)
            item = save(body, f"x2d-resumed-{i+1:02d}", "resumed live"); report["x2d"]["resumeSamples"].append(item)
            if isinstance(current.get("videoFramesRendered"), int): resume_counts.append(current["videoFramesRendered"])
            time.sleep(LIVE_SAMPLE_INTERVAL)
        resume_advanced = len(resume_counts) >= 2 and resume_counts[-1] > resume_counts[0]
        check(resume_advanced, "X2D renderer counter did not advance after resume")
        report["x2d"]["resumeAnalysis"] = {"rendererCountersAdvanced": resume_advanced}; print("PASS  resume: renderer counters advanced")

        stopped = api(client, "/os12/media/stop", method="POST"); validate_status(stopped)
        check(stopped.get("_http_status") == 200 and stopped.get("session") == "Idle", "X2D stop failed")
        try: show(client, "media")
        except AcceptanceError: pass
        for i, delay in enumerate((0.0, 0.08, 0.16, 0.32, 0.64, 1.0), 1):
            if delay: time.sleep(delay)
            report["x2d"]["exitSamples"].append(save(frame_bytes(client), f"x2d-exit-{i:02d}", f"post-stop Media transition sample {i}"))
        exit_blanks = [item["metrics"]["videoViewport"]["blankSuspect"] for item in report["x2d"]["exitSamples"]]
        if any(exit_blanks): report["warnings"].append("one or more post-stop Media framebuffer samples were almost entirely black")
        report["x2d"]["exitAnalysis"] = {"blankSuspectCount": sum(bool(v) for v in exit_blanks)}; print(f"PASS  exit capture: blankSuspects={sum(exit_blanks)}")

        print(f"\nREOPEN STRESS ({args.cycles} cycles)")
        for cycle in range(1, args.cycles + 1):
            start = api(client, "/os12/media/video/start-x2d-bridge", method="POST"); validate_status(start); check(start.get("_http_status") == 202, f"cycle {cycle}: X2D start failed")
            live = wait_for_live_frame(client, args.live_start_timeout)
            live_item = save(frame_bytes(client), f"x2d-cycle-{cycle:02d}-live", f"reopen cycle {cycle} live")
            stop = api(client, "/os12/media/stop", method="POST"); validate_status(stop); check(stop.get("_http_status") == 200 and stop.get("session") == "Idle", f"cycle {cycle}: stop failed")
            try: show(client, "media")
            except AcceptanceError: pass
            idle_item = save(frame_bytes(client), f"x2d-cycle-{cycle:02d}-media", f"reopen cycle {cycle} returned to Media")
            report["x2d"]["reopenCycles"].append({"cycle": cycle, "live": live_item, "media": idle_item, "lastRenderedFrame": live.get("videoFramesRendered")}); print(f"PASS  cycle {cycle}: live -> stop -> Media")

        ensure_idle(client)
        try: show(client, "home")
        except AcceptanceError: pass
        report["finalStatus"] = {k: v for k, v in status(client).items() if not str(k).startswith("_")}
        report["automatedChecksPassed"] = True
    except Exception as exc:
        failure = exc; report["failure"] = f"{type(exc).__name__}: {exc}"
        try: ensure_idle(client)
        except Exception: pass
    finally:
        (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_contact_sheet(out_dir, captures)
        (out_dir / "README.txt").write_text("Automated WS350 framebuffer/UI evidence. Open index.html for the contact sheet.\nFramebuffer evidence can detect many render/compositor defects but does not by itself prove absence of LCD sub-frame flicker. Upload the ZIP for visual review.\n", encoding="utf-8")
        zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir.parent, base_dir=out_dir.name)
        print(f"\nFolder: {out_dir}\nZIP:    {zip_path}")
    if failure is not None: raise AcceptanceError(str(failure)) from failure
    print(f"\nWS350 X2D FULL UI CAPTURE: PASS\nFrames retained: {len(captures)}\nWarnings: {len(report['warnings'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    parser.add_argument("--output-dir")
    parser.add_argument("--live-samples", type=int, default=12)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--live-start-timeout", type=float, default=12.0)
    args = parser.parse_args()
    if args.live_samples < 4: raise SystemExit("--live-samples must be at least 4")
    if args.cycles < 1: raise SystemExit("--cycles must be at least 1")
    try: return run(args)
    except (AcceptanceError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
