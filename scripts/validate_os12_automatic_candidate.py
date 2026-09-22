#!/usr/bin/env python3
"""Validate the unattended WS350 acceptance bundle for one exact OS12 candidate.

This validator consumes only machine-produced evidence. It never upgrades
sensory observations into physical acceptance. A successful result means the
automatic runtime/framebuffer/media/capture validation set is internally
consistent for one exact source SHA.
"""
from __future__ import annotations

import argparse
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
    "finger-driven touchscreen comfort/responsiveness",
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
