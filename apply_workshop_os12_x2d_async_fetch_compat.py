#!/usr/bin/env python3
"""Apply the X2D async fetch overlay against the real reconstructed OS12 backend.

The OS12 camera-ownership patch expands the PrinterCamera stop path into a
multi-line block. The original async overlay fixture used the older one-line
cameraStop() form, so its final stop-session anchor drifted on the actual
reconstructed tree. This compatibility wrapper preserves the original
transactional async overlay while teaching only that one anchor how to handle
both forms.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import apply_workshop_os12_x2d_async_fetch as async_fetch
from scripts.smart_home_patch_utils import PatchError


OWNERSHIP_STOP = """  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) {
    cameraStop();
    cameraSetMediaOwned(false);
  }
"""
X2D_STOP = """#if defined(ESP32)
  if (videoRequested_ && videoSource_ == VideoSource::X2dBridge) x2dStopFetchSession();
#endif
"""


def _compat_replace_once(text: str, old: str, new: str, label: str) -> str:
    if label != "X2D worker stop":
        return _ORIGINAL_REPLACE_ONCE(text, old, new, label)

    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count > 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")

    if X2D_STOP in text:
        return text

    ownership_count = text.count(OWNERSHIP_STOP)
    if ownership_count != 1:
        raise PatchError(
            f"{label}: neither legacy stop anchor nor ownership stop block is unique; "
            f"ownership blocks={ownership_count}"
        )
    return text.replace(OWNERSHIP_STOP, OWNERSHIP_STOP + X2D_STOP, 1)


_ORIGINAL_REPLACE_ONCE = async_fetch.replace_once


def apply(repo: Path) -> None:
    previous = async_fetch.replace_once
    async_fetch.replace_once = _compat_replace_once
    try:
        async_fetch.apply(repo)
    finally:
        async_fetch.replace_once = previous


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
