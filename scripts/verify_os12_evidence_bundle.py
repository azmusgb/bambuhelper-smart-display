#!/usr/bin/env python3
"""Offline verification for a finalized Workshop OS 12 evidence bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--expect-bundle-sha256")
    args = ap.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    require(bundle.is_file(), f"bundle missing: {bundle}")
    bundle_sha = digest(bundle)
    if args.expect_bundle_sha256:
        require(
            bundle_sha == args.expect_bundle_sha256.strip().lower(),
            "bundle SHA-256 does not match expected value",
        )

    with tempfile.TemporaryDirectory(prefix="os12-evidence-verify-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(bundle) as zf:
            names = zf.namelist()
            require(names, "bundle is empty")
            for name in names:
                pure = PurePosixPath(name)
                require(not pure.is_absolute(), f"absolute archive member: {name}")
                require(".." not in pure.parts, f"path traversal archive member: {name}")
            zf.extractall(root)

        top = [p for p in root.iterdir() if p.is_dir()]
        require(len(top) == 1, "bundle must contain exactly one top-level evidence directory")
        evidence_root = top[0]
        index_path = evidence_root / "evidence-index.json"
        require(index_path.is_file(), "bundle missing evidence-index.json")
        index = json.loads(index_path.read_text(encoding="utf-8"))

        require(index.get("schemaVersion") == 2, "unsupported evidence index schema")
        require(index.get("kind") == "workshop-os12-evidence-bundle-index", "wrong evidence index kind")
        require(index.get("automaticValidationPassed") is True, "automatic validation is not passing")
        require(index.get("physicalAcceptancePassed") is None, "bundle must not claim physical sensory acceptance")
        require(index.get("accepted") is False, "bundle must not claim accepted")
        require(index.get("stable") is False, "bundle must not claim stable")

        indexed = index.get("files")
        require(isinstance(indexed, list) and indexed, "evidence index has no files")
        indexed_paths = set()
        for item in indexed:
            require(isinstance(item, dict), "invalid evidence-index file entry")
            rel = item.get("path")
            expected_sha = item.get("sha256")
            expected_bytes = item.get("bytes")
            require(isinstance(rel, str) and rel, "indexed file path missing")
            pure = PurePosixPath(rel)
            require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe indexed path: {rel}")
            path = (evidence_root / Path(*pure.parts)).resolve()
            require(path.is_relative_to(evidence_root.resolve()), f"indexed path escapes evidence root: {rel}")
            require(path.is_file(), f"indexed file missing: {rel}")
            require(path.stat().st_size == expected_bytes, f"indexed byte count mismatch: {rel}")
            require(digest(path) == expected_sha, f"indexed SHA-256 mismatch: {rel}")
            indexed_paths.add(rel)

        actual_paths = {
            p.relative_to(evidence_root).as_posix()
            for p in evidence_root.rglob("*")
            if p.is_file() and p.name != "evidence-index.json"
        }
        require(actual_paths == indexed_paths, "bundle contains unindexed or missing evidence files")

    print(f"PASS: evidence bundle verified offline: {bundle}")
    print(f"Bundle SHA-256: {bundle_sha}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
