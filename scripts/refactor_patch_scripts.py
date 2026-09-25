#!/usr/bin/env python3
"""Strip locally-defined helpers from apply_*.py and import them from utils."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ["fail", "replace_once", "replace_braced_block"]
IMPORT_LINE = "from scripts.smart_home_patch_utils import fail, replace_once, replace_braced_block\n"

def strip_def(source: str, name: str) -> tuple[str, bool]:
    """Remove a top-level def block by name. Returns (new_source, changed)."""
    pattern = re.compile(
        rf"^def {name}\(.*?\)(?:\s*->\s*[^:]+)?:\n(?:[ \t].*\n|\n)*",
        re.MULTILINE,
    )
    new_source, n = pattern.subn("", source, count=1)
    return new_source, n > 0

def process(path: Path) -> None:
    if path.name == "smart_home_patch_utils.py":
        return
    source = path.read_text()
    changed = False
    for helper in HELPERS:
        source, did = strip_def(source, helper)
        changed = changed or did
    if not changed:
        return
    # Add the import right after the last top-level import
    if "from smart_home_patch_utils import" not in source:
        lines = source.splitlines(keepends=True)
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith(("import ", "from ")):
                insert_at = i + 1
        lines.insert(insert_at, IMPORT_LINE)
        source = "".join(lines)
    path.write_text(source)
    print(f"refactored {path.name}")

def main() -> int:
    targets = sorted(ROOT.glob("apply_*.py"))
    if not targets:
        print("No apply_*.py files found.", file=sys.stderr)
        return 1
    for path in targets:
        process(path)
    print(f"\nDone. Processed {len(targets)} files.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
