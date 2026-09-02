#!/usr/bin/env python3
from pathlib import Path
import argparse
import re


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart Home v9.5 experience evolution")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")

    repo = Path(args.repo)
    p = repo / "src" / "smart_hub.cpp"
    text = p.read_text(encoding="utf-8")

    print("=== SMART HUB RENDER DIAGNOSTIC ===")
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"fillScreen|fillRect|draw|render|Redraw|redraw|Tick|tick|Page|page|smartHub", line):
            lo = max(1, i - 2)
            hi = min(len(lines), i + 2)
            print(f"--- lines {lo}-{hi} ---")
            for n in range(lo, hi + 1):
                print(f"{n:04d}: {lines[n-1]}")
    print("=== END SMART HUB RENDER DIAGNOSTIC ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
