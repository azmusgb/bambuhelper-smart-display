#!/usr/bin/env python3
"""Validate the Workshop OS 12 device-state contract and core truth invariants.

This validator intentionally uses only the Python standard library so it can run
in the repository's existing Validate workflow without adding dependencies.
It validates both the schema guardrails and representative semantic payloads.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "workshop-device-state-v1.schema.json"

ALLOWED_TOP_LEVEL = {
    "schemaVersion",
    "generatedAt",
    "profileScope",
    "source",
    "inventory",
    "placements",
    "attention",
    "readiness",
}

ALLOWED_PLACEMENT = {
    "spoolId",
    "printerId",
    "pathType",
    "feederId",
    "slotId",
    "evidenceId",
    "observedAt",
    "freshness",
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

FRESHNESS = {"fresh", "stale", "unknown", "conflicting"}
QUANTITY_QUALITY = {
    "measured",
    "calculated_from_measured",
    "printer_estimated",
    "visual_estimate",
    "imported_estimate",
    "unknown",
}
READINESS = {"ready", "ready_with_caveat", "not_ready", "undetermined"}


class ValidationError(RuntimeError):
    """Contract validation failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def normalized_name(value: str) -> str:
    return value.replace("-", "").replace(" ", "").lower()


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


def validate_schema_guardrails(schema: dict[str, Any]) -> None:
    require(schema.get("type") == "object", "top-level schema must be an object")
    require(schema.get("additionalProperties") is False, "top-level contract must fail closed")
    require(set(schema.get("required", [])) == ALLOWED_TOP_LEVEL, "top-level required fields drifted")
    require(set(schema.get("properties", {})) == ALLOWED_TOP_LEVEL, "top-level properties drifted")

    props = schema["properties"]
    require(props["schemaVersion"].get("const") == "1.0", "schemaVersion must be locked to 1.0")

    source = props["source"]
    require(source.get("additionalProperties") is False, "source must fail closed")
    require(
        source["properties"]["authority"].get("const") == "filamentinventory",
        "Filament Inventory must remain the contract authority",
    )

    defs = schema.get("$defs", {})
    freshness = set(defs.get("freshness", {}).get("enum", []))
    require(freshness == FRESHNESS, "freshness states must remain explicit")

    placement = defs.get("placement", {})
    require(placement.get("additionalProperties") is False, "placement must fail closed")
    require(
        {"spoolId", "printerId", "pathType", "evidenceId", "observedAt", "freshness"}.issubset(
            set(placement.get("required", []))
        ),
        "placement must require explicit identity, evidence, time, and freshness",
    )
    require(
        set(placement.get("properties", {})) == ALLOWED_PLACEMENT,
        "placement surface changed; review truth-boundary implications",
    )
    require(
        set(placement["properties"]["pathType"].get("enum", [])) == {"ams_slot", "external_spool"},
        "placement path types drifted",
    )

    quantity = defs.get("quantityProjection", {})
    require(quantity.get("additionalProperties") is False, "quantity projection must fail closed")
    require(
        set(quantity["properties"]["quality"].get("$ref", "") for _ in [0]) == {"#/$defs/evidenceQuality"},
        "quantity quality must use evidenceQuality",
    )
    require(
        set(defs.get("evidenceQuality", {}).get("enum", [])) == QUANTITY_QUALITY,
        "quantity evidence qualities drifted",
    )

    readiness = defs.get("readiness", {})
    require(
        set(readiness["properties"]["status"].get("enum", [])) == READINESS,
        "readiness must preserve undetermined and caveated states",
    )

    normalized_prohibited = {normalized_name(name) for name in PROHIBITED_SECRET_NAMES}
    for name in walk_property_names(schema):
        require(
            normalized_name(name) not in normalized_prohibited,
            f"device contract must not expose credential field: {name}",
        )


def expect_keys_exact(obj: dict[str, Any], allowed: set[str], context: str) -> None:
    extras = set(obj) - allowed
    require(not extras, f"{context} contains unsupported fields: {sorted(extras)}")


