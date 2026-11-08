#!/usr/bin/env python3
"""The checked-in baseline: pinned upstream BambuHelper plus Workshop OS's own changes to it, as plain files.

The WS350 image is built from the pinned upstream with baseline/ laid over it, then the apply_workshop_os12_*.py layers.
(Until 7 Nov 2026 baseline/ was rebuilt on every build by some 100 apply_*.py layers, v8 to v11.28; they are deleted and
the baseline is now the source: edit baseline/files directly.)

  baseline/UPSTREAM        the upstream repository and the pinned commit
  baseline/files/          every file Workshop OS adds or changes, at its path in the tree
  baseline/deleted.txt     files of the pinned upstream that Workshop OS removes (one path per line; may be empty)
  baseline/MANIFEST.sha256 sha256 of every file under baseline/files (checked on apply)

  baseline.py apply    --build DIR         clone the pinned upstream into DIR and lay the baseline over it
  baseline.py manifest                     rewrite MANIFEST.sha256 after editing baseline/files
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FILES = BASE / "files"
SKIP_TOP = (".git", ".pio")


def skipped(rel: str) -> bool:
    parts = rel.split("/")
    return parts[0] in SKIP_TOP or "__pycache__" in parts


def upstream() -> tuple[str, str]:
    values = dict(line.split("=", 1) for line in (BASE / "UPSTREAM").read_text().split("\n") if "=" in line)
    return values["repo"].strip(), values["sha"].strip()


def run(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_files(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        dirnames[:] = [d for d in dirnames if not skipped((rel_dir + "/" + d).lstrip("/"))]
        for name in filenames:
            rel = (rel_dir + "/" + name).lstrip("/")
            if not skipped(rel):
                out[rel] = Path(dirpath) / name
    return out


def manifest() -> dict[str, str]:
    lines = (BASE / "MANIFEST.sha256").read_text().splitlines()
    return {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in lines if line}


def cmd_apply(build: Path) -> int:
    repo, sha = upstream()
    if build.exists():
        shutil.rmtree(build)
    run("git", "clone", "--quiet", repo, str(build))
    run("git", "checkout", "--quiet", sha, cwd=build)
    expected = manifest()
    present = {rel: p for rel, p in tree_files(FILES).items()}
    if set(expected) != set(present):
        print("FAIL: baseline/files does not match MANIFEST.sha256:", sorted(set(expected) ^ set(present)), file=sys.stderr)
        return 1
    for rel, path in sorted(present.items()):
        if sha256(path) != expected[rel]:
            print(f"FAIL: baseline/files/{rel} differs from MANIFEST.sha256", file=sys.stderr)
            return 1
        target = build / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        shutil.copymode(path, target)
    deleted = [l.strip() for l in (BASE / "deleted.txt").read_text().splitlines() if l.strip()]
    for rel in deleted:
        if not (build / rel).exists():
            print(f"FAIL: baseline/deleted.txt names {rel}, which the pinned upstream does not have", file=sys.stderr)
            return 1
        (build / rel).unlink()
    print(f"baseline applied: upstream {sha[:12]} + {len(present)} files, {len(deleted)} removed -> {build}")
    return 0


def cmd_manifest() -> int:
    files = tree_files(FILES)
    (BASE / "MANIFEST.sha256").write_text("".join(f"{sha256(p)}  {r}\n" for r, p in sorted(files.items())))
    print(f"manifest: {len(files)} files")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply"); p.add_argument("--build", type=Path, required=True)
    sub.add_parser("manifest")
    args = ap.parse_args()
    if args.cmd == "apply":
        return cmd_apply(args.build.resolve())
    if args.cmd == "manifest":
        return cmd_manifest()
    return 2


if __name__ == "__main__":
    sys.exit(main())
