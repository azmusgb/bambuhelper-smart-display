#!/usr/bin/env python3
"""Install the authenticated Workshop OS 12 Filament Inventory control API.

The API accepts only the revocable device-scoped token issued by Filament
Inventory. It never accepts, stores, or returns the broader browser sync key.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


HANDLERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS 12 Filament Inventory device-feed control API
// ---------------------------------------------------------------------------
static void sendWorkshopInventoryStatus(int httpCode = 200) {
  const WorkshopInventoryRuntimeSnapshot snap = workshopInventorySnapshot();
  JsonDocument doc;
  doc["configured"] = snap.credentialConfigured;
  doc["busy"] = snap.busy;
  doc["available"] = snap.state.available;
  doc["freshness"] =
      snap.state.freshness == workshop::platform::Freshness::Fresh ? "Fresh" :
      snap.state.freshness == workshop::platform::Freshness::Stale ? "Stale" :
      snap.state.freshness == workshop::platform::Freshness::Conflicting ? "Conflicting" : "Unknown";
  doc["spoolCount"] = snap.state.spoolCount;
  doc["loadedCount"] = snap.state.loadedCount;
  doc["lowCount"] = snap.state.lowCount;
  doc["unknownQuantityCount"] = snap.state.unknownQuantityCount;
  doc["staleQuantityCount"] = snap.state.staleQuantityCount;
  doc["quantityConflictCount"] = snap.state.conflictCount;
  doc["invalidLineageCount"] = snap.state.invalidLineageCount;
  doc["unknownPlacementCount"] = snap.state.unknownPlacementCount;
  doc["stalePlacementCount"] = snap.state.stalePlacementCount;
  doc["placementConflictCount"] = snap.state.placementConflictCount;
  doc["quantityVerificationRequired"] = snap.state.quantityVerificationRequired;
  doc["placementVerificationRequired"] = snap.state.placementVerificationRequired;
  doc["profileId"] = snap.state.profileId;
  doc["lastAttemptAtMs"] = snap.lastAttemptAtMs;
  doc["lastSuccessAtMs"] = snap.lastSuccessAtMs;
  doc["statusMessage"] = snap.statusMessage;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopInventoryStatus() {
  sendWorkshopInventoryStatus();
}

static void handleWorkshopInventoryCredential() {
  if (!server.hasArg("token")) {
    server.send(400, "application/json",
        "{\"status\":\"error\",\"message\":\"token is required\"}");
    return;
  }
  String token = server.arg("token");
  const bool saved = workshopInventorySetDeviceCredential(token.c_str());
  token = "";
  if (!saved) {
    server.send(400, "application/json",
        "{\"status\":\"error\",\"message\":\"Invalid Workshop OS device token.\"}");
    return;
  }
  sendWorkshopInventoryStatus(202);
}

static void handleWorkshopInventoryCredentialClear() {
  workshopInventoryClearDeviceCredential();
  sendWorkshopInventoryStatus();
}

static void handleWorkshopInventoryRefresh() {
  const bool accepted = workshopInventoryRequestRefresh();
  sendWorkshopInventoryStatus(accepted ? 202 : 409);
}
'''

ROUTES = '''  SECURE_GET("/os12/inventory/status", handleWorkshopInventoryStatus);
  SECURE_POST("/os12/inventory/credential", handleWorkshopInventoryCredential);
  SECURE_POST("/os12/inventory/credential/clear", handleWorkshopInventoryCredentialClear);
  SECURE_POST("/os12/inventory/refresh", handleWorkshopInventoryRefresh);
'''


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def apply(repo: Path) -> None:
    path = repo / "src/web_server.cpp"
    text = load(path)
    if not (repo / "include/workshop_inventory_service.h").is_file():
        raise PatchError("inventory service must be installed before inventory API")
    if "PortalLoginPageState" not in text:
        raise PatchError("portal authentication hardening must be present")

    if '#include "workshop_inventory_service.h"' not in text:
        # Reconstructed web_server.cpp does not necessarily consume the platform
        # bridge directly. Anchor to the stable update-service include used by
        # the other OS12 authenticated APIs instead of requiring an unrelated
        # include to exist first.
        anchors = (
            '#include "workshop_update_service.h"\n',
            '#include "security_manager.h"\n',
        )
        anchor = next((candidate for candidate in anchors if text.count(candidate) == 1), None)
        if anchor is None:
            raise PatchError("inventory API stable include anchor missing/non-unique")
        text = text.replace(anchor, anchor + '#include "workshop_inventory_service.h"\n', 1)

    if "sendWorkshopInventoryStatus" not in text:
        marker = "void initWebServer() {\n"
        if text.count(marker) != 1:
            raise PatchError("web server init anchor missing/non-unique")
        text = text.replace(marker, HANDLERS + "\n" + marker, 1)

    if '/os12/inventory/status' not in text:
        # Register directly at the authenticated init boundary. Inventory routes
        # use SECURE_GET/SECURE_POST themselves, so they do not depend on any
        # unrelated OS12 feature route being present in this reconstruction.
        route_anchor = "void initWebServer() {\n"
        if text.count(route_anchor) != 1:
            raise PatchError("web server init route anchor missing/non-unique")
        text = text.replace(route_anchor, route_anchor + ROUTES, 1)

    route_registrations = (
        'SECURE_GET("/os12/inventory/status", handleWorkshopInventoryStatus);',
        'SECURE_POST("/os12/inventory/credential", handleWorkshopInventoryCredential);',
        'SECURE_POST("/os12/inventory/credential/clear", handleWorkshopInventoryCredentialClear);',
        'SECURE_POST("/os12/inventory/refresh", handleWorkshopInventoryRefresh);',
    )
    for registration in route_registrations:
        if text.count(registration) != 1:
            raise PatchError(f"inventory route missing/non-unique: {registration}")

    init_start = text.find("void initWebServer() {")
    init_end = text.find("\nvoid handleWebServer()", init_start)
    if init_start < 0 or init_end < 0:
        raise PatchError("web route-registration block missing")
    registration = text[init_start:init_end]
    if 'server.on("/os12/inventory/' in registration:
        raise PatchError("inventory controls must use authenticated SECURE routes")

    # The API must never expose or accept the browser sync credential.
    for forbidden in ("X-Filament-Sync-Key", "X-Filament-Profile", "sk-"):
        if forbidden in HANDLERS:
            raise PatchError(f"forbidden credential marker: {forbidden}")

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 authenticated Filament Inventory API installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
