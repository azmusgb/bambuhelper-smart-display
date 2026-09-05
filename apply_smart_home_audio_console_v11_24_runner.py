#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import apply_smart_home_audio_console_v11_24 as base


def block_bounds_from_match(text: str, start: int, label: str) -> tuple[int, int]:
    brace = text.find("{", start)
    if brace < 0:
        raise base.PatchError(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise base.PatchError(f"{label}: closing brace missing")


def robust_function_body(text: str, signature_fragment: str, label: str) -> tuple[int, int, str]:
    if signature_fragment != "int buzzerBackendMicEcho(":
        return base._v1124_original_function_body(text, signature_fragment, label)

    matches = list(re.finditer(
        r"(?m)^[ \t]*int[ \t]+buzzerBackendMicEcho[ \t]*\([^;{]*\)[ \t]*\{",
        text,
    ))
    candidates: list[tuple[int, int, str]] = []
    for match in matches:
        a, b = block_bounds_from_match(text, match.start(), label)
        block = text[a:b]
        if "1400" in block and (
            "MALLOC_CAP_SPIRAM" in block
            or "stopAudioTaskForDiagnostic" in block
            or "heap_caps_malloc" in block
        ):
            candidates.append((a, b, block))

    if len(candidates) != 1:
        raise base.PatchError(
            f"{label}: expected one PSRAM-backed definition with 1400 ms cap, "
            f"found {len(candidates)} from {len(matches)} definitions"
        )
    return candidates[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")

    base._v1124_original_function_body = base.function_body
    base.function_body = robust_function_body
    base.patch(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
