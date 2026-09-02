#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import zlib
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parent / ".bambuhelper-validation" / "v10-1-hardware.zlib.b64"


class PatchError(RuntimeError):
    pass


def load_core() -> dict:
    if not PAYLOAD.exists():
        raise PatchError(f"v10.1 hardware payload missing: {PAYLOAD}")
    try:
        source = zlib.decompress(base64.b64decode(PAYLOAD.read_text().strip())).decode("utf-8")
    except Exception as exc:
        raise PatchError(f"v10.1 hardware payload decode failed: {exc}") from exc
    ns = {"__name__": "v10_1_hardware_core", "__file__": str(PAYLOAD)}
    exec(compile(source, str(PAYLOAD), "exec"), ns, ns)
    if "apply" not in ns or "verify" not in ns:
        raise PatchError("v10.1 hardware core missing apply()/verify()")
    return ns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        print("Smart Home v10.1 Hardware + Audio patch ready. Use --apply.")
        return 0
    core = load_core()
    repo = Path(args.repo).resolve()
    core["apply"](repo)
    core["verify"](repo)
    print("Smart Home v10.1 Hardware + Audio applied and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
