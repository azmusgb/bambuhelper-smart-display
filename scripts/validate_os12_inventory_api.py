#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    args=ap.parse_args()
    root=Path(args.repo).resolve()
    web=(root/"src/web_server.cpp").read_text(encoding="utf-8")
    service=(root/"src/workshop_inventory_service.cpp").read_text(encoding="utf-8")
    header=(root/"include/workshop_inventory_service.h").read_text(encoding="utf-8")

    required=(
        '#include "workshop_inventory_service.h"',
        'SECURE_GET("/os12/inventory/status"',
        'SECURE_POST("/os12/inventory/credential"',
        'SECURE_POST("/os12/inventory/credential/clear"',
        'SECURE_POST("/os12/inventory/refresh"',
        'workshopInventorySetDeviceCredential',
        'workshopInventoryClearDeviceCredential',
        'workshopInventoryRequestRefresh',
        'quantityVerificationRequired',
        'placementVerificationRequired',
        'invalidLineageCount',
        'placementConflictCount',
    )
    joined=web+service+header
    for marker in required:
        if marker not in joined:
            fail(f"missing inventory API marker: {marker}")

    registration=web[web.find("void initWebServer() {"):web.find("\nvoid handleWebServer()",web.find("void initWebServer() {"))]
    if 'server.on("/os12/inventory/' in registration:
        fail("inventory API bypasses authenticated SECURE route macros")

    for forbidden in ("X-Filament-Sync-Key","X-Filament-Profile","OPENAI_API_KEY","sk-"):
        if forbidden in service or forbidden in web[web.find("sendWorkshopInventoryStatus"):web.find("void initWebServer() {")]:
            fail(f"broad credential leaked into inventory device boundary: {forbidden}")

    status=web[web.find("sendWorkshopInventoryStatus"):web.find("static void handleWorkshopInventoryCredential()")]
    if 'device_token' in status or 'Authorization' in status or 'tokenHash' in status:
        fail("inventory status endpoint exposes credential material")

    print("PASS: OS12 inventory API is authenticated, revocable-token-only and evidence-aware")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
