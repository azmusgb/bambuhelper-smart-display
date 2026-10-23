#!/usr/bin/env python3
"""Validate Figtree brand vector typography for Workshop OS (LocalAI Terminal).

Checks:
- Figtree Regular and Bold source TTF assets exist in assets/fonts/.
- Pre-compiled Figtree VLW headers exist in firmware/platform/fonts/.
- Headers carry the canonical Figtree metadata and PROGMEM symbols.
- Byte budgets match expected memory boundaries for ESP32 flash.
- Host layout smoke tests compile and pass.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT / "assets" / "fonts"
PLATFORM_FONTS = ROOT / "firmware" / "platform" / "fonts"

REQUIRED_HEADERS = {
    "inter_10.h": ("Figtree-Regular.ttf", 12, "inter_10"),
    "inter_14.h": ("Figtree-Regular.ttf", 16, "inter_14"),
    "inter_19.h": ("Figtree-Bold.ttf", 22, "inter_19"),
    "inter_22.h": ("Figtree-Bold.ttf", 26, "inter_22"),
}


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        sys.exit(1)


def validate_source_assets() -> None:
    print("Validating Figtree source TTF assets...")
    for ttf in ["Figtree-Regular.ttf", "Figtree-Bold.ttf"]:
        p = FONTS_DIR / ttf
        check(p.is_file(), f"missing source font: {p}")
        check(p.stat().st_size > 10000, f"font asset {ttf} is unexpectedly small")
    print("  PASS: Source TTF assets present and valid.")


def validate_headers(fonts_dir: Path, label: str) -> None:
    print(f"Validating font headers in {label} ({fonts_dir})...")
    check(fonts_dir.is_dir(), f"missing fonts directory: {fonts_dir}")
    total_bytes = 0
    for filename, (source_ttf, pixel_size, symbol) in REQUIRED_HEADERS.items():
        header_path = fonts_dir / filename
        check(header_path.is_file(), f"missing header: {header_path}")
        content = header_path.read_text(encoding="utf-8")
        check(f"Figtree VLW font: {symbol}" in content, f"{filename} missing Figtree header comment")
        check(f"const uint8_t {symbol}[] PROGMEM" in content, f"{filename} missing symbol {symbol}")
        size = header_path.stat().st_size
        total_bytes += size
        check(20000 < size < 700000, f"{filename} size {size} out of expected bounds")
    print(f"  PASS: All 4 Figtree headers verified ({total_bytes / 1024:.1f} KB total source text).")


def run_host_smoke_tests() -> None:
    print("Running host layout smoke tests...")
    tests = [
        ROOT / "tests" / "workshop_os12_tabs_layout_smoke.cpp",
        ROOT / "tests" / "workshop_os12_more_layout_smoke.cpp",
    ]
    with tempfile.TemporaryDirectory() as td:
        for test_src in tests:
            bin_path = Path(td) / test_src.stem
            res = subprocess.run(
                ["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic", str(test_src), "-o", str(bin_path)],
                capture_output=True, text=True
            )
            check(res.returncode == 0, f"compilation of {test_src.name} failed:\n{res.stderr}")
            run_res = subprocess.run([str(bin_path)], capture_output=True, text=True)
            check(run_res.returncode == 0, f"smoke test {test_src.name} failed:\n{run_res.stdout}\n{run_res.stderr}")
            for line in run_res.stdout.splitlines():
                if "smoke: PASS" in line:
                    print(f"  {line.strip()}")
    print("  PASS: Host layout smoke tests passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="Optional reconstructed build tree to validate")
    args = parser.parse_args()

    validate_source_assets()
    validate_headers(PLATFORM_FONTS, "firmware/platform/fonts")

    if args.repo:
        repo_fonts = args.repo / "include" / "fonts"
        validate_headers(repo_fonts, f"{args.repo.name}/include/fonts")

    run_host_smoke_tests()

    print("\nFIGTREE BRAND TYPOGRAPHY VALIDATION: PASS")


if __name__ == "__main__":
    main()
