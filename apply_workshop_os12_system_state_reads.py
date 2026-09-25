#!/usr/bin/env python3
"""Migrate Network and Printer & Power informational reads to WorkshopState.

This slice changes display/read paths only. Smart-plug mapping, persistence,
printer commands, and all device-control authority stay on their existing
implementations.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




NETWORK_OLD = '''static void drawUi13Network() {
  const bool wifi=WiFi.status()==WL_CONNECTED;String ip=wifi?WiFi.localIP().toString():String("Unknown");
  tft.fillScreen(C10_BG);drawHeader("Network",wifi?"Connected":"Offline",3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Not connected",wifi?ip.c_str():"No network connection",wifi?C10_GREEN:C10_ORANGE);
'''
NETWORK_NEW = '''static void drawUi13Network() {
  const workshop::platform::NetworkState& os12Network=workshopPlatformState().network;const bool wifi=workshopPlatformWifiOnline();const char* ip=(wifi&&os12Network.localAddress[0])?os12Network.localAddress:"Unknown";
  tft.fillScreen(C10_BG);drawHeader("Network",wifi?"Connected":"Offline",3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Not connected",wifi?ip:"No network connection",wifi?C10_GREEN:C10_ORANGE);
'''

PRINTER_POWER_OLD = '''static void drawUi13PrinterPower() {
  const bool configured=isAnyPrinterConfigured();const PrinterSlot* p=configured?&displayedPrinter():nullptr;const bool connected=p&&p->state.connected;const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;const bool plugReady=mapped&&tasmotaSettings[plug].enabled&&tasmotaSettings[plug].ip[0];
'''
PRINTER_POWER_NEW = '''static void drawUi13PrinterPower() {
  const bool configured=workshopPlatformState().configuredPrinterCount>0;const uint8_t os12Slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;const PrinterSlot* p=configured?&displayedPrinter():nullptr;const bool connected=configured&&workshopPlatformPrinterOnline(os12Slot);const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;const bool plugReady=mapped&&tasmotaSettings[plug].enabled&&tasmotaSettings[plug].ip[0];
'''

POWER_OPTIONS_OLD = '''static void drawUi13PowerOptions() {
  const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;
'''
POWER_OPTIONS_NEW = '''static void drawUi13PowerOptions() {
  const bool configured=workshopPlatformState().configuredPrinterCount>0;const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;
'''


def apply(repo: Path) -> None:
    marker = repo / "include" / "smart_home_build.h"
    hub_path = repo / "src" / "smart_hub.cpp"
    if not marker.is_file() or not hub_path.is_file():
        raise PatchError("OS12 system read migration requires reconstructed UI13 source")
    if "#define WORKSHOP_OS_V11_28_UI13 1" not in marker.read_text(encoding="utf-8"):
        raise PatchError("OS12 system read migration requires v11.28 UI13")
    if not (repo / "include" / "workshop_platform_bridge.h").is_file():
        raise PatchError("OS12 platform bridge must be installed first")

    text = hub_path.read_text(encoding="utf-8")
    if '#include "workshop_platform_bridge.h"' not in text:
        raise PatchError("Home/Printer read migration must install the smart_hub platform include first")

    text = replace_once(text, NETWORK_OLD, NETWORK_NEW, "Network normalized reads")
    text = replace_once(text, PRINTER_POWER_OLD, PRINTER_POWER_NEW, "Printer & Power normalized reads")
    text = replace_once(text, POWER_OPTIONS_OLD, POWER_OPTIONS_NEW, "Power Options configured read")
    hub_path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 Network + Printer & Power informational reads migrated")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
