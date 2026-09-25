#!/usr/bin/env python3
"""Temporarily enable the observed X2D/20P LAN camera path for physical testing.

Evidence for this temporary test branch:
- the configured displayed printer is local-mode and connected,
- an access code is present,
- TCP/6000 on the printer is reachable,
- the existing camera transport is otherwise the same bounded Bambu LAN path.

This patch is intentionally scoped to the temp-open-LAN physical-test branch.
It must not be promoted to accepted/stable without completed camera runtime and
physical validation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def apply(repo: Path) -> None:
    camera_path = repo / "src/camera_client.cpp"
    web_path = repo / "src/web_server.cpp"

    camera = load(camera_path)
    camera = replace_once(
        camera,
        '         strncmp(s, "039", 3) == 0 || strncmp(s, "030", 3) == 0;\n',
        '         strncmp(s, "039", 3) == 0 || strncmp(s, "030", 3) == 0 ||\n'
        '         strncmp(s, "20P", 3) == 0;\n',
        "temporary 20P camera-family gate",
    )
    camera_path.write_text(camera, encoding="utf-8")

    web = load(web_path)
    web = replace_once(
        web,
        '    doc["hasLanCamera"] = (cfg.mode == CONN_LOCAL) && cfg.accessCode[0] && p1a1;\n',
        '    doc["hasLanCamera"] = (cfg.mode == CONN_LOCAL) && cfg.accessCode[0] &&\n'
        '                          (p1a1 || strncmp(cfg.serial, "20P", 3) == 0);\n',
        "temporary 20P redacted capability status",
    )
    web_path.write_text(web, encoding="utf-8")

    final_camera = load(camera_path)
    final_web = load(web_path)
    if 'strncmp(s, "20P", 3) == 0' not in final_camera:
        raise PatchError("20P camera eligibility was not installed")
    if 'strncmp(cfg.serial, "20P", 3) == 0' not in final_web:
        raise PatchError("20P portal capability reporting was not installed")

    print("Workshop OS 12 TEMP 20P/X2D camera physical-test support installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
