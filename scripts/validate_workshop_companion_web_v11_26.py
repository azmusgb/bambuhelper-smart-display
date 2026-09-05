#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("upstream")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(f"missing {rel}")
    return path.read_text(encoding="utf-8")


def require(body: str, needle: str, label: str) -> None:
    if needle not in body:
        raise SystemExit(f"{label}: missing {needle}")


def forbid(body: str, needle: str, label: str) -> None:
    if needle in body:
        raise SystemExit(f"{label}: forbidden {needle}")


def main() -> None:
    build = read("include/smart_home_build.h")
    header = read("src/companion_web.h")
    impl = read("src/companion_web.cpp")
    web = read("src/web_server.cpp")
    ble = read("src/workshop_companion_ble.cpp")

    for needle in [
        'SMART_HOME_VERSION "v11.26"',
        'SMART_HOME_PROFILE "companion-web"',
        'Smart Home v11.26 Companion Web RC1',
        'Workshop OS v11.26 Companion Web RC1',
    ]:
        require(build, needle, "build identity")

    for needle in [
        'void registerCompanionWebRoutes();',
        'bool companionWebPhoneConnected();',
        'uint32_t companionWebLastSeenMs();',
    ]:
        require(header, needle, "companion web header")

    for needle in [
        'server.on("/companion", HTTP_GET, handleCompanionPage);',
        'server.on("/companion/heartbeat", HTTP_POST, handleCompanionHeartbeat);',
        'server.on("/companion/connection", HTTP_GET, handleCompanionConnection);',
        'securitySessionValid(server)',
        'securityAuthorize(server, true)',
        'securityAuthorize(server, false)',
        'Location", "/login?next=/companion"',
        'kPhoneOnlineMs = 15000',
        'wifi-web',
        'Cache-Control", "no-store"',
    ]:
        require(impl, needle, "companion web implementation")

    # The page itself is compiled into companion_web.cpp as a PROGMEM raw string.
    for needle in [
        "Workshop Companion",
        "apple-mobile-web-app-capable",
        "fetchJson('/status?slot='+s",
        "fetchJson('/printer/power/status?slot='+s",
        "command('/light/set'",
        "command('/printer/control'",
        "confirm:'STOP'",
        "post('/printer/power'",
        "POWER OFF DURING PRINT",
        "post('/companion/heartbeat'",
        "document.hidden?5000:1200",
        "capture=\"environment\"",
        "Web v1 does not upload it yet",
    ]:
        require(impl, needle, "embedded Companion page")

    # Companion must preserve the existing session + same-origin boundary.
    for needle in [
        '#include "companion_web.h"',
        'registerCompanionWebRoutes();',
        "name='next' value='/companion'",
        'server.arg("next") == "/companion"',
    ]:
        require(web, needle, "web-server integration")

    # The login continuation is allowlisted to one local path; there must be no
    # generic redirect assignment from an attacker-controlled next argument.
    forbid(web, 'sendHeader("Location", server.arg("next"))', "login open-redirect boundary")
    forbid(web, 'sendHeader("Location", server.arg("redirect"))', "login open-redirect boundary")

    # Web presence joins BLE presence without moving any auth/command authority
    # into the BLE module.
    require(ble, '#include "companion_web.h"', "BLE/web presence bridge")
    require(ble, 'g_phoneConnected || companionWebPhoneConnected()', "BLE/web presence bridge")

    for forbidden in [
        "portalCode",
        "securityPortalCode",
        "BHSESSION=",
        "printerAccessCode",
        "access_code",
        "wifiPassword",
        "ssidPassword",
        "Authorization:",
        "WebSocket",
        "ws://",
        "wss://",
    ]:
        forbid(impl, forbidden, "Companion secret/transport boundary")

    # The page must not introduce speculative printer commands; only the proven
    # routes are allowed for mutations.
    for forbidden in [
        "/printer/speed",
        "/printer/fan",
        "/printer/temp",
        "/ams/load",
        "/ams/unload",
    ]:
        forbid(impl, forbidden, "Companion command scope")

    match = re.search(r"<script>(.*?)</script>", impl, flags=re.S)
    if not match:
        raise SystemExit("embedded Companion page: inline script not found")
    script = match.group(1)
    proc = subprocess.run(
        ["node", "--check"],
        input=script,
        text=True,
        capture_output=True,
    )
    if proc.returncode:
        raise SystemExit("embedded Companion JavaScript syntax failed:\n" + proc.stderr)

    print("Workshop Companion Web v11.26 contract: PASS")


if __name__ == "__main__":
    main()
