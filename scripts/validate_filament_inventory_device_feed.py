#!/usr/bin/env python3
"""Validate the Filament Inventory -> Workshop OS device-feed v1 trust boundary.

This validator intentionally uses only the Python standard library. It checks
schema guardrails plus semantic fixture invariants that must remain fail-closed
at the firmware boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "filament-inventory-device-feed-v1.schema.json"

TOP_LEVEL = {
    "schemaVersion",
    "generatedAt",
    "scope",
    "freshness",
    "inventory",
    "readiness",
    "unknowns",
    "attention",
}

QUANTITY_METHODS = {
    "Measured",
    "CalculatedFromMeasured",
    "PrinterEstimatedUsage",
    "VisualEstimate",
    "ImportedEstimate",
    "Unknown",
}

QUANTITY_STATUS = {"Current", "Stale", "Conflict", "InvalidLineage", "Unknown"}
PLACEMENT_STATUS = {"Current", "Stale", "Conflict", "Unknown"}
PLACEMENT_STATE = {"Stored", "Loaded", "Unknown"}
STOCK_STATE = {"Available", "Low", "Empty", "Unknown"}

READINESS = {
    "Ready",
    "ReadyWithSubstitute",
    "NeedsLoad",
    "NeedsDry",
    "InsufficientQuantity",
    "EvidenceStale",
    "Undetermined",
}

PROHIBITED_SECRET_NAMES = {
    "apikey",
    "api_key",
    "accesstoken",
    "access_token",
    "refreshtoken",
    "refresh_token",
    "password",
    "secret",
    "providerkey",
    "provider_key",
    "openaiapikey",
    "openai_api_key",
}


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def normalized_name(value: str) -> str:
    return value.replace("-", "").replace("_", "").replace(" ", "").lower()


def walk_property_names(node: Any) -> list[str]:
    names: list[str] = []
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            names.extend(str(key) for key in properties)
        for value in node.values():
            names.extend(walk_property_names(value))
    elif isinstance(node, list):
        for value in node:
            names.extend(walk_property_names(value))
    return names


def validate_schema(schema: dict[str, Any]) -> None:
    require(schema.get("type") == "object", "device feed schema must be an object")
    require(schema.get("additionalProperties") is False, "device feed must fail closed")
    require(set(schema.get("required", [])) == TOP_LEVEL, "top-level required fields drifted")
    require(set(schema.get("properties", {})) == TOP_LEVEL, "top-level properties drifted")
    require(schema["properties"]["schemaVersion"].get("const") == 1, "schemaVersion must remain v1")
    require(schema["properties"]["scope"]["properties"]["type"].get("const") == "profile", "feed must remain profile scoped")

    quantity = (
        schema["properties"]["inventory"]["properties"]["spools"]["items"]
        ["properties"]["quantity"]
    )
    require(quantity.get("additionalProperties") is False, "quantity projection must fail closed")
    qprops = quantity.get("properties", {})
    require(set(qprops["method"].get("enum", [])) == QUANTITY_METHODS, "quantity methods drifted")
    require(set(qprops["status"].get("enum", [])) == QUANTITY_STATUS, "quantity status drifted")
    required_quantity = {
        "evidenceId",
        "remainingGrams",
        "method",
        "source",
        "grossGrams",
        "tareGrams",
        "observedAt",
        "staleAfter",
        "confidence",
        "status",
        "evidenceCount",
        "conflict",
        "conflictEvidenceIds",
        "verificationRequired",
    }
    require(set(quantity.get("required", [])) == required_quantity, "quantity evidence projection drifted")

    placement = (
        schema["properties"]["inventory"]["properties"]["spools"]["items"]
        ["properties"]["placement"]
    )
    require(placement.get("additionalProperties") is False, "placement projection must fail closed")
    pprops = placement.get("properties", {})
    require(set(pprops["status"].get("enum", [])) == PLACEMENT_STATUS, "placement status drifted")
    require(set(pprops["state"].get("enum", [])) == PLACEMENT_STATE, "placement state drifted")
    required_placement = {
        "status",
        "state",
        "printerId",
        "feederId",
        "slot",
        "external",
        "observedAt",
        "source",
        "verificationRequired",
    }
    require(set(placement.get("required", [])) == required_placement, "placement evidence projection drifted")

    readiness = schema["properties"]["readiness"]["properties"]["state"]
    require(set(readiness.get("enum", [])) == READINESS, "readiness states drifted")

    normalized_prohibited = {normalized_name(name) for name in PROHIBITED_SECRET_NAMES}
    for name in walk_property_names(schema):
        require(
            normalized_name(name) not in normalized_prohibited,
            f"device feed must not expose credential field: {name}",
        )


def expect_exact(obj: dict[str, Any], allowed: set[str], context: str) -> None:
    require(set(obj) == allowed, f"{context} fields drifted: {sorted(set(obj) ^ allowed)}")


def validate_quantity(quantity: dict[str, Any], context: str) -> None:
    allowed = {
        "evidenceId",
        "remainingGrams",
        "method",
        "source",
        "grossGrams",
        "tareGrams",
        "observedAt",
        "staleAfter",
        "confidence",
        "status",
        "evidenceCount",
        "conflict",
        "conflictEvidenceIds",
        "verificationRequired",
    }
    expect_exact(quantity, allowed, context)
    require(quantity["method"] in QUANTITY_METHODS, f"{context}.method invalid")
    require(quantity["status"] in QUANTITY_STATUS, f"{context}.status invalid")
    require(isinstance(quantity["evidenceCount"], int) and quantity["evidenceCount"] >= 0, f"{context}.evidenceCount invalid")
    require(isinstance(quantity["conflict"], bool), f"{context}.conflict must be bool")
    require(isinstance(quantity["verificationRequired"], bool), f"{context}.verificationRequired must be bool")
    require(isinstance(quantity["conflictEvidenceIds"], list), f"{context}.conflictEvidenceIds must be list")

    remaining = quantity["remainingGrams"]
    require(remaining is None or (isinstance(remaining, (int, float)) and remaining >= 0), f"{context}.remainingGrams invalid")

    if quantity["status"] == "Current":
        require(remaining is not None, f"{context}: Current requires remainingGrams")
        require(quantity["method"] != "Unknown", f"{context}: Current cannot use Unknown method")
        require(quantity["verificationRequired"] is False, f"{context}: Current must not require verification")

    if quantity["status"] == "Unknown":
        require(remaining is None, f"{context}: Unknown must not expose grams")
        require(quantity["verificationRequired"] is True, f"{context}: Unknown must require verification")

    if quantity["status"] in {"Stale", "Conflict", "InvalidLineage"}:
        require(quantity["verificationRequired"] is True, f"{context}: non-current evidence must require verification")

    if quantity["status"] == "Conflict":
        require(quantity["conflict"] is True, f"{context}: Conflict status must set conflict=true")
        require(len(quantity["conflictEvidenceIds"]) >= 2, f"{context}: Conflict requires at least two evidence IDs")


def validate_placement(placement: dict[str, Any], context: str) -> None:
    allowed = {
        "status",
        "state",
        "printerId",
        "feederId",
        "slot",
        "external",
        "observedAt",
        "source",
        "verificationRequired",
    }
    expect_exact(placement, allowed, context)
    require(placement["status"] in PLACEMENT_STATUS, f"{context}.status invalid")
    require(placement["state"] in PLACEMENT_STATE, f"{context}.state invalid")
    require(isinstance(placement["verificationRequired"], bool), f"{context}.verificationRequired must be bool")

    if placement["status"] == "Current":
        require(placement["verificationRequired"] is False, f"{context}: Current must not require verification")
    else:
        require(placement["verificationRequired"] is True, f"{context}: non-current placement must require verification")

    if placement["state"] == "Stored":
        require(placement["printerId"] is None, f"{context}: Stored cannot retain printerId")
        require(placement["feederId"] is None, f"{context}: Stored cannot retain feederId")
        require(placement["slot"] is None, f"{context}: Stored cannot retain slot")
        require(placement["external"] is False, f"{context}: Stored must set external=false")

    if placement["state"] == "Unknown":
        require(placement["printerId"] is None, f"{context}: Unknown cannot invent printerId")
        require(placement["feederId"] is None, f"{context}: Unknown cannot invent feederId")
        require(placement["slot"] is None, f"{context}: Unknown cannot invent slot")
        require(placement["external"] is None, f"{context}: Unknown must preserve external unknown")

    if placement["state"] == "Loaded" and placement["status"] == "Current":
        require(bool(placement["printerId"]), f"{context}: current Loaded placement requires printerId")
        if placement["external"] is True:
            require(placement["feederId"] is None and placement["slot"] is None, f"{context}: external path cannot have feeder/slot")
        else:
            require(bool(placement["feederId"]), f"{context}: feeder path requires feederId")
            require(isinstance(placement["slot"], int) and placement["slot"] >= 0, f"{context}: feeder path requires slot")


def validate_payload(payload: dict[str, Any]) -> None:
    expect_exact(payload, TOP_LEVEL, "payload")
    require(payload["schemaVersion"] == 1, "unsupported schemaVersion")

    scope = payload["scope"]
    expect_exact(scope, {"type", "id"}, "scope")
    require(scope["type"] == "profile", "scope must be profile")
    require(isinstance(scope["id"], str) and scope["id"].strip(), "scope.id required")

    freshness = payload["freshness"]
    expect_exact(freshness, {"sourceUpdatedAt", "ageSeconds", "stale"}, "freshness")
    require(isinstance(freshness["stale"], bool), "freshness.stale must be bool")

    inventory = payload["inventory"]
    expect_exact(inventory, {"status", "spools"}, "inventory")
    require(inventory["status"] in {"available", "unavailable"}, "inventory status invalid")
    require(isinstance(inventory["spools"], list), "inventory.spools must be list")

    seen_spools: set[str] = set()
    for index, spool in enumerate(inventory["spools"]):
        context = f"inventory.spools[{index}]"
        expect_exact(spool, {"spoolId", "material", "stockState", "color", "quantity", "placement"}, context)
        require(spool["stockState"] in STOCK_STATE, f"{context}.stockState invalid")
        spool_id = spool["spoolId"]
        require(isinstance(spool_id, str) and spool_id.strip(), f"{context}.spoolId required")
        require(spool_id not in seen_spools, f"duplicate spoolId: {spool_id}")
        seen_spools.add(spool_id)
        validate_quantity(spool["quantity"], f"{context}.quantity")

        validate_placement(spool["placement"], f"{context}.placement")

    readiness = payload["readiness"]
    expect_exact(readiness, {"state", "reason", "requiredGrams"}, "readiness")
    require(readiness["state"] in READINESS, "readiness state invalid")
    require(isinstance(readiness["reason"], str) and readiness["reason"].strip(), "readiness.reason required")

    require(isinstance(payload["unknowns"], list), "unknowns must be list")
    require(isinstance(payload["attention"], list), "attention must be list")


def representative_payload() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-09-20T05:00:00.000Z",
        "scope": {"type": "profile", "id": "profile-fixture"},
        "freshness": {
            "sourceUpdatedAt": "2026-09-20T04:59:30.000Z",
            "ageSeconds": 30,
            "stale": False,
        },
        "inventory": {
            "status": "available",
            "spools": [
                {
                    "spoolId": "spool-1",
                    "material": "PLA",
                    "stockState": "Available",
                    "color": "Black",
                    "quantity": {
                        "evidenceId": "qe-1",
                        "remainingGrams": 612,
                        "method": "Measured",
                        "source": "smart-weigh",
                        "grossGrams": 850,
                        "tareGrams": 238,
                        "observedAt": "2026-09-20T04:58:00.000Z",
                        "staleAfter": "2026-09-21T04:58:00.000Z",
                        "confidence": "Confirmed",
                        "status": "Current",
                        "evidenceCount": 1,
                        "conflict": False,
                        "conflictEvidenceIds": [],
                        "verificationRequired": False,
                    },
                    "placement": {
                        "status": "Current",
                        "state": "Loaded",
                        "printerId": "printer-1",
                        "feederId": "ams-1",
                        "slot": 1,
                        "external": False,
                        "observedAt": "2026-09-20T04:57:00.000Z",
                        "source": "manual-load",
                        "verificationRequired": False,
                    },
                }
            ],
        },
        "readiness": {
            "state": "Undetermined",
            "reason": "No print requirement supplied.",
            "requiredGrams": None,
        },
        "unknowns": ["Print readiness undetermined"],
        "attention": [],
    }


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    validate_schema(schema)
    validate_payload(representative_payload())

    conflict = representative_payload()
    q = conflict["inventory"]["spools"][0]["quantity"]
    q["status"] = "Conflict"
    q["conflict"] = True
    q["conflictEvidenceIds"] = ["qe-a", "qe-b"]
    q["verificationRequired"] = True
    validate_payload(conflict)

    unknown = representative_payload()
    q = unknown["inventory"]["spools"][0]["quantity"]
    q["evidenceId"] = None
    q["remainingGrams"] = None
    q["method"] = "Unknown"
    q["status"] = "Unknown"
    q["evidenceCount"] = 0
    q["verificationRequired"] = True
    validate_payload(unknown)

    placement_conflict = representative_payload()
    p = placement_conflict["inventory"]["spools"][0]["placement"]
    p["status"] = "Conflict"
    p["slot"] = None
    p["verificationRequired"] = True
    validate_payload(placement_conflict)

    placement_unknown = representative_payload()
    p = placement_unknown["inventory"]["spools"][0]["placement"]
    p["status"] = "Unknown"
    p["state"] = "Unknown"
    p["printerId"] = None
    p["feederId"] = None
    p["slot"] = None
    p["external"] = None
    p["verificationRequired"] = True
    validate_payload(placement_unknown)

    print("Filament Inventory device-feed v1 contract validation passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"Filament Inventory device-feed v1 validation failed: {exc}") from exc
