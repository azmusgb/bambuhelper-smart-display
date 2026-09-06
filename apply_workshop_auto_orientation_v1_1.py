#!/usr/bin/env python3
"""Robust v1.1 applicator for Workshop Instrument UI auto orientation.

The v1 applicator intentionally used exact include anchors. Reconstructed
BambuHelper source has legitimate trailing comments on some include lines (for
example display_split.cpp), so v1.1 preserves all v1 behavior while making only
include insertion line-aware. It still fails closed on zero or multiple anchors.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import apply_workshop_auto_orientation_v1 as v1


def line_aware_add_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text

    wanted = anchor.strip()
    if wanted.startswith("#include"):
        lines = text.splitlines(keepends=True)
        matches = [
            i for i, line in enumerate(lines)
            if line.lstrip().startswith(wanted)
        ]
        if len(matches) != 1:
            raise v1.PatchError(
                f"{label}: expected exactly one include line beginning {wanted!r}, "
                f"found {len(matches)}"
            )
        insert_at = matches[0] + 1
        lines.insert(insert_at, include)
        return "".join(lines)

    return v1.once(text, anchor, anchor + include, label)


def apply(root: Path) -> None:
    # patch_effective_rotation() and patch_rotation_modal() resolve add_include
    # dynamically from the v1 module globals, so this changes only anchor
    # matching and leaves the reviewed orientation behavior untouched.
    v1.add_include = line_aware_add_include
    v1.apply(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
