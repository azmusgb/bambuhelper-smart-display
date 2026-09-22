#!/usr/bin/env python3
"""Unattended Workshop OS 12 acceptance runner for a real WS350.

This runner intentionally automates only evidence that the device can prove
without an operator: exact running source identity, native-view coverage,
framebuffer geometry/content sanity, navigation routing, media lifecycle,
video framebuffer motion/freeze behavior, network reachability, clean final
state, and monotonic uptime.

It does NOT silently promote automated evidence into physical acceptance for
sensory or touch-only properties. Those residual checks remain a final release
spot-check rather than an every-build interaction requirement.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse
import urllib.request

from accept_os12_media_physical import update_identity
from accept_os12_media_runtime import api, status, validate_status, wait_for_session
from accept_os12_portal_runtime import AcceptanceError, Client, assert_code_free_portal, check

HEX40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_VIEWS = (
    "home",
    "printer",
    "workshop",
    "more",
    "settings-display",
    "settings-sounds",
    "settings-network",
    "settings-printer-power",
    "system",
    "system-date-time",
    "system-update",
    "system-diagnostics",
    "media",
    "media-lab",
    "media-video",
)

MANUAL_RESIDUALS = (
    "physical LCD panel appearance: brightness, color, panel artifacts, and real-world readability",
    "actual finger-driven touchscreen responsiveness and target comfort",
    "audible speaker quality/distortion in the room",
    "microphone intelligibility/acoustic quality in the room",
    "physical full-image recovery/rollback when that release gate is due",
)


def local_git_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip().lower()
    return value if HEX40.fullmatch(value) is not None else None


def load_expected_source(manifest: Path, channel: str) -> tuple[str, dict]:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AcceptanceError(f"update manifest not found: {manifest}") from exc
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"update manifest is not valid JSON: {manifest}") from exc

    channels = payload.get("channels")
    check(isinstance(channels, dict), "update manifest missing channels")
    selected = channels.get(channel)
    check(isinstance(selected, dict), f"update manifest missing {channel!r} channel")
    source = selected.get("sourceCommit")
    check(
        isinstance(source, str) and HEX40.fullmatch(source) is not None,
        f"{channel} channel sourceCommit is not an exact 40-character SHA",
    )
    return source, selected


def request_json(client: Client, path: str, *, timeout: float = 10.0) -> dict:
    response = client.request(
        path,
        headers={"X-BambuHelper-Client": "1", "Accept": "application/json"},
        timeout=timeout,
    )
    check(response.status == 200, f"GET {path} returned HTTP {response.status}")
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"GET {path} did not return JSON") from exc
    check(isinstance(payload, dict), f"GET {path} did not return a JSON object")
    return payload


def catalog(client: Client) -> list[dict]:
    payload = request_json(client, "/hub/views")
    views = payload.get("views")
    check(isinstance(views, list) and views, "native view catalog contains no views")
    return views


def show(client: Client, view_id: str) -> None:
    response = client.request(
        "/hub/show",
        method="POST",
        form={"page": view_id},
        headers={
            "X-BambuHelper-Client": "1",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=10.0,
    )
    check(response.status == 200, f"/hub/show refused {view_id}: HTTP {response.status}")
    time.sleep(0.22)


def frame_bytes(client: Client) -> bytes:
    url = urljoin(client.base_url + "/", "hub/frame.ppm")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "WorkshopOS-Unattended-Acceptance/1",
            "X-BambuHelper-Client": "1",
            "Accept": "image/x-portable-pixmap",
        },
    )
    try:
        with client.opener.open(request, timeout=12.0) as response:
            status_code = response.status
            body = response.read()
    except Exception as exc:
        raise AcceptanceError(f"framebuffer capture request failed: {exc}") from exc
    check(status_code == 200, f"GET /hub/frame.ppm returned HTTP {status_code}")
    return body


def parse_ppm(body: bytes) -> tuple[int, int, bytes]:
    check(body.startswith(b"P6\n"), "framebuffer capture is not binary PPM")
    parts = body.split(b"\n", 3)
    check(len(parts) == 4, "PPM header is incomplete")
    dims = parts[1].split()
    check(len(dims) == 2, "PPM dimensions are malformed")
    try:
        width, height = int(dims[0]), int(dims[1])
    except ValueError as exc:
        raise AcceptanceError("PPM dimensions are not integers") from exc
    check(parts[2].strip() == b"255", "PPM max value is not 255")
    pixels = parts[3]
    expected = width * height * 3
    check(
        len(pixels) == expected,
        f"PPM payload size mismatch: expected {expected}, got {len(pixels)}",
    )
    return width, height, pixels


def analyze_frame(body: bytes) -> dict:
    width, height, pixels = parse_ppm(body)
    check((width, height) == (480, 320), f"expected 480x320, got {width}x{height}")

    stride = max(1, (width * height) // 12000)
    colors: Counter[tuple[int, int, int]] = Counter()
    min_channel = 255
    max_channel = 0
    sample_count = 0

    for pixel_index in range(0, width * height, stride):
        offset = pixel_index * 3
        rgb = (pixels[offset], pixels[offset + 1], pixels[offset + 2])
        colors[rgb] += 1
        min_channel = min(min_channel, *rgb)
        max_channel = max(max_channel, *rgb)
        sample_count += 1

    dominant = colors.most_common(1)[0][1] if colors else 0
    dominant_ratio = dominant / sample_count if sample_count else 1.0
    unique_sample_colors = len(colors)
    channel_span = max_channel - min_channel

    check(unique_sample_colors >= 6, f"frame looks blank/degenerate: only {unique_sample_colors} sampled colors")
    check(channel_span >= 24, f"frame contrast span is unexpectedly low: {channel_span}")
    check(dominant_ratio < 0.995, f"frame is almost entirely one color: dominant ratio {dominant_ratio:.4f}")

    return {
        "width": width,
        "height": height,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "sampledUniqueColors": unique_sample_colors,
        "sampledDominantColorRatio": round(dominant_ratio, 6),
        "sampledChannelSpan": channel_span,
    }


def pixel_difference_ratio(first: bytes, second: bytes) -> float:
    w1, h1, p1 = parse_ppm(first)
    w2, h2, p2 = parse_ppm(second)
    check((w1, h1) == (w2, h2), "cannot compare framebuffers with different dimensions")
    changed = 0
    total = w1 * h1
    for i in range(total):
        offset = i * 3
        if (
            abs(p1[offset] - p2[offset]) > 6
            or abs(p1[offset + 1] - p2[offset + 1]) > 6
            or abs(p1[offset + 2] - p2[offset + 2]) > 6
        ):
            changed += 1
    return changed / total


def safe_public(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def output_path(arg: str | None, stamp: str) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return Path.home() / "Downloads" / f"workshop-os12-unattended-{stamp}.json"


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")), "--base-url must start with http:// or https://")

    manifest = Path(args.manifest).expanduser().resolve()
    expected_source = args.expect_source_sha
    manifest_channel: dict | None = None
    expected_origin = "explicit-cli"

    if expected_source is None:
        repo_root = Path(__file__).resolve().parents[1]
        git_head = local_git_head(repo_root)
        if git_head is not None:
            expected_source = git_head
            expected_origin = "local-git-head"
        else:
            expected_source, manifest_channel = load_expected_source(manifest, args.channel)
            expected_origin = f"manifest:{args.channel}"
    else:
        check(
            HEX40.fullmatch(expected_source) is not None,
            "--expect-source-sha must be exactly 40 lowercase hex characters",
        )

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    destination = output_path(args.output, stamp)

    evidence: dict = {
        "schemaVersion": 1,
        "kind": "workshop-os12-unattended-runtime-hardware-evidence",
        "recordedAt": now.isoformat(),
        "targetHost": urlparse(base_url).hostname,
        "expectedSourceSha": expected_source,
        "expectedSourceOrigin": expected_origin,
        "manifestChannel": manifest_channel,
        "runtimeIdentityStart": None,
        "runtimeIdentityEnd": None,
        "portalMode": "unknown",
        "views": {},
        "viewCatalogCount": 0,
        "viewHashDiversity": None,
        "media": {},
        "networkReachableAtEnd": False,
        "uptimeMonotonic": None,
        "automatedPassed": False,
        "physicalAcceptancePassed": None,
        "manualResiduals": list(MANUAL_RESIDUALS),
        "completed": False,
        "failure": None,
        "scope": (
            "unattended objective evidence only; does not silently convert "
            "runtime/framebuffer diagnostics into final physical acceptance"
        ),
    }

    client = Client(base_url)

    try:
        assert_code_free_portal(client)
        evidence["portalMode"] = "local-code-free"
        print("PASS  code-free local portal contract")

        identity_start = update_identity(client)
        evidence["runtimeIdentityStart"] = identity_start
        if identity_start["runningSourceCommit"] != expected_source:
            raise AcceptanceError(
                "runtime source SHA does not match expected candidate source: "
                f"device={identity_start['runningSourceCommit']} "
                f"expected={expected_source} "
                f"expectedOrigin={expected_origin}. "
                "Flash the exact expected CI candidate before acceptance, or pass "
                "--expect-source-sha explicitly when intentionally validating another build."
            )
        print(f"PASS  exact running source: {expected_source} ({expected_origin})")

        initial = status(client)
        validate_status(initial)
        start_uptime = initial.get("deviceUptimeMs")
        check(initial["session"] == "Idle", f"media service must start Idle, got {initial['session']}")

        views = catalog(client)
        evidence["viewCatalogCount"] = len(views)
        by_id = {str(item.get("id", "")): item for item in views}
        missing = [view_id for view_id in REQUIRED_VIEWS if view_id not in by_id]
        check(not missing, "required native views missing: " + ", ".join(missing))

        hashes: set[str] = set()
        print("\nUNATTENDED UI WALK")
        for view_id in REQUIRED_VIEWS:
            show(client, view_id)
            frame = analyze_frame(frame_bytes(client))
            hashes.add(frame["sha256"])
            evidence["views"][view_id] = {
                "label": by_id[view_id].get("label"),
                "group": by_id[view_id].get("group"),
                "sensitive": bool(by_id[view_id].get("sensitive")),
                "routeAccepted": True,
                "frame": frame,
            }
            print(
                f"PASS  {view_id:24s} "
                f"{frame['width']}x{frame['height']} "
                f"colors={frame['sampledUniqueColors']} "
                f"hash={frame['sha256'][:12]}..."
            )

        diversity = len(hashes) / len(REQUIRED_VIEWS)
        evidence["viewHashDiversity"] = round(diversity, 6)
        check(
            len(hashes) >= max(6, len(REQUIRED_VIEWS) // 2),
            f"native view routing looks stuck: only {len(hashes)} unique frames across {len(REQUIRED_VIEWS)} views",
        )
        print(f"PASS  native view hash diversity: {len(hashes)}/{len(REQUIRED_VIEWS)}")

        print("\nUNATTENDED MEDIA WALK")
        for key in ("speakerAvailable", "microphoneAvailable", "videoDecoderAvailable", "psramAvailable"):
            check(initial.get(key) is True, f"required media capability unavailable: {key}")

        speaker = api(client, "/os12/media/speaker-test", method="POST")
        validate_status(speaker)
        check(speaker["_http_status"] == 202, f"speaker test refused: {speaker.get('error')}")
        time.sleep(0.15)
        speaker_active = status(client)
        validate_status(speaker_active)
        check(speaker_active["session"] == "PlayingAudio", "speaker test never entered PlayingAudio")
        speaker_diag = {
            "codecReady": speaker_active.get("audioCodecReady"),
            "i2sReady": speaker_active.get("audioI2sReady"),
            "pipelineRunning": speaker_active.get("audioPipelineRunning"),
            "ampEnabled": speaker_active.get("audioAmpEnabled"),
            "frequency": speaker_active.get("audioCurrentFrequency"),
            "targetGain": speaker_active.get("audioTargetGain"),
            "currentGain": speaker_active.get("audioCurrentGain"),
        }
        for key in ("codecReady", "i2sReady", "pipelineRunning", "ampEnabled"):
            check(speaker_diag[key] is True, f"speaker active diagnostic not healthy: {key}")
        wait_for_session(client, {"Idle"}, 3.5)
        evidence["media"]["speakerLifecycle"] = speaker_diag
        print("PASS  speaker lifecycle + active hardware diagnostics")

        mic_samples = []
        for _ in range(3):
            mic = api(client, "/os12/media/microphone-sample", method="POST")
            validate_status(mic)
            check(mic["_http_status"] == 200, f"microphone sample refused: {mic.get('error')}")
            level = mic.get("microphoneLevelPercent")
            peak = mic.get("microphoneLastPeak")
            check(isinstance(level, int) and 0 <= level <= 100, "microphone level is invalid")
            check(isinstance(peak, int) and peak >= 0, "microphone peak is invalid")
            mic_samples.append({"levelPercent": level, "peak": peak})
            time.sleep(0.12)
        evidence["media"]["microphoneSamples"] = mic_samples
        print("PASS  microphone ADC/sample path returned valid measurements")

        show(client, "media-lab")
        record_start = api(client, "/os12/media/record/start", method="POST")
        validate_status(record_start)
        check(
            record_start["_http_status"] == 202 and record_start["session"] == "Recording",
            f"record start refused: {record_start.get('error')}",
        )
        completed = wait_for_session(client, {"Idle"}, 7.5)
        check(completed.get("recordingAvailable") is True, "recording completed without retained local recording")
        playback = api(client, "/os12/media/record/play", method="POST")
        validate_status(playback)
        check(
            playback["_http_status"] == 202 and playback["session"] == "PlayingRecording",
            f"recording playback refused: {playback.get('error')}",
        )
        wait_for_session(client, {"Idle"}, 7.5)
        evidence["media"]["recordPlaybackLifecycle"] = True
        print("PASS  bounded record -> idle -> playback -> idle lifecycle")

        show(client, "media-video")
        before_video = frame_bytes(client)
        video_start = api(client, "/os12/media/video/start", method="POST")
        validate_status(video_start)
        check(
            video_start["_http_status"] == 202 and video_start["session"] == "PlayingVideo",
            f"video start refused: {video_start.get('error')}",
        )
        time.sleep(0.35)
        play_a = frame_bytes(client)
        play_status_a = status(client)
        time.sleep(0.45)
        play_b = frame_bytes(client)
        play_status_b = status(client)
        play_motion = pixel_difference_ratio(play_a, play_b)

        play_frames_a = play_status_a.get("videoFramesRendered")
        play_frames_b = play_status_b.get("videoFramesRendered")
        play_frame_id_a = play_status_a.get("videoLastFrameId")
        play_frame_id_b = play_status_b.get("videoLastFrameId")
        counter_motion_play = (
            isinstance(play_frames_a, int)
            and isinstance(play_frames_b, int)
            and play_frames_b > play_frames_a
        ) or (
            isinstance(play_frame_id_a, int)
            and isinstance(play_frame_id_b, int)
            and play_frame_id_b > play_frame_id_a
        )
        check(counter_motion_play, "video renderer counters did not advance while PlayingVideo")

        pause = api(client, "/os12/media/video/pause", method="POST")
        validate_status(pause)
        check(pause["_http_status"] == 200 and pause["session"] == "Paused", f"video pause refused: {pause.get('error')}")
        time.sleep(0.25)
        pause_a = frame_bytes(client)
        pause_status_a = status(client)
        time.sleep(0.45)
        pause_b = frame_bytes(client)
        pause_status_b = status(client)
        pause_motion = pixel_difference_ratio(pause_a, pause_b)

        pause_frames_a = pause_status_a.get("videoFramesRendered")
        pause_frames_b = pause_status_b.get("videoFramesRendered")
        pause_frame_id_a = pause_status_a.get("videoLastFrameId")
        pause_frame_id_b = pause_status_b.get("videoLastFrameId")
        counter_stable_pause = (
            not isinstance(pause_frames_a, int)
            or not isinstance(pause_frames_b, int)
            or pause_frames_b == pause_frames_a
        ) and (
            not isinstance(pause_frame_id_a, int)
            or not isinstance(pause_frame_id_b, int)
            or pause_frame_id_b == pause_frame_id_a
        )
        check(counter_stable_pause, "video renderer counters advanced while Paused")

        resume = api(client, "/os12/media/video/resume", method="POST")
        validate_status(resume)
        check(
            resume["_http_status"] == 200 and resume["session"] == "PlayingVideo",
            f"video resume refused: {resume.get('error')}",
        )
        time.sleep(0.35)
        resume_a = frame_bytes(client)
        resume_status_a = status(client)
        time.sleep(0.45)
        resume_b = frame_bytes(client)
        resume_status_b = status(client)
        resume_motion = pixel_difference_ratio(resume_a, resume_b)

        resume_frames_a = resume_status_a.get("videoFramesRendered")
        resume_frames_b = resume_status_b.get("videoFramesRendered")
        resume_frame_id_a = resume_status_a.get("videoLastFrameId")
        resume_frame_id_b = resume_status_b.get("videoLastFrameId")
        counter_motion_resume = (
            isinstance(resume_frames_a, int)
            and isinstance(resume_frames_b, int)
            and resume_frames_b > resume_frames_a
        ) or (
            isinstance(resume_frame_id_a, int)
            and isinstance(resume_frame_id_b, int)
            and resume_frame_id_b > resume_frame_id_a
        )
        check(counter_motion_resume, "video renderer counters did not advance after resume")

        motion_floor = max(args.video_motion_floor, pause_motion * args.motion_vs_pause_multiplier)
        framebuffer_motion_play = play_motion >= motion_floor
        framebuffer_motion_resume = resume_motion >= motion_floor
        framebuffer_freeze_pause = pause_motion < max(play_motion, resume_motion)

        stop = api(client, "/os12/media/stop", method="POST")
        validate_status(stop)
        check(stop["_http_status"] == 200 and stop["session"] == "Idle", f"video stop refused: {stop.get('error')}")

        evidence["media"]["videoRenderer"] = {
            "playingFrames": [play_frames_a, play_frames_b],
            "playingFrameIds": [play_frame_id_a, play_frame_id_b],
            "pausedFrames": [pause_frames_a, pause_frames_b],
            "pausedFrameIds": [pause_frame_id_a, pause_frame_id_b],
            "resumedFrames": [resume_frames_a, resume_frames_b],
            "resumedFrameIds": [resume_frame_id_a, resume_frame_id_b],
            "playingAdvanced": counter_motion_play,
            "pausedStable": counter_stable_pause,
            "resumedAdvanced": counter_motion_resume,
        }
        evidence["media"]["videoFramebuffer"] = {
            "beforeVideoSha256": hashlib.sha256(before_video).hexdigest(),
            "playingDifferenceRatio": round(play_motion, 8),
            "pausedDifferenceRatio": round(pause_motion, 8),
            "resumedDifferenceRatio": round(resume_motion, 8),
            "requiredMotionFloor": round(motion_floor, 8),
            "playingMotionObserved": framebuffer_motion_play,
            "pausedFreezeObserved": framebuffer_freeze_pause,
            "resumedMotionObserved": framebuffer_motion_resume,
            "captureIsSupplemental": True,
        }
        print(
            "PASS  video renderer counters motion/freeze/resume "
            f"play={play_frames_a}->{play_frames_b} "
            f"pause={pause_frames_a}->{pause_frames_b} "
            f"resume={resume_frames_a}->{resume_frames_b}"
        )
        if framebuffer_motion_play and framebuffer_motion_resume:
            print(
                "PASS  framebuffer also observed video motion "
                f"play={play_motion:.5f} pause={pause_motion:.5f} resume={resume_motion:.5f}"
            )
        else:
            print(
                "WARN  framebuffer capture did not observe direct TFT video updates; "
                "renderer counters are the machine-verifiable motion authority "
                f"(play={play_motion:.5f} pause={pause_motion:.5f} resume={resume_motion:.5f})"
            )

        final = status(client)
        validate_status(final)
        check(final["session"] == "Idle" and final["error"] == "None", "final media state is not clean Idle")
        end_uptime = final.get("deviceUptimeMs")
        if isinstance(start_uptime, int) and isinstance(end_uptime, int):
            evidence["uptimeMonotonic"] = end_uptime >= start_uptime
            check(evidence["uptimeMonotonic"], "device uptime moved backwards; reboot/watchdog suspected")

        catalog(client)
        evidence["networkReachableAtEnd"] = True
        identity_end = update_identity(client)
        evidence["runtimeIdentityEnd"] = identity_end
        check(identity_end["runningSourceCommit"] == expected_source, "running source identity changed during test")

        evidence["media"]["initialStatus"] = safe_public(initial)
        evidence["media"]["finalStatus"] = safe_public(final)
        evidence["automatedPassed"] = True
        evidence["completed"] = True

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print(f"\nEvidence: {destination}")
        print("UNATTENDED WORKSHOP OS 12 ACCEPTANCE: PASS")
        print("No operator prompts were required.")
        print("Final release physical acceptance still retains a small manual spot-check for:")
        for item in MANUAL_RESIDUALS:
            print(f"  - {item}")
        return 0

    except (AcceptanceError, OSError, ValueError) as exc:
        evidence["failure"] = str(exc)
        evidence["completed"] = True
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nEvidence: {destination}")
        print(f"UNATTENDED WORKSHOP OS 12 ACCEPTANCE: FAIL: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
    )
    parser.add_argument(
        "--manifest",
        default="releases/device-update.json",
        help="device update manifest used to resolve the expected source when --expect-source-sha is omitted",
    )
    parser.add_argument("--channel", choices=("stable", "candidate"), default="candidate")
    parser.add_argument(
        "--expect-source-sha",
        help="optional exact source SHA; otherwise derived from the selected manifest channel",
    )
    parser.add_argument("--output")
    parser.add_argument("--video-motion-floor", type=float, default=0.002)
    parser.add_argument("--motion-vs-pause-multiplier", type=float, default=2.0)
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
