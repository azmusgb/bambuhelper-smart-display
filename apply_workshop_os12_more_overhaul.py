#!/usr/bin/env python3
"""WS350 More/System overhaul (Workshop OS 12.1.x).

Owning patch for the More area. It runs last in the recipe, after
apply_workshop_os12_status_lite.py, and owns whole functions rather than
editing lines inside them, so earlier layers cannot silently undo it.

12.1.1 installs the shared page table and geometry,
``firmware/platform/ui/more_layout.hpp``, as ``include/workshop_more_layout.hpp``
and includes it in smart_hub.cpp. Nothing on screen changes yet; the host test
tests/workshop_os12_more_layout_smoke.cpp checks the geometry in both
orientations.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_MORE_OVERHAUL 1"
LAYOUT_SOURCE = Path("firmware") / "platform" / "ui" / "more_layout.hpp"
LAYOUT_TARGET = Path("include") / "workshop_more_layout.hpp"

OLD_INCLUDE = '#include "smart_hub.h"\n'
NEW_INCLUDE = '#include "smart_hub.h"\n#include "workshop_more_layout.hpp"\n'


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def install_layout(repo: Path, source_root: Path) -> None:
    source = source_root / LAYOUT_SOURCE
    if not source.is_file():
        raise PatchError(f"missing {source}")
    target = repo / LAYOUT_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def patch_smart_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    text = replace_once(text, OLD_INCLUDE, NEW_INCLUDE, "layout include")
    path.write_text(text, encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1" not in build:
        raise PatchError("the More overhaul runs after apply_workshop_os12_status_lite.py")
    if BUILD_MARKER in build:
        raise PatchError("the More overhaul is already applied")
    install_layout(repo, source_root)
    patch_smart_hub(repo)
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.1 More layout installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
