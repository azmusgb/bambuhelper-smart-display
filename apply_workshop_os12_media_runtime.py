#!/usr/bin/env python3
"""Install the Workshop OS 12 media runtime into reconstructed UI13 source."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


class PatchError(RuntimeError):
    pass


MEDIA_HEADERS = (
    "media_service.h",
    "ws350_media_backend.h",
    "workshop_media_runtime.h",
)
MEDIA_SOURCES = (
    "media_service.cpp",
    "ws350_media_backend.cpp",
    "workshop_media_runtime.cpp",
)

INCLUDE_ANCHOR = '#include "workshop_platform_bridge.h"\n'
INCLUDE_LINE = '#include "workshop_media_runtime.h"\n'
BEGIN_ANCHOR = "    workshopPlatformBegin();\n"
POLL_ANCHOR = "  workshopPlatformPoll();\n"


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing media source asset: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def insert_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def apply(repo: Path, source_root: Path) -> None:
    main_cpp = repo / "src" / "main.cpp"
    build_h = repo / "include" / "smart_home_build.h"
    buzzer_h = repo / "src" / "buzzer_backend.h"
    if not main_cpp.is_file() or not build_h.is_file() or not buzzer_h.is_file():
        raise PatchError("OS12 media runtime requires reconstructed firmware source")

    build_text = build_h.read_text(encoding="utf-8")
    if "WORKSHOP_OS_RELEASE_VERSION" not in build_text:
        raise PatchError("OS12 media runtime must be applied after release identity")

    # The OS12 backend intentionally reuses the proven ES8311 volume/tone API.
    # If this contract disappears from the reconstructed baseline, fail instead
    # of silently creating a second audio implementation.
    buzzer_text = buzzer_h.read_text(encoding="utf-8")
    if "buzzerBackendSetVolume" not in buzzer_text:
        raise PatchError("reconstructed audio backend lacks buzzerBackendSetVolume contract")

    media_root = source_root / "firmware" / "platform" / "media"
    for name in MEDIA_HEADERS:
        copy_exact(media_root / name, repo / "include" / name)
    for name in MEDIA_SOURCES:
        copy_exact(media_root / name, repo / "src" / name)

    text = main_cpp.read_text(encoding="utf-8")
    text = insert_once(text, INCLUDE_ANCHOR, INCLUDE_LINE, "media runtime include")
    text = insert_once(text, BEGIN_ANCHOR, "    workshopMediaBegin();\n", "media begin")
    text = insert_once(text, POLL_ANCHOR, "  workshopMediaPoll();\n", "media poll")
    main_cpp.write_text(text, encoding="utf-8")

    if text.count("workshopMediaBegin();") != 1:
        raise PatchError("workshopMediaBegin must be injected exactly once")
    if text.count("workshopMediaPoll();") != 1:
        raise PatchError("workshopMediaPoll must be injected exactly once")

    print("Workshop OS 12 media runtime installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
