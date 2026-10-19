#!/usr/bin/env python3
"""Show the running Workshop OS release in the portal's version labels.

The header pill read SMART_HOME_VERSION ("v11.28", the old UI generation) and
the sidebar brand and footer hard-coded "12.0.0", so a 12.3.x build announced
two wrong versions. %SMART_VER% now expands to WORKSHOP_OS_RELEASE_VERSION
(set per build by apply_workshop_os12_release_identity.py), and both sidebar
labels use it.
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
    template.write_text(t, encoding="utf-8")
    pages.write_text(p, encoding="utf-8")
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
