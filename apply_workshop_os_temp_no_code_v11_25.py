#!/usr/bin/env python3
"""Temporarily disable the station-mode portal/device code for WS350 testing.

This is intentionally test-only. It bypasses the boot-scoped portal session on
normal station-mode LAN access while preserving the same-origin guard for
mutating requests and the existing AP/setup/recovery route policy.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "WORKSHOP_OS_TEMP_NO_CODE_LAN"


def fail(message: str) -> None:
    raise SystemExit(message)


def block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        fail("opening brace missing")
    depth = 0
    string = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line_comment = True
            i += 1
        elif c == "/" and n == "*":
            block_comment = True
            i += 1
        elif c in ('"', "'"):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    fail("unterminated braced block")


def replace_block(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        fail(f"{label}: signature missing/non-unique")
    return text[:start] + replacement.rstrip() + text[block_end(text, start):]


def apply(repo: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = build_path.read_text(encoding="utf-8")
    if "WORKSHOP_OS_V11_25_UI_OVERHAUL_RC2 1" not in build:
        fail("temporary no-code mode requires v11.25 RC2 source")
    if MARKER not in build:
        build += f"\n// TEMPORARY physical-acceptance mode; remove before promotion.\n#define {MARKER} 1\n"
    build_path.write_text(build, encoding="utf-8")

    security_path = repo / "src" / "security_manager.cpp"
    security = security_path.read_text(encoding="utf-8")
    if "if (mutating && !sameOrigin(server))" not in security:
        fail("same-origin mutating-request guard is missing")
    security = replace_block(
        security,
        "bool securitySessionValid(WebServer& server)",
        """bool securitySessionValid(WebServer& server) {
  ensureInitialized();
#if defined(WORKSHOP_OS_TEMP_NO_CODE_LAN) && WORKSHOP_OS_TEMP_NO_CODE_LAN
  // TEMPORARY: normal station-mode LAN access does not require the boot code.
  // AP/setup/recovery policy remains governed by the existing authorization path.
  if (!isAPMode()) return true;
#endif
  return cookieMatches(server);
}""",
        "session policy",
    )
    security_path.write_text(security, encoding="utf-8")
    print("Workshop OS v11.25 RC2 station-LAN device code disabled for physical testing")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        fail("refusing to modify source without --apply")
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
