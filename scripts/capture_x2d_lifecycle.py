#!/usr/bin/env python3
"""Focused unattended WS350 X2D lifecycle capture.

Runs only the camera lifecycle so physical X2D evidence is not delayed behind
large full-catalog framebuffer sweeps. Captures Media ready, live motion, pause,
resume, post-stop transition frames, and repeated reopen cycles. Evidence is
retained even if a later assertion fails.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time

from accept_os12_media_physical import update_identity
from accept_os12_media_runtime import api, status, validate_status
from accept_os12_portal_runtime import AcceptanceError, Client, check
from accept_os12_unattended import frame_bytes, show
from capture_x2d_full_ui import frame_metrics, png_bytes, wait_for_live_frame, ensure_idle


def retry_frame(client: Client, attempts: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return frame_bytes(client)
        except (TimeoutError, OSError) as exc:
            last = exc
            if attempt == attempts:
                break
            time.sleep(0.35 * attempt)
    raise AcceptanceError(f"framebuffer capture failed after {attempts} attempts: {last}")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    client = Client(base_url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else Path.home() / "Downloads" / f"ws350-x2d-lifecycle-{stamp}"
    png_dir = out_dir / "png"
    ppm_dir = out_dir / "ppm"
    png_dir.mkdir(parents=True, exist_ok=False)
    ppm_dir.mkdir(parents=True, exist_ok=False)

    report = {
        "schemaVersion": 1,
        "kind": "ws350-x2d-focused-lifecycle-evidence",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base_url,
        "runtimeIdentity": update_identity(client),
        "captures": [],
        "cycles": [],
        "automatedChecksPassed": False,
        "failure": None,
    }
    seq = 0

    def save(label: str, detail: str) -> dict:
        nonlocal seq
        body = retry_frame(client)
        seq += 1
        stem = f"{seq:03d}-{label}"
        ppm = ppm_dir / f"{stem}.ppm"
        png = png_dir / f"{stem}.png"
        ppm.write_bytes(body)
        # parse through metrics first so malformed captures fail closed.
        metrics = frame_metrics(body)
        from accept_os12_unattended import parse_ppm
        width, height, rgb = parse_ppm(body)
        png.write_bytes(png_bytes(width, height, rgb))
        item = {
            "index": seq,
            "label": label,
            "detail": detail,
            "ppm": str(ppm.relative_to(out_dir)),
            "png": str(png.relative_to(out_dir)),
            "metrics": metrics,
            "capturedAt": datetime.now(timezone.utc).isoformat(),
        }
        report["captures"].append(item)
        print(f"CAPTURE {seq:02d} {label:24s} {metrics['sha256'][:12]}...")
        return item

    failure: Exception | None = None
    try:
        ensure_idle(client)
        try:
            show(client, "media")
        except AcceptanceError:
            pass
        save("media-ready", "Media before X2D start")

        started = api(client, "/os12/media/video/start-x2d-bridge", method="POST")
        validate_status(started)
        check(started.get("_http_status") == 202 and started.get("session") == "PlayingVideo",
              f"X2D start refused: HTTP {started.get('_http_status')} error={started.get('error')}")
        ready = wait_for_live_frame(client, args.live_start_timeout)
        print(f"PASS start: frames={ready.get('videoFramesRendered')} last={ready.get('videoLastFrameId')}")

        first_count = None
        last_count = None
        for i in range(args.live_samples):
            item = save(f"live-{i+1:02d}", f"live sample {i+1}/{args.live_samples}")
            current = status(client)
            validate_status(current)
            count = current.get("videoFramesRendered")
            item["status"] = {
                "session": current.get("session"),
                "videoFramesRendered": count,
                "videoLastFrameId": current.get("videoLastFrameId"),
                "videoNoFramePolls": current.get("videoNoFramePolls"),
            }
            if isinstance(count, int):
                if first_count is None:
                    first_count = count
                last_count = count
            time.sleep(args.sample_interval)
        check(isinstance(first_count, int) and isinstance(last_count, int) and last_count > first_count,
              "X2D renderer counters did not advance during live sampling")
        print(f"PASS live: rendered {first_count}->{last_count}")

        paused = api(client, "/os12/media/video/pause", method="POST")
        validate_status(paused)
        check(paused.get("_http_status") == 200 and paused.get("session") == "Paused", "X2D pause failed")
        pause_counts: list[int] = []
        for i in range(3):
            save(f"paused-{i+1:02d}", "paused")
            current = status(client)
            validate_status(current)
            count = current.get("videoFramesRendered")
            if isinstance(count, int):
                pause_counts.append(count)
            time.sleep(0.20)
        check(not pause_counts or max(pause_counts) == min(pause_counts), "X2D renderer advanced while paused")
        print("PASS pause: renderer stable")

        resumed = api(client, "/os12/media/video/resume", method="POST")
        validate_status(resumed)
        check(resumed.get("_http_status") == 200 and resumed.get("session") == "PlayingVideo", "X2D resume failed")
        wait_for_live_frame(client, args.live_start_timeout)
        resume_counts: list[int] = []
        for i in range(4):
            save(f"resumed-{i+1:02d}", "resumed live")
            current = status(client)
            validate_status(current)
            count = current.get("videoFramesRendered")
            if isinstance(count, int):
                resume_counts.append(count)
            time.sleep(args.sample_interval)
        check(len(resume_counts) >= 2 and resume_counts[-1] > resume_counts[0], "X2D renderer did not advance after resume")
        print(f"PASS resume: rendered {resume_counts[0]}->{resume_counts[-1]}")

        stopped = api(client, "/os12/media/stop", method="POST")
        validate_status(stopped)
        check(stopped.get("_http_status") == 200 and stopped.get("session") == "Idle", "X2D stop failed")
        try:
            show(client, "media")
        except AcceptanceError:
            pass
        for i, delay in enumerate((0.0, 0.08, 0.16, 0.32, 0.64), 1):
            if delay:
                time.sleep(delay)
            save(f"exit-{i:02d}", f"post-stop Media transition sample {i}")
        print("PASS exit capture")

        for cycle in range(1, args.cycles + 1):
            start = api(client, "/os12/media/video/start-x2d-bridge", method="POST")
            validate_status(start)
            check(start.get("_http_status") == 202, f"cycle {cycle}: X2D start failed")
            live = wait_for_live_frame(client, args.live_start_timeout)
            live_item = save(f"cycle-{cycle:02d}-live", f"reopen cycle {cycle} live")
            stop = api(client, "/os12/media/stop", method="POST")
            validate_status(stop)
            check(stop.get("_http_status") == 200 and stop.get("session") == "Idle", f"cycle {cycle}: stop failed")
            try:
                show(client, "media")
            except AcceptanceError:
                pass
            media_item = save(f"cycle-{cycle:02d}-media", f"reopen cycle {cycle} returned to Media")
            report["cycles"].append({
                "cycle": cycle,
                "live": live_item,
                "media": media_item,
                "lastRenderedFrame": live.get("videoFramesRendered"),
            })
            print(f"PASS cycle {cycle}: live -> stop -> Media")

        ensure_idle(client)
        report["finalStatus"] = {k: v for k, v in status(client).items() if not str(k).startswith("_")}
        report["automatedChecksPassed"] = True
    except Exception as exc:
        failure = exc
        report["failure"] = f"{type(exc).__name__}: {exc}"
        try:
            ensure_idle(client)
        except Exception:
            pass
    finally:
        (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out_dir / "README.txt").write_text(
            "Focused WS350 X2D lifecycle framebuffer evidence. Physical LCD flicker still requires direct observation.\n",
            encoding="utf-8",
        )
        zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir.parent, base_dir=out_dir.name)
        print(f"\nFolder: {out_dir}\nZIP:    {zip_path}")

    if failure is not None:
        raise AcceptanceError(str(failure)) from failure
    print(f"\nWS350 X2D LIFECYCLE: PASS\nCaptures: {seq}\nCycles: {len(report['cycles'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://10.0.0.124")
    parser.add_argument("--output-dir")
    parser.add_argument("--live-samples", type=int, default=8)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--sample-interval", type=float, default=0.22)
    parser.add_argument("--live-start-timeout", type=float, default=12.0)
    args = parser.parse_args()
    try:
        return run(args)
    except (AcceptanceError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
