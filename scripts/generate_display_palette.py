#!/usr/bin/env python3
"""Generate the display's one palette from the kit's tokens (display-kit K1).

The WS350 firmware names colours in four hand-written families in smart_hub.cpp: UI_*, OS12V_*, C10_* and W25_*.
Each constant is a role (a card fill, a border, a lamp). ROLES below says which kit token plays that role, and
this script writes firmware/platform/ui/display_palette.h, where every old name is defined as the kit's UI_COLOR_*
(assets/ui/tokens.h) or, for the few tinted fills the kit has no token for, as the kit's own 18% lamp tint
(the Chip's tint: appliance-ui display/canvas.h blend565). apply_workshop_os12_display_kit_palette.py removes the
old definitions and includes the header, so every screen takes the kit's colours and the old values are gone.

  python3 scripts/generate_display_palette.py            write the header
  python3 scripts/generate_display_palette.py --check    fail if the header is not what the kit and ROLES give
  python3 scripts/generate_display_palette.py --report   print the mapping (token, RGB565) as a markdown table

The ROLES table is the only hand-written part: a decision per constant, with the reason where it is not obvious.
A constant that is not in the table, or a token that is not in tokens.h, fails the run.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "assets" / "ui" / "tokens.h"
VERSION = ROOT / "assets" / "ui" / "VERSION"
HEADER = ROOT / "firmware" / "platform" / "ui" / "display_palette.h"

# name -> token ("ACCENT" is UI_COLOR_ACCENT), or ("tint", token, base token, percent): `percent` of the token over
# the base, the way the kit's Chip tints a lamp (18%) and its accentSoft is 14%.
ROLES: dict[str, dict[str, object]] = {
    "OS12V": {
        "OS12V_BG": "BG",
        "OS12V_SURFACE": "SURFACE",
        "OS12V_SURFACE2": "SURFACE_2",
        "OS12V_LINE": "LINE",
        "OS12V_TEXT": "TEXT",
        "OS12V_MUTED": "MUTED",
        "OS12V_ACCENT": "ACCENT",           # was ember orange (v10), then LocalAI blue: now coolant teal
        "OS12V_BLUE": "ACCENT_TEXT",        # "information": the kit has one accent, and its text-safe lighter step
        "OS12V_GREEN": "OK",
        "OS12V_AMBER": "WARN",
        "OS12V_RED": "BAD",
    },
    "UI": {
        "UI_BG": "BG",
        "UI_PANEL": "SURFACE",
        "UI_PANEL_2": "SURFACE_2",
        "UI_PANEL_3": "LINE",               # "active surface": a step above surface_2; the kit has no third fill
        "UI_BORDER": "LINE",
        "UI_BORDER_2": "LINE",              # "soft separator": the kit has one hairline, so the two borders merge
        "UI_ORANGE": "ACCENT",              # the old ember accent: the kit's accent
        "UI_ORANGE_2": "ACCENT_TEXT",       # its highlight: the kit's text-safe accent
        "UI_GLOW": ("tint", "ACCENT", "BG", 14),  # low glow behind an accent: the kit's accentSoft, 14% over the page
        "UI_GREEN": "OK",
        "UI_CYAN": "ACCENT",
        "UI_BLUE": "ACCENT",
        "UI_PURPLE": "ACCENT_TEXT",         # no violet in the kit (one accent): X2 family marks take the lighter accent
        "UI_AMBER": "WARN",
        "UI_RED": "BAD",
        "UI_TEXT": "TEXT",
        "UI_DIM": "MUTED",
        "UI_MUTED": "MUTED",                # "faint" text: the kit's lowest text tier is muted (4.5:1), so dim and muted merge
        "UI_GREEN_BG": ("tint", "OK", "SURFACE", 18),
        "UI_WARN_BG": ("tint", "WARN", "SURFACE", 18),
        "UI_PURP_BG": ("tint", "ACCENT_TEXT", "SURFACE", 18),
        "UI_CYAN_BG": ("tint", "ACCENT", "SURFACE", 18),
    },
    "C10": {
        "C10_BG": "BG",
        "C10_SURFACE": "SURFACE",
        "C10_SURFACE_2": "SURFACE_2",
        "C10_SURFACE_3": "LINE",
        "C10_SEPARATOR": "LINE",
        "C10_TEXT": "TEXT",
        "C10_MUTED": "MUTED",
        "C10_ACCENT": "ACCENT",
        "C10_GREEN": "OK",
        "C10_ORANGE": "WARN",               # an "attention" colour, orange only by name
        "C10_RED": "BAD",
    },
    "W25": {
        "W25_BG": "BG",
        "W25_NAV": "BAR",
        "W25_SURFACE": "SURFACE",
        "W25_SURFACE_2": "SURFACE_2",
        "W25_SURFACE_3": "LINE",
        "W25_LINE": "LINE",
        "W25_TEXT": "TEXT",
        "W25_TEXT_2": "TEXT",               # secondary bright text: the kit has text and muted only
        "W25_MUTED": "MUTED",
        "W25_ACCENT": "ACCENT",
        "W25_INFO": "ACCENT_TEXT",
        "W25_WARN": "WARN",
        "W25_DANGER": "BAD",
        "W25_SUCCESS": "OK",
    },
}

FAMILY_NOTE = {
    "OS12V": "OS12V_*: the OS12 visual overhaul's palette (apply_workshop_os12_visual_overhaul.py)",
    "UI": "UI_*: the v10 theme's palette (baseline/files/src/smart_hub.cpp)",
    "C10": "C10_*: the shared row and card helpers",
    "W25": "W25_*: the v11.25 shell (baseline/files/src/smart_hub.cpp)",
}


def all_roles() -> dict[str, object]:
    return {name: spec for family in ROLES.values() for name, spec in family.items()}


def read_tokens(path: Path = TOKENS) -> dict[str, int]:
    """UI_COLOR_<NAME> -> RGB565, from the kit's tokens.h."""
    found = {m.group(1): int(m.group(2), 16)
             for m in re.finditer(r"^#define UI_COLOR_([A-Z0-9_]+) 0x([0-9A-Fa-f]{4})\s*$", path.read_text(encoding="utf-8"), re.M)}
    if not found:
        raise SystemExit(f"no UI_COLOR_* tokens in {path}")
    return found


