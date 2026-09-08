#!/usr/bin/env python3
"""Verify the RC6 secure acceptance binary and retained RC5 UI5 assets.

Runtime-relevant strings are verified in compiled bytes. Compile-time-only
security guards are intentionally verified by the source contract validator,
because a successful preprocessor guard is absent from the resulting binary.
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
        out.append({"offset": pos, "compressed_bytes": consumed, "plain": plain,
                    "plain_bytes": len(plain), "sha256": sha256(plain)})
    return out


def require_bytes(blob: bytes, needle: str) -> None:
    if needle.encode("utf-8") not in blob:
        raise SystemExit(f"FAIL: compiled application missing RC6 marker: {needle}")


def forbid_bytes(blob: bytes, needle: str) -> None:
    if needle.encode("utf-8") in blob:
        raise SystemExit(f"FAIL: compiled application contains forbidden test marker: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--full", required=True)
    ap.add_argument("--css", required=True)
    ap.add_argument("--report")
    args = ap.parse_args()

    app_path, full_path, css_path = Path(args.app), Path(args.full), Path(args.css)
    app, full = app_path.read_bytes(), full_path.read_bytes()
    css_layer = css_path.read_bytes().rstrip() + b"\n"

    if len(full) < APP_OFFSET + len(app):
        raise SystemExit("FAIL: Full image is too small to contain application at 0x10000")
    if full[APP_OFFSET:APP_OFFSET + len(app)] != app:
        raise SystemExit("FAIL: Full image does not contain exact OTA/application image at 0x10000")

    native_markers = [
        "Workshop OS v11.25 RC6 Secure Physical Acceptance",
        "UI5-H", "UI5-P", "UI5-W", "UI5-M", "UI5-S",
        "ATTENTION", "ALL CLEAR", "OPEN PRINTER",
        "Inventory: Unknown", "Printer telemetry only", "DIRECT CONTROLS",
        "Stop requires hold", "DEVICE HEALTH", "PORTAL CODE",
        "Workshop OS Secure Sign In", "Secure LAN access", "Sign in securely",
        "portal-code", "stationConnected", "stationIp", "softApIp",
    ]
    for marker in native_markers:
        require_bytes(app, marker)
    forbid_bytes(app, "TEST / NO CODE")
    forbid_bytes(app, "physical-test no-code build requires")

    members = gzip_members(app)
    css_member = None
    for member in members:
        plain = member["plain"]
        assert isinstance(plain, bytes)
        if css_layer in plain:
            css_member = member
            break
    if css_member is None:
        raise SystemExit("FAIL: exact retained RC5 portal CSS layer not found in embedded gzip assets")

    report = {
        "status": "PASS",
        "app": {"path": app_path.name, "bytes": len(app), "sha256": sha256(app)},
        "full": {"path": full_path.name, "bytes": len(full), "sha256": sha256(full),
                 "app_offset": APP_OFFSET, "exact_app_embedding": True},
        "native_markers": native_markers,
        "source_only_guards": ["RC6 secure physical acceptance forbids WORKSHOP_OS_TEMP_NO_CODE_LAN"],
        "forbidden_markers_absent": ["TEST / NO CODE", "physical-test no-code build requires"],
        "gzip_members": [{"offset": int(m["offset"]), "compressed_bytes": int(m["compressed_bytes"]),
                          "plain_bytes": int(m["plain_bytes"]), "sha256": str(m["sha256"])} for m in members],
        "portal_css": {"source": css_path.name, "bytes": len(css_layer), "sha256": sha256(css_layer),
                       "embedded_exactly": True, "gzip_offset": int(css_member["offset"])},
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("RC6 secure compiled binary verification: PASS")
    print("full_contains_exact_app_at_0x10000=PASS")
    print(f"secure_runtime_markers={len(native_markers)}_PASS")
    print("compile_time_no_code_guard=SOURCE_VALIDATED")
    print("temp_no_code_runtime_markers=ABSENT")
    print("embedded_rc5_css=EXACT_BYTE_MATCH")
    print(f"app_sha256={report['app']['sha256']}")
    print(f"full_sha256={report['full']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