def require_string(value: Any, context: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{context} must be a non-empty string")
    return value


def validate_payload(payload: dict[str, Any]) -> None:
    """Validate semantic invariants that matter to the firmware trust boundary.

    This is intentionally narrower than a complete JSON Schema implementation.
    The checked invariants are the ones that must remain fail-closed even before
    a full schema validator is introduced in a consumer.
    """

    require(isinstance(payload, dict), "payload must be an object")
    expect_keys_exact(payload, ALLOWED_TOP_LEVEL, "payload")
    require(set(payload) == ALLOWED_TOP_LEVEL, "payload is missing required top-level fields")
    require(payload["schemaVersion"] == "1.0", "unsupported schemaVersion")

    profile = payload["profileScope"]
    require(isinstance(profile, dict), "profileScope must be an object")
    expect_keys_exact(profile, {"memberId", "scopeType"}, "profileScope")
    require_string(profile.get("memberId"), "profileScope.memberId")
    require(profile.get("scopeType") in {"private", "shared"}, "invalid profile scope")

    source = payload["source"]
    require(isinstance(source, dict), "source must be an object")
    expect_keys_exact(source, {"authority", "freshness", "observedAt"}, "source")
    require(source.get("authority") == "filamentinventory", "unexpected device-data authority")
    require(source.get("freshness") in FRESHNESS, "invalid source freshness")
    require_string(source.get("observedAt"), "source.observedAt")

    inventory = payload["inventory"]
    require(isinstance(inventory, list), "inventory must be an array")
    seen_spools: set[str] = set()
    for index, spool in enumerate(inventory):
        context = f"inventory[{index}]"
        require(isinstance(spool, dict), f"{context} must be an object")
        expect_keys_exact(
            spool,
            {"spoolId", "displayName", "material", "color", "remaining", "freshness"},
            context,
        )
        spool_id = require_string(spool.get("spoolId"), f"{context}.spoolId")
        require(spool_id not in seen_spools, f"duplicate spool projection: {spool_id}")
        seen_spools.add(spool_id)
        require(spool.get("freshness") in FRESHNESS, f"invalid {context}.freshness")

        remaining = spool.get("remaining")
        require(isinstance(remaining, dict), f"{context}.remaining must be an object")
        expect_keys_exact(
            remaining,
            {"state", "grams", "quality", "evidenceId", "observedAt"},
            f"{context}.remaining",
        )
        state = remaining.get("state")
        require(state in {"known", "unknown", "conflicting"}, f"invalid {context}.remaining.state")
        require(remaining.get("quality") in QUANTITY_QUALITY, f"invalid {context}.remaining.quality")
        grams = remaining.get("grams")
        evidence_id = remaining.get("evidenceId")
        if state == "known":
            require(isinstance(grams, (int, float)) and not isinstance(grams, bool), f"{context} known grams required")
            require(grams >= 0, f"{context} grams cannot be negative")
            require_string(evidence_id, f"{context}.remaining.evidenceId")
        else:
            require(grams is None, f"{context} {state} quantity must not expose a gram claim")

    placements = payload["placements"]
    require(isinstance(placements, list), "placements must be an array")
    placed_spools: set[str] = set()
    for index, placement in enumerate(placements):
        context = f"placements[{index}]"
        require(isinstance(placement, dict), f"{context} must be an object")
        expect_keys_exact(placement, ALLOWED_PLACEMENT, context)
        spool_id = require_string(placement.get("spoolId"), f"{context}.spoolId")
        require(spool_id not in placed_spools, f"spool has more than one placement: {spool_id}")
        placed_spools.add(spool_id)
        require_string(placement.get("printerId"), f"{context}.printerId")
        require_string(placement.get("evidenceId"), f"{context}.evidenceId")
        require_string(placement.get("observedAt"), f"{context}.observedAt")
        require(placement.get("freshness") in FRESHNESS, f"invalid {context}.freshness")
        path_type = placement.get("pathType")
        require(path_type in {"ams_slot", "external_spool"}, f"invalid {context}.pathType")
        if path_type == "ams_slot":
            require_string(placement.get("feederId"), f"{context}.feederId")
            require_string(placement.get("slotId"), f"{context}.slotId")
        else:
            require(placement.get("slotId") is None, f"{context} external spool cannot claim an AMS slot")

    require(isinstance(payload["attention"], list), "attention must be an array")

    readiness = payload["readiness"]
    require(isinstance(readiness, dict), "readiness must be an object")
    expect_keys_exact(readiness, {"status", "freshness", "summary", "requirementEvidenceId"}, "readiness")
    require(readiness.get("status") in READINESS, "invalid readiness status")
    require(readiness.get("freshness") in FRESHNESS, "invalid readiness freshness")

    # Fail closed on credential-shaped keys even if a future caller bypasses the
    # top-level exact-key checks by passing nested extension objects.
    def reject_secret_keys(node: Any, context: str = "payload") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                require(
                    normalized_name(str(key)) not in {normalized_name(name) for name in PROHIBITED_SECRET_NAMES},
                    f"{context} contains credential-shaped field: {key}",
                )
                reject_secret_keys(value, f"{context}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                reject_secret_keys(value, f"{context}[{index}]")

    reject_secret_keys(payload)


def base_valid_payload() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": "2026-09-16T21:00:00Z",
        "profileScope": {"memberId": "member-test", "scopeType": "private"},
        "source": {
            "authority": "filamentinventory",
            "freshness": "fresh",
            "observedAt": "2026-09-16T21:00:00Z",
        },
        "inventory": [
            {
                "spoolId": "spool-001",
                "displayName": "Black PLA",
                "material": "PLA",
                "color": "Black",
                "remaining": {
                    "state": "known",
                    "grams": 612,
                    "quality": "measured",
                    "evidenceId": "qe-001",
                    "observedAt": "2026-09-16T20:58:00Z",
                },
                "freshness": "fresh",
            }
        ],
        "placements": [
            {
                "spoolId": "spool-001",
                "printerId": "printer-001",
                "pathType": "ams_slot",
                "feederId": "ams-001",
                "slotId": "A1",
                "evidenceId": "placement-001",
                "observedAt": "2026-09-16T20:59:00Z",
                "freshness": "fresh",
            }
        ],
        "attention": [],
        "readiness": {
            "status": "undetermined",
            "freshness": "fresh",
            "summary": "Print requirement evidence has not been supplied.",
            "requirementEvidenceId": None,
        },
    }


def expect_invalid(name: str, mutate: Any) -> None:
    payload = base_valid_payload()
    mutate(payload)
    try:
        validate_payload(payload)
    except ValidationError:
        return
    raise ValidationError(f"negative fixture unexpectedly passed: {name}")


def run_semantic_fixtures() -> None:
    validate_payload(base_valid_payload())

    expect_invalid("unsupported schema version", lambda p: p.__setitem__("schemaVersion", "2.0"))
    expect_invalid("wrong authority", lambda p: p["source"].__setitem__("authority", "workshop-os"))
    expect_invalid("known quantity without evidence", lambda p: p["inventory"][0]["remaining"].__setitem__("evidenceId", None))
    expect_invalid("unknown quantity with grams", lambda p: p["inventory"][0]["remaining"].update({"state": "unknown", "grams": 612}))
    expect_invalid("AMS placement without slot", lambda p: p["placements"][0].__setitem__("slotId", None))

    def duplicate_placement(payload: dict[str, Any]) -> None:
        duplicate = copy.deepcopy(payload["placements"][0])
        duplicate["slotId"] = "A2"
        duplicate["evidenceId"] = "placement-002"
        payload["placements"].append(duplicate)

    expect_invalid("one spool in two placements", duplicate_placement)

    def telemetry_inference(payload: dict[str, Any]) -> None:
        payload["placements"][0]["matchedByColorMaterial"] = True

    expect_invalid("color/material inferred placement", telemetry_inference)

    def leaked_secret(payload: dict[str, Any]) -> None:
        payload["apiKey"] = "forbidden"

    expect_invalid("credential field", leaked_secret)


def main() -> int:
    require(SCHEMA_PATH.is_file(), f"missing schema: {SCHEMA_PATH}")
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot load schema: {exc}") from exc

    validate_schema_guardrails(schema)
    run_semantic_fixtures()
    print("Workshop OS 12 device contract validation passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"Workshop OS 12 device contract validation failed: {exc}") from exc
