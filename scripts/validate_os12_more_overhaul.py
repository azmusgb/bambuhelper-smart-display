#!/usr/bin/env python3
"""Validate the WS350 More/System overhaul (Workshop OS 12.1.x).

String and behaviour contracts on the rebuilt src/smart_hub.cpp, plus the
host-compiled geometry and touch-routing test
tests/workshop_os12_more_layout_smoke.cpp (both orientations, every control
on every page, centre and edges).
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "firmware/platform/ui/more_layout.hpp"
TEST = ROOT / "tests/workshop_os12_more_layout_smoke.cpp"


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def run_host_test() -> str:
    with tempfile.TemporaryDirectory(prefix="os12-more-layout-") as td:
        binary = Path(td) / "more-layout-smoke"
        subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        str(TEST), "-o", str(binary)], check=True, cwd=ROOT)
        result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip()


def validate(repo: Path) -> str:
    build = read(repo / "include/smart_home_build.h")
    hub = read(repo / "src/smart_hub.cpp")
    installed = read(repo / "include/workshop_more_layout.hpp")

    need(build, "#define WORKSHOP_OS12_MORE_OVERHAUL 1", "build marker")
    if installed != read(LAYOUT):
        raise ValidationError("installed include/workshop_more_layout.hpp differs from firmware/platform/ui/more_layout.hpp")
    need(hub, '#include "workshop_more_layout.hpp"', "layout include")
    return run_host_test()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    try:
        summary = validate(Path(args.repo).resolve())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}")
    print(summary)
    print("PASS: More overhaul layout installed; geometry and touch routing hold in 480x320 and 320x480")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
