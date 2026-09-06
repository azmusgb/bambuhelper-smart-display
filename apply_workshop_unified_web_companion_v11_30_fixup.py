#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Workshop OS v11.30 Companion jump-target fixup"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to mutate without --apply")

    root = Path(args.repo).resolve()
    build_path = root / "include" / "smart_home_build.h"
    companion_path = root / "src" / "companion_web.cpp"
    build = build_path.read_text(encoding="utf-8")
    companion = companion_path.read_text(encoding="utf-8")

    if 'SMART_HOME_VERSION "v11.30"' not in build:
        raise SystemExit("v11.30 reconstructed source is required")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return 0

    old = "var cards=document.querySelectorAll('.card');if(cards[i])cards[i].scrollIntoView"
    new = "var cards=document.querySelectorAll('.card:not(#v1130AttentionCard)');if(cards[i])cards[i].scrollIntoView"
    count = companion.count(old)
    if count != 1:
        raise SystemExit(f"Companion jump target anchor: expected 1 match, found {count}")
    companion = companion.replace(old, new, 1)
    companion_path.write_text(companion, encoding="utf-8")
    build_path.write_text(build + f"\n// {MARKER}\n", encoding="utf-8")

    final = companion_path.read_text(encoding="utf-8")
    if ".card:not(#v1130AttentionCard)" not in final:
        raise SystemExit("Companion operational-card selector missing after fixup")
    if "querySelectorAll('.card');" in final[final.find('v1130CompanionEnhance'):]:
        raise SystemExit("stale Companion all-card jump selector remains")

    print("Workshop OS v11.30 Companion jump targets: PASS")
    print("Overview -> printer overview")
    print("Controls -> quick controls")
    print("Photo -> phone/photo handoff")
    print("System -> connection/system")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
