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
    css = (root / "web" / "app.css").read_text(encoding="utf-8")

    for needle in [
        'SMART_HOME_VERSION "v11.25"',
        'SMART_HOME_PROFILE "full-device-ui-overhaul"',
        'Workshop OS v11.25 Full Device UI Overhaul RC3',
        'WORKSHOP_OS_V11_25_UI_OVERHAUL 1',
        'WORKSHOP_OS_V11_25_UI_OVERHAUL_RC2 1',
        'WORKSHOP_OS_V11_25_UI_OVERHAUL_RC3 1',
        'WORKSHOP_OS_TEMP_NO_CODE_LAN 1',
    ]:
        require(build, needle, "RC3 build identity")

    for needle in [
        'uiDrawFit("PRINTER COMMAND CENTER"',
        'uiDrawFit("QUICK CONTROL"',
        'uiDrawFit("LIVE TELEMETRY"',
        'uiDrawFit("INVENTORY ID"',
        'uiDrawFit("WORKSHOP TIMER"',
        'uiDrawFit("ACCESS OPEN / TEST"',
        'uiDrawFit("LOCAL ACCESS"',
        'uiDrawFit("OPEN / TEST BUILD"',
        'tft.fillRect(r.x+1,r.y+r.h-4,r.w-2,3,edge);',
        'tft.fillRect(r.x+1,r.y+r.h-4,r.w-2,3,UI_ORANGE);',
        'static const char* labels[4]={"HOME","PRINTER","WORKSHOP","MORE"};',
        '"STATUS","AMS","CONTROL"',
        'powerConfirmOpenForSlot(slot)',
        's.connected&&active&&longPress',
    ]:
        require(hub, needle, "RC3 device UI/UX contract")

    for needle in [
        'Workshop OS v11.25 RC3 — premium portal polish',
        '--rc3-orange:#ff7a2f',
        '.wk116-printer::before',
        '.wk116-percent{font-size:44px',
        '.wk116-control{min-height:62px',
        '.nav-item[aria-current="true"]',
        '.section input:focus',
        '@media(prefers-reduced-motion:reduce)',
    ]:
        require(css, needle, "RC3 portal CSS contract")

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
        'requestSpeedCommand', 'requestFanCommand',
        'matchSpoolByColor', 'matchSpoolByMaterial', 'resolveSpool',
    ]:
        forbid(hub, needle, "authority/control regression")

    for fn in ["drawHome", "drawPrinter", "drawWorkshop", "drawMore", "drawSystem"]:
        count = len(re.findall(rf"static void {fn}\s*\(", hub))
        if count != 1:
            raise AssertionError(f"{fn}: expected 1 definition, found {count}")

    print("Workshop OS v11.25 RC3 premium UI/UX + CSS contract: PASS")
    print("device_language=PREMIUM_ORANGE_INSTRUMENT_PANEL")
    print("portal_css=POLISHED_RESPONSIVE_ACCESSIBLE")
    print("primary_nav=HOME_PRINTER_WORKSHOP_MORE")
    print("printer_modes=STATUS_AMS_CONTROL")
    print("inventory_identity=UNKNOWN_UNLESS_AUTHORITATIVE_CONTRACT")
    print("station_lan_device_code=TEMPORARILY_DISABLED")
    print("same_origin_mutation_guard=PRESERVED")
    print("physical_acceptance=REQUIRED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
