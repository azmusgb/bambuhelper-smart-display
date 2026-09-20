#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL: missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"FAIL: forbidden {label}: {needle}")


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args=ap.parse_args()
    repo=Path(args.repo).resolve()

    service=(repo/"src/workshop_inventory_service.cpp").read_text(encoding="utf-8")
    header=(repo/"include/workshop_inventory_service.h").read_text(encoding="utf-8")
    main_cpp=(repo/"src/main.cpp").read_text(encoding="utf-8")
    web=(repo/"src/web_server.cpp").read_text(encoding="utf-8")
    html=(repo/"include/web_pages.h").read_text(encoding="utf-8")
    js=(repo/"web/app.js").read_text(encoding="utf-8")
    build=(repo/"include/smart_home_build.h").read_text(encoding="utf-8")

    for marker in (
        'https://filamentinventory.netlify.app/api/device-feed/v1',
        'Authorization',
        'Bearer ',
        'fi_dev_',
        'setCACertBundle(rootca_crt_bundle_start)',
        'HTTPC_DISABLE_FOLLOW_REDIRECTS',
        'schemaVersion',
        'InventoryFeedObservation',
        'normalizeInventoryFeedObservation',
        'workshopPlatformPublishInventoryState',
        'placementConflictCount',
        'invalidLineageCount',
        'stockState',
        'quantity["verificationRequired"]',
        'placement["verificationRequired"]',
        'Stale quantity evidence must require verification.',
        'Conflicting quantity evidence failed conflict contract.',
        'Invalid quantity lineage must require verification.',
        'Unknown quantity evidence must preserve unknown grams and require verification.',
        'Stale placement evidence must require verification.',
        'Conflicting placement evidence must require verification.',
        'Unknown placement evidence must preserve unknown physical state.',
    ):
        need(service,marker,"inventory service contract")

    for forbidden in (
        "X-Filament-Sync-Key",
        "x-filament-sync-key",
        "X-Filament-Profile",
        "openai",
        "apiKey",
        "providerKey",
    ):
        forbid(service,forbidden,"broad credential/provider secret")

    for marker in (
        "workshopInventoryServiceBegin",
        "workshopInventoryServiceLoop",
        "workshopInventorySetDeviceCredential",
        "workshopInventoryClearDeviceCredential",
        "WorkshopInventoryRuntimeSnapshot",
    ):
        need(header,marker,"service API")

    if main_cpp.count("workshopInventoryServiceBegin();") != 1:
        raise SystemExit("FAIL: inventory service begin must appear exactly once")
    if main_cpp.count("workshopInventoryServiceLoop();") != 1:
        raise SystemExit("FAIL: inventory service loop must appear exactly once")

    for marker in (
        'SECURE_GET("/os12/inventory/status"',
        'SECURE_POST("/os12/inventory/refresh"',
        'SECURE_POST("/os12/inventory/credential"',
        'SECURE_POST("/os12/inventory/credential/clear"',
    ):
        need(web,marker,"authenticated inventory portal route")

    for marker in (
        "WS350 device token",
        "read-only WS350 token",
        "broader browser sync key",
        'type="password"',
        'autocomplete="off"',
        "fiDeviceFeedStatus",
    ):
        need(html,marker,"least-authority portal UX")

    for marker in (
        "loadInventoryDeviceFeedStatus",
        "saveInventoryDeviceToken",
        "clearInventoryDeviceToken",
        "refreshInventoryDeviceFeed",
        "/os12/inventory/status",
    ):
        need(js,marker,"device-feed portal behavior")

    need(build,"WORKSHOP_OS12_INVENTORY_DEVICE_FEED 1","build identity")
    print("PASS: OS12 Filament Inventory transport is profile-scoped, bearer-only, fail-closed, and locally revocable")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
