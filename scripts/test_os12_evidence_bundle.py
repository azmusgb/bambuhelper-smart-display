#!/usr/bin/env python3
"""Offline self-test for OS12 evidence finalization and verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if cp.returncode != expect:
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        raise SystemExit(f"FAIL: {' '.join(args)} returned {cp.returncode}, expected {expect}")
    return cp


def main() -> int:
    source = "1" * 40
    collector = "2" * 40
    firmware = "3" * 64

    with tempfile.TemporaryDirectory(prefix="os12-evidence-selftest-") as td:
        base = Path(td)
        evidence = base / "evidence"
        capture = evidence / "view-capture"
        capture.mkdir(parents=True)

        artifact = base / "candidate.zip"
        artifact.write_bytes(b"synthetic-candidate-artifact")

        (evidence / "collection-context.json").write_text(
            json.dumps({"kind": "workshop-os12-automatic-evidence-collection-context"}) + "\n",
            encoding="utf-8",
        )
        (evidence / "unattended.json").write_text(
            json.dumps({"automatedPassed": True}) + "\n", encoding="utf-8"
        )
        (capture / "manifest.json").write_text(
            json.dumps({"kind": "workshop-os12-native-view-capture"}) + "\n",
            encoding="utf-8",
        )
        (capture / "frame.ppm").write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
        (evidence / "automatic-validation.json").write_text(
            json.dumps({
                "automaticValidationPassed": True,
                "sourceSha": source,
                "firmwareSha256": firmware,
                "physicalAcceptancePassed": None,
                "accepted": False,
                "stable": False,
            }) + "\n",
            encoding="utf-8",
        )

        finalized = run(
            sys.executable,
            "scripts/finalize_os12_evidence_bundle.py",
            "--evidence-dir", str(evidence),
            "--source-sha", source,
            "--firmware-sha256", firmware,
            "--artifact-zip", str(artifact),
            "--collector-source-sha", collector,
        )
        result = json.loads(finalized.stdout)
        bundle = Path(result["bundleZip"])
        bundle_sha = result["bundleSha256"]
        if sha(bundle) != bundle_sha:
            raise SystemExit("FAIL: finalized bundle digest does not match emitted digest")

        run(
            sys.executable,
            "scripts/verify_os12_evidence_bundle.py",
            "--bundle", str(bundle),
            "--expect-bundle-sha256", bundle_sha,
        )

        tamper_root = base / "tamper"
        with zipfile.ZipFile(bundle) as zf:
            zf.extractall(tamper_root)
        top = next(p for p in tamper_root.iterdir() if p.is_dir())
        target = top / "unattended.json"
        target.write_text('{"automatedPassed": false}\n', encoding="utf-8")
        tampered = base / "tampered.zip"
        with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(p for p in top.rglob("*") if p.is_file()):
                zf.write(path, arcname=(top.name / path.relative_to(top)).as_posix())

        rejected = run(
            sys.executable,
            "scripts/verify_os12_evidence_bundle.py",
            "--bundle", str(tampered),
            expect=1,
        )
        if "indexed SHA-256 mismatch" not in rejected.stderr:
            raise SystemExit("FAIL: tampered evidence was rejected for an unexpected reason")

    print("PASS: evidence bundle finalization verifies clean bytes and rejects tampering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
