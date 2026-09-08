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
    css = (root / "web" / "app.css").read_text(encoding="utf-8")

    for needle in (
        'SMART_HOME_VERSION "v11.25"',
        'SMART_HOME_PROFILE "native-ui-acceptance"',
        'Workshop OS v11.25 RC5 Native UI Acceptance',
        'WORKSHOP_OS_V11_25_UI_RC5 1',
        'WORKSHOP_OS_UI_SCHEMA "UI5"',
        'WORKSHOP_OS_TEMP_NO_CODE_LAN 1',
    ):
        require(build, needle, "RC5 build identity")

    for needle in (
        'return "UI5-H";',
        'return "UI5-P";',
        'return "UI5-W";',
        'return "UI5-M";',
        'return "UI5-S";',
        'uiDrawFit(hubV1125UiFingerprint(page)',
        'static const char* labels[4]={"HOME","PRINTER","WORKSHOP","MORE"};',
        'static const char* labels[3]={"STATUS","AMS","CONTROL"};',
        '"ATTENTION"',
        '"ALL CLEAR"',
        '"NEXT"',
        '"OPEN PRINTER"',
        '"Inventory: Unknown"',
        '"INVENTORY"',
        '"Printer telemetry only"',
        '"DIRECT CONTROLS"',
        '"Stop requires hold"',
        '"DEVICE HEALTH"',
        '"Speaker · mic · events"',
        'drawHeader("SYSTEM",overall?"HEALTHY":"CHECK",4)',
    ):
        require(hub, needle, "RC5 native UI contract")

    helper_pos = hub.find("static const char* hubV1125UiFingerprint")
    header_pos = hub.find("static void drawHeader(")
    if helper_pos < 0 or header_pos < 0 or helper_pos > header_pos:
        raise AssertionError("RC5 fingerprint helper must be declared before drawHeader")

    for fn in ("drawHome", "drawPrinter", "drawWorkshop", "drawMore", "drawSystem"):
        count = len(re.findall(rf"static void {fn}\s*\(", hub))
        if count != 1:
            raise AssertionError(f"{fn}: expected one active definition, found {count}")

    for forbidden in ("resolveSpool", "matchSpoolByColor", "matchSpoolByMaterial"):
        forbid(hub, forbidden, "firmware-side inventory identity inference")

    require(security, '#include "smart_home_build.h"', "no-code marker visibility")
    require(security, "if (!isAPMode()) return true;", "temporary station-LAN no-code session path")
    require(security, "if (mutating && !sameOrigin(server))", "same-origin mutation guard")
    require(security, "WORKSHOP_OS_TEMP_NO_CODE_LAN", "test-only no-code authorization path")

    for needle in (
        "Workshop OS v11.25 RC5 Native UI Acceptance",
        "--ui5-accent:#20b7a8",
        "--ui5-control:48px",
        ".wk116-grid",
        ".wk116-control",
        "@media(pointer:coarse)",
        "@media(prefers-reduced-motion:reduce)",
        "@media(forced-colors:active)",
    ):
        require(css, needle, "RC5 portal CSS")
    if css.rfind("Workshop OS v11.25 RC5 Native UI Acceptance") < css.rfind("Workshop OS v11.25 RC4 Product Polish"):
        raise AssertionError("RC5 CSS does not override RC4 CSS")

    print("Workshop OS v11.25 RC5 Native UI Acceptance contract: PASS")
    print("runtime_fingerprint=UI5-H/P/W/M/S")
    print("home_hierarchy=STATE_ATTENTION_NEXT_ACTION")
    print("printer_hierarchy=STATUS_AMS_CONTROL")
    print("inventory_identity_inference=FORBIDDEN")
    print("portal_css=UI5_RESPONSIVE_TOUCH_ACCESSIBLE")
    print("station_lan_device_code=TEMPORARILY_DISABLED_TEST_ONLY")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
