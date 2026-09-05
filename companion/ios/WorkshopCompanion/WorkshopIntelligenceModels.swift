import Foundation

enum WorkshopIntelligenceV1 {
    static let version = 1
    static let maxQuestionCharacters = 500
    static let maxSnapshotTextCharacters = 160
    static let maxSummaryCharacters = 500
    static let maxObservationCharacters = 240
    static let maxObservations = 5
    static let maxActionCharacters = 160
    static let maxActions = 3

    enum QuestionKind: String, Codable, CaseIterable, Sendable {
        case explainStatus = "explain-status"
        case diagnose
        case summarize
        case recommendNext = "recommend-next"
        case photoInspect = "photo-inspect"
    }

    enum Severity: String, Codable, CaseIterable, Sendable {
        case info
        case watch
        case warning
        case critical
    }

    enum ActionIntent: String, Codable, CaseIterable, Sendable {
        case physicalCheck = "physical-check"
        case openWorkshopOS = "open-workshop-os"
        case reviewPrinter = "review-printer"
        case reviewPower = "review-power"
        case reviewNetwork = "review-network"
        case none
    }

    struct DeviceSnapshot: Codable, Equatable, Sendable {
        var identity: String
        var online: Bool?
        var lanReachable: Bool?
        var authenticatedSession: Bool?
    }

    struct PrinterSnapshot: Codable, Equatable, Sendable {
        var name: String?
        var state: String?
        var progressPct: Double?
        var layer: Int?
        var layerTotal: Int?
        var nozzleC: Double?
        var bedC: Double?
        var chamberC: Double?
        var errorSummary: String?
    }

    struct PowerSnapshot: Codable, Equatable, Sendable {
        var mapped: Bool?
        var on: Bool?
        var watts: Double?
    }

    struct CompanionSnapshot: Codable, Equatable, Sendable {
        var bleConnected: Bool?
        var lanReady: Bool?
        var latestPhoneCaptureAvailable: Bool?
    }

    struct Snapshot: Codable, Equatable, Sendable {
        var device: DeviceSnapshot
        var printer: PrinterSnapshot?
        var power: PowerSnapshot?
        var companion: CompanionSnapshot?
    }

    struct Request: Codable, Equatable, Identifiable, Sendable {
        let v: Int
        let id: String
        let kind: QuestionKind
        let question: String
        let snapshot: Snapshot

        init(
            id: String = UUID().uuidString,
            kind: QuestionKind,
            question: String,
            snapshot: Snapshot
        ) {
            self.v = WorkshopIntelligenceV1.version
            self.id = id
            self.kind = kind
            self.question = WorkshopTextHardener.clean(question, maxCharacters: maxQuestionCharacters)
            self.snapshot = WorkshopSnapshotHardener.clean(snapshot)
        }
    }

    struct RecommendedAction: Codable, Equatable, Sendable, Identifiable {
        let id: UUID
        let label: String
        let intent: ActionIntent
        let advisoryOnly: Bool

        init(label: String, intent: ActionIntent) {
            self.id = UUID()
            self.label = WorkshopTextHardener.clean(label, maxCharacters: maxActionCharacters)
            self.intent = intent
            self.advisoryOnly = true
        }

        enum CodingKeys: String, CodingKey {
            case label
            case intent
            case advisoryOnly
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.id = UUID()
            self.label = WorkshopTextHardener.clean(
                try container.decode(String.self, forKey: .label),
                maxCharacters: maxActionCharacters
            )
            self.intent = try container.decode(ActionIntent.self, forKey: .intent)
            self.advisoryOnly = true
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(label, forKey: .label)
            try container.encode(intent, forKey: .intent)
            try container.encode(true, forKey: .advisoryOnly)
        }
    }

    struct Answer: Codable, Equatable, Identifiable, Sendable {
        let v: Int
        let id: String
        let provider: String
        let severity: Severity
        let summary: String
        let observations: [String]
        let recommendedActions: [RecommendedAction]
        let requiresPhysicalCheck: Bool

