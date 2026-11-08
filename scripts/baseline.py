#!/usr/bin/env python3
"""The checked-in baseline: pinned upstream BambuHelper plus Workshop OS's own changes to it, as plain files.

Until now the WS350 image was rebuilt by running some 100 apply_*.py layers (v8 to v11.28, scripts/run_ui13_local.sh)
over the pinned upstream. baseline/ holds what that chain produces, so the build copies it over the pinned upstream
instead. The layers stay in the repo for now (LEGACY_CHAIN=1 runs them) so CI can prove the two are identical.

  baseline/UPSTREAM        the upstream repository and the pinned commit
  baseline/files/          every file the chain adds or changes, at its path in the tree
  baseline/deleted.txt     files of the pinned upstream the chain removes (one path per line; may be empty)
  baseline/MANIFEST.sha256 sha256 of every file under baseline/files (checked on apply)

  baseline.py apply   --build DIR          clone the pinned upstream into DIR and lay the baseline over it
  baseline.py capture --chain TREE         rewrite baseline/ from a tree built by the legacy chain (a maintainer's step)
  baseline.py manifest                     rewrite MANIFEST.sha256 after editing baseline/files by hand
  baseline.py verify  --chain TREE --build DIR   the two trees are the same files with the same bytes and modes

Not part of the product, left out of the baseline and of the comparison (nothing later in the build reads them): the
backup directories the old layers leave at the top of the tree (.*-backup), and the copies of the repo's
firmware/ui-v11.* fragments that rc9 and rc10 make inside the tree.
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
    top = parts[0]
    if top in SKIP_TOP or (top.startswith(".") and top.endswith("-backup")) or "__pycache__" in parts:
        return True
    # rc9 and rc10 copy the repo's firmware/ui-v11.25* fragments into the tree (upstream's .gitignore hides firmware/);
    # nothing later reads those copies.
    return len(parts) > 1 and top == "firmware" and parts[1].startswith("ui-v11.")


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


def cmd_capture(chain: Path) -> int:
    repo, sha = upstream()
    head = run("git", "rev-parse", "HEAD", cwd=chain).strip()
    if head != sha:
        print(f"FAIL: {chain} is at {head}, not the pinned {sha}", file=sys.stderr)
        return 1
    status = run("git", "status", "--porcelain", "--untracked-files=all", "-z", cwd=chain).split("\0")
    changed, deleted = [], []
    for entry in status:
        if not entry:
            continue
        code, rel = entry[:2], entry[3:]
        if skipped(rel):
            continue
        (deleted if "D" in code else changed).append(rel)
    if FILES.exists():
        shutil.rmtree(FILES)
    for rel in sorted(changed):
        target = FILES / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chain / rel, target)
        shutil.copymode(chain / rel, target)
    (BASE / "deleted.txt").write_text("".join(f"{r}\n" for r in sorted(deleted)))
    (BASE / "MANIFEST.sha256").write_text("".join(f"{sha256(FILES / r)}  {r}\n" for r in sorted(changed)))
    print(f"captured {len(changed)} files, {len(deleted)} deleted")
    return 0


def cmd_manifest() -> int:
    files = tree_files(FILES)
    (BASE / "MANIFEST.sha256").write_text("".join(f"{sha256(p)}  {r}\n" for r, p in sorted(files.items())))
    print(f"manifest: {len(files)} files")
    return 0


def cmd_verify(chain: Path, build: Path) -> int:
    a, b = tree_files(chain), tree_files(build)
    problems = []
    for rel in sorted(set(a) | set(b)):
        if rel not in a:
            problems.append(f"only in the baseline build: {rel}")
        elif rel not in b:
            problems.append(f"only in the chain build: {rel}")
        elif a[rel].read_bytes() != b[rel].read_bytes():
            problems.append(f"bytes differ: {rel}")
        elif stat.S_IMODE(a[rel].stat().st_mode) != stat.S_IMODE(b[rel].stat().st_mode):
            problems.append(f"mode differs: {rel}")
    if problems:
        print("\n".join(problems[:50]), file=sys.stderr)
        print(f"FAIL: {len(problems)} differences", file=sys.stderr)
        return 1
    print(f"PASS: the baseline build and the legacy chain build are the same {len(a)} files, byte for byte")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply"); p.add_argument("--build", type=Path, required=True)
    p = sub.add_parser("capture"); p.add_argument("--chain", type=Path, required=True)
    sub.add_parser("manifest")
    p = sub.add_parser("verify"); p.add_argument("--chain", type=Path, required=True); p.add_argument("--build", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "apply":
        return cmd_apply(args.build.resolve())
    if args.cmd == "capture":
        return cmd_capture(args.chain.resolve())
    if args.cmd == "manifest":
        return cmd_manifest()
    return cmd_verify(args.chain.resolve(), args.build.resolve())


if __name__ == "__main__":
    sys.exit(main())
