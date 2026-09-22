#!/usr/bin/env python3
"""Validate targeted OS12 physical-acceptance UI refinements."""
from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def check(repo: Path) -> None:
    hub = load(repo / "src" / "smart_hub.cpp")
    web = load(repo / "src" / "web_server.cpp")

    required_hub = (
        '"PRINTER STATUS"',
        '"PRINT JOB"',
        '"Filament Inventory"',
        '"ATTENTION"',
        '"Print Readiness"',
        '"Loaded Spools"',
        '"Use - / + to change"',
        '"24-Hour Clock"',
        '"CURRENT VERSION"',
        '"Release State"',
        '"Update Method"',
        '"Only exact validated artifacts"',
    )
    for marker in required_hub:
        if marker not in hub:
            raise ValidationError(f"missing refined UI marker: {marker}")

    normalized = web.replace('\\\"', '"')
    workshop_lines = [
        line for line in normalized.splitlines()
        if '"id":"workshop"' in line
    ]
    if len(workshop_lines) != 1:
        raise ValidationError(
            f"Workshop capture catalog entry expected once, found {len(workshop_lines)}"
        )
    if '"label":"Workshop"' not in workshop_lines[0]:
        raise ValidationError("Workshop capture catalog label is not Workshop")
    if '"label":"Tools"' in workshop_lines[0]:
        raise ValidationError("stale Tools label remains on Workshop capture route")

    print("PASS: OS12 physical acceptance UI refinements are present and stale labels are retired")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    try:
        check(Path(args.repo).resolve())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
