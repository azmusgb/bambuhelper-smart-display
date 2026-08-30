#!/usr/bin/env python3
"""
BambuHelper Release Builder

Verifies firmware images against the release manifest and publishes
them to the dist directory. Can perform a dry-run to only check hashes
without copying files.

Usage:
    python build.py [--root PATH] [--dist PATH] [--dry-run]
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
from pathlib import Path

# Configure logging for clear output
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def verify_file(path: Path, expected_size: int, expected_sha: str, label: str) -> bytes:
    """
    Read a file and verify its size and SHA-256 hash.

    Args:
        path: Path to the file.
        expected_size: Expected file size in bytes.
        expected_sha: Expected SHA-256 hexadecimal string.
        label: Human-readable label for error messages.

    Returns:
        The raw bytes of the file if valid.

    Raises:
        ValueError: If size or hash does not match.
    """
    raw = path.read_bytes()
    if len(raw) != expected_size:
        raise ValueError(
            f"{label}: size mismatch (expected {expected_size}, got {len(raw)})"
        )
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(
            f"{label}: SHA mismatch (expected {expected_sha}, got {actual_sha})"
        )
    return raw


def publish(src: Path, dest: Path, size: int, sha: str, label: str) -> None:
    """
    Verify a source file and copy it to the destination.

    Args:
        src: Source file path.
        dest: Destination file path (inside dist).
        size: Expected size.
        sha: Expected SHA-256.
        label: Label for logging.
    """
    raw = verify_file(src, size, sha, label)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    logging.info(f"Published {label}: {len(raw)} bytes, SHA={sha[:12]}...")


def main() -> int:
    """
    Main entry point. Returns exit code (0 success, non-zero failure).
    """
    parser = argparse.ArgumentParser(description="Build and verify BambuHelper release")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root directory (default: script directory)",
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=None,
        help="Output directory (default: <root>/dist)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only verify, do not copy files",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    dist = (args.dist or root / "dist").resolve()

    # Safety: ensure dist is inside root to prevent accidental deletion of unrelated data
    if not str(dist).startswith(str(root)):
        logging.error("Output directory must be inside the project root")
        return 1

    # Clean previous dist directory
    if dist.exists():
        logging.info(f"Removing existing dist directory: {dist}")
        shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)

    # Copy base files (they are not verified by hash but are required)
    base_files = ["index.html", "styles.css", "app.js", "release.json"]
    for name in base_files:
        src = root / name
        if not src.exists():
            logging.error(f"Missing required base file: {src}")
            return 1
        if not args.dry_run:
            shutil.copy2(src, dist / name)
            logging.info(f"Copied base file: {name}")

    # Load release manifest
    manifest_path = root / "release.json"
    try:
        release = json.loads(manifest_path.read_text())
    except FileNotFoundError:
        logging.error(f"Manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in release.json: {e}")
        return 1

    # Validate critical metadata
    if release.get("release") != "production-rc-v7.2":
        logging.error("Unexpected release identifier in manifest")
        return 1
    if release.get("board", {}).get("id") != "ws_lcd_350":
        logging.error("Unexpected board identifier in manifest")
        return 1

    profiles = release.get("profiles", {})
    if not profiles:
        logging.error("No profiles found in release.json")
        return 1

    # Process each profile
    for pid, profile in profiles.items():
        # ---- Full image ----
        full_file = profile.get("file")
        full_size = profile.get("size")
        full_sha = profile.get("sha256")
        if not all([full_file, full_size, full_sha]):
            logging.error(f"Profile '{pid}': missing 'file', 'size', or 'sha256' for Full image")
            return 1

        full_src = root / full_file
        if not full_src.exists():
            logging.error(f"Profile '{pid}': Full image file not found: {full_src}")
            return 1

        full_dest = dist / full_file
        try:
            if args.dry_run:
                verify_file(full_src, full_size, full_sha, f"{pid} Full")
                logging.info(f"Dry-run verified {pid} Full")
            else:
                publish(full_src, full_dest, full_size, full_sha, f"{pid} Full")
        except ValueError as e:
            logging.error(str(e))
            return 1

        # ---- OTA image (optional) ----
        if profile.get("otaFile"):
            ota_file = profile["otaFile"]
            ota_size = profile.get("otaSize")
            ota_sha = profile.get("otaSha256")
            if not ota_size or not ota_sha:
                logging.error(
                    f"Profile '{pid}': 'otaFile' present but 'otaSize' or 'otaSha256' missing"
                )
                return 1

            ota_src = root / ota_file
            if not ota_src.exists():
                logging.error(f"Profile '{pid}': OTA file not found: {ota_src}")
                return 1

            ota_dest = dist / ota_file
            try:
                if args.dry_run:
                    verify_file(ota_src, ota_size, ota_sha, f"{pid} OTA")
                    logging.info(f"Dry-run verified {pid} OTA")
                else:
                    publish(ota_src, ota_dest, ota_size, ota_sha, f"{pid} OTA")
            except ValueError as e:
                logging.error(str(e))
                return 1

    logging.info("Build completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())