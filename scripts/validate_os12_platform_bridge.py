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
    bridge_h = (ROOT / "firmware/platform/bridge/workshop_platform_bridge.h").read_text(encoding="utf-8")
    bridge = (ROOT / "firmware/platform/bridge/workshop_platform_bridge.cpp").read_text(encoding="utf-8")

    required = {
        "four printer slots": "kMaxPrinterSlots = 4",
        "explicit cloud unknown": "observation.cloud = Connectivity::Unknown",
        "explicit AP state": "accessPointMode",
        "rollover-safe elapsed": "nowMs - observedAtMs",
        "existing printer authority": "printers[slot].state",
        "existing Wi-Fi authority": "isWiFiConnected()",
        "observation poll seam": "workshopPlatformPoll()",
        "command facade": "workshopPlatformDispatchPrinterCommand",
        "deterministic command preflight": "validatePrinterCommand",
        "deferred Bambu command transport": "requestPrinterControlCommand",
        "existing chamber-light transport": "requestLightCommand",
        "guard rejection": "RejectedGuardRequired",
        "invalid-state rejection": "RejectedInvalidState",
        "explicit command-channel rejection": "RejectedCommandChannelUnavailable",
        "operation feedback idle": "OperationPhase::Idle",
        "operation feedback pending": "OperationPhase::Pending",
        "operation feedback success": "OperationPhase::Success",
        "operation feedback recoverable": "OperationPhase::RecoverableError",
        # FatalError is intentionally a reserved contract state. No current
        # CommandResult maps to it, because ordinary rejection/transport failure
        # is recoverable. Validate that the enum state exists without requiring
        # a fabricated runtime mapping merely to satisfy this structural gate.
        "operation feedback fatal contract": "FatalError,",
        "result-to-feedback mapping": "commandOperationFromResult",
        "inventory projection state": "InventoryProjectionState",
        "inventory quantity state": "InventoryQuantityState",
        "inventory readiness state": "InventoryReadinessState",
        "inventory quantity gate": "inventoryQuantityUsable",
        "inventory readiness gate": "inventoryReadinessClean",
        "inventory service seam": "class IInventoryService",
        "inventory publish facade": "workshopPlatformPublishInventoryState",
        "inventory read facade": "workshopPlatformInventoryState",
        "inventory normalized adapter": "normalizeInventoryFeedObservation",
    }
    joined = state + adapter + service + bridge_h + bridge
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
    headers = state + adapter + service + bridge_h
    if "namespace workshop::platform {" in headers or "[[nodiscard]]" in headers:
        fail("platform headers must remain compatible with Arduino C++11")

    stop_guard = service.find("RejectedGuardRequired")
    accepted = service.find("return CommandResult::Accepted;", stop_guard)
    if stop_guard < 0 or accepted < 0 or accepted < stop_guard:
        fail("guarded Stop preflight must reject before command acceptance")

    channel_guard = service.find("if (!state.commandChannelReady)")
    channel_reject = service.find("RejectedCommandChannelUnavailable", channel_guard)
    activity_guard = service.find("printerActivityAllowsCommand", channel_guard)
    if channel_guard < 0 or channel_reject < 0 or activity_guard < 0 or channel_reject > activity_guard:
        fail("printer command-channel readiness must fail closed before activity eligibility")

    if "FailedTransport" not in service or "state.retryable = true" not in service:
        fail("recoverable transport failures must participate in operation feedback")


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

        installed_service = (repo / "include/workshop_platform/service_contracts.hpp").read_text(encoding="utf-8")
        for marker in (
            "RejectedCommandChannelUnavailable",
            "OperationPhase::Pending",
            "OperationPhase::RecoverableError",
            "FatalError,",
            "commandOperationFromResult",
            "InventoryQuantityState",
            "InventoryReadinessState",
            "class IInventoryService",
            "publishInventoryState",
        ):
            if marker not in installed_service:
                fail(f"reconstructed source lost command feedback marker: {marker}")


def main() -> int:
    validate_templates()
    validate_patcher()
    print("Workshop OS 12 platform bridge validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