def kit_version() -> str:
    import json
    return json.loads(VERSION.read_text(encoding="utf-8"))["version"]


# The kit's arithmetic (display/canvas.h expand5, expand6, blend565), so a tint here is the tint the kit's parts draw.
def _x5(v: int) -> int:
    return (v << 3) | (v >> 2)


def _x6(v: int) -> int:
    return (v << 2) | (v >> 4)


def blend565(a: int, b: int, pct: int) -> int:
    def mix(x: int, y: int) -> int:
        return (x * pct + y * (100 - pct) + 50) // 100
    r = mix(_x5(a >> 11), _x5(b >> 11))
    g = mix(_x6((a >> 5) & 63), _x6((b >> 5) & 63))
    bl = mix(_x5(a & 31), _x5(b & 31))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (bl >> 3)


def value_of(spec: object, tokens: dict[str, int]) -> int:
    if isinstance(spec, str):
        return tokens[spec]
    _, token, base, pct = spec  # type: ignore[misc]
    return blend565(tokens[token], tokens[base], pct)


def validate(tokens: dict[str, int]) -> None:
    names = [n for family in ROLES.values() for n in family]
    if len(names) != len(set(names)):
        raise SystemExit("a constant appears twice in ROLES")
    for name, spec in all_roles().items():
        parts = [spec] if isinstance(spec, str) else [spec[1], spec[2]]  # type: ignore[index]
        for token in parts:
            if token not in tokens:
                raise SystemExit(f"{name}: UI_COLOR_{token} is not in the kit's tokens.h")


def expression(spec: object) -> str:
    if isinstance(spec, str):
        return f"UI_COLOR_{spec}"
    _, token, base, pct = spec  # type: ignore[misc]
    return f"uiTint565(UI_COLOR_{token}, UI_COLOR_{base}, {pct})"


def render(tokens: dict[str, int], version: str) -> str:
    out = [
        f"// generated by scripts/generate_display_palette.py from assets/ui/tokens.h (appliance-ui v{version}): do not edit;",
        "// change ROLES there, or the kit, and regenerate (display-kit K1). Installed as include/workshop_display_palette.h.",
        "#pragma once",
        "#include <stdint.h>",
        '#include "kit/tokens.h"',
        "",
        "// The kit's tint (display/canvas.h blend565): `pct` percent of a over the rest of b, each at 8 bits per channel,",
        "// rounded, back to RGB565. C++11 constexpr, so the tints below fold to constants.",
        "constexpr int uiTintX5(unsigned v) { return (int)((v << 3) | (v >> 2)); }",
        "constexpr int uiTintX6(unsigned v) { return (int)((v << 2) | (v >> 4)); }",
        "constexpr int uiTintMix(int x, int y, int pct) { return (x * pct + y * (100 - pct) + 50) / 100; }",
        "constexpr uint16_t uiTint565(uint16_t a, uint16_t b, int pct) {",
        "  return (uint16_t)(((uiTintMix(uiTintX5(a >> 11), uiTintX5(b >> 11), pct) >> 3) << 11) |",
        "                    ((uiTintMix(uiTintX6((a >> 5) & 63), uiTintX6((b >> 5) & 63), pct) >> 2) << 5) |",
        "                    (uiTintMix(uiTintX5(a & 31), uiTintX5(b & 31), pct) >> 3));",
        "}",
    ]
    width = max(len(n) for n in all_roles())
    for family, roles in ROLES.items():
        out += ["", f"// {FAMILY_NOTE[family]}"]
        for name, spec in roles.items():
            out.append(f"static constexpr uint16_t {name.ljust(width)} = {expression(spec)};")
    return "\n".join(out) + "\n"


def report(tokens: dict[str, int]) -> str:
    rows = ["| Old constant | Kit token | RGB565 |", "|---|---|---|"]
    for name, spec in all_roles().items():
        label = f"UI_COLOR_{spec}" if isinstance(spec, str) else f"{spec[3]}% UI_COLOR_{spec[1]} over UI_COLOR_{spec[2]}"  # type: ignore[index]
        rows.append(f"| {name} | {label} | 0x{value_of(spec, tokens):04X} |")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if the committed header is stale")
    ap.add_argument("--report", action="store_true", help="print the mapping as a markdown table")
    args = ap.parse_args()
    tokens = read_tokens()
    validate(tokens)
    if args.report:
        print(report(tokens))
        return 0
    text = render(tokens, kit_version())
    if args.check:
        have = HEADER.read_text(encoding="utf-8") if HEADER.is_file() else ""
        if have != text:
            print(f"FAIL: {HEADER.relative_to(ROOT)} is stale: run python3 scripts/generate_display_palette.py", file=sys.stderr)
            return 1
        print(f"display palette: {len(all_roles())} constants, header matches the kit (v{kit_version()})")
        return 0
    HEADER.write_text(text, encoding="utf-8")
    print(f"wrote {HEADER.relative_to(ROOT)} ({len(all_roles())} constants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
