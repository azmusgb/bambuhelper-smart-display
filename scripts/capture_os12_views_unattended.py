#!/usr/bin/env python3
"""Capture every required Workshop OS 12 native view without operator prompts.

The helper drives the local code-free portal, verifies exact running firmware
source identity, captures all required 480x320 framebuffer views, converts them
to PNG, writes a manifest, and packages the result as a ZIP for review.

It refuses catalog entries marked sensitive and never captures printer
configuration/settings exports.
"""
from __future__ import annotations

import argparse
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import time
import zlib

from accept_os12_media_physical import update_identity
from accept_os12_portal_runtime import AcceptanceError, Client, assert_code_free_portal, check
from accept_os12_unattended import (
    REQUIRED_VIEWS,
    analyze_frame,
    catalog,
    frame_bytes,
    parse_ppm,
    pixel_difference_ratio,
    pixel_difference_ratio_region,
    show,
)


SETTLE_DIFF_THRESHOLD = 0.003
SETTLE_MAX_ATTEMPTS = 10
SETTLE_INTERVAL_SECONDS = 0.08
VIDEO_VIEW_ISOLATION_MIN = 0.02


def capture_settled_frame(client: Client, view_id: str) -> tuple[bytes, dict]:
    """Capture only after the routed view has stopped materially changing."""
    started = time.monotonic()
    previous: bytes | None = None
    attempts: list[dict] = []
    for attempt in range(1, SETTLE_MAX_ATTEMPTS + 1):
        body = frame_bytes(client)
        frame = analyze_frame(body)
        diff = None if previous is None else pixel_difference_ratio(previous, body)
        attempts.append({
            "attempt": attempt,
            "sha256": frame["sha256"],
            "differenceFromPrevious": None if diff is None else round(diff, 8),
        })
        if previous is not None and diff is not None and diff <= SETTLE_DIFF_THRESHOLD:
            return body, {
                "stable": True,
                "attempts": attempt,
                "elapsedMs": round((time.monotonic() - started) * 1000),
                "finalDifferenceRatio": round(diff, 8),
                "threshold": SETTLE_DIFF_THRESHOLD,
                "observations": attempts,
            }
        previous = body
        time.sleep(SETTLE_INTERVAL_SECONDS)
    raise AcceptanceError(
        f"{view_id}: framebuffer did not settle within {SETTLE_MAX_ATTEMPTS} attempts "
        f"at threshold {SETTLE_DIFF_THRESHOLD}"
    )


def png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

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


