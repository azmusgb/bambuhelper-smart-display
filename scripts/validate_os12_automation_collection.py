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
            "unsupported unattended evidence schema",
            "unsupported capture evidence schema",
            "manifest SHA does not match retained PPM",
            "retained PNG signature is invalid",
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
            "finalize_os12_evidence_bundle.py",
            "verify_os12_evidence_bundle.py",
            "collection-context.json",
            "Offline bundle verification: PASS",
            "Sensory physical acceptance: PENDING",
        ),
    )

    collector = require(
        ROOT / "scripts" / "collect_os12_candidate_evidence_macos.sh",
        (
            "Device mutation:   NO",
            "collection-context.json",
            "accept_os12_unattended.py",
            "capture_os12_views_unattended.py",
            "validate_os12_automatic_candidate.py",
            "finalize_os12_evidence_bundle.py",
            "verify_os12_evidence_bundle.py",
            "Offline bundle verification: PASS",
            "Physical sensory acceptance: PENDING",
            "Device flash mutation: NO",
        ),
    )

    finalizer = require(
        ROOT / "scripts" / "finalize_os12_evidence_bundle.py",
        (
            '"schemaVersion": 2',
            '"kind": "workshop-os12-evidence-bundle-index"',
            '"collectorSourceSha": collector',
            '"candidateArtifact": {',
            '"automaticValidationPassed": True',
            '"physicalAcceptancePassed": None',
            '"accepted": False',
            '"stable": False',
        ),
    )

    verifier = require(
        ROOT / "scripts" / "verify_os12_evidence_bundle.py",
        (
            "path traversal archive member",
            "bundle contains unindexed or missing evidence files",
            "indexed SHA-256 mismatch",
            'index.get("physicalAcceptancePassed") is None',
            'index.get("accepted") is False',
            'index.get("stable") is False',
        ),
    )

    selftest = require(
        ROOT / "scripts" / "test_os12_evidence_bundle.py",
        (
            "evidence bundle finalization verifies clean bytes and rejects tampering",
            "tampered.zip",
            "indexed SHA-256 mismatch",
        ),
    )

    compact_unattended = unattended.replace(" ", "")
    if '"physicalAcceptancePassed":True' in compact_unattended:
        raise SystemExit(
            "FAIL: unattended runner must not promote automated evidence into physical acceptance"
        )

    for text, label in (
        (automatic, "automatic validator"),
        (installer, "installer"),
        (collector, "collector"),
        (finalizer, "finalizer"),
        (verifier, "verifier"),
        (selftest, "self-test"),
    ):
        compact = text.replace(" ", "")
        for forbidden in ('"accepted":True', '"stable":True'):
            if forbidden in compact:
                raise SystemExit(
                    f"FAIL: {label} must not promote automated evidence into accepted/stable"
                )

    print(
        "PASS: OS12 automated collection now requires settled captures, "
        "cross-view isolation, retained-file integrity, no-flash collection, "
        "offline bundle verification, and tamper detection"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
