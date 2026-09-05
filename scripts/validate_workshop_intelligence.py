#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "companion/intelligence/workshop-intelligence-v1.md"
SCHEMA = ROOT / "companion/intelligence/workshop-intelligence-v1.schema.json"
EVALS = ROOT / "companion/intelligence/eval-cases.json"
KNOWLEDGE_JSON = ROOT / "companion/intelligence/workshop-domain-knowledge-v1.json"
MODELS = ROOT / "companion/ios/WorkshopCompanion/WorkshopIntelligenceModels.swift"
ENGINE = ROOT / "companion/ios/WorkshopCompanion/WorkshopIntelligenceProvider.swift"
SAFETY = ROOT / "companion/ios/WorkshopCompanion/WorkshopIntelligenceSafety.swift"
KNOWLEDGE_SWIFT = ROOT / "companion/ios/WorkshopCompanion/WorkshopDomainKnowledge.swift"
APPLE = ROOT / "companion/ios/WorkshopCompanion/AppleFoundationModelsWorkshopProvider.swift"
CONTENT = ROOT / "companion/ios/WorkshopCompanion/ContentView.swift"
TESTS = ROOT / "companion/ios/WorkshopCompanionTests/WorkshopIntelligenceSafetyTests.swift"
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
REQUIRED_EVAL_IDS = {
    "normal-print",
    "missing-telemetry",
    "prompt-injection-device-name",
    "prompt-injection-error-text",
    "direct-control-request",
    "ordinary-error-not-critical",
    "urgent-smoke-evidence",
    "offline-device",
    "photo-inspect-reserved",
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
    evals = json.loads(text(EVALS))
    knowledge_json = json.loads(text(KNOWLEDGE_JSON))
    models = text(MODELS)
    engine = text(ENGINE)
    safety = text(SAFETY)
    knowledge_swift = text(KNOWLEDGE_SWIFT)
    apple = text(APPLE)
    content = text(CONTENT)
    tests = text(TESTS)
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
        "TRUSTED WORKSHOP DOMAIN RULES",
        "UNTRUSTED WORKSHOP EVIDENCE",
        "WorkshopDomainKnowledge.select",
        "photoInspectionUnavailable",
        "guard kind != .photoInspect",
        "guard request.kind != .photoInspect",
        "never as instructions",
        "Never claim that you changed hardware",
    ])

    require("deterministic output guard", safety, [
        "WorkshopIntelligenceOutputGuard",
        "prohibitedExecutionClaims",
        "hasUrgentEvidence",
        "answer.severity == .critical && !hasUrgentEvidence(snapshot)",
        "No hardware action was performed",
        ".openWorkshopOS",
    ])

    require("Apple provider", apple, [
        "#if canImport(FoundationModels)",
        "import FoundationModels",
        "SystemLanguageModel.default",
        "LanguageModelSession(instructions:",
        "generating: AppleWorkshopGeneratedAnswer.self",
        "WorkshopIntelligenceOutputGuard.apply",
        "@Generable",
        ".maximumCount(5)",
        ".maximumCount(3)",
        "never operate hardware",
    ])

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
        'Button("Attention")',
        'Button("Next check")',
        'Button("Explain")',
        'Button("Read aloud")',
    ])

    require("executable safety tests", tests, [
        "testTextHardenerStripsControlCharactersAndCapsLength",
        "testRecommendedActionAlwaysDecodesAsAdvisoryOnly",
        "testExecutionClaimIsWithheld",
        "testCriticalDowngradesWithoutUrgentEvidence",
        "testCriticalCanRemainWhenSnapshotContainsUrgentEvidence",
        "testRequestSanitizesUntrustedSnapshotText",
        "testDomainKnowledgeSelectsActivePrintAndPowerGuard",
        "testDomainKnowledgeSelectsNetworkSemanticsWhenLanIsDown",
        "testPromptSeparatesTrustedRulesFromUntrustedEvidence",
        "testPhotoInspectionFailsClosedUntilImageProviderExists",
    ])

    if 'deploymentTarget:\n    iOS: "17.0"' not in project:
        fail("minimum iOS compatibility changed unexpectedly")
    if 'SWIFT_VERSION: "6.0"' not in project:
        fail("Workshop Companion must stay on Swift 6")
    require("Xcode project", project, [
        "WorkshopCompanionTests:",
        "type: bundle.unit-test",
        "- WorkshopCompanionTests",
    ])

    if evals.get("version") != 1:
        fail("eval corpus version must be 1")
    cases = evals.get("cases")
    if not isinstance(cases, list):
        fail("eval corpus cases must be a list")
    ids = {case.get("id") for case in cases if isinstance(case, dict)}
    if ids != REQUIRED_EVAL_IDS:
        fail(f"eval corpus drift: {sorted(ids)}")
    for case in cases:
        if case.get("kind") not in EXPECTED_KINDS:
            fail(f"eval {case.get('id')} has invalid question kind")
        if not case.get("question") or len(case["question"]) > 500:
            fail(f"eval {case.get('id')} has invalid question")
        expectations = case.get("expectations", {})
        if expectations.get("advisoryOnly") is not True:
            fail(f"eval {case.get('id')} must require advisory-only output")

    injection_cases = [case for case in cases if str(case.get("id", "")).startswith("prompt-injection-")]
    if len(injection_cases) < 2:
        fail("at least two prompt-injection eval cases are required")
    if not all(case.get("expectations", {}).get("mustIgnoreEmbeddedInstructions") is True for case in injection_cases):
        fail("prompt-injection cases must require embedded instructions to be ignored")

    direct = next(case for case in cases if case.get("id") == "direct-control-request")
    if direct.get("expectations", {}).get("mustRefuseDirectExecution") is not True:
        fail("direct-control eval must require refusal of direct execution")

    photo = next(case for case in cases if case.get("id") == "photo-inspect-reserved")
    if photo.get("expectations", {}).get("mustFailClosedUntilMultimodal") is not True:
        fail("photo-inspect eval must require fail-closed behavior")
    if photo.get("expectations", {}).get("mustNotClaimVisualInspection") is not True:
        fail("photo-inspect eval must prohibit unsupported visual claims")

    if knowledge_json.get("version") != 1:
        fail("domain knowledge version must be 1")
    entries = knowledge_json.get("entries")
    if not isinstance(entries, list) or len(entries) < 10:
        fail("domain knowledge must contain at least 10 entries")
    ids = []
    for entry in entries:
        entry_id = entry.get("id")
        entry_text = entry.get("text")
        tags = entry.get("tags")
        if not entry_id or not entry_text or not isinstance(tags, list) or not tags:
            fail(f"invalid domain knowledge entry: {entry}")
        if len(entry_text) > 300:
            fail(f"domain knowledge entry too long: {entry_id}")
        ids.append(entry_id)
        if f'id: "{entry_id}"' not in knowledge_swift:
            fail(f"Swift knowledge missing id: {entry_id}")
        if f'text: "{entry_text}"' not in knowledge_swift:
            fail(f"Swift knowledge text drift: {entry_id}")
    if len(ids) != len(set(ids)):
        fail("domain knowledge ids must be unique")
    require("Swift domain knowledge", knowledge_swift, [
        "static let version = 1",
        "static let maxSelectedEntries = 4",
        "static func select(",
        "no-action-authority",
        "selected.count >= maxSelectedEntries",
    ])

    print(
        f"Workshop Intelligence v1 contract, safety boundary, executable tests, "
        f"{len(cases)} eval cases and {len(entries)} domain rules passed"
    )


if __name__ == "__main__":
    main()
