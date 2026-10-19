#!/usr/bin/env python3
"""Local Portal on phones: 44 px tap targets and AA contrast in both themes.

Runs after apply_workshop_os12_portal_css_consolidate.py (and the design scale,
when present). It appends one layer to web/app.css and makes small inline-style
edits to the Recovery and AP-setup pages. It changes nothing else. (Sideways
scroll at 390 px is already fixed by #183's minmax(0,1fr) shell column.)

1. Tap targets. The hamburger (36 px), theme toggle (40 px), colour inputs
   (36 px), the Printer tabs (36/40 px tall), the "Release notes" link and the
   "Require access code" label grow to 44 px. The checkbox keeps its size: its
   label is the 44 px hit area. Recovery buttons (41 px) and the AP-setup
   fields (34 px), button (41 px) and "Show password" label grow to 44 px.

2. Contrast. Light theme: the accent, success, danger and warning colours
   darken to shades that pass WCAG AA (4.5:1) as text on white, on the page
   background and on their own tint, and with the page background as text on
   them (primary buttons, the OS mark). The orange version pill gets a dark
   orange. Dark theme: a few active tabs and badges put white text on the
   bright dark-theme fill (1.8:1); they use the dark page colour instead, as
   the dark primary button already does.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

MARKER = "/* phone fit 12.3.5: 44px tap targets, AA contrast */"
CONSOLIDATED_MARKER = "consolidated at build time by"
TAP_PX = 44

# Light-theme colours. Each passes 4.5:1 as text on #fff, on the light page
# background #f4f4f2 and on its own 7-14% tint, and with #f4f4f2 text on it.
LIGHT_TOKENS = {
    "--accent": "#0d7068",
    "--accent-hover": "#0a5d56",
    "--ui5-accent": "#0d7068",
    "--success": "#1b7346",
    "--danger": "#b8352d",
    "--warn": "#8a5a0e",
}
LIGHT_BUILD_PILL = "#a8410c"

LAYER = f"""{MARKER}
.topbar .hamburger{{width:{TAP_PX}px;height:{TAP_PX}px}}
.icon-btn{{width:{TAP_PX}px}}
.section input[type="color"]{{width:{TAP_PX}px}}
.v96-tab,.v104-printer-workspace .v96-tab{{min-height:{TAP_PX}px}}
.section a.small[href]{{display:inline-flex;align-items:center;min-height:{TAP_PX}px}}
.os12-security-control label[for]{{display:inline-flex;align-items:center;min-height:{TAP_PX}px;padding-right:8px;cursor:pointer}}
html[data-theme="light"]{{{";".join(f"{k}:{v}" for k, v in LIGHT_TOKENS.items())}}}
html[data-theme="light"] .v92-build-pill{{color:{LIGHT_BUILD_PILL}!important}}
html[data-theme="dark"] :is(.v96-tab.active,.tab-btn.active,.power-tab-btn.active,.security-callout-icon,.btn-success-solid,.btn-danger-solid),
html[data-theme="dark"] .setup-step:is([data-state="active"],[data-state="done"],[data-state="error"]) .setup-step-num{{color:var(--bg)}}
"""

# (file, anchor, replacement, label). Inline styles on pages that do not load app.css.
PAGE_EDITS = (
    ("src/web_server.cpp",
     "button{width:100%;border:1px solid #3a4652;border-radius:10px;background:#202a34;color:#fff;padding:12px;font-weight:700;margin:5px 0}",
     f"button{{width:100%;min-height:{TAP_PX}px;border:1px solid #3a4652;border-radius:10px;background:#202a34;color:#fff;padding:12px;font-weight:700;margin:5px 0}}",
     "Recovery page buttons"),
    ("include/web_pages.h",
     "input[type=text],input[type=password]{width:100%;padding:8px 10px;",
     f"input[type=text],input[type=password]{{width:100%;min-height:{TAP_PX}px;padding:8px 10px;",
     "AP setup fields"),
    ("include/web_pages.h",
     ".btn{display:block;width:100%;padding:12px;border:none;border-radius:6px;font-size:15px;",
     f".btn{{display:block;width:100%;min-height:{TAP_PX}px;padding:12px;border:none;border-radius:6px;font-size:15px;",
     "AP setup button"),
    ("include/web_pages.h",
     '<label for="showpass" style="color:#8B949E;font-size:12px;margin:0 0 0 4px;display:inline">',
     f'<label for="showpass" style="color:#8B949E;font-size:12px;margin:0;padding:0 8px 0 4px;display:inline-flex;align-items:center;min-height:{TAP_PX}px">',
     "AP setup Show password label"),
)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def apply_css(css: str) -> str:
    if MARKER in css:
        return css
    if CONSOLIDATED_MARKER not in css:
        raise PatchError("run apply_workshop_os12_portal_css_consolidate.py before the phone fit")
    for needle in (".topbar .hamburger{", ".icon-btn{", '.section input[type="color"]{',
                   ".v96-tab{", ".os12-security-control"):
        if needle not in css:
            raise PatchError(f"phone fit: expected selector {needle!r} in web/app.css")
    return css.rstrip("\n") + "\n" + LAYER


def apply(repo: Path) -> None:
    css_path = repo / "web" / "app.css"
    if not css_path.is_file():
        raise PatchError(f"missing reconstructed portal stylesheet: {css_path}")
    js_path = repo / "web" / "app.js"
    if ".v92-build-pill{" not in (js_path.read_text(encoding="utf-8") if js_path.is_file() else ""):
        raise PatchError("phone fit: web/app.js no longer injects .v92-build-pill; review the light pill colour")
    css_path.write_text(apply_css(css_path.read_text(encoding="utf-8")), encoding="utf-8")
    for rel, old, new, label in PAGE_EDITS:
        path = repo / rel
        if not path.is_file():
            raise PatchError(f"missing {path}")
        path.write_text(_replace_once(path.read_text(encoding="utf-8"), old, new, label), encoding="utf-8")
    print("Portal phone fit: 44px tap targets, light-theme AA colours, "
          f"{len(PAGE_EDITS)} Recovery/AP inline-style edits")


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
