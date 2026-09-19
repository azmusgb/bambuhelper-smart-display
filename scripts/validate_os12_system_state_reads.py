#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_system_state_reads.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_system_reads", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load OS12 system read patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_hub() -> str:
    return '''#include "workshop_platform_bridge.h"\n\nstatic void drawUi13Network() {\n  const bool wifi=WiFi.status()==WL_CONNECTED;String ip=wifi?WiFi.localIP().toString():String("Unknown");\n  tft.fillScreen(C10_BG);drawHeader("Network",wifi?"Connected":"Offline",3);uiBottomNav(3,nullptr);\n  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Not connected",wifi?ip.c_str():"No network connection",wifi?C10_GREEN:C10_ORANGE);\n}\n\nstatic void drawUi13PrinterPower() {\n  const bool configured=isAnyPrinterConfigured();const PrinterSlot* p=configured?&displayedPrinter():nullptr;const bool connected=p&&p->state.connected;const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;const bool plugReady=mapped&&tasmotaSettings[plug].enabled&&tasmotaSettings[plug].ip[0];\n}\n\nstatic void drawUi13PowerOptions() {\n  const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;\n}\n'''


def validate() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-system-reads-") as tmp:
        repo = Path(tmp)
        (repo / "include").mkdir(parents=True)
        (repo / "src").mkdir(parents=True)
        (repo / "include/smart_home_build.h").write_text(
            "#pragma once\n#define WORKSHOP_OS_V11_28_UI13 1\n", encoding="utf-8"
        )
        (repo / "include/workshop_platform_bridge.h").write_text("#pragma once\n", encoding="utf-8")
        (repo / "src/smart_hub.cpp").write_text(synthetic_hub(), encoding="utf-8")

        patcher.apply(repo)
        patcher.apply(repo)
        text = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8")

        required = (
            "const workshop::platform::NetworkState& os12Network=workshopPlatformState().network",
            "const bool wifi=workshopPlatformWifiOnline()",
            "const bool connected=configured&&workshopPlatformPrinterOnline(os12Slot)",
            "const bool configured=workshopPlatformState().configuredPrinterCount>0",
        )
        for needle in required:
            if needle not in text:
                fail(f"normalized system read missing: {needle}")

        forbidden = (
            "const bool wifi=WiFi.status()==WL_CONNECTED",
            "const bool connected=p&&p->state.connected",
            "const bool configured=isAnyPrinterConfigured()",
        )
        for needle in forbidden:
            if needle in text:
                fail(f"legacy informational read survived migration: {needle}")

        # Smart-plug mapping remains explicitly outside the platform authority.
        if "hubPowerConfigPlug()" not in text or "tasmotaSettings" not in text:
            fail("system-read migration overreached into smart-plug authority")


def main() -> int:
    validate()
    print("Workshop OS 12 Network + Printer & Power normalized read validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
