#!/usr/bin/env python3
"""Raw-colour guard for the display's UI code (display-kit K7).

The display takes every colour from the kit's tokens (assets/ui/tokens.h, UI_COLOR_*). This check fails on

  - a raw `0x....` RGB565 colour literal, and
  - a new palette constant (`static const uint16_t NAME = <literal>`, `#define NAME 0x....`, a `color565(...)` call)

in UI code: firmware/platform/**, firmware/ui-*/** and the apply_*.py scripts that carry the UI's C++. An alias of a
kit token (`= UI_COLOR_ACCENT;`, `= uiTint565(...)`) is not a palette constant.

Files not yet ported to the kit's parts are on an allow list, scripts/ui_raw_colour_allowlist.json, that may only
shrink: each entry is the file and the number of offending lines in it today. The check fails when

  - a file not on the list has an offence (a new raw colour);
  - a listed file has more offences than its entry (it grew);
  - a listed file has fewer (lower the entry) or none (remove it: the file is clean), or no longer exists;
  - with --base REF, an entry is added or raised compared with the list at REF (the list grew).

  python3 scripts/validate_ui_raw_colours.py                    check
  python3 scripts/validate_ui_raw_colours.py --base origin/main also compare the list with the base branch's
  python3 scripts/validate_ui_raw_colours.py --update           rewrite the list from the tree; refuses to add or raise (but writes the first one)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = Path("scripts") / "ui_raw_colour_allowlist.json"

# UI code: tracked files only.
SCOPE = (
    re.compile(r"^firmware/platform/(?!fonts/).+\.(?:cppfrag|hpp|h|cpp)$"),
    re.compile(r"^firmware/ui-[^/]+/.+\.(?:cppfrag|hpp|h|cpp)$"),
    re.compile(r"^(?:vendor/[^/]+/)?apply_[^/]+\.py$"),
)
# In scope by path but not UI: these have 0x.... values that are not colours.
NOT_COLOURS = {
    "firmware/platform/ui/lab_judge.hpp": "a JSON string decoder: 0xD800..0xDFFF are UTF-16 surrogates",
}

RAW_COLOUR = re.compile(r"(?<![\w.])0[xX][0-9A-Fa-f]{4}(?![\w.])")
# A uint16_t (or define) given a colour that is not a kit token: a literal, a color565() call, a TFT_* name.
PALETTE_CONSTANT = re.compile(
    r"(?:\b(?:static\s+)?(?:constexpr\s+|const\s+)+uint16_t\s+[A-Za-z_]\w*\s*=\s*(?:0[xX][0-9A-Fa-f]+|\(?\s*(?:uint16_t\)\s*)?(?:\w+(?:\.|->))?(?:color565|RGB565|rgb565|TFT_)\w*))"
    r"|(?:^\s*#\s*define\s+[A-Z][A-Z0-9_]*\s+0[xX][0-9A-Fa-f]+)"
)


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.decode()
    return sorted(f for f in out.split("\0") if f and any(p.match(f) for p in SCOPE) and f not in NOT_COLOURS)


def offences(text: str) -> list[int]:
    """Line numbers (1-based) that hold a raw colour literal or declare a palette constant."""
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        if RAW_COLOUR.search(line) or PALETTE_CONSTANT.search(line):
            lines.append(number)
    return lines


def scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for name in tracked_files():
        path = ROOT / name
        if not path.is_file():
            continue
        hits = offences(path.read_text(encoding="utf-8", errors="replace"))
        if hits:
            found[name] = hits
    return found


def read_list(text: str) -> dict[str, int]:
    data = json.loads(text)
    files = data.get("files")
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in files.items()):
        raise SystemExit(f"{ALLOWLIST}: 'files' must map a path to a positive count")
    return dict(files)


def list_at(ref: str) -> dict[str, int] | None:
    result = subprocess.run(["git", "show", f"{ref}:{ALLOWLIST.as_posix()}"], cwd=ROOT, capture_output=True)
    if result.returncode != 0:
        return None  # the list did not exist at the base: the first one is the baseline
    return read_list(result.stdout.decode())


def problems(found: dict[str, list[int]], allowed: dict[str, int], base: dict[str, int] | None) -> list[str]:
    out: list[str] = []
    for name, hits in sorted(found.items()):
        shown = ", ".join(str(n) for n in hits[:6]) + (" ..." if len(hits) > 6 else "")
        if name not in allowed:
            out.append(f"{name}:{hits[0]}: raw colour or new palette constant (lines {shown}). Use a kit token (UI_COLOR_*); "
                       f"do not add the file to the allow list.")
        elif len(hits) > allowed[name]:
            out.append(f"{name}: {len(hits)} raw colour lines, the allow list has {allowed[name]} (lines {shown}). The list may only shrink.")
        elif len(hits) < allowed[name]:
            out.append(f"{name}: now {len(hits)} raw colour lines; lower its allow-list entry from {allowed[name]} to {len(hits)}.")
    for name, count in sorted(allowed.items()):
        if name not in found:
            exists = (ROOT / name).is_file()
            out.append(f"{name}: on the allow list but {'clean' if exists else 'gone'}: remove the entry.")
    if base is not None:
        for name, count in sorted(allowed.items()):
            if name not in base:
                out.append(f"{name}: added to the allow list since the base. The list may only shrink.")
            elif count > base[name]:
                out.append(f"{name}: allow-list entry raised from {base[name]} to {count}. The list may only shrink.")
    return out


def write_list(found: dict[str, list[int]]) -> str:
    body = {
        "note": "Files not yet on the kit's display parts (display-kit K7). May only shrink: scripts/validate_ui_raw_colours.py. "
                "Each value is the number of lines with a raw 0x.... colour or a new palette constant. Rollout steps 4 and 5 remove entries.",
        "files": {name: len(hits) for name, hits in sorted(found.items())},
    }
    return json.dumps(body, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="a git ref whose allow list this one may not exceed (e.g. origin/main)")
    ap.add_argument("--update", action="store_true", help="rewrite the allow list from the tree (never adds or raises an entry)")
    args = ap.parse_args()

    found = scan()
    path = ROOT / ALLOWLIST
    allowed = read_list(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if args.update:
        grown = [n for n, hits in found.items() if len(hits) > allowed.get(n, 0)] if path.is_file() else []  # no list yet: today's offenders
        if grown:
            print("FAIL: --update only shrinks the list; these files are new or grew: " + ", ".join(grown), file=sys.stderr)
            return 1
        path.write_text(write_list(found), encoding="utf-8")
        print(f"allow list: {len(found)} files, {sum(len(h) for h in found.values())} lines")
        return 0
    base = list_at(args.base) if args.base else None
    errors = problems(found, allowed, base)
    if errors:
        print("FAIL: raw-colour guard", file=sys.stderr)
        for line in errors:
            print("  " + line, file=sys.stderr)
        return 1
    print(f"raw-colour guard: PASS ({len(allowed)} files on the allow list, {sum(allowed.values())} lines"
          f"{'; list no larger than ' + args.base if base is not None else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
