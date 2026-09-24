#!/usr/bin/env python3
"""Validate the unattended WS350 acceptance bundle for one exact OS12 candidate.

This validator consumes only machine-produced evidence. It never upgrades
sensory observations into physical acceptance. A successful result means the
automatic runtime/framebuffer/media/capture validation set is internally
consistent for one exact source SHA.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

HEX40 = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_VIEWS = (
    "home","printer","workshop","more","settings-display","settings-sounds",
    "settings-network","settings-printer-power","system","system-date-time",
    "system-update","system-diagnostics","media","media-lab","media-video",
)
MANUAL_RESIDUALS = (
    "physical LCD panel appearance/readability",
    "finger-driven touchscreen comfort/responsiveness + Workshop Refresh/Portal action mapping",
    "audible speaker quality/distortion",
    "microphone intelligibility/acoustic quality",
    "full-image recovery/rollback when due",
)

class ValidationError(RuntimeError):
    pass

def require(cond: bool, message: str) -> None:
    if not cond:
        raise ValidationError(message)

def load_json(path: Path) -> dict:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"missing evidence file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {path}") from exc
    require(isinstance(data, dict), f"JSON root must be an object: {path}")
    return data


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def resolve_relative_file(root: Path, value: object, label: str) -> Path:
    require(isinstance(value,str) and value.strip(), f"{label} path missing")
    rel=Path(value)
    require(not rel.is_absolute(), f"{label} path must be relative")
    candidate=(root/rel).resolve()
    require(candidate.is_relative_to(root.resolve()), f"{label} path escapes capture directory")
    require(candidate.is_file(), f"{label} file missing: {candidate}")
    return candidate

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--unattended", required=True)
    ap.add_argument("--capture-manifest", required=True)
    ap.add_argument("--expect-source-sha", required=True)
    ap.add_argument("--expect-firmware-sha256", required=True)
    ap.add_argument("--output", required=True)
    args=ap.parse_args()

    source=args.expect_source_sha.strip().lower()
    firmware=args.expect_firmware_sha256.strip().lower()
    require(HEX40.fullmatch(source) is not None, "invalid expected source SHA")
    require(re.fullmatch(r"[0-9a-f]{64}", firmware) is not None, "invalid expected firmware SHA-256")

    unattended_path=Path(args.unattended).expanduser().resolve()
    capture_path=Path(args.capture_manifest).expanduser().resolve()
    out=Path(args.output).expanduser().resolve()
    unattended=load_json(unattended_path)
    capture=load_json(capture_path)

    require(unattended.get("schemaVersion")==2, "unsupported unattended evidence schema")
    require(unattended.get("kind")=="workshop-os12-unattended-runtime-hardware-evidence",
            "wrong unattended evidence kind")
    require(unattended.get("expectedSourceSha")==source,
            "unattended evidence source does not match expected candidate")
    require(unattended.get("automatedPassed") is True,
            "unattended acceptance did not pass")
    require(unattended.get("completed") is True,
            "unattended acceptance is incomplete")
    require(unattended.get("networkReachableAtEnd") is True,
            "device was not reachable at end of unattended acceptance")
    require(unattended.get("uptimeMonotonic") is not False,
            "device uptime evidence indicates reset/watchdog")
    for key in ("runtimeIdentityStart","runtimeIdentityEnd"):
        ident=unattended.get(key)
        require(isinstance(ident,dict), f"missing {key}")
        require(ident.get("runningSourceCommit")==source,
                f"{key} source does not match expected candidate")

    views=unattended.get("views")
    require(isinstance(views,dict), "unattended evidence missing views")
    require(set(REQUIRED_VIEWS).issubset(views.keys()),
            "unattended evidence missing required native views")
    isolation=(unattended.get("viewIsolation") or {}).get("mediaLabVsMediaVideo")
    require(isinstance(isolation,dict), "unattended evidence missing Video Viewer isolation check")
    require(isolation.get("passed") is True, "Video Viewer isolation check did not pass")
    content_diff=isolation.get("contentDifferenceRatio")
    minimum=isolation.get("minimumRequired")
    require(isinstance(content_diff,(int,float)) and isinstance(minimum,(int,float)),
            "Video Viewer isolation metrics are invalid")
    require(content_diff >= minimum, "Video Viewer content is too similar to Recorder")


    require(capture.get("schemaVersion")==2, "unsupported capture evidence schema")
    require(capture.get("kind")=="workshop-os12-native-view-capture",
            "wrong capture evidence kind")
    require(capture.get("expectedSourceSha")==source and capture.get("runningSourceSha")==source,
            "capture source identity does not match expected candidate")
    require(capture.get("operatorPrompts") is False,
            "capture unexpectedly required operator prompts")
    require(capture.get("sensitiveViewsRetained") is False,
            "capture retained sensitive views")
    resolution=capture.get("resolution") or {}
    require(resolution.get("width")==480 and resolution.get("height")==320,
            "capture is not 480x320")
    captured=capture.get("views")
    require(isinstance(captured,list), "capture manifest missing views")
    ids=[str(v.get("id","")) for v in captured if isinstance(v,dict)]
    require(ids==list(REQUIRED_VIEWS),
            "capture view order/coverage does not match required 15-view set")
    hashes=[str(v.get("sha256","")) for v in captured if isinstance(v,dict)]
    require(len(hashes)==len(REQUIRED_VIEWS), "capture hash count mismatch")
    require(all(re.fullmatch(r"[0-9a-f]{64}",h) for h in hashes),
            "capture contains invalid frame SHA-256")
    require(len(set(hashes))==len(REQUIRED_VIEWS),
            "capture does not have 15/15 frame-hash diversity")

    capture_root=capture_path.parent
    verified_files=[]
    for item in captured:
        require(isinstance(item,dict), "capture view entry is not an object")
        settle=item.get("settle")
        require(isinstance(settle,dict) and settle.get("stable") is True,
                f"{item.get('id')}: framebuffer did not record a stable settled capture")
        require(isinstance(settle.get("attempts"),int) and settle["attempts"] >= 2,
                f"{item.get('id')}: settle evidence requires at least two observations")
        final_diff=settle.get("finalDifferenceRatio")
        threshold=settle.get("threshold")
        require(isinstance(final_diff,(int,float)) and isinstance(threshold,(int,float)),
                f"{item.get('id')}: settle metrics are invalid")
        require(final_diff <= threshold,
                f"{item.get('id')}: final framebuffer difference exceeds settle threshold")

        ppm=resolve_relative_file(capture_root,item.get("ppm"),f"{item.get('id')} ppm")
        png=resolve_relative_file(capture_root,item.get("png"),f"{item.get('id')} png")
        actual_ppm_sha=sha256_file(ppm)
        require(actual_ppm_sha==item.get("sha256"),
                f"{item.get('id')}: manifest SHA does not match retained PPM")
        require(png.read_bytes()[:8]==b"\x89PNG\r\n\x1a\n",
                f"{item.get('id')}: retained PNG signature is invalid")
        verified_files.append({
            "id": item.get("id"),
            "ppmSha256": actual_ppm_sha,
            "pngSha256": sha256_file(png),
            "ppmBytes": ppm.stat().st_size,
            "pngBytes": png.stat().st_size,
        })

    comparisons=capture.get("comparisons") or {}
    video_compare=comparisons.get("mediaLabVsMediaVideo")
    require(isinstance(video_compare,dict) and video_compare.get("passed") is True,
            "capture manifest missing passing Media Lab vs Video Viewer isolation")
    capture_content_diff=video_compare.get("contentDifferenceRatio")
    capture_minimum=video_compare.get("minimumRequired")
    require(isinstance(capture_content_diff,(int,float)) and isinstance(capture_minimum,(int,float)),
            "capture Video Viewer isolation metrics are invalid")
    require(capture_content_diff >= capture_minimum,
            "capture Video Viewer isolation is below required threshold")

    result={
        "schemaVersion":1,
        "kind":"workshop-os12-automatic-candidate-validation",
        "recordedAt":datetime.now(timezone.utc).isoformat(),
        "sourceSha":source,
        "firmwareSha256":firmware,
        "unattendedEvidence":str(unattended_path),
        "captureManifest":str(capture_path),
        "requiredViews":list(REQUIRED_VIEWS),
        "viewHashDiversity":f"{len(set(hashes))}/{len(REQUIRED_VIEWS)}",
        "inputDigests":{
            "unattendedSha256":sha256_file(unattended_path),
            "captureManifestSha256":sha256_file(capture_path),
        },
        "verifiedCaptureFiles":verified_files,
        "videoViewerIsolation":{
            "unattendedContentDifferenceRatio":content_diff,
            "captureContentDifferenceRatio":capture_content_diff,
        },
        "automaticValidationPassed":True,
        "physicalAcceptancePassed":None,
        "manualResiduals":list(MANUAL_RESIDUALS),
        "accepted":False,
        "stable":False,
        "scope":"automatic machine-verifiable candidate validation only; sensory physical truth remains separate",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"PASS: automatic candidate validation complete for {source}")
    print(f"Evidence: {out}")
    print("Automatic validation: PASS")
    print("Physical sensory acceptance: PENDING")
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
