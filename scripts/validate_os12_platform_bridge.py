#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_platform_bridge.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_bridge_patcher", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load bridge patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_templates() -> None:
    state = (ROOT / "firmware/platform/workshop_state.hpp").read_text(encoding="utf-8")
    adapter = (ROOT / "firmware/platform/runtime_adapter.hpp").read_text(encoding="utf-8")
    service = (ROOT / "firmware/platform/service_contracts.hpp").read_text(encoding="utf-8")
    bridge = (ROOT / "firmware/platform/bridge/workshop_platform_bridge.cpp").read_text(encoding="utf-8")

    required = {
        "four printer slots": "kMaxPrinterSlots = 4",
        "explicit cloud unknown": "observation.cloud = Connectivity::Unknown",
        "explicit AP state": "accessPointMode",
        "rollover-safe elapsed": "nowMs - observedAtMs",
        "existing printer authority": "printers[slot].state",
        "existing Wi-Fi authority": "isWiFiConnected()",
        "observation poll seam": "workshopPlatformPoll()",
    }
    joined = state + adapter + service + bridge
    for label, needle in required.items():
        if needle not in joined:
            fail(f"missing {label}: {needle}")

    forbidden = (
        "spoolId",
        "ownerId",
        "placementId",
        "inferPlacement",
        "materialMatch",
        "colorMatch",
        "OPENAI_API_KEY",
        "sk-",
    )
    for needle in forbidden:
        if needle in bridge:
            fail(f"bridge contains forbidden authority/credential marker: {needle}")

    # `using namespace workshop::platform;` is valid C++11. Reject only the
    # C++17 nested namespace declaration syntax and attributes we intentionally
    # avoid in firmware-facing headers.
    headers = state + adapter + service
    if "namespace workshop::platform {" in headers or "[[nodiscard]]" in headers:
        fail("platform headers must remain compatible with Arduino C++11")


def validate_patcher() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-bridge-") as tmp:
        repo = Path(tmp)
        (repo / "include").mkdir(parents=True)
        (repo / "src").mkdir(parents=True)
        (repo / "include/smart_home_build.h").write_text(
            "#pragma once\n#define WORKSHOP_OS_V11_28_UI13 1\n", encoding="utf-8"
        )
        (repo / "src/main.cpp").write_text(
            '#include "wifi_manager.h"\n\n'
            'static void initAll(){\n'
            '    tasmotaInit();\n'
            '}\n\n'
            'void loop(){\n'
            '  handleWiFi();\n'
            '}\n',
            encoding="utf-8",
        )

        patcher.apply(repo, ROOT)
        patcher.apply(repo, ROOT)

        main = (repo / "src/main.cpp").read_text(encoding="utf-8")
        if main.count('#include "workshop_platform_bridge.h"') != 1:
            fail("bridge include was not injected exactly once")
        if main.count("workshopPlatformBegin();") != 1:
            fail("bridge begin was not injected exactly once")
        if main.count("workshopPlatformPoll();") != 1:
            fail("bridge poll was not injected exactly once")

        for path in (
            "include/workshop_platform/workshop_state.hpp",
            "include/workshop_platform/runtime_adapter.hpp",
            "include/workshop_platform/service_contracts.hpp",
            "include/workshop_platform_bridge.h",
            "src/workshop_platform_bridge.cpp",
        ):
            if not (repo / path).is_file():
                fail(f"patcher failed to install {path}")


def main() -> int:
    validate_templates()
    validate_patcher()
    print("Workshop OS 12 platform bridge validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
