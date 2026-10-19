#!/usr/bin/env python3
"""Put the consolidated portal stylesheet on one type, radius, breakpoint and colour scale.

Runs after apply_workshop_os12_portal_css_consolidate.py. Unlike that lossless
step, this one deliberately changes visuals, by small and measured amounts:

- Font sizes snap to eight tokens (--fs-2xs ... --fs-2xl: 10/11/12/13/14/16/24/28px).
  Half-pixel sizes round up. Largest change: 1px.
- Border radii snap to 2/4/8/12/16/20px; pills (999px) are kept.
- max-width media queries snap to four tiers: 560/720/860/1050px (custom
  properties cannot be used in media queries, so these stay literals).
- Hex colours closer than CIEDE76 2.0 (not distinguishable by eye) merge onto
  the most-used shade of their group.

The v96/v98/v99 families draw a scaled miniature of the 480x320 device screen
and keep their sizes and radii.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

MARKER = "/* design scale: --fs-2xs"
CONSOLIDATED_MARKER = "consolidated at build time by"
TYPE_SCALE = {"--fs-2xs": 10, "--fs-xs": 11, "--fs-sm": 12, "--fs-md": 13, "--fs-base": 14,
              "--fs-lg": 16, "--fs-xl": 24, "--fs-2xl": 28}
RADII = (2, 4, 8, 12, 16, 20)
BREAKPOINTS = (560, 720, 860, 1050)
SAME_COLOUR_DELTA_E = 2.0
DEVICE_MINIATURE = re.compile(r"\.v9[689]-")
FONT_PX = re.compile(r"(font-size:|font:[^;{}]*?\b)(\d+(?:\.\d+)?)px")
RADIUS_PX = re.compile(r"(border-radius:)(\d+(?:\.\d+)?)px(?=[;}!])")
MAX_WIDTH = re.compile(r"max-width:\s*(\d+)px")
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")


def nearest(value: float, scale) -> float:
    # Ties go to the larger step: slightly larger text and rounder corners.
    return min(scale, key=lambda s: (abs(s - value), -s))


def type_token(px: float) -> str:
    target = nearest(math.ceil(px), TYPE_SCALE.values())
    return next(name for name, size in TYPE_SCALE.items() if size == target)


def _rgb(h: str) -> tuple[int, int, int]:
    h = h[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lab(c) -> tuple[float, float, float]:
    def lin(u):
        u /= 255
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in c)
    x = (r * .4124 + g * .3576 + b * .1805) / .95047
    y = r * .2126 + g * .7152 + b * .0722
    z = (r * .0193 + g * .1192 + b * .9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def colour_merges(css: str) -> dict[str, str]:
    counts = Counter(h.lower() for h in HEX.findall(css))
    canon: dict[str, str] = {}
    anchors: list[str] = []
    for colour, _ in counts.most_common():
        lab = _lab(_rgb(colour))
        match = next((a for a in anchors if math.dist(lab, _lab(_rgb(a))) < SAME_COLOUR_DELTA_E), None)
        if match is None:
            anchors.append(colour)
        else:
            canon[colour] = match
    return canon


def apply_scale(css: str) -> tuple[str, dict[str, int]]:
    stats = Counter()
    merges = colour_merges(css)
    out = []
    for line in css.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("@media"):
            def snap_bp(m):
                new = nearest(int(m.group(1)), BREAKPOINTS)
                stats["breakpoints"] += new != int(m.group(1))
                return f"max-width:{new}px"
            line = MAX_WIDTH.sub(snap_bp, line)
        elif "{" in line and not stripped.startswith("@") and not stripped.startswith("/*"):
            head, body = line.split("{", 1)
            if not DEVICE_MINIATURE.search(head):
                def snap_font(m):
                    stats["fontSizes"] += 1
                    return f"{m.group(1)}var({type_token(float(m.group(2)))})"
                def snap_radius(m):
                    new = nearest(float(m.group(2)), RADII)
                    stats["radii"] += new != float(m.group(2))
                    return f"{m.group(1)}{new:g}px"
                body = FONT_PX.sub(snap_font, body)
                body = RADIUS_PX.sub(lambda m: m.group(0) if float(m.group(2)) >= 999 else snap_radius(m), body)
            def merge(m):
                new = merges.get(m.group(0).lower())
                if new is None:
                    return m.group(0)
                stats["colours"] += 1
                return new
            line = head + "{" + HEX.sub(merge, body)
        out.append(line)
    tokens = ";".join(f"{name}:{size}px" for name, size in TYPE_SCALE.items())
    css = "\n".join(out)
    header_end = css.find("*/\n") + 3
    scale = (f"{MARKER} ... --fs-2xl; radii {'/'.join(map(str, RADII))}px; "
             f"breakpoints {'/'.join(map(str, BREAKPOINTS))}px */\n:root{{{tokens}}}\n")
    stats["colourGroupsMerged"] = len(set(merges.values()))
    stats["coloursRetired"] = len(merges)
    return css[:header_end] + scale + css[header_end:], dict(stats)


def apply(repo: Path) -> None:
    path = repo / "web" / "app.css"
    if not path.is_file():
        raise PatchError(f"missing reconstructed portal stylesheet: {path}")
    css = path.read_text(encoding="utf-8")
    if MARKER in css:
        print("Portal design scale already applied")
        return
    if CONSOLIDATED_MARKER not in css:
        raise PatchError("run apply_workshop_os12_portal_css_consolidate.py before the design scale")
    scaled, stats = apply_scale(css)
    path.write_text(scaled, encoding="utf-8")
    print(f"Portal design scale: {stats.get('fontSizes', 0)} font sizes on 8 tokens, "
          f"{stats.get('radii', 0)} radii and {stats.get('breakpoints', 0)} breakpoints snapped, "
          f"{stats.get('coloursRetired', 0)} near-duplicate colours merged into {stats.get('colourGroupsMerged', 0)}")


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
