#!/usr/bin/env python3
"""Turn the portal sidebar into a LocalAI-style icon rail.

LocalAI navigates with a narrow rail: an icon above a short label, the current
section highlighted. This step gives the portal the same pattern:

- include/web_pages.h: each workspace button gets an outline icon (Home,
  Printer, Workshop, More) in front of its label.
- web/app.css: from 821px up the sidebar becomes an 84px rail (icon over label;
  the brand, "Workspaces" heading and version footer are hidden because the
  header already shows them). Below that, the slide-out drawer stays and shows
  each icon beside its label.

Runs after apply_workshop_os12_portal_localai_theme.py so the rail uses the
LocalAI tokens.
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

MARKER = "/* LocalAI icon rail */"
SVG = ('<svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>')
ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    "printer": '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
    "workshop": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    "more": ('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
             '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
}

RAIL_CSS = MARKER + """
.nav-ico{width:20px;height:20px;flex:0 0 auto}
@media(max-width:820px){
  .nav-item{justify-content:flex-start;gap:12px}
}
@media(min-width:821px){
  :root{--sidebar-w:84px}
  .sidebar{padding:12px 8px;display:flex;flex-direction:column;gap:6px}
  .sidebar h4,.sidebar .portal-nav-brand,.sidebar .sidebar-footer{display:none!important}
  .nav-item{flex-direction:column;justify-content:center;align-items:center;gap:5px;padding:10px 4px;margin:0;
    border:1px solid transparent;border-radius:var(--radius);box-shadow:none;text-align:center;
    font-size:var(--fs-xs);font-weight:600;color:var(--text-dim)}
  .nav-item .nav-ico{width:22px;height:22px}
  .nav-item:hover{transform:none;background:var(--bg-elev);color:var(--text)}
  .nav-item[aria-current="true"],.nav-item.active{background:var(--bg-elev);border-color:var(--line);color:var(--text);box-shadow:none}
  .nav-item[aria-current="true"] .nav-ico,.nav-item.active .nav-ico{color:var(--accent)}
  .nav-item[aria-current="true"]::before{display:none}
}
"""


def add_icons(html: str) -> str:
    for section, paths in ICONS.items():
        pattern = re.compile(r'(<button class="nav-item"[^>]*data-section="' + section + r'"[^>]*>)(<span>)')
        matches = pattern.findall(html)
        if len(matches) != 1:
            raise PatchError(f"nav button {section}: expected one, found {len(matches)}")
        html = pattern.sub(lambda m: m.group(1) + SVG.format(paths) + m.group(2), html, count=1)
    return html


def apply(repo: Path) -> None:
    css_path = repo / "web" / "app.css"
    pages_path = repo / "include" / "web_pages.h"
    for path in (css_path, pages_path):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")
    css = css_path.read_text(encoding="utf-8")
    if MARKER in css:
        print("Portal icon rail already applied")
        return
    if "LocalAI design system:" not in css:
        raise PatchError("run apply_workshop_os12_portal_localai_theme.py before the icon rail")
    pages = add_icons(pages_path.read_text(encoding="utf-8"))
    css_path.write_text(css.rstrip("\n") + "\n" + RAIL_CSS, encoding="utf-8")
    pages_path.write_text(pages, encoding="utf-8")
    print("Portal icon rail: 84px LocalAI-style rail on desktop, icons in the phone drawer")


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
