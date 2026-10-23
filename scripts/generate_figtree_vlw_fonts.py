#!/usr/bin/env python3
"""Generate Figtree smooth VLW font headers for Workshop OS (LocalAI Terminal).

Produces LovyanGFX/TFT_eSPI-compatible VLW PROGMEM tables from the canonical
Figtree Regular and Bold TrueType fonts in assets/fonts/.

Font mapping:
  inter_10 (12px): Figtree Regular (FONT_SMALL, labels, footnotes, timestamps)
  inter_14 (16px): Figtree Regular (FONT_BODY, primary card titles, values, buttons)
  inter_19 (22px): Figtree Bold    (FONT_LARGE, status headers, large metric values)
  inter_22 (26px): Figtree Bold    (FONT_XLARGE, high-prominence headers)

The array names match the existing LovyanGFX loader symbols in src/fonts.cpp
for zero-friction drop-in replacement with 100% cryptographic brand parity.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

try:
    import freetype
except ImportError:
    print("ERROR: freetype-py is required. Install via: pip install freetype-py", file=sys.stderr)
    sys.exit(1)

# Character set: printable ASCII + Latin-1 Supplement + Latin Extended-A
# + Romanian comma-below S/T + Euro sign. Sorted ascending for binary search.
CHARSET = sorted(set(
    list(range(0x20, 0x7F))          # printable ASCII
    + list(range(0xA0, 0x100))       # Latin-1 Supplement (umlauts, degree, ...)
    + list(range(0x100, 0x180))      # Latin Extended-A (Polish, Czech, etc.)
    + [0x218, 0x219, 0x21A, 0x21B]   # Romanian S,s,T,t with comma below
    + [0x20AC]                       # Euro sign
))

ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT / "assets" / "fonts"

FONTS = [
    ("inter_10", "Figtree-Regular.ttf", 12),
    ("inter_14", "Figtree-Regular.ttf", 16),
    ("inter_19", "Figtree-Bold.ttf",    22),
    ("inter_22", "Figtree-Bold.ttf",    26),
]


def generate_vlw(ttf_path: Path, pixel_size: int) -> bytes:
    """Generate VLW binary data for the given font and pixel size."""
    face = freetype.Face(str(ttf_path))
    face.set_pixel_sizes(0, pixel_size)

    glyphs = []
    for codepoint in CHARSET:
        if face.get_char_index(codepoint) == 0:
            continue
        face.load_char(chr(codepoint), freetype.FT_LOAD_RENDER)
        g = face.glyph
        bmp = g.bitmap

        width = bmp.width
        height = bmp.rows
        advance = g.advance.x >> 6
        top_offset = g.bitmap_top
        left_offset = g.bitmap_left

        if width > 0 and height > 0:
            alpha = bytes(bmp.buffer)
            if bmp.pitch != width:
                alpha = b""
                for row in range(height):
                    start = row * bmp.pitch
                    alpha += bytes(bmp.buffer[start:start + width])
        else:
            alpha = b""

        glyphs.append({
            "unicode": codepoint,
            "height": height,
            "width": width,
            "advance": advance,
            "top_offset": top_offset,
            "left_offset": left_offset,
            "bitmap": alpha,
        })

    ascent = face.size.ascender >> 6
    descent = -(face.size.descender >> 6)

    buf = bytearray()
    glyph_count = len(glyphs)
    buf += struct.pack(">I", glyph_count)
    buf += struct.pack(">I", 6)           # VLW version 6
    buf += struct.pack(">I", pixel_size)
    buf += struct.pack(">I", 0)           # padding
    buf += struct.pack(">I", ascent)
    buf += struct.pack(">I", descent)

    for g in glyphs:
        buf += struct.pack(">I", g["unicode"])
        buf += struct.pack(">I", g["height"])
        buf += struct.pack(">I", g["width"])
        buf += struct.pack(">I", g["advance"])
        buf += struct.pack(">i", g["top_offset"])
        buf += struct.pack(">i", g["left_offset"])
        buf += struct.pack(">I", 0)       # padding

    for g in glyphs:
        buf += g["bitmap"]

    return bytes(buf)


def vlw_to_header(name: str, vlw_data: bytes, source_ttf: str, pixel_size: int) -> str:
    """Convert VLW binary to a C PROGMEM header."""
    lines = [
        f"// Auto-generated Figtree VLW font: {name} ({source_ttf} @ {pixel_size}px)",
        f"// Size: {len(vlw_data)} bytes ({len(vlw_data) / 1024:.1f} KB)",
        "// Brand Typography: Figtree (LocalAI Appliance Suite)",
        "#pragma once",
        "#include <pgmspace.h>",
        "",
        f"const uint8_t {name}[] PROGMEM = {{",
    ]

    for i in range(0, len(vlw_data), 16):
        chunk = vlw_data[i:i + 16]
        hex_vals = ", ".join(f"0x{b:02X}" for b in chunk)
        lines.append(f"    {hex_vals},")

    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "firmware" / "platform" / "fonts")
    parser.add_argument("--sync-upstream", action="store_true", help="Sync to upstream/include/fonts/")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for name, ttf_name, size in FONTS:
        ttf_path = FONTS_DIR / ttf_name
        if not ttf_path.exists():
            print(f"ERROR: TTF not found: {ttf_path}", file=sys.stderr)
            sys.exit(1)

        vlw_data = generate_vlw(ttf_path, size)
        header_text = vlw_to_header(name, vlw_data, ttf_name, size)

        out_file = args.out_dir / f"{name}.h"
        out_file.write_bytes(header_text.encode("utf-8"))
        print(f"Generated {out_file.name}: {len(vlw_data)} bytes ({len(vlw_data) / 1024:.1f} KB)")

        if args.sync_upstream:
            upstream_dir = ROOT / "upstream" / "include" / "fonts"
            if upstream_dir.exists():
                (upstream_dir / f"{name}.h").write_bytes(header_text.encode("utf-8"))
                print(f"  Synced to upstream/include/fonts/{name}.h")

    print("Figtree VLW generation complete.")


if __name__ == "__main__":
    main()
