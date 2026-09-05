#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("upstream")

UUIDS = [
    "A3D10000-7A4B-4B82-9C52-57534F533530",
    "A3D10001-7A4B-4B82-9C52-57534F533530",
    "A3D10002-7A4B-4B82-9C52-57534F533530",
    "A3D10003-7A4B-4B82-9C52-57534F533530",
    "A3D10004-7A4B-4B82-9C52-57534F533530",
]


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
    impl = read("src/workshop_companion_ble.cpp")
    header = read("src/workshop_companion_ble.h")
    main_cpp = read("src/main.cpp")
    board = read("boards/ws_lcd_350.ini")
    shared = read("platformio.ini")
    build = read("include/smart_home_build.h")

    for uuid in UUIDS:
        require(impl, uuid, "BLE implementation UUID parity")

    for needle in [
        'constexpr uint8_t kProtocolVersion = 1;',
        '"portal-session"',
        'kBlePayloadTarget = 180',
        'BLECharacteristic::PROPERTY_READ',
        'BLECharacteristic::PROPERTY_NOTIFY',
        'BLECharacteristic::PROPERTY_WRITE',
        'workshopCompanionBleNotify(',
        '"hello"',
        '"camera-request"',
        '"tts-request"',
        '"notify"',
        '"lan-handoff"',
        'WiFi.status() == WL_CONNECTED',
    ]:
        require(impl, needle, "BLE implementation")

    for needle in [
        'initWorkshopCompanionBle();',
        'workshopCompanionBleTick();',
        '#include "workshop_companion_ble.h"',
    ]:
        if main_cpp.count(needle) != 1:
            raise SystemExit(f"main.cpp: expected one {needle}")

    require(board, '-D WORKSHOP_COMPANION_BLE=1', "WS350 build flag")
    forbid(shared, 'WORKSHOP_COMPANION_BLE=1', "shared platform profile must remain BLE-neutral")
    require(header, '#if defined(WORKSHOP_COMPANION_BLE) && defined(BOARD_IS_WS350)', "BLE header capability gate")

    for needle in [
        'SMART_HOME_VERSION "v11.25"',
        'SMART_HOME_PROFILE "workshop-companion"',
        'Smart Home v11.25 Workshop Companion BLE RC1',
        'Workshop OS v11.25 Workshop Companion BLE RC1',
    ]:
        require(build, needle, "build identity")

    # BLE v1 is orchestration only. Any direct mutation path here is a release blocker.
    for forbidden in [
        'requestPause', 'requestResume', 'requestStop', 'requestLightCommand',
        'requestPower', 'tasmotaSet', 'tasmotaToggle', 'saveSettings(',
        'portalCode', 'access_code', 'accessCode', 'password', 'ssid',
        'sessionCookie', 'Set-Cookie', 'Authorization',
    ]:
        forbid(impl, forbidden, "BLE security boundary")

    require(impl, 'No BLE message maps to printer,', "BLE mutation-denial comment")
    require(impl, 'auth remains portal-session over LAN', "BLE auth-boundary log")

    print("Workshop Companion BLE v11.25 contract: PASS")


if __name__ == "__main__":
    main()