        init(
            requestID: String,
            provider: String,
            severity: Severity,
            summary: String,
            observations: [String],
            recommendedActions: [RecommendedAction],
            requiresPhysicalCheck: Bool
        ) {
            self.v = WorkshopIntelligenceV1.version
            self.id = requestID
            self.provider = WorkshopTextHardener.clean(provider, maxCharacters: 80)
            self.severity = severity
            self.summary = WorkshopTextHardener.clean(summary, maxCharacters: maxSummaryCharacters)
            self.observations = Array(observations.prefix(maxObservations)).map {
                WorkshopTextHardener.clean($0, maxCharacters: maxObservationCharacters)
            }
            self.recommendedActions = Array(recommendedActions.prefix(maxActions))
            self.requiresPhysicalCheck = requiresPhysicalCheck
        }
    }
}

enum WorkshopTextHardener {
    static func clean(_ value: String, maxCharacters: Int) -> String {
        var scalars = String.UnicodeScalarView()
        scalars.reserveCapacity(min(value.unicodeScalars.count, maxCharacters))

        for scalar in value.unicodeScalars {
            let code = scalar.value
            let isAllowedWhitespace = scalar == "\n" || scalar == "\t" || scalar == " "
            let isControl = code < 0x20 || (code >= 0x7F && code <= 0x9F)
            if isControl && !isAllowedWhitespace { continue }
            scalars.append(scalar)
            if scalars.count >= maxCharacters { break }
        }

        return String(scalars)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func optional(_ value: String?, maxCharacters: Int) -> String? {
        guard let value else { return nil }
        let cleaned = clean(value, maxCharacters: maxCharacters)
        return cleaned.isEmpty ? nil : cleaned
    }
}

enum WorkshopSnapshotHardener {
    static func clean(_ snapshot: WorkshopIntelligenceV1.Snapshot) -> WorkshopIntelligenceV1.Snapshot {
        let limit = WorkshopIntelligenceV1.maxSnapshotTextCharacters
        let device = WorkshopIntelligenceV1.DeviceSnapshot(
            identity: WorkshopTextHardener.clean(snapshot.device.identity, maxCharacters: limit),
            online: snapshot.device.online,
            lanReachable: snapshot.device.lanReachable,
            authenticatedSession: snapshot.device.authenticatedSession
        )

        let printer = snapshot.printer.map {
            WorkshopIntelligenceV1.PrinterSnapshot(
                name: WorkshopTextHardener.optional($0.name, maxCharacters: limit),
                state: WorkshopTextHardener.optional($0.state, maxCharacters: limit),
                progressPct: bounded($0.progressPct, 0...100),
                layer: nonNegative($0.layer),
                layerTotal: nonNegative($0.layerTotal),
                nozzleC: finite($0.nozzleC),
                bedC: finite($0.bedC),
                chamberC: finite($0.chamberC),
                errorSummary: WorkshopTextHardener.optional($0.errorSummary, maxCharacters: limit)
            )
        }

        let power = snapshot.power.map {
            WorkshopIntelligenceV1.PowerSnapshot(
                mapped: $0.mapped,
                on: $0.on,
                watts: nonNegative($0.watts)
            )
        }

        return WorkshopIntelligenceV1.Snapshot(
            device: device,
            printer: printer,
            power: power,
            companion: snapshot.companion
        )
    }

    private static func finite(_ value: Double?) -> Double? {
        guard let value, value.isFinite else { return nil }
        return value
    }

    private static func bounded(_ value: Double?, _ range: ClosedRange<Double>) -> Double? {
        guard let value = finite(value) else { return nil }
        return min(max(value, range.lowerBound), range.upperBound)
    }

    private static func nonNegative(_ value: Double?) -> Double? {
        guard let value = finite(value) else { return nil }
        return max(0, value)
    }

    private static func nonNegative(_ value: Int?) -> Int? {
        guard let value else { return nil }
        return max(0, value)
    }
}
