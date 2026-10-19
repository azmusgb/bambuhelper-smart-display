#!/usr/bin/env python3
"""Put the WS350 touchscreen on the LocalAI palette.

The device UI draws from three role-named RGB565 palettes in smart_hub.cpp:
UI_* (v9), OS12V_* (the main OS12 palette) and C10_* (shared row/card
helpers, also used by the 12.1+ More pages). This step rewrites each
constant's value to the LocalAI colour for the same role (LocalAI
app/public/app.css --ds-* tokens): navy surfaces, #6cb6ff accent in place of
the orange ember, and LocalAI's good/attention/bad. Draw code is untouched,
so layout and behaviour do not change; the user-chosen gauge themes on the
printer screens are separate settings and are not affected.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

DS = {  # LocalAI --ds-* tokens, plus dark tints for status backgrounds
    "bg": "#0a111c", "bg2": "#0c1828", "surface": "#121b2b", "surface2": "#172238", "surface3": "#182b45",
    "line": "#1b2740", "line_card": "#1f2c42", "line2": "#2d4a6d",
    "text": "#eaf0f8", "soft": "#c3d3e3", "muted": "#93a4bc", "faint": "#8698b1",
    "accent": "#6cb6ff", "accent_text": "#7cc0ff", "accent_glow": "#18293d",
    "good": "#3ed598", "attention": "#ffb224", "bad": "#ff6b6b", "violet": "#a99cff",
    "good_bg": "#102a26", "attention_bg": "#2a2414", "violet_bg": "#1d1f3a", "accent_bg": "#132538",
}
ROLES = {
    "OS12V_BG": "bg", "OS12V_SURFACE": "surface", "OS12V_SURFACE2": "surface2", "OS12V_LINE": "line_card",
    "OS12V_TEXT": "text", "OS12V_MUTED": "muted", "OS12V_ACCENT": "accent", "OS12V_BLUE": "accent_text",
    "OS12V_GREEN": "good", "OS12V_AMBER": "attention", "OS12V_RED": "bad",
    "C10_BG": "bg", "C10_SURFACE": "surface", "C10_SURFACE_2": "surface2", "C10_SURFACE_3": "surface3",
    "C10_SEPARATOR": "line_card", "C10_TEXT": "text", "C10_MUTED": "muted", "C10_ACCENT": "accent",
    "C10_GREEN": "good", "C10_ORANGE": "attention", "C10_RED": "bad",
    "UI_BG": "bg", "UI_PANEL": "surface", "UI_PANEL_2": "surface2", "UI_PANEL_3": "surface3",
    "UI_BORDER": "line_card", "UI_BORDER_2": "line", "UI_ORANGE": "accent", "UI_ORANGE_2": "accent_text",
    "UI_GLOW": "accent_glow", "UI_GREEN": "good", "UI_CYAN": "accent", "UI_BLUE": "accent",
    "UI_PURPLE": "violet", "UI_AMBER": "attention", "UI_RED": "bad", "UI_TEXT": "text",
    "UI_DIM": "muted", "UI_MUTED": "faint", "UI_GREEN_BG": "good_bg", "UI_WARN_BG": "attention_bg",
    "UI_PURP_BG": "violet_bg", "UI_CYAN_BG": "accent_bg",
}
MARKER = "// LocalAI palette (apply_workshop_os12_device_localai_palette.py)"


def rgb565(hex_colour: str) -> int:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def repaint(src: str) -> tuple[str, int]:
    changed = 0
    for name, role in ROLES.items():
        # The whole definition line, so the old colour comment goes too.
        pattern = re.compile(r"(static (?:constexpr |const )uint16_t " + re.escape(name) + r"\s*=\s*)0x[0-9A-Fa-f]{4};[^\n]*")
        hits = pattern.findall(src)
        if len(hits) != 1:
            raise PatchError(f"{name}: expected one definition, found {len(hits)}")
        value = rgb565(DS[role])
        src = pattern.sub(lambda m: f"{m.group(1)}0x{value:04X}; // LocalAI {role} {DS[role]}", src, count=1)
        changed += 1
    first = re.search(r"static (?:constexpr |const )uint16_t (?:UI|OS12V|C10)_", src)
    return src[:first.start()] + MARKER + "\n" + src[first.start():], changed


def apply(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        print("WS350 LocalAI palette already applied")
        return
    painted, changed = repaint(src)
    path.write_text(painted, encoding="utf-8")
    print(f"WS350 touchscreen on the LocalAI palette: {changed} colour constants remapped by role")


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
