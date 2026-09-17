#!/usr/bin/env python3
"""Validate the machine-readable Workshop OS UI/review safety contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "workshop-ui-review-v1.json"

EXPECTED_LAYERS = {
    "artifact",
    "control-plane",
    "recovery",
    "architecture",
    "acceptance",
}
EXPECTED_TELEMETRY = [
    "Fresh",
    "Stale",
    "Unavailable",
    "Connecting",
    "CommandChannelUnavailable",
    "InvalidForCurrentState",
]
EXPECTED_ACTION_CLASSES = [
    "ordinary",
    "guarded",
    "destructive",
    "recovery-impacting",
]
EXPECTED_OPERATION_STATES = [
    "Idle",
    "Pending",
    "Success",
    "RecoverableError",
    "FatalError",
]
EXPECTED_ACCEPTANCE_STATES = [
    "implemented",
    "built",
    "tested",
    "runtime-validated",
    "production-validated",
    "physically-validated",
    "accepted",
    "stable",
]
EXPECTED_PRIORITY = [
    "fail-safe-markup",
    "control-semantics",
    "accessibility-architecture",
    "privileged-api-hardening",
    "recovery-and-ota",
    "maintainability",
    "polish",
]

REQUIRED_CHECKS = {
    "artifact": {
        "valid-markup",
        "fail-safe-initial-state",
        "accessible-navigation",
        "focus-management",
        "loading-empty-error-states",
        "reduced-motion",
    },
    "control-plane": {
        "authenticated-mutations",
        "freshness-before-command",
        "command-eligibility",
        "destructive-action-classification",
        "capability-gating",
        "double-submit-prevention",
    },
    "recovery": {
        "ota-structure-validation",
        "board-compatibility-validation",
        "artifact-size-and-sha256-verification",
        "rollback-or-recovery-path",
        "interrupted-update-behavior",
        "network-recovery",
    },
    "architecture": {
        "workshop-os-is-firmware-authority",
        "filament-inventory-is-inventory-authority",
        "no-inferred-ams-placement",
        "unknown-remains-unknown",
        "least-authority-device-credential",
        "capabilities-not-model-string-feature-gates",
    },
    "acceptance": {
        "exact-source-sha",
        "test-evidence",
        "runtime-evidence",
        "physical-evidence",
        "artifact-identity",
        "no-state-promotion-without-evidence",
    },
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def expect_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        fail(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def main() -> int:
    if not CONTRACT.is_file():
        fail(f"missing contract: {CONTRACT.relative_to(ROOT)}")

    try:
        data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    expect_equal("schemaVersion", data.get("schemaVersion"), "workshop-ui-review-v1")

    layers = data.get("reviewLayers")
    if not isinstance(layers, list):
        fail("reviewLayers must be an array")

    by_id: dict[str, dict[str, object]] = {}
    for layer in layers:
        if not isinstance(layer, dict):
            fail("every review layer must be an object")
        layer_id = layer.get("id")
        if not isinstance(layer_id, str) or not layer_id:
            fail("every review layer requires a non-empty id")
        if layer_id in by_id:
            fail(f"duplicate review layer: {layer_id}")
        by_id[layer_id] = layer

    expect_equal("review layer ids", set(by_id), EXPECTED_LAYERS)

    for layer_id, required in REQUIRED_CHECKS.items():
        checks = by_id[layer_id].get("requiredChecks")
        if not isinstance(checks, list) or not all(isinstance(v, str) for v in checks):
            fail(f"{layer_id}.requiredChecks must be a string array")
        missing = required.difference(checks)
        if missing:
            fail(f"{layer_id} missing required checks: {sorted(missing)}")

    expect_equal("telemetryStates", data.get("telemetryStates"), EXPECTED_TELEMETRY)
    expect_equal("actionClasses", data.get("actionClasses"), EXPECTED_ACTION_CLASSES)
    expect_equal("operationStates", data.get("operationStates"), EXPECTED_OPERATION_STATES)
    expect_equal("acceptanceStates", data.get("acceptanceStates"), EXPECTED_ACCEPTANCE_STATES)
    expect_equal("priorityOrder", data.get("priorityOrder"), EXPECTED_PRIORITY)

    capability = data.get("capabilityPolicy")
    if not isinstance(capability, dict):
        fail("capabilityPolicy must be an object")
    expect_equal(
        "capabilityPolicy.deviceIdentityMayResolveCapabilities",
        capability.get("deviceIdentityMayResolveCapabilities"),
        True,
    )
    expect_equal(
        "capabilityPolicy.modelStringMayDirectlyGateFeatures",
        capability.get("modelStringMayDirectlyGateFeatures"),
        False,
    )
    expect_equal(
        "capabilityPolicy.unknownCapabilitiesFailClosed",
        capability.get("unknownCapabilitiesFailClosed"),
        True,
    )

    routing = data.get("routingPolicy")
    if not isinstance(routing, dict):
        fail("routingPolicy must be an object")
    expect_equal("routingPolicy.hashRoutingRequiredOnWs350", routing.get("hashRoutingRequiredOnWs350"), False)
    expect_equal("routingPolicy.predictableBackRequired", routing.get("predictableBackRequired"), True)
    expect_equal(
        "routingPolicy.safeWorkspacePersistencePreferred",
        routing.get("safeWorkspacePersistencePreferred"),
        True,
    )

    print("Workshop UI review contract validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
