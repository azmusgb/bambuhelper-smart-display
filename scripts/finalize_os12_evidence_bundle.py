#!/usr/bin/env python3
"""Finalize a tamper-evident Workshop OS 12 automatic evidence bundle.

This helper is intentionally packaging-only. It binds the candidate artifact,
collector source, and every retained evidence file by SHA-256. It does not
create physical-acceptance, accepted, or stable claims.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--firmware-sha256", required=True)
    ap.add_argument("--artifact-zip", required=True)
    ap.add_argument("--collector-source-sha", required=True)
    ap.add_argument("--output-zip")
    args = ap.parse_args()

    root = Path(args.evidence_dir).expanduser().resolve()
    artifact = Path(args.artifact_zip).expanduser().resolve()
    source = args.source_sha.strip().lower()
    firmware = args.firmware_sha256.strip().lower()
    collector = args.collector_source_sha.strip().lower()

    if not root.is_dir():
        fail(f"evidence directory missing: {root}")
    if not artifact.is_file():
        fail(f"candidate artifact missing: {artifact}")
    if SHA40.fullmatch(source) is None:
        fail("source SHA must be exact lowercase 40-hex")
    if SHA64.fullmatch(firmware) is None:
        fail("firmware SHA-256 must be exact lowercase 64-hex")
    if SHA40.fullmatch(collector) is None:
        fail("collector source SHA must be exact lowercase 40-hex")

    required = (
        root / "collection-context.json",
        root / "unattended.json",
        root / "view-capture" / "manifest.json",
        root / "automatic-validation.json",
    )
    for path in required:
        if not path.is_file():
            fail(f"required evidence file missing: {path}")

    automatic = json.loads((root / "automatic-validation.json").read_text(encoding="utf-8"))
    if automatic.get("automaticValidationPassed") is not True:
        fail("automatic-validation.json does not record a passing automatic validation")
    if automatic.get("sourceSha") != source:
        fail("automatic validation source SHA does not match bundle source")
    if automatic.get("firmwareSha256") != firmware:
        fail("automatic validation firmware SHA-256 does not match bundle firmware")

    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "evidence-index.json"):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        })

    index = {
        "schemaVersion": 2,
        "kind": "workshop-os12-evidence-bundle-index",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "candidateSourceSha": source,
        "firmwareSha256": firmware,
        "collectorSourceSha": collector,
        "candidateArtifact": {
            "fileName": artifact.name,
            "sha256": digest(artifact),
            "bytes": artifact.stat().st_size,
        },
        "files": files,
        "automaticValidationPassed": True,
        "physicalAcceptancePassed": None,
        "accepted": False,
        "stable": False,
        "scope": (
            "machine-produced acceptance evidence only; LCD appearance, finger-touch feel, "
            "speaker quality, and microphone intelligibility remain separate physical observations"
        ),
    }

    index_path = root / "evidence-index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index_sha = digest(index_path)

    output = (
        Path(args.output_zip).expanduser().resolve()
        if args.output_zip
        else root.with_suffix(".zip")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            zf.write(path, arcname=(root.name / path.relative_to(root)).as_posix())
    bundle_sha = digest(output)

    sidecar = Path(str(output) + ".sha256")
    sidecar.write_text(f"{bundle_sha}  {output.name}\n", encoding="utf-8")

    result = {
        "evidenceIndex": str(index_path),
        "evidenceIndexSha256": index_sha,
        "bundleZip": str(output),
        "bundleSha256": bundle_sha,
        "bundleSha256Sidecar": str(sidecar),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