def capture(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    expected = args.expect_source_sha.strip().lower()
    check(len(expected) == 40 and all(c in "0123456789abcdef" for c in expected),
          "--expect-source-sha must be exactly 40 lowercase hex characters")

    client = Client(base_url)
    assert_code_free_portal(client)

    identity = update_identity(client)
    running = identity["runningSourceCommit"]
    check(
        running == expected,
        f"running source SHA mismatch: device={running} expected={expected}",
    )

    views = catalog(client)
    by_id = {str(v.get("id", "")): v for v in views}
    missing = [view for view in REQUIRED_VIEWS if view not in by_id]
    check(not missing, "required views missing: " + ", ".join(missing))

    sensitive = [
        view for view in REQUIRED_VIEWS
        if by_id[view].get("sensitive") not in (None, False, "", 0)
    ]
    check(
        not sensitive,
        "required capture set contains sensitive views; refusing unattended retention: "
        + ", ".join(sensitive),
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else Path.home() / "Downloads" / f"workshop-os12-view-capture-{stamp}"
    )
    png_dir = out_dir / "png"
    ppm_dir = out_dir / "ppm"
    png_dir.mkdir(parents=True, exist_ok=False)
    ppm_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "schemaVersion": 2,
        "kind": "workshop-os12-native-view-capture",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base_url,
        "expectedSourceSha": expected,
        "runningVersion": identity["runningVersion"],
        "runningSourceSha": running,
        "resolution": {"width": 480, "height": 320},
        "views": [],
        "sensitiveViewsRetained": False,
        "operatorPrompts": False,
        "capturePolicy": {
            "settleDifferenceThreshold": SETTLE_DIFF_THRESHOLD,
            "settleMaxAttempts": SETTLE_MAX_ATTEMPTS,
            "settleIntervalMs": round(SETTLE_INTERVAL_SECONDS * 1000),
        },
        "comparisons": {},
    }

    print(f"Output: {out_dir}")
    print(f"PASS  exact running source: {running}")
    print()

    captured_frames: dict[str, bytes] = {}
    for index, view_id in enumerate(REQUIRED_VIEWS, 1):
        meta = by_id[view_id]
        show(client, view_id)
        body, settle = capture_settled_frame(client, view_id)
        captured_frames[view_id] = body
        width, height, rgb = parse_ppm(body)
        check((width, height) == (480, 320), f"{view_id}: expected 480x320, got {width}x{height}")

        stem = f"{index:02d}-{view_id}"
        ppm_path = ppm_dir / f"{stem}.ppm"
        png_path = png_dir / f"{stem}.png"
        ppm_path.write_bytes(body)
        png_path.write_bytes(png_bytes(width, height, rgb))

        frame_sha = hashlib.sha256(body).hexdigest()
        manifest["views"].append({
            "index": index,
            "id": view_id,
            "label": meta.get("label"),
            "group": meta.get("group"),
            "sensitive": False,
            "ppm": str(ppm_path.relative_to(out_dir)),
            "png": str(png_path.relative_to(out_dir)),
            "sha256": frame_sha,
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "settle": settle,
        })
        print(
            f"PASS  {index:02d}/15  {view_id:24s}  sha256={frame_sha[:12]}... "
            f"settled={settle['attempts']} attempts diff={settle['finalDifferenceRatio']:.6f}"
        )
        time.sleep(0.08)

    video_full_diff = pixel_difference_ratio(
        captured_frames["media-lab"], captured_frames["media-video"]
    )
    video_content_diff = pixel_difference_ratio_region(
        captured_frames["media-lab"], captured_frames["media-video"],
        0, 0, 480, 240,
    )
    check(
        video_content_diff >= VIDEO_VIEW_ISOLATION_MIN,
        "media-video content region is too similar to media-lab; stale Recorder content suspected",
    )
    manifest["comparisons"]["mediaLabVsMediaVideo"] = {
        "fullFrameDifferenceRatio": round(video_full_diff, 8),
        "contentRegion": {"x": 0, "y": 0, "width": 480, "height": 240},
        "contentDifferenceRatio": round(video_content_diff, 8),
        "minimumRequired": VIDEO_VIEW_ISOLATION_MIN,
        "passed": True,
    }
    print(
        "PASS  Video Viewer isolation from Recorder "
        f"contentDiff={video_content_diff:.5f}"
    )

    # Return the physical display to Home after the review capture.
    show(client, "home")

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    review_note = out_dir / "REVIEW-NOTE.txt"
    review_note.write_text(
        "This bundle contains native framebuffer captures from the WS350 at 480x320.\n"
        "It is intended for visual/UI critique. Static framebuffer review does not prove\n"
        "touch feel, LCD panel quality, speaker quality, microphone intelligibility, or\n"
        "physical acceptance. No sensitive catalog views were retained.\n",
        encoding="utf-8",
    )

    zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir.parent, base_dir=out_dir.name)

    print()
    print("UNATTENDED WS350 VIEW CAPTURE: PASS")
    print(f"Frames:   {len(REQUIRED_VIEWS)}")
    print(f"Folder:   {out_dir}")
    print(f"ZIP:      {zip_path}")
    print("Upload the ZIP to ChatGPT for full-view critique.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://10.0.0.124")
    parser.add_argument("--expect-source-sha", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    try:
        return capture(args)
    except (AcceptanceError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
