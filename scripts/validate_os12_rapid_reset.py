#!/usr/bin/env python3
"""Validate the NVS-backed triple-reset Safe Mode entry (12.1.1).

Checks the rebuilt recovery_manager.cpp counts rapid resets in NVS rather than
RTC_DATA_ATTR memory, clears the count after the 15 s window, and runs the
host test of the counting rule.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests/workshop_os12_rapid_reset_smoke.cpp"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        fail(f"missing function: {signature}")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    fail(f"unterminated function: {signature}")
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    cpp = (repo / "src/recovery_manager.cpp").read_text(encoding="utf-8")
    build = (repo / "include/smart_home_build.h").read_text(encoding="utf-8")

    if "#define WORKSHOP_OS12_RAPID_RESET_NVS 1" not in build:
        fail("rapid-reset build marker missing")
    if not (repo / "include/workshop_rapid_reset_policy.hpp").is_file():
        fail("rapid-reset policy header not installed")
    # RTC_DATA_ATTR is re-initialised on every non-deep-sleep reset.
    for line in cpp.splitlines():
        if "RTC_DATA_ATTR" in line and re.search(r"sRapid", line):
            fail(f"rapid-reset state is still in RTC_DATA_ATTR memory: {line.strip()}")
    if "sRapidMagic" in cpp:
        fail("RTC magic word still present")

    probe = block(cpp, "void recoveryBootProbe()")
    for needle in ('prefs.getUChar("rapid",0)', 'prefs.putUChar("rapid",next)',
                   "workshop::recovery::rapidResetOnBoot(", "sSafeMode=true;"):
        if needle not in probe:
            fail(f"boot probe missing {needle!r}")
    if probe.find('prefs.putUChar("rapid",next)') > probe.find("loadState();"):
        fail("rapid count must be stored before candidate handling can restart the device")

    tick = block(cpp, "void recoveryTick()")
    for needle in ("workshop::recovery::rapidResetWindowClosed(", 'prefs.putUChar("rapid",0)'):
        if needle not in tick:
            fail(f"recoveryTick missing {needle!r}")

    with tempfile.TemporaryDirectory(prefix="os12-rapid-reset-") as td:
        binary = Path(td) / "rapid-reset-smoke"
        subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        str(TEST), "-o", str(binary)], check=True, cwd=ROOT)
        subprocess.run([str(binary)], check=True, cwd=ROOT)

    print("PASS: triple reset counts in NVS, clears after 15 s of uptime and enters Safe Mode on the third rapid boot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
