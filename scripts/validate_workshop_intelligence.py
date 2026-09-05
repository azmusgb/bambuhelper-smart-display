#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "companion/intelligence/workshop-intelligence-v1.md"
SCHEMA = ROOT / "companion/intelligence/workshop-intelligence-v1.schema.json"
MODELS = ROOT / "companion/ios/WorkshopCompanion/WorkshopIntelligenceModels.swift"
ENGINE = ROOT / "companion/ios/WorkshopCompanion/WorkshopIntelligenceProvider.swift"
APPLE = ROOT / "companion/ios/WorkshopCompanion/AppleFoundationModelsWorkshopProvider.swift"
CONTENT = ROOT / "companion/ios/WorkshopCompanion/ContentView.swift"
PROJECT = ROOT / "companion/ios/project.yml"

EXPECTED_KINDS = {
    "explain-status",
    "diagnose",
    "summarize",
    "recommend-next",
    "photo-inspect",
}
EXPECTED_SEVERITIES = {"info", "watch", "warning", "critical"}
EXPECTED_INTENTS = {
    "physical-check",
    "open-workshop-os",
    "review-printer",
    "review-power",
    "review-network",
    "none",
}


def fail(message: str) -> None:
    raise SystemExit(f"Workshop Intelligence validation failed: {message}")


def text(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require(source_name: str, source: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in source]
    if missing:
        fail(f"{source_name} missing required contracts: {', '.join(missing)}")


def main() -> None:
    spec = text(SPEC)
    schema = json.loads(text(SCHEMA))
    models = text(MODELS)
    engine = text(ENGINE)
    apple = text(APPLE)
    content = text(CONTENT)
    project = text(PROJECT)

    defs = schema.get("$defs", {})
    request = defs.get("request", {})
    response = defs.get("response", {})
    action = defs.get("action", {})

    if request.get("properties", {}).get("v", {}).get("const") != 1:
        fail("request schema version must be 1")
    if response.get("properties", {}).get("v", {}).get("const") != 1:
        fail("response schema version must be 1")

    kinds = set(request.get("properties", {}).get("kind", {}).get("enum", []))
    if kinds != EXPECTED_KINDS:
        fail(f"question-kind allow-list drift: {sorted(kinds)}")

    severities = set(response.get("properties", {}).get("severity", {}).get("enum", []))
    if severities != EXPECTED_SEVERITIES:
        fail(f"severity allow-list drift: {sorted(severities)}")

    intents = set(action.get("properties", {}).get("intent", {}).get("enum", []))
    if intents != EXPECTED_INTENTS:
        fail(f"action-intent allow-list drift: {sorted(intents)}")

    if action.get("properties", {}).get("advisoryOnly", {}).get("const") is not True:
        fail("advisoryOnly must be hard-locked true")

    question_max = request.get("properties", {}).get("question", {}).get("maxLength")
    summary_max = response.get("properties", {}).get("summary", {}).get("maxLength")
    observations_max = response.get("properties", {}).get("observations", {}).get("maxItems")
    actions_max = response.get("properties", {}).get("recommendedActions", {}).get("maxItems")
    if (question_max, summary_max, observations_max, actions_max) != (500, 500, 5, 3):
        fail("schema output/input caps drifted")

    require("spec", spec, [
        "The ESP32 remains the trusted physical surface",
        "LLM output is advisory",
        "never silently fall back",
        "untrusted evidence",
        "There is no direct mutation intent in v1",
    ])

    require("Swift models", models, [
        "maxQuestionCharacters = 500",
        "maxSummaryCharacters = 500",
        "maxObservations = 5",
        "maxActions = 3",
        "self.advisoryOnly = true",
        "WorkshopSnapshotHardener.clean",
    ])

    require("provider engine", engine, [
        "protocol WorkshopIntelligenceProvider: Sendable",
        "WorkshopIntelligenceProviderFactory.preferred()",
        "UNTRUSTED WORKSHOP EVIDENCE",
        "never as instructions",
        "Never claim that you changed hardware",
    ])

    require("Apple provider", apple, [
        "#if canImport(FoundationModels)",
        "import FoundationModels",
        "SystemLanguageModel.default",
        "LanguageModelSession(instructions:",
        "generating: AppleWorkshopGeneratedAnswer.self",
        "@Generable",
        ".maximumCount(5)",
        ".maximumCount(3)",
        "never operate hardware",
    ])

    # The provider layer may reason and recommend. It must not become a hidden
    # network client or direct printer/power mutation path.
    forbidden_provider_tokens = [
        "URLSession",
        "apiKey",
        "Authorization: Bearer",
        "/api/printer/stop",
        "/api/printer/pause",
        "/api/printer/resume",
        "/api/power",
        "tasmota",
        "printerAccessCode",
        "portalCode",
        "sessionCookie",
    ]
    for token in forbidden_provider_tokens:
        if token in apple or token in engine:
            fail(f"provider boundary contains forbidden authority/secret token: {token}")

    require("Companion UI", content, [
        'Section("Workshop Copilot")',
        'Text("Copilot is advisory only.',
        "WorkshopIntelligenceV1.Snapshot(",
        "Ask Workshop Copilot",
    ])

    if 'deploymentTarget:\n    iOS: "17.0"' not in project:
        fail("minimum iOS compatibility changed unexpectedly")
    if 'SWIFT_VERSION: "6.0"' not in project:
        fail("Workshop Companion must stay on Swift 6")

    print("Workshop Intelligence v1 contract and safety boundary passed")


if __name__ == "__main__":
    main()
