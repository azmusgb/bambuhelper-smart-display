#!/usr/bin/env python3
"""Deterministic release-gate checks for the Waveshare Smart Display repository."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    Path("README.md"),
    Path("release.json"),
    Path("releases/current.json"),
    Path(".github/workflows/validate.yml"),
    Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.2-validated.bin"),
]
FORBIDDEN_PREFIXES = ("firmware/build/",)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"missing required release asset: {rel}")

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(FORBIDDEN_PREFIXES):
            fail(f"generated build output is tracked/present in source tree: {rel}")

    for rel in (Path("release.json"), Path("releases/current.json")):
        try:
            json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON in {rel}: {exc}")

    manifest = json.loads((ROOT / "releases/current.json").read_text(encoding="utf-8"))
    if not manifest.get("version"):
        fail("releases/current.json has no version")
    if not manifest.get("channel"):
        fail("releases/current.json has no channel")

    print("Release gate: PASS")
    print(f"Current release: {manifest['version']} ({manifest['channel']})")
    print("Required firmware asset: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
