#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
VERSION = "12.0.0"


def run(*args: str, cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != expect:
        raise SystemExit(
            f"command returned {result.returncode}, expected {expect}: {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    source_root = Path(__file__).resolve().parents[1]
    publisher = source_root / "scripts" / "prepare_os12_device_candidate.py"
    source_manifest = source_root / "releases" / "device-update.json"
    if not publisher.is_file() or not source_manifest.is_file():
        raise SystemExit("publisher or device-update manifest missing")

    with tempfile.TemporaryDirectory(prefix="os12-publisher-") as tmp:
        repo = Path(tmp)
        (repo / "releases").mkdir(parents=True)
        shutil.copyfile(source_manifest, repo / "releases" / "device-update.json")
        run("git", "init", "-q", cwd=repo)
        run("git", "config", "user.email", "validator@example.invalid", cwd=repo)
        run("git", "config", "user.name", "OS12 Validator", cwd=repo)
        run("git", "add", "releases/device-update.json", cwd=repo)
        run("git", "commit", "-qm", "baseline", cwd=repo)

        stable_before = json.loads((repo / "releases/device-update.json").read_text())["channels"]["stable"]

        firmware = repo / "firmware.bin"
        payload = b"\xE9" + bytes(range(1, 255)) * 32
        firmware.write_bytes(payload)
        expected_digest = hashlib.sha256(payload).hexdigest()

        result = run(
            sys.executable,
            str(publisher),
            "--repo", str(repo),
            "--firmware", str(firmware),
            "--version", VERSION,
            "--label", "Workshop OS 12 candidate validation",
            "--source-sha", SOURCE_SHA,
            "--apply",
            cwd=repo,
        )
        if "no push or stable promotion" not in result.stdout:
            raise SystemExit("publisher did not report non-promotion boundary")

        manifest = json.loads((repo / "releases/device-update.json").read_text())
        if manifest["channels"]["stable"] != stable_before:
            raise SystemExit("publisher changed stable channel")
        candidate = manifest["channels"]["candidate"]
        if candidate["version"] != VERSION or candidate["sourceCommit"] != SOURCE_SHA:
            raise SystemExit("candidate release identity mismatch")
        if candidate["acceptance"] != "unaccepted-hardware-candidate" or candidate["fullFlash"] is not None:
            raise SystemExit("candidate acceptance/recovery boundary mismatch")
        ota = candidate["ota"]
        target = repo / ota["path"]
        if not target.is_file() or target.read_bytes() != payload:
            raise SystemExit("published candidate bytes do not match input application image")
        if ota["size"] != len(payload) or ota["sha256"] != expected_digest:
            raise SystemExit("candidate size/SHA-256 metadata mismatch")
        info = json.loads((target.parent / "BUILD-INFO.json").read_text())
        if info["physicalAcceptance"] is not False or info["stable"] is not False:
            raise SystemExit("candidate provenance overclaims acceptance/stable state")

        # Commit the exact first publication, then prove a second invocation is
        # idempotent for the same identity.
        run("git", "add", "releases", cwd=repo)
        run("git", "commit", "-qm", "candidate", cwd=repo)
        run(
            sys.executable,
            str(publisher),
            "--repo", str(repo),
            "--firmware", str(firmware),
            "--version", VERSION,
            "--label", "Workshop OS 12 candidate validation",
            "--source-sha", SOURCE_SHA,
            "--apply",
            cwd=repo,
        )

        # A published version is immutable: different bytes must be rejected.
        run("git", "add", "releases", cwd=repo)
        if run("git", "status", "--porcelain", "--", "releases", cwd=repo).stdout.strip():
            run("git", "commit", "-qm", "idempotent refresh", cwd=repo)
        different = repo / "different.bin"
        different.write_bytes(b"\xE9different application bytes")
        rejected = run(
            sys.executable,
            str(publisher),
            "--repo", str(repo),
            "--firmware", str(different),
            "--version", VERSION,
            "--label", "Attempted replacement",
            "--source-sha", "89abcdef0123456789abcdef0123456789abcdef",
            "--apply",
            cwd=repo,
            expect=1,
        )
        if "already published with different identity" not in (rejected.stdout + rejected.stderr):
            raise SystemExit("publisher did not reject same-version identity replacement")

        full = repo / "Workshop-OS-Full.bin"
        full.write_bytes(payload)
        rejected_full = run(
            sys.executable,
            str(publisher),
            "--repo", str(repo),
            "--firmware", str(full),
            "--version", "12.0.1",
            "--label", "Forbidden Full image",
            "--source-sha", SOURCE_SHA,
            "--apply",
            cwd=repo,
            expect=1,
        )
        if "Full/merged images are forbidden" not in (rejected_full.stdout + rejected_full.stderr):
            raise SystemExit("publisher did not reject Full-image name")

    print("OS12 candidate publisher validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
