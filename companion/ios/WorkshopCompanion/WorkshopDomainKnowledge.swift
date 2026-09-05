import Foundation

enum WorkshopDomainKnowledge {
    static let version = 1
    static let maxSelectedEntries = 4

    struct Entry: Equatable, Sendable {
        let id: String
        let tags: Set<String>
        let text: String
    }

    static let entries: [Entry] = [
        .init(
            id: "state-running",
            tags: ["printer", "state", "running", "printing"],
            text: "RUNNING means the printer reports an active print. Pause, Stop, and power-off recommendations must respect the active-print guard."
        ),
        .init(
            id: "state-pause",
            tags: ["printer", "state", "pause", "paused"],
            text: "PAUSE means the print is still active but paused. Resume is a guarded user action; a paused print is not equivalent to idle."
        ),
        .init(
            id: "state-finish",
            tags: ["printer", "state", "finish", "finished"],
            text: "FINISH is a completed print state, not an error. Post-print cooldown, bed temperature, and configured auto-off behavior may still matter."
        ),
        .init(
            id: "state-failed",
            tags: ["printer", "state", "failed", "error"],
            text: "FAILED alone does not establish a dangerous condition. Use errorSummary and supplied telemetry to distinguish cancellation, filament issues, connectivity, or an actual fault."
        ),
        .init(
            id: "state-prepare",
            tags: ["printer", "state", "prepare", "heating"],
            text: "PREPARE is part of an active print lifecycle and can include homing or heating. Treat it as active for destructive power-off guidance."
        ),
        .init(
            id: "printer-disconnected",
            tags: ["printer", "offline", "disconnected", "connection"],
            text: "Workshop OS can be online while a configured printer is disconnected. Do not infer printer state from device reachability when printer telemetry is absent."
        ),
        .init(
            id: "device-offline",
            tags: ["device", "offline", "network", "wifi", "lan"],
            text: "If the Workshop device or LAN link is unavailable, printer telemetry may be stale or unknown. Prefer network/reachability checks before diagnosing print mechanics from missing data."
        ),
        .init(
            id: "portal-session",
            tags: ["auth", "session", "authentication", "lan"],
            text: "BLE discovery never authenticates protected Workshop OS routes. A portal/session-authenticated LAN connection is required for protected state or controls."
        ),
        .init(
            id: "power-mapped",
            tags: ["power", "plug", "mapped", "smart"],
            text: "A mapped smart plug is a separate power-control integration. Plug state and printer MQTT state are distinct evidence and can disagree during boot, shutdown, or connectivity loss."
        ),
        .init(
            id: "power-active-print",
            tags: ["power", "printing", "running", "pause", "prepare"],
            text: "Cutting printer power during RUNNING, PAUSE, or PREPARE is destructive. Workshop OS uses an explicit active-print power-off guard; Copilot must never suggest bypassing it."
        ),
        .init(
            id: "temperature-evidence",
            tags: ["temperature", "nozzle", "bed", "chamber", "heat"],
            text: "Temperatures are evidence, not diagnoses. Expected nozzle and bed temperatures depend on material, stage, and printer behavior; do not declare overheating from a normal print temperature without supporting fault evidence."
        ),
        .init(
            id: "critical-severity",
            tags: ["critical", "fire", "smoke", "thermal", "burning"],
            text: "CRITICAL is reserved for supplied urgent evidence such as smoke, fire, burning smell, thermal runaway, electrical short, or equivalent physical hazard. Ordinary print failures should not be promoted to critical."
        ),
        .init(
            id: "physical-check",
            tags: ["physical", "visual", "adhesion", "spaghetti", "mechanical"],
            text: "Some failures require visual or physical verification. If available telemetry cannot establish adhesion, spaghetti failure, obstruction, smoke, noise, or mechanical interference, say that a physical check is required."
        ),
        .init(
            id: "phone-photo",
            tags: ["photo", "camera", "image", "iphone"],
            text: "A phone capture being available does not mean the current v1 text model inspected it. Never claim visual findings unless a future explicit multimodal photo-inspect path supplied image evidence."
        ),
        .init(
            id: "no-action-authority",
            tags: ["stop", "pause", "resume", "power", "light", "settings", "ota", "recovery"],
            text: "Workshop Copilot v1 is advisory-only. Hardware and configuration mutations remain explicit Workshop OS controls outside model authority."
        )
    ]

    static func select(
        question: String,
        snapshot: WorkshopIntelligenceV1.Snapshot
    ) -> [Entry] {
        let evidence = searchableText(question: question, snapshot: snapshot)
        let tokens = Set(tokenize(evidence))

        let scored = entries.compactMap { entry -> (Entry, Int)? in
            let score = entry.tags.reduce(0) { partial, tag in
                partial + (tokens.contains(tag) ? 1 : 0)
            }
            return score > 0 ? (entry, score) : nil
        }
        .sorted {
            if $0.1 != $1.1 { return $0.1 > $1.1 }
            return $0.0.id < $1.0.id
        }

        var selected = Array(scored.prefix(maxSelectedEntries).map(\.0))

        // Requests mentioning any control-like word always carry the immutable
        // advisory-authority rule even if four other entries scored higher.
        let controlRule = entries.first { $0.id == "no-action-authority" }
        let controlTokens = Set(["stop", "pause", "resume", "power", "light", "settings", "ota", "recovery"])
        if !tokens.isDisjoint(with: controlTokens),
           let controlRule,
           !selected.contains(where: { $0.id == controlRule.id }) {
            if selected.count >= maxSelectedEntries { selected.removeLast() }
            selected.append(controlRule)
        }

        return selected
    }

    static func render(_ entries: [Entry]) -> String {
        entries.map { "[\($0.id)] \($0.text)" }.joined(separator: "\n")
    }

    private static func searchableText(
        question: String,
        snapshot: WorkshopIntelligenceV1.Snapshot
    ) -> String {
        [
            question,
            snapshot.device.identity,
            snapshot.printer?.name,
            snapshot.printer?.state,
            snapshot.printer?.errorSummary,
            snapshot.device.online == false ? "device offline network" : nil,
            snapshot.device.lanReachable == false ? "lan offline network" : nil,
            snapshot.device.authenticatedSession == false ? "auth session" : nil,
            snapshot.power?.mapped == true ? "power mapped plug" : nil,
            snapshot.power?.on == false ? "power off" : nil,
            snapshot.companion?.latestPhoneCaptureAvailable == true ? "photo camera iphone" : nil
        ]
        .compactMap { $0 }
        .joined(separator: " ")
    }

    private static func tokenize(_ value: String) -> [String] {
        value.lowercased()
            .split { !$0.isLetter && !$0.isNumber }
            .map(String.init)
    }
}
