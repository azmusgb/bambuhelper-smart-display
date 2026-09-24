#!/usr/bin/env python3
"""Validate the strengthened OS12 unattended evidence-collection contract."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: Path, markers: tuple[str, ...]) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path}")
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"FAIL: {path}: missing {marker!r}")
    return text


def main() -> int:
    unattended = require(
        ROOT / "scripts" / "accept_os12_unattended.py",
        (
            '"schemaVersion": 2',
            "pixel_difference_ratio_region",
            '"viewIsolation": {}',
            '"mediaLabVsMediaVideo"',
            '"minimumRequired": 0.02',
            "stale Recorder content suspected",
            '"physicalAcceptancePassed": None',
        ),
    )

    capture = require(
        ROOT / "scripts" / "capture_os12_views_unattended.py",
        (
            "SETTLE_DIFF_THRESHOLD = 0.003",
            "SETTLE_MAX_ATTEMPTS = 10",
            "capture_settled_frame",
            '"schemaVersion": 2',
            '"capturePolicy": {',
            '"settle": settle',
            '"mediaLabVsMediaVideo"',
            "VIDEO_VIEW_ISOLATION_MIN = 0.02",
            "stale Recorder content suspected",
            '"sensitiveViewsRetained": False',
        ),
    )

    automatic = require(
        ROOT / "scripts" / "validate_os12_automatic_candidate.py",
        (
            "sha256_file",
            "resolve_relative_file",
            '"unsupported unattended evidence schema"',
            '"unsupported capture evidence schema"',
            '"manifest SHA does not match retained PPM"',
            '"retained PNG signature is invalid"',
            '"verifiedCaptureFiles":verified_files',
            '"inputDigests":{',
            '"automaticValidationPassed":True',
            '"physicalAcceptancePassed":None',
            '"accepted":False',
            '"stable":False',
        ),
    )

    installer = require(
        ROOT / "scripts" / "install_accept_os12_candidate_macos.sh",
        (
            "Finalize tamper-evident evidence bundle",
            '"kind":"workshop-os12-evidence-bundle-index"',
            '"candidateArtifact":{',
            '"accepted":False',
            '"stable":False',
            "Evidence bundle SHA-256",
            "Tamper-evident evidence bundle",
        ),
    )

    for text, label in (
        (unattended, "unattended runner"),
        (capture, "capture runner"),
        (automatic, "automatic validator"),
        (installer, "installer"),
    ):
        for forbidden in (
            '"physicalAcceptancePassed":True',
            '"accepted":True',
            '"stable":True',
        ):
            if forbidden in text.replace(" ", ""):
                raise SystemExit(
                    f"FAIL: {label} must not promote automated evidence into acceptance/stable"
                )

    print(
        "PASS: OS12 automated collection now requires settled captures, "
        "cross-view isolation, retained-file integrity, and tamper-evident bundling"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
