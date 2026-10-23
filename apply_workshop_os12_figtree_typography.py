#!/usr/bin/env python3
"""Install Figtree brand typography (LocalAI Suite) into Workshop OS (WS350).

Replaces the default Inter VLW font headers in include/fonts/ with the
canonical Figtree Regular and Bold tables generated from assets/fonts/.
This brings 100% typographic parity across all three LocalAI surfaces:
  - LocalAI Hub (Figtree Web)
  - LocalAI Materials (Figtree PWA)
  - LocalAI Terminal (Figtree VLW on ST7796 480x320 hardware)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import replace_once

ROOT = Path(__file__).resolve().parent
FONTS_SRC = ROOT / "firmware" / "platform" / "fonts"

FONT_HEADERS = [
    "inter_10.h",  # Figtree Regular 12px (FONT_SMALL)
    "inter_14.h",  # Figtree Regular 16px (FONT_BODY)
    "inter_19.h",  # Figtree Bold 22px    (FONT_LARGE)
    "inter_22.h",  # Figtree Bold 26px    (FONT_XLARGE)
]


def apply(repo: Path) -> None:
    dest_dir = repo / "include" / "fonts"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for header in FONT_HEADERS:
        src = FONTS_SRC / header
        if not src.is_file():
            raise SystemExit(f"FAIL: missing source Figtree font header: {src}")
        dst = dest_dir / header
        shutil.copy2(src, dst)
        print(f"Installed Figtree font header: {dst.relative_to(repo)}")

    # Update include/fonts.h comments to document Figtree branding
    fonts_h = repo / "include" / "fonts.h"
    if fonts_h.is_file():
        text = fonts_h.read_text(encoding="utf-8")
        old_desc = "// Smooth VLW font identifiers - values match the old bitmap font numbers"
        new_desc = "// Figtree brand typography (LocalAI Suite) - smooth VLW font identifiers"
        text = replace_once(text, old_desc, new_desc, "fonts.h Figtree description")
        fonts_h.write_text(text, encoding="utf-8")

    # Update src/fonts.cpp comments
    fonts_cpp = repo / "src" / "fonts.cpp"
    if fonts_cpp.is_file():
        text = fonts_cpp.read_text(encoding="utf-8")
        marker = "// Brand Typography: Figtree (LocalAI Appliance Suite)"
        if marker not in text:
            old_blob = '#include "fonts/inter_10.h"'
            new_blob = f'{marker}\n#include "fonts/inter_10.h"'
            text = replace_once(text, old_blob, new_blob, "fonts.cpp Figtree marker")
            fonts_cpp.write_text(text, encoding="utf-8")

    print("PASS: Figtree vector typography installed across all font sizes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Reconstructed build directory")
    parser.add_argument("--apply", action="store_true", help="Apply the patch")
    args = parser.parse_args()

    if not args.apply:
        print("Dry run: specify --apply to install Figtree typography.")
        return

    apply(args.repo)


if __name__ == "__main__":
    main()
