#!/usr/bin/env python3
"""Show the running Workshop OS release in the portal's version labels.

The header pill read SMART_HOME_VERSION ("v11.28", the old UI generation) and
the sidebar brand and footer hard-coded "12.0.0", so a 12.3.x build announced
two wrong versions, and app.js wrote a third ("Workshop OS v10.4 ·
ws_lcd_350") into the drawer footer. %SMART_VER% now expands to
WORKSHOP_OS_RELEASE_VERSION (set per build by
apply_workshop_os12_release_identity.py); the sidebar labels use it, the page
hands it to app.js as DEV.ver, and the footer reads DEV.ver and DEV.board.
The v9.2 orange "Workshop OS" pill, a second copy of the brand next to the
brand, is no longer added.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

TEMPLATE_OLD = 'if (strcmp(name, "SMART_VER") == 0) { out = SMART_HOME_VERSION; return true; }'
TEMPLATE_NEW = 'if (strcmp(name, "SMART_VER") == 0) { out = WORKSHOP_OS_RELEASE_VERSION; return true; }'
DEV_OLD = "<script>var DEV={board:'%BOARD%',"
DEV_NEW = "<script>var DEV={ver:'%SMART_VER%',board:'%BOARD%',"
FOOTER_OLD = "footer.innerHTML='<strong>Workshop OS v10.4</strong><span>ws_lcd_350 · local-first</span>"
FOOTER_NEW = "footer.innerHTML='<strong>Workshop OS '+(DEV.ver||'')+'</strong><span>'+(DEV.board||'WS350')+' · local-first</span>"
PILL_OLD = """  var brand = document.querySelector('.brand');
  if (brand && !document.getElementById('smartHomeBuildPill')){
    var pill = document.createElement('span');
    pill.id = 'smartHomeBuildPill';
    pill.className = 'version-pill v92-build-pill';
    pill.textContent = 'Workshop OS';
    brand.appendChild(pill);
  }
"""
PILL_NEW = "  // The brand and its version pill already name Workshop OS; no second pill.\n"
PAGE_LABELS = (
    ("<small>WS350 · 12.0.0</small>", "<small>WS350 · %SMART_VER%</small>"),
    ("<strong>Workshop OS 12.0.0</strong>", "<strong>Workshop OS %SMART_VER%</strong>"),
)


def swap(text: str, old: str, new: str, label: str) -> str:
    if new in text and old not in text:
        return text
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected one {old!r}, found {text.count(old)}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    template = repo / "src" / "web_template.cpp"
    pages = repo / "include" / "web_pages.h"
    for path in (template, pages):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")
    t = swap(template.read_text(encoding="utf-8"), TEMPLATE_OLD, TEMPLATE_NEW, "SMART_VER source")
    if "WORKSHOP_OS_RELEASE_VERSION" not in (repo / "include" / "smart_home_build.h").read_text(encoding="utf-8"):
        raise PatchError("smart_home_build.h does not define WORKSHOP_OS_RELEASE_VERSION")
    p = pages.read_text(encoding="utf-8")
    for old, new in PAGE_LABELS:
        p = swap(p, old, new, "sidebar version label")
    p = swap(p, DEV_OLD, DEV_NEW, "DEV.ver for app.js")
    script = repo / "web" / "app.js"
    if not script.is_file():
        raise PatchError(f"missing reconstructed source: {script}")
    js = swap(script.read_text(encoding="utf-8"), FOOTER_OLD, FOOTER_NEW, "drawer footer version")
    js = swap(js, PILL_OLD, PILL_NEW, "v9.2 build pill")
    template.write_text(t, encoding="utf-8")
    pages.write_text(p, encoding="utf-8")
    script.write_text(js, encoding="utf-8")
    print("Portal version labels follow WORKSHOP_OS_RELEASE_VERSION")


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
