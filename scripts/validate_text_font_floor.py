#!/usr/bin/env python3
"""Text-size floor for the display (display-kit K3: Archivo everywhere, nothing under 14 px).

Fails if a text font under 14 px can be reached:

  - baseline/files/src/fonts.cpp maps every text FontID to a kit Archivo face of index 0..3 (14, 16, 20, 26 px), loads
    nothing else, includes no other font table, and its bitmap fallback uses only built-in fonts of 16 px or more;
  - the kit's Archivo VLW files are all 14 px or larger (name and VLW header);
  - no UI code selects a built-in bitmap font under 16 px (setTextFont 0, 1, 3 or 5, lgfx::fonts::Font0/Font1/Font3/
    Font5, a Free/GFX font), loads a VLW outside fonts.cpp and the kit adapter, or sets a text size under 1.

  python3 scripts/validate_text_font_floor.py
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS_CPP = Path("baseline/files/src/fonts.cpp")
VLW_DIR = Path("assets/ui/display/fonts")
MIN_PX = 14
SCOPE = (
    re.compile(r"^baseline/files/(?:src|include)/.+\.(?:cpp|h|hpp)$"),
    re.compile(r"^firmware/platform/.+\.(?:cppfrag|hpp|h|cpp)$"),
    re.compile(r"^(?:vendor/[^/]+/)?apply_[^/]+\.py$"),
)
LOADERS = {"baseline/files/src/fonts.cpp", "firmware/platform/ui/lgfx_canvas.hpp"}
SMALL_BUILTIN = re.compile(r"setTextFont\s*\(\s*([0135])\s*\)|fonts::(?:Font[0135]|TomThumb|Org_01|Picopixel|FreeMono\w*|FreeSans\w*|FreeSerif\w*)\b|setFreeFont\s*\(")
TEXT_SIZE = re.compile(r"setTextSize\s*\(\s*(0(?:\.\d+)?f?|0?\.\d+f?)\s*[,)]")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.decode()
    return sorted(f for f in out.split("\0") if f and any(p.match(f) for p in SCOPE))


def check_vlw(problems: list[str]) -> None:
    files = sorted((ROOT / VLW_DIR).glob("*.vlw"))
    if not files:
        problems.append(f"{VLW_DIR}: no VLW faces found")
    for f in files:
        named = int(re.search(r"(\d+)\.vlw$", f.name).group(1))
        data = f.read_bytes()
        px = struct.unpack(">6i", data[:24])[2] if len(data) >= 24 else 0
        if named < MIN_PX or px < MIN_PX:
            problems.append(f"{VLW_DIR / f.name}: {named} px (header {px}) is under {MIN_PX} px")


def check_fonts_cpp(text: str, problems: list[str]) -> None:
    if re.search(r'#\s*include\s*"fonts/', text) or "inter_" in text or "figtree" in text.lower():
        problems.append(f"{FONTS_CPP}: another font table is included or named")
    ids = set(re.findall(r"case (FONT_[A-Z0-9]+):\s*return kWorkshopArchivoFonts\.vlw\[(kFace\d+)\]", text))
    want = {"FONT_SMALL": "kFace14", "FONT_BODY": "kFace16", "FONT_LARGE": "kFace20", "FONT_XLARGE": "kFace26"}
    if dict(ids) != want:
        problems.append(f"{FONTS_CPP}: faceFor must map {want}, found {dict(ids)}")
    faces = dict(re.findall(r"(kFace\d+)\s*=\s*(\d+)", text))
    if faces != {"kFace14": "0", "kFace16": "1", "kFace20": "2", "kFace26": "3"}:
        problems.append(f"{FONTS_CPP}: kFace indices must be 0..3 in UiFont order (14, 16, 20, 26 px), found {faces}")
    for m in re.finditer(r"(?<![A-Za-z])loadFont\s*\(", text):
        if not re.match(r"loadFont\s*\(\s*(?:faceFor\(id\)|face)\s*\)", text[m.start():]):
            problems.append(f"{FONTS_CPP}: loadFont({text[m.end():m.end() + 30].splitlines()[0]} is not an Archivo face")
    for n in re.findall(r"setTextFont\s*\(\s*(\d+)\s*\)", text):
        if int(n) not in (2, 4, 6, 7, 8):
            problems.append(f"{FONTS_CPP}: setTextFont({n}) is a bitmap font under 16 px")
    if SMALL_BUILTIN.search(text.replace("setTextFont(2)", "").replace("setTextFont(4)", "").replace("setTextFont(7)", "")):
        problems.append(f"{FONTS_CPP}: a built-in font under 16 px is reachable")


def check_scope(problems: list[str]) -> None:
    for rel in tracked():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if rel not in LOADERS and re.search(r"\bloadFont\s*\(", line):
                problems.append(f"{rel}:{i}: loadFont outside fonts.cpp and the kit adapter")
            if rel == str(FONTS_CPP):
                continue
            if SMALL_BUILTIN.search(line) or TEXT_SIZE.search(line):
                problems.append(f"{rel}:{i}: a text font under {MIN_PX} px: {line.strip()[:80]}")


def main() -> int:
    problems: list[str] = []
    path = ROOT / FONTS_CPP
    if not path.is_file():
        problems.append(f"{FONTS_CPP} missing")
    else:
        check_fonts_cpp(path.read_text(encoding="utf-8"), problems)
    check_vlw(problems)
    check_scope(problems)
    if problems:
        print("FAIL: text-size floor")
        for p in problems:
            print("  " + p)
        return 1
    print(f"text-size floor: PASS (every text face is Archivo, {MIN_PX} px or larger)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
