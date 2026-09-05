import Foundation

enum WorkshopIntelligenceOutputGuard {
    private static let prohibitedExecutionClaims = [
        "i stopped",
        "i have stopped",
        "i've stopped",
        "i paused",
        "i have paused",
        "i've paused",
        "i resumed",
        "i have resumed",
        "i've resumed",
        "i restarted",
        "i have restarted",
        "i've restarted",
        "i rebooted",
        "i have rebooted",
        "i've rebooted",
        "i powered off",
        "i have powered off",
        "i've powered off",
        "i powered on",
        "i have powered on",
        "i've powered on",
        "i turned off",
        "i have turned off",
        "i've turned off",
        "i turned on",
        "i have turned on",
        "i've turned on",
        "i changed the setting",
        "i changed settings",
        "i updated the firmware",
        "i installed the update",
        "i reset the device",
        "stop command sent",
        "pause command sent",
        "resume command sent",
        "power-off command sent",
        "power off command sent",
        "power-on command sent",
        "power on command sent",
        "restart command sent",
        "reboot command sent"
    ]

    private static let urgentSnapshotEvidenceTerms = [
        "fire",
        "smoke",
        "thermal runaway",
        "overheat",
        "overheating",
        "electrical short",
        "short circuit",
        "burning smell"
    ]

    // User text is evidence too, but use report-like phrases so a hypothetical
    // question such as "what if there were smoke?" does not automatically grant
    // CRITICAL severity.
    private static let urgentUserEvidencePhrases = [
        "i see smoke",
        "there is smoke",
        "there's smoke",
        "smoke coming",
        "smoke is coming",
        "i smell burning",
        "smells like burning",
        "burning smell",
        "on fire",
        "caught fire",
        "thermal runaway",
        "electrical short",
        "short circuit",
        "is overheating",
        "it's overheating"
    ]

    static func apply(
        _ answer: WorkshopIntelligenceV1.Answer,
        to snapshot: WorkshopIntelligenceV1.Snapshot,
        userQuestion: String = ""
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
        if answer.severity == .critical && !hasUrgentEvidence(snapshot, userQuestion: userQuestion) {
            // Critical is a scarce signal. The LLM cannot promote ordinary or
            // incomplete telemetry to urgent without deterministic evidence in
            // either the sanitized snapshot or a direct user hazard report.
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

    private static func hasUrgentEvidence(
        _ snapshot: WorkshopIntelligenceV1.Snapshot,
        userQuestion: String
    ) -> Bool {
        let snapshotEvidence = [
            snapshot.printer?.state,
            snapshot.printer?.errorSummary
        ]
        .compactMap { $0 }
        .joined(separator: " ")
        .lowercased()

        if urgentSnapshotEvidenceTerms.contains(where: snapshotEvidence.contains) {
            return true
        }

        let userEvidence = WorkshopTextHardener.clean(
            userQuestion,
            maxCharacters: WorkshopIntelligenceV1.maxQuestionCharacters
        ).lowercased()
        return urgentUserEvidencePhrases.contains(where: userEvidence.contains)
    }
}
