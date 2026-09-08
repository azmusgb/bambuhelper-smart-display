#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    root = Path(args.repo)
    hub = (root / "src" / "smart_hub.cpp").read_text(encoding="utf-8")
    build = (root / "include" / "smart_home_build.h").read_text(encoding="utf-8")
    security = (root / "src" / "security_manager.cpp").read_text(encoding="utf-8")
    web = (root / "src" / "web_server.cpp").read_text(encoding="utf-8")

    for needle in [
        'SMART_HOME_VERSION "v11.25"',
        'SMART_HOME_PROFILE "full-device-ui-overhaul"',
        'Workshop OS v11.25 Full Device UI Overhaul RC2',
        'WORKSHOP_OS_V11_25_UI_OVERHAUL 1',
        'WORKSHOP_OS_V11_25_UI_OVERHAUL_RC2 1',
        'WORKSHOP_OS_TEMP_NO_CODE_LAN 1',
    ]:
        require(build, needle, "RC2 build identity")

    for needle in [
        'tft.fillRoundRect(8,7,30,26,4,UI_ORANGE);',
        'uiDrawFit("W",23,20,20,FONT_BODY,MC_DATUM,UI_BG,UI_ORANGE);',
        'tft.fillRect(0,HH-2,W,2,UI_ORANGE);',
        'const uint16_t c=selected?UI_ORANGE:UI_MUTED;',
        'tft.fillRect(r.x,r.y+r.h-4,r.w,4,UI_ORANGE);',
        'static const char* labels[4]={"HOME","PRINTER","WORKSHOP","MORE"};',
        'if(i==1) return hr(8,48,320,212);',
        'uiDrawFit("NEXT ACTION"',
        'uiDrawFit(wifi?"OPEN / TEST":"OFFLINE"',
        'uiProgressBar(hero.x+16,hero.y+150,hero.w-32,s->progress,UI_ORANGE);',
        '"STATUS","AMS","CONTROL"',
        'Printer telemetry only • no identity inferred from color/material',
        'Inventory spool: Unknown',
        'g_printerMode!=HUB_PRINTER_CONTROL',
        'powerConfirmOpenForSlot(slot)',
        's.connected&&active&&longPress',
    ]:
        require(hub, needle, "RC2 visible/touch contract")

    for needle in [
        '#if defined(WORKSHOP_OS_TEMP_NO_CODE_LAN) && WORKSHOP_OS_TEMP_NO_CODE_LAN',
        'if (!isAPMode()) return true;',
        'return cookieMatches(server);',
        'if (mutating && !sameOrigin(server))',
    ]:
        require(security, needle, "temporary no-code boundary")

    for needle in [
        'SECURE_GET("/hub/views", handleHubViews)',
        'SECURE_GET("/hub/frame.ppm", handleHubFramePpm)',
        'SECURE_POST("/hub/show", handleHubShow)',
    ]:
        require(web, needle, "secured route wrapper")

    for needle in [
        'requestSpeedCommand',
        'requestFanCommand',
        'matchSpoolByColor',
        'matchSpoolByMaterial',
        'resolveSpool',
    ]:
        forbid(hub, needle, "authority/control regression")

    for fn in ["drawHome", "drawPrinter", "drawWorkshop", "drawMore", "drawSystem"]:
        count = len(re.findall(rf"static void {fn}\s*\(", hub))
        if count != 1:
            raise AssertionError(f"{fn}: expected 1 definition, found {count}")

    print("Workshop OS v11.25 RC2 physical-feedback contract: PASS")
    print("visual_delta=ORANGE_INDUSTRIAL_FLAT_COMMAND_CENTER")
    print("home_layout=320PX_PRIMARY_COMMAND_CENTER_PLUS_RIGHT_STATUS_RAIL")
    print("routine_touch_floor=48px")
    print("inventory_identity=UNKNOWN_UNLESS_AUTHORITATIVE_CONTRACT")
    print("station_lan_device_code=TEMPORARILY_DISABLED")
    print("mutating_same_origin_guard=PRESERVED")
    print("physical_acceptance=REQUIRED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
