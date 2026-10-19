#!/usr/bin/env python3
"""Consolidate the reconstructed portal stylesheet and apply its a11y fixes.

Runs after every overlay that appends to web/app.css. Two stages:

1. scripts/consolidate_portal_css.py: lossless. Shadowed declarations, rules
   for markup that no longer exists, and unused custom properties are removed
   without changing any computed style; rule order is preserved.
2. Accessibility and layout fixes, the only intentional visual changes:
   - light theme muted text #7b8a91 (3.3:1 on #f5f7f7) becomes #5a686f
     (5.1:1 or better on every light surface);
   - portal text set below 10px is raised to 10px. The v96/v98/v99 families
     draw a scaled miniature of the 480x320 device screen and keep their sizes;
   - the one-column phone layout uses minmax(0,1fr) so wide children scroll
     inside themselves instead of widening the page.

New portal styling belongs in the layer that owns it; this step only removes
what the cascade already overrode.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.consolidate_portal_css import consolidate, portal_corpus
from scripts.smart_home_patch_utils import PatchError

MARKER = "consolidated at build time by\n   scripts/consolidate_portal_css.py"
LIGHT_ROOT_DIM_OLD = "--text-dim:#7b8a91"
LIGHT_ROOT_DIM_NEW = "--text-dim:#5a686f"
# Below 820px the shell becomes one column. A bare 1fr track cannot shrink below
# its widest child, so the 4-step setup strip (4 x 128px) widened the whole page
# to 560px on a phone instead of scrolling inside itself as intended.
NARROW_APP_OLD = ".app{grid-template-columns:1fr!important}"
NARROW_APP_NEW = ".app{grid-template-columns:minmax(0,1fr)!important}"
DEVICE_MINIATURE = re.compile(r"\.v9[689]-")
TINY_FONT = re.compile(r"(font-size:|font:[^;{}]*?\b)(\d+(?:\.\d+)?)px")
MIN_FONT_PX = 10.0


def apply_a11y_fixes(css: str) -> tuple[str, int]:
    lines = css.split("\n")
    root = [i for i, line in enumerate(lines) if line.startswith(":root{") and LIGHT_ROOT_DIM_OLD in line]
    if len(root) != 1:
        raise PatchError(f"light theme muted text: expected one :root rule with {LIGHT_ROOT_DIM_OLD}, found {len(root)}")
    lines[root[0]] = lines[root[0]].replace(LIGHT_ROOT_DIM_OLD, LIGHT_ROOT_DIM_NEW, 1)

    narrow = [i for i, line in enumerate(lines) if line.strip() == NARROW_APP_OLD]
    if len(narrow) != 1:
        raise PatchError(f"narrow shell column: expected one {NARROW_APP_OLD}, found {len(narrow)}")
    lines[narrow[0]] = lines[narrow[0]].replace(NARROW_APP_OLD, NARROW_APP_NEW, 1)

    raised = 0

    def bump(match: re.Match) -> str:
        nonlocal raised
        if float(match.group(2)) >= MIN_FONT_PX:
            return match.group(0)
        raised += 1
        return f"{match.group(1)}{MIN_FONT_PX:g}px"

    for i, line in enumerate(lines):
        selector = line.split("{", 1)[0]
        if "{" in line and not line.lstrip().startswith("@") and not DEVICE_MINIATURE.search(selector):
            head, body = line.split("{", 1)
            lines[i] = head + "{" + TINY_FONT.sub(bump, body)
    return "\n".join(lines), raised


def apply(repo: Path) -> None:
    css_path = repo / "web" / "app.css"
    if not css_path.is_file():
        raise PatchError(f"missing reconstructed portal stylesheet: {css_path}")
    css = css_path.read_text(encoding="utf-8")
    if MARKER in css:
        print("Portal stylesheet already consolidated")
        return

    consolidated, stats = consolidate(css, portal_corpus(repo))
    fixed, raised = apply_a11y_fixes(consolidated)
    css_path.write_text(fixed, encoding="utf-8")
    print(f"Portal stylesheet consolidated: {len(css)} -> {len(fixed)} bytes "
          f"({stats['shadowedDeclarations']} shadowed declarations, {stats['deadSelectors']} dead selectors, "
          f"{stats['unusedProperties']} unused custom properties removed)")
    print(f"Accessibility: light muted text {LIGHT_ROOT_DIM_NEW.split(':')[1]}; {raised} sub-10px font sizes raised")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
