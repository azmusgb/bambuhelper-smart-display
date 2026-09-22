#!/usr/bin/env python3
"""Prepare an exact Workshop OS OTA candidate for repository publication.

This command is intentionally local/repository-only: it never pushes, merges,
or promotes stable. It copies one already-built ws_lcd_350 *application* image
into a deterministic releases path, records SHA-256/size/source provenance, and
updates only the candidate entry in releases/device-update.json.

Use the output as one reviewable commit/PR. Physical acceptance is a separate
step; stable promotion must preserve the exact accepted bytes rather than
rebuilding them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_AUTHORITY = "azmusgb/bambuhelper-smart-display"
EXPECTED_BOARD = "ws_lcd_350"
EXPECTED_BASE = "https://raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/"


class PublishError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PublishError(f"git {' '.join(args)} failed") from exc


def require_clean_release_paths(root: Path) -> None:
    status = git_output(root, "status", "--porcelain", "--", "releases")
    if status:
        raise PublishError("releases/ already has uncommitted changes; commit/stash them before preparing a candidate")


def validate_manifest(manifest: dict) -> None:
    if manifest.get("schemaVersion") != 1:
        raise PublishError("manifest schemaVersion must be 1")
    if manifest.get("board") != EXPECTED_BOARD:
        raise PublishError("manifest board is not ws_lcd_350")
    if manifest.get("authority") != EXPECTED_AUTHORITY:
        raise PublishError("manifest authority mismatch")
    if manifest.get("artifactBaseUrl") != EXPECTED_BASE:
        raise PublishError("manifest artifactBaseUrl is not the canonical raw main URL")
    rules = manifest.get("rules") or {}
    required_true = (
        "normalDeviceUpdateUsesOtaOnly",
        "verifySizeBeforeInstall",
        "verifySha256BeforeInstall",
        "fullFlashRequiresRecoveryFlow",
        "unknownOrUnacceptedCandidateMustNotBePromotedToStable",
    )
    for key in required_true:
        if rules.get(key) is not True:
            raise PublishError(f"manifest safety rule is missing/false: {key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--firmware", required=True, help="built ws_lcd_350 firmware.bin application image")
    parser.add_argument("--version", required=True, help="numeric OS12 release version, e.g. 12.0.0")
    parser.add_argument("--label", required=True, help="human-readable candidate label")
    parser.add_argument("--source-sha", help="exact 40-char source SHA; defaults to current HEAD")
    parser.add_argument("--apply", action="store_true", help="write release bytes + candidate manifest entry")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    firmware = Path(args.firmware).expanduser().resolve()
    if not args.apply:
        raise SystemExit("refusing to modify release metadata without --apply")
    if not VERSION_RE.fullmatch(args.version):
        raise SystemExit("FAIL: version must be numeric MAJOR.MINOR.PATCH")
    if not firmware.is_file() or firmware.stat().st_size == 0:
        raise SystemExit(f"FAIL: firmware image missing/empty: {firmware}")

    try:
        require_clean_release_paths(root)
        source_sha = args.source_sha or git_output(root, "rev-parse", "HEAD")
        if not SHA_RE.fullmatch(source_sha):
            raise PublishError("source SHA must be exactly 40 lowercase hex characters")

        # This publisher is for PlatformIO's application image, not a merged
        # Full/recovery image. Refuse obviously wrong names and require the ESP
        # application-image magic byte before touching release metadata.
        if "full" in firmware.name.lower() or "merged" in firmware.name.lower():
            raise PublishError("Full/merged images are forbidden in the device OTA publisher")
        with firmware.open("rb") as stream:
            magic = stream.read(1)
        if magic != b"\xE9":
            raise PublishError("firmware does not look like an ESP application image (missing 0xE9 image magic)")

        manifest_path = root / "releases" / "device-update.json"
        if not manifest_path.is_file():
            raise PublishError("releases/device-update.json is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_manifest(manifest)

        size = firmware.stat().st_size
        digest = sha256_file(firmware)
        release_dir = root / "releases" / "os12-candidates" / args.version
        filename = f"Workshop-OS-{args.version}-WS350-{source_sha[:12]}-OTA.bin"
        relative = Path("releases") / "os12-candidates" / args.version / filename
        target = root / relative

        candidate = (manifest.get("channels") or {}).get("candidate") or {}
        if candidate.get("status") == "published" and candidate.get("version") == args.version:
            old_ota = candidate.get("ota") or {}
            same = (
                candidate.get("sourceCommit") == source_sha and
                old_ota.get("sha256") == digest and
                old_ota.get("size") == size and
                old_ota.get("path") == relative.as_posix()
            )
            if not same:
                raise PublishError(
                    "candidate version is already published with different identity; bump the version instead of replacing bytes"
                )

        release_dir.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256_file(target) != digest:
            raise PublishError("target candidate path already contains different bytes")
        shutil.copyfile(firmware, target)

        info = {
            "releaseState": "published-candidate-unaccepted",
            "version": args.version,
            "label": args.label,
            "board": EXPECTED_BOARD,
            "sourceCommit": source_sha,
            "artifactType": "OTA/application image",
            "path": relative.as_posix(),
            "size": size,
            "sha256": digest,
            "fullImage": False,
            "physicalAcceptance": False,
            "stable": False,
        }
        (release_dir / "BUILD-INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        (release_dir / "SHA256SUMS.txt").write_text(f"{digest}  {filename}\n", encoding="utf-8")

        stable_before = json.loads(json.dumps(manifest["channels"]["stable"]))
        manifest["channels"]["candidate"] = {
            "status": "published",
            "release": f"workshop-os-{args.version}-candidate",
            "version": args.version,
            "label": args.label,
            "acceptance": "unaccepted-hardware-candidate",
            "sourceCommit": source_sha,
            "ota": {
                "path": relative.as_posix(),
                "size": size,
                "sha256": digest,
            },
            "fullFlash": None,
        }
        if manifest["channels"]["stable"] != stable_before:
            raise PublishError("stable channel changed unexpectedly")

        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # Re-read what was written; publication metadata must describe the
        # exact bytes in the same working tree before a commit is created.
        written = json.loads(manifest_path.read_text(encoding="utf-8"))["channels"]["candidate"]
        if written["ota"]["size"] != target.stat().st_size or written["ota"]["sha256"] != sha256_file(target):
            raise PublishError("post-write candidate identity verification failed")

        print("OS12 device candidate prepared; no push or stable promotion performed")
        print(f"version={args.version}")
        print(f"source_sha={source_sha}")
        print(f"path={relative.as_posix()}")
        print(f"size={size}")
        print(f"sha256={digest}")
        print("next: review git diff/status, then commit these exact bytes + manifest together")
        return 0
    except (PublishError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
