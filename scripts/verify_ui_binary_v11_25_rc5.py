#!/usr/bin/env python3
"""Prove that the RC5 native UI and portal CSS reached the compiled firmware.

This intentionally validates bytes, not only source contracts. It verifies that
Full.bin embeds the exact application image at 0x10000, that RC5 native renderer
markers are present in that application image, and that the exact final RC5 CSS
layer is inside one of the gzip-compressed web assets embedded in firmware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zlib
from pathlib import Path

APP_OFFSET = 0x10000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gzip_members(blob: bytes) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for match in re.finditer(b"\x1f\x8b\x08", blob):
        pos = match.start()
        try:
            decomp = zlib.decompressobj(31)
            plain = decomp.decompress(blob[pos:]) + decomp.flush()
        except zlib.error:
            continue
        consumed = len(blob[pos:]) - len(decomp.unused_data)
        if consumed <= 18 or not plain:
            continue
        out.append({
            "offset": pos,
            "compressed_bytes": consumed,
            "plain": plain,
            "plain_bytes": len(plain),
            "sha256": sha256(plain),
        })
    return out


def require_bytes(blob: bytes, needle: str) -> None:
    raw = needle.encode("utf-8")
    if raw not in blob:
        raise SystemExit(f"FAIL: compiled application missing native UI marker: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--full", required=True)
    ap.add_argument("--css", required=True)
    ap.add_argument("--report")
    args = ap.parse_args()

    app_path = Path(args.app)
    full_path = Path(args.full)
    css_path = Path(args.css)
    app = app_path.read_bytes()
    full = full_path.read_bytes()
    css_layer = css_path.read_bytes().rstrip() + b"\n"

    if len(full) < APP_OFFSET + len(app):
        raise SystemExit("FAIL: Full image is too small to contain application at 0x10000")
    if full[APP_OFFSET:APP_OFFSET + len(app)] != app:
        raise SystemExit("FAIL: Full image does not contain the exact OTA/application image at 0x10000")

    native_markers = [
        "Workshop OS v11.25 RC5 Native UI Acceptance",
        "UI5-H",
        "UI5-P",
        "UI5-W",
        "UI5-M",
        "UI5-S",
        "ATTENTION",
        "ALL CLEAR",
        "OPEN PRINTER",
        "Inventory: Unknown",
        "Printer telemetry only",
        "DIRECT CONTROLS",
        "Stop requires hold",
        "DEVICE HEALTH",
        "TEST / NO CODE",
    ]
    for marker in native_markers:
        require_bytes(app, marker)

    members = gzip_members(app)
    css_member = None
    for member in members:
        plain = member["plain"]
        assert isinstance(plain, bytes)
        if css_layer in plain:
            css_member = member
            break
    if css_member is None:
        raise SystemExit("FAIL: exact RC5 portal CSS layer not found inside embedded gzip web assets")

    report = {
        "status": "PASS",
        "app": {
            "path": app_path.name,
            "bytes": len(app),
            "sha256": sha256(app),
        },
        "full": {
            "path": full_path.name,
            "bytes": len(full),
            "sha256": sha256(full),
            "app_offset": APP_OFFSET,
            "exact_app_embedding": True,
        },
        "native_markers": native_markers,
        "gzip_members": [
            {
                "offset": int(m["offset"]),
                "compressed_bytes": int(m["compressed_bytes"]),
                "plain_bytes": int(m["plain_bytes"]),
                "sha256": str(m["sha256"]),
            }
            for m in members
        ],
        "portal_css": {
            "source": css_path.name,
            "bytes": len(css_layer),
            "sha256": sha256(css_layer),
            "embedded_exactly": True,
            "gzip_offset": int(css_member["offset"]),
        },
    }

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("RC5 compiled UI binary verification: PASS")
    print("full_contains_exact_app_at_0x10000=PASS")
    print(f"native_ui_markers={len(native_markers)}_PASS")
    print("embedded_rc5_css=EXACT_BYTE_MATCH")
    print(f"app_sha256={report['app']['sha256']}")
    print(f"full_sha256={report['full']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
