import Foundation

enum WorkshopIntelligenceOutputGuard {
    private static let prohibitedExecutionClaims = [
        "i stopped",
        "i paused",
        "i resumed",
        "i restarted",
        "i rebooted",
        "i powered off",
        "i powered on",
        "i turned off",
        "i turned on",
        "i changed the setting",
        "i changed settings",
        "i updated the firmware",
        "i installed the update",
        "i reset the device"
    ]

    private static let urgentEvidenceTerms = [
        "fire",
        "smoke",
        "thermal runaway",
        "overheat",
        "overheating",
        "electrical short",
        "short circuit",
        "burning smell"
    ]

    static func apply(
        _ answer: WorkshopIntelligenceV1.Answer,
        to snapshot: WorkshopIntelligenceV1.Snapshot
    ) -> WorkshopIntelligenceV1.Answer {
        if containsExecutionClaim(answer) {
            return WorkshopIntelligenceV1.Answer(
                requestID: answer.id,
                provider: answer.provider,
                severity: .warning,
                summary: "Workshop Copilot withheld a model response that incorrectly implied it operated hardware. No hardware action was performed.",
                observations: [
                    "Workshop Intelligence is advisory-only; control state must come from Workshop OS telemetry."
                ],
                recommendedActions: [
                    .init(label: "Review the live Workshop OS state", intent: .openWorkshopOS)
                ],
                requiresPhysicalCheck: false
            )
        }

        let severity: WorkshopIntelligenceV1.Severity
        if answer.severity == .critical && !hasUrgentEvidence(snapshot) {
            // Critical is a scarce signal. The LLM cannot promote ordinary or
            // incomplete telemetry to urgent without deterministic evidence in
            // the snapshot. It may still use warning/watch for uncertainty.
            severity = .warning
        } else {
            severity = answer.severity
        }

        return WorkshopIntelligenceV1.Answer(
            requestID: answer.id,
            provider: answer.provider,
            severity: severity,
            summary: answer.summary,
            observations: answer.observations,
            recommendedActions: answer.recommendedActions.map {
                .init(label: $0.label, intent: $0.intent)
            },
            requiresPhysicalCheck: answer.requiresPhysicalCheck
        )
    }

    private static func containsExecutionClaim(_ answer: WorkshopIntelligenceV1.Answer) -> Bool {
        let corpus = ([answer.summary] + answer.observations + answer.recommendedActions.map(\.label))
            .joined(separator: "\n")
            .lowercased()
        return prohibitedExecutionClaims.contains { corpus.contains($0) }
    }

    private static func hasUrgentEvidence(_ snapshot: WorkshopIntelligenceV1.Snapshot) -> Bool {
        let evidence = [
            snapshot.printer?.state,
            snapshot.printer?.errorSummary
        ]
        .compactMap { $0 }
        .joined(separator: " ")
        .lowercased()

        return urgentEvidenceTerms.contains { evidence.contains($0) }
    }
}
