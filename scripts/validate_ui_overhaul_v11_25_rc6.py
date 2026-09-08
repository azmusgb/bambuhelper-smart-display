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
    settings_bytes = (root / "src" / "settings.cpp").read_bytes()

    if b"\x00" in settings_bytes:
        raise AssertionError("settings.cpp contains an embedded NUL byte; reconstructed source must be warning-clean")
    settings = settings_bytes.decode("utf-8")
    require(settings, "'\\0'", "escaped C++ NUL character literal")

    for needle in (
        'SMART_HOME_VERSION "v11.25"',
        'SMART_HOME_PROFILE "secure-physical-acceptance"',
        'Workshop OS v11.25 RC6 Secure Physical Acceptance',
        'WORKSHOP_OS_V11_25_UI_RC5 1',
        'WORKSHOP_OS_V11_25_SECURE_ACCEPTANCE_RC6 1',
        'WORKSHOP_OS_UI_SCHEMA "UI5"',
        'WORKSHOP_OS_AUTH_MODE "portal-code"',
    ):
        require(build, needle, "RC6 build identity")
    forbid(build, '#define WORKSHOP_OS_TEMP_NO_CODE_LAN 1', "temporary no-code build marker")

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
        'securityPortalCode()',
        '"PORTAL CODE"',
    ):
        require(hub, needle, "RC6 native UI contract")
    if hub.count("securityPortalCode()") < 2:
        raise AssertionError("System must render the portal code in both layouts")
    forbid(hub, "TEST / NO CODE", "test-only access copy")

    helper_pos = hub.find("static const char* hubV1125UiFingerprint")
    header_pos = hub.find("static void drawHeader(")
    if helper_pos < 0 or header_pos < 0 or helper_pos > header_pos:
        raise AssertionError("UI5 fingerprint helper must remain declared before drawHeader")
    for fn in ("drawHome", "drawPrinter", "drawWorkshop", "drawMore", "drawSystem"):
        count = len(re.findall(rf"static void {fn}\s*\(", hub))
        if count != 1:
            raise AssertionError(f"{fn}: expected one active definition, found {count}")
    for forbidden in ("resolveSpool", "matchSpoolByColor", "matchSpoolByMaterial"):
        forbid(hub, forbidden, "firmware-side inventory identity inference")

    require(security, '#include "smart_home_build.h"', "secure build identity visibility")
    require(security, 'return cookieMatches(server);', "boot-scoped session enforcement")
    require(security, 'if (mutating && !sameOrigin(server))', "same-origin mutation guard")
    require(security, 'RC6 secure physical acceptance forbids WORKSHOP_OS_TEMP_NO_CODE_LAN', "fail-closed no-code guard")
    forbid(security, 'if (!isAPMode()) return true;', "station-LAN session bypass")
    if security.count("WORKSHOP_OS_TEMP_NO_CODE_LAN") != 2:
        raise AssertionError("temporary no-code marker must appear only in RC6 fail-closed guard")

    for needle in (
        "Workshop OS Secure Sign In",
        "Secure LAN access",
        "Sign in securely",
        "min-height:52px",
        "input:focus-visible",
        "button:focus-visible",
        "@media(prefers-reduced-motion:reduce)",
        "@media(forced-colors:active)",
        'd["authMode"]',
        'd["apMode"]',
        'd["stationConnected"]',
        'd["stationIp"]',
        'd["softApIp"]',
        "WORKSHOP_OS_AUTH_MODE",
    ):
        require(web, needle, "RC6 secure portal/runtime observability")

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
        require(css, needle, "retained RC5 portal presentation authority")

    print("Workshop OS v11.25 RC6 Secure Physical Acceptance contract: PASS")
    print("runtime_fingerprint=UI5-H/P/W/M/S")
    print("final_presentation_authority=RC5_UI5_RETAINED")
    print("inventory_identity_inference=FORBIDDEN")
    print("station_lan_auth=BOOT_SCOPED_PORTAL_CODE")
    print("mutating_same_origin_guard=PRESERVED")
    print("temp_no_code=FORBIDDEN")
    print("runtime_auth_observability=EXPLICIT")
    print("generated_settings_source=NUL_FREE_WARNING_CLEAN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
