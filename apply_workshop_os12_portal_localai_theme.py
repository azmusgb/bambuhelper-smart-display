#!/usr/bin/env python3
"""Give the Workshop OS portal the LocalAI design system.

Runs last on web/app.css (after consolidation and the design scale) and once on
include/web_pages.h. LocalAI (app/public/app.css, the --ds-* tokens) is the
reference; this step maps the portal's existing tokens onto it, so every rule
that already reads a token follows without per-rule edits:

- Dark theme: LocalAI's palette verbatim (navy surfaces, #6cb6ff accent,
  good/attention/bad colours). Dark is the default; a saved choice still wins.
- Light theme: LocalAI has none, so a light palette in the same navy/blue family,
  every text pairing at WCAG AA or better, including accent and status colours
  on their own 7-14% tints.
- Type: the design-scale tokens take LocalAI's scale (11 badge, 13, 15, 17, 22, 28).
- Radii: LocalAI's 8/12/16.
- Font: LocalAI's Figtree (variable, latin, 20 KB, SIL OFL 1.1; see
  assets/fonts/OFL-Figtree.txt), embedded in the stylesheet so the display
  serves it from flash with the CSS's immutable cache, with no new route.

The v96/v98/v99 device-screen miniature keeps its own palette and font.
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

MARKER = "/* LocalAI design system:"
FONT = _here / "assets" / "fonts" / "figtree-latin-wght-normal.woff2"
SANS = 'Figtree,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif'

LIGHT = {
    "--accent": "#1b61bb", "--accent-soft": "rgba(27,97,187,.12)", "--accent-hover": "#164f9a",
    "--bg": "#f4f7fb", "--bg-elev": "#ffffff", "--bg-sub": "#eaf0f7", "--bg-input": "#ffffff",
    "--line": "#d3deea", "--line-soft": "#e3eaf3",
    "--text": "#0d1b2c", "--text-mid": "#33465f", "--text-dim": "#56677e",
    "--danger": "#b43030", "--success": "#166f48", "--warn": "#8e5500", "--info": "#1b61bb",
    "--radius-s": "8px", "--radius": "12px", "--radius-l": "16px",
}
DARK = {  # LocalAI --ds-* values
    "--accent": "#6cb6ff", "--accent-soft": "rgba(108,182,255,.14)", "--accent-hover": "#7cc0ff",
    "--bg": "#0a111c", "--bg-elev": "#121b2b", "--bg-sub": "#0c1828", "--bg-input": "#0c1828",
    "--line": "#1f2c42", "--line-soft": "#1b2740",
    "--text": "#eaf0f8", "--text-mid": "#c3d3e3", "--text-dim": "#93a4bc",
    "--danger": "#ff6b6b", "--success": "#3ed598", "--warn": "#ffb224", "--info": "#6cb6ff",
}
# Older layers that still read their own accent and radius tokens.
EXTRA_LIGHT = {"--ui5-accent": "#1b61bb", "--ui5-radius": "12px", "--rc7-radius-sm": "8px", "--rc7-radius-md": "12px"}
EXTRA_DARK = {"--ui5-accent": "#6cb6ff"}
TYPE = {"--fs-2xs": "11px", "--fs-xs": "11px", "--fs-sm": "13px", "--fs-md": "13px",
        "--fs-base": "15px", "--fs-lg": "17px", "--fs-xl": "22px", "--fs-2xl": "28px"}

# The old orange accent survived as two raw colours (focus ring, primary-button
# glow) outside the token system; they follow the new accent too.
STRAY_ACCENT = {"rgba(255,122,47,.82)": "var(--accent)", "rgba(255,122,47,.18)": "var(--accent-soft)"}
DEVICE_MINIATURE = re.compile(r"\.v9[689]-")

THEME_DEFAULT_OLD = "t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';"
THEME_DEFAULT_NEW = "t='dark';"


def set_tokens(line: str, values: dict[str, str], label: str, required: bool = True) -> str:
    for name, value in values.items():
        pattern = re.compile(re.escape(name) + r":[^;}]+")
        if not pattern.search(line):
            if required:
                raise PatchError(f"{label}: token {name} missing")
            continue
        line = pattern.sub(f"{name}:{value}", line, count=1)
    return line


def theme_css(css: str, font: bytes) -> str:
    lines = css.split("\n")

    def one(predicate, label: str) -> int:
        hits = [i for i, line in enumerate(lines) if predicate(line)]
        if len(hits) != 1:
            raise PatchError(f"{label}: expected one rule, found {len(hits)}")
        return hits[0]

    light = one(lambda l: l.startswith(":root{") and "--bg-elev:" in l, "light palette :root")
    dark = one(lambda l: l.startswith('html[data-theme="dark"]{') and "--bg-elev:" in l, "dark palette")
    lines[light] = set_tokens(lines[light], LIGHT, "light palette")
    lines[dark] = set_tokens(lines[dark], DARK, "dark palette")

    for i, line in enumerate(lines):
        if line.startswith(":root{") and ("--ui5-accent:" in line or "--rc7-radius" in line):
            lines[i] = set_tokens(line, EXTRA_LIGHT, "legacy tokens", required=False)
        elif line.startswith('html[data-theme="dark"]{') and "--ui5-accent:" in line:
            lines[i] = set_tokens(line, EXTRA_DARK, "legacy dark tokens", required=False)
        elif line.startswith(":root{") and "--fs-2xs:" in line:
            lines[i] = set_tokens(line, TYPE, "type scale")
        elif line.startswith('html[data-theme="light"]{') and any(f"{k}:" in line for k in LIGHT):
            # A later layer (12.3.5 phone fit) re-declares light tokens with a
            # more specific selector than :root; keep it on the LocalAI palette.
            lines[i] = set_tokens(line, {**LIGHT, **EXTRA_LIGHT}, "light override", required=False)

    for i, line in enumerate(lines):
        if DEVICE_MINIATURE.search(line.split("{", 1)[0]):
            continue
        for old, new in STRAY_ACCENT.items():
            line = line.replace(old, new)
        lines[i] = line

    sans = one(lambda l: l.startswith(":root{") and "--sans:" in l, "font token")
    lines[sans] = re.sub(r"--sans:[^;}]+", f"--sans:{SANS}", lines[sans], count=1)

    face = ("@font-face{font-family:Figtree;font-style:normal;font-weight:400 700;font-display:swap;"
            "src:url(data:font/woff2;base64," + base64.b64encode(font).decode() + ") format('woff2')}")
    header_end = css.find("*/\n") + 3 if css.startswith("/*") else 0
    note = (f"{MARKER} LocalAI app/public/app.css --ds-* tokens; Figtree (c) The Figtree Project "
            "Authors, SIL OFL 1.1 */\n")
    body = "\n".join(lines)
    return body[:header_end] + note + face + "\n" + body[header_end:]


def theme_pages(html: str) -> str:
    if THEME_DEFAULT_NEW in html and THEME_DEFAULT_OLD not in html:
        return html
    if html.count(THEME_DEFAULT_OLD) != 1:
        raise PatchError("default theme script: expected one prefers-color-scheme fallback")
    return html.replace(THEME_DEFAULT_OLD, THEME_DEFAULT_NEW, 1)


def apply(repo: Path) -> None:
    css_path = repo / "web" / "app.css"
    pages_path = repo / "include" / "web_pages.h"
    for path in (css_path, pages_path, FONT):
        if not path.is_file():
            raise PatchError(f"missing file: {path}")
    css = css_path.read_text(encoding="utf-8")
    if MARKER in css:
        print("Portal LocalAI theme already applied")
        return
    if "consolidated at build time by" not in css:
        raise PatchError("run apply_workshop_os12_portal_css_consolidate.py before the LocalAI theme")

    themed = theme_css(css, FONT.read_bytes())
    pages = theme_pages(pages_path.read_text(encoding="utf-8"))
    css_path.write_text(themed, encoding="utf-8")
    pages_path.write_text(pages, encoding="utf-8")
    print(f"Portal LocalAI theme: palette, type, radii and Figtree applied ({len(css)} -> {len(themed)} bytes); dark by default")


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
