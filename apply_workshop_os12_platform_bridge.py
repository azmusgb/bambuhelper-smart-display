#!/usr/bin/env python3
"""Install the observation-only Workshop OS 12 platform bridge into reconstructed UI13 source."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


class PatchError(RuntimeError):
    pass


PLATFORM_HEADERS = (
    "workshop_state.hpp",
    "runtime_adapter.hpp",
    "service_contracts.hpp",
)

INVENTORY_FILES = (
    "workshop_inventory_service.h",
    "workshop_inventory_service.cpp",
)

INCLUDE_LINE = '#include "workshop_platform_bridge.h"\n'
INVENTORY_INCLUDE_LINE = '#include "workshop_inventory_service.h"\n'
INCLUDE_ANCHOR = '#include "wifi_manager.h"\n'
BEGIN_ANCHOR = "    tasmotaInit();\n"
POLL_ANCHOR = "  handleWiFi();\n"


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing source asset: {source}")
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
    marker = repo / "include" / "smart_home_build.h"
    main_cpp = repo / "src" / "main.cpp"
    if not marker.is_file() or not main_cpp.is_file():
        raise PatchError("Workshop OS 12 bridge requires reconstructed BambuHelper/UI13 source")
    marker_text = marker.read_text(encoding="utf-8")
    if "#define WORKSHOP_OS_V11_28_UI13 1" not in marker_text:
        raise PatchError("Workshop OS 12 bridge requires reconstructed v11.28 UI13 source")

    platform_source = source_root / "firmware" / "platform"
    include_target = repo / "include" / "workshop_platform"
    for name in PLATFORM_HEADERS:
        copy_exact(platform_source / name, include_target / name)

    bridge_source = platform_source / "bridge"
    copy_exact(bridge_source / "workshop_platform_bridge.h", repo / "include" / "workshop_platform_bridge.h")
    copy_exact(bridge_source / "workshop_platform_bridge.cpp", repo / "src" / "workshop_platform_bridge.cpp")

    inventory_source = platform_source / "inventory"
    copy_exact(inventory_source / "workshop_inventory_service.h", repo / "include" / "workshop_inventory_service.h")
    copy_exact(inventory_source / "workshop_inventory_service.cpp", repo / "src" / "workshop_inventory_service.cpp")

    text = main_cpp.read_text(encoding="utf-8")
    text = insert_once(text, INCLUDE_ANCHOR, INCLUDE_LINE + INVENTORY_INCLUDE_LINE, "bridge include")
    text = insert_once(text, BEGIN_ANCHOR, "    workshopPlatformBegin();\n    workshopInventoryServiceBegin();\n", "bridge begin")
    text = insert_once(text, POLL_ANCHOR, "  workshopPlatformPoll();\n  workshopInventoryServiceLoop();\n", "bridge poll")
    main_cpp.write_text(text, encoding="utf-8")

    if text.count("workshopPlatformBegin();") != 1:
        raise PatchError("workshopPlatformBegin must be injected exactly once")
    if text.count("workshopPlatformPoll();") != 1:
        raise PatchError("workshopPlatformPoll must be injected exactly once")
    if text.count("workshopInventoryServiceBegin();") != 1:
        raise PatchError("workshopInventoryServiceBegin must be injected exactly once")
    if text.count("workshopInventoryServiceLoop();") != 1:
        raise PatchError("workshopInventoryServiceLoop must be injected exactly once")

    print("Workshop OS 12 platform bridge and Filament Inventory consumer installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="reconstructed UI13 BambuHelper root")
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
