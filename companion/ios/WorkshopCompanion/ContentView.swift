import SwiftUI

struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var bluetooth = BLECentral()
    @StateObject private var capabilities = CompanionCapabilities()
    @StateObject private var intelligence = WorkshopIntelligenceEngine()
    @State private var intelligenceQuestion = "What needs attention right now?"

    var body: some View {
        NavigationStack {
            List {
                Section("Connection") {
                    LabeledContent("Bluetooth", value: bluetooth.phase.rawValue)
                    if let name = bluetooth.peripheralName {
                        LabeledContent("Device", value: name)
                    }
                    HStack {
                        Button("Scan for Workshop OS") { bluetooth.scan() }
                            .disabled(bluetooth.phase == .scanning || bluetooth.phase == .connecting)
                        if bluetooth.phase == .connected {
                            Button("Disconnect", role: .destructive) { bluetooth.disconnect() }
                        }
                    }
                }

                Section("Workshop OS") {
                    if let bootstrap = bluetooth.bootstrap {
                        LabeledContent("Identity", value: bootstrap.device)
                        LabeledContent("Authentication", value: bootstrap.auth)
                        if let url = bootstrap.baseURL {
                            LabeledContent("LAN endpoint", value: url.absoluteString)
                            Link("Open authenticated Workshop OS", destination: loginURL(from: url))
                        }
                    } else {
                        Text("Connect over BLE to discover the local Workshop OS endpoint. BLE discovery does not authenticate protected routes.")
                            .foregroundStyle(.secondary)
                    }
                }

                if let state = bluetooth.deviceState {
                    Section("Device state") {
                        statusRow("Device online", state.online)
                        statusRow("Phone present", state.phone)
                        statusRow("LAN reachable", state.lan)
                        statusRow("LAN session", state.session)
                    }
                }

                Section("Workshop Copilot") {
                    LabeledContent("Provider", value: intelligence.providerName)
                    LabeledContent("Context", value: copilotContextLabel())

                    if let reason = intelligence.availabilityReason,
                       intelligence.phase == .unavailable {
                        Text(reason)
                            .foregroundStyle(.secondary)
                    }

                    TextField("Ask about the current workshop state", text: $intelligenceQuestion, axis: .vertical)
                        .lineLimit(2...5)

                    HStack {
                        Button("Attention") {
                            runCopilot(.summarize, "What needs attention right now?")
                        }
                        .buttonStyle(.bordered)

                        Button("Next check") {
                            runCopilot(.recommendNext, "What is the safest useful thing to check next?")
                        }
                        .buttonStyle(.bordered)

                        Button("Explain") {
                            runCopilot(.explainStatus, "Explain the current Workshop state in plain language.")
                        }
                        .buttonStyle(.bordered)
                    }
                    .disabled(intelligence.phase == .thinking || intelligence.phase == .checking)

                    Button {
                        runCopilot(.diagnose, intelligenceQuestion)
                    } label: {
                        if intelligence.phase == .thinking {
                            HStack(spacing: 8) {
                                ProgressView()
                                Text("Thinking on iPhone…")
                            }
                        } else {
                            Text("Ask Workshop Copilot")
                        }
                    }
                    .disabled(intelligence.phase == .thinking || intelligence.phase == .checking)

                    Text("Copilot is advisory only. The model never receives Workshop credentials and cannot directly pause, stop, power, configure, update, or recover hardware.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if let answer = intelligence.answer {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(answer.severity.rawValue.uppercased())
                                    .font(.caption.bold())
                                    .foregroundStyle(severityColor(answer.severity))
                                Spacer()
                                Text(answer.provider)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                            }

                            Text(answer.summary)
                                .font(.body)

                            if !answer.observations.isEmpty {
                                Text("Observations")
                                    .font(.caption.bold())
                                ForEach(answer.observations, id: \.self) { observation in
                                    Text("• \(observation)")
                                        .font(.callout)
                                }
                            }

                            if !answer.recommendedActions.isEmpty {
                                Text("Recommended next checks")
                                    .font(.caption.bold())
                                ForEach(answer.recommendedActions) { action in
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(action.label)
                                            .font(.callout)
                                        Text(action.intent.rawValue)
                                            .font(.caption.monospaced())
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }

                            if answer.requiresPhysicalCheck {
                                Label("Physical verification recommended", systemImage: "eye")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            HStack {
                                Button("Read aloud") {
                                    _ = capabilities.speak(copilotSpeechText(answer))
                                }
                                .buttonStyle(.bordered)

                                Button("Clear") {
                                    intelligence.clearAnswer()
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }

                    if let error = intelligence.lastError {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }

                Section("Companion request") {
                    if let event = bluetooth.lastEvent {
                        LabeledContent("Type", value: event.t)
                        Text("Correlation: \(event.id)")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)

                        if isActionable(event) {
                            Button(actionTitle(event)) { perform(event) }
                                .disabled(capabilities.cameraActive)
                        } else {
                            Text("No user action is required for this event.")
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("No companion event received yet.")
                            .foregroundStyle(.secondary)
                    }
                }

                if let photo = capabilities.lastPhotoURL {
                    Section("Latest camera capture") {
                        Text(photo.lastPathComponent)
                            .font(.caption.monospaced())
                        Text("The image remains local to the iPhone in the accepted Companion baseline. Candidate firmware adds authenticated LAN transfer; BLE never carries photo payloads.")
                            .foregroundStyle(.secondary)
                    }
                }

                if let error = bluetooth.lastError ?? capabilities.lastError {
                    Section("Needs attention") {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Workshop Companion")
            .task {
                await intelligence.refreshAvailability()
            }
        }
    }

    @ViewBuilder
    private func statusRow(_ label: String, _ value: Bool?) -> some View {
        LabeledContent(label, value: value.map { $0 ? "Yes" : "No" } ?? "Unknown")
    }

    private func loginURL(from base: URL) -> URL {
        base.appendingPathComponent("login")
    }

    private func runCopilot(_ kind: WorkshopIntelligenceV1.QuestionKind, _ question: String) {
        intelligenceQuestion = question
        Task {
            await intelligence.ask(
                kind: kind,
                question: question,
                snapshot: intelligenceSnapshot()
            )
        }
    }

    private func intelligenceSnapshot() -> WorkshopIntelligenceV1.Snapshot {
        let identity = bluetooth.bootstrap?.device
            ?? bluetooth.peripheralName
            ?? "Workshop OS"

        return WorkshopIntelligenceV1.Snapshot(
            device: .init(
                identity: identity,
                online: bluetooth.deviceState?.online,
                lanReachable: bluetooth.deviceState?.lan,
                authenticatedSession: bluetooth.deviceState?.session
            ),
            printer: nil,
            power: nil,
            companion: .init(
                bleConnected: bluetooth.phase == .connected,
                lanReady: bluetooth.deviceState?.lan,
                latestPhoneCaptureAvailable: capabilities.lastPhotoURL != nil
            )
        )
    }

    private func copilotContextLabel() -> String {
        if bluetooth.deviceState != nil {
            return "Live device link"
        }
        if bluetooth.phase == .connected {
            return "BLE connection"
        }
        return "Local app only"
    }

    private func copilotSpeechText(_ answer: WorkshopIntelligenceV1.Answer) -> String {
        var parts = [answer.summary]
        if !answer.observations.isEmpty {
            parts.append("Observations: " + answer.observations.joined(separator: ". "))
        }
        if !answer.recommendedActions.isEmpty {
            parts.append("Recommended next checks: " + answer.recommendedActions.map(\.label).joined(separator: ". "))
        }
        if answer.requiresPhysicalCheck {
            parts.append("Physical verification is recommended.")
        }
        return parts.joined(separator: " ")
    }

    private func severityColor(_ severity: WorkshopIntelligenceV1.Severity) -> Color {
        switch severity {
        case .info: return .secondary
        case .watch: return .yellow
        case .warning: return .orange
        case .critical: return .red
        }
    }

    private func isActionable(_ event: CompanionEnvelope) -> Bool {
        [
            CompanionProtocolV1.DeviceEvent.cameraRequest.rawValue,
            CompanionProtocolV1.DeviceEvent.ttsRequest.rawValue,
            CompanionProtocolV1.DeviceEvent.notificationRequest.rawValue
        ].contains(event.t)
    }

    private func actionTitle(_ event: CompanionEnvelope) -> String {
        switch event.t {
        case CompanionProtocolV1.DeviceEvent.cameraRequest.rawValue: return "Take requested photo"
        case CompanionProtocolV1.DeviceEvent.ttsRequest.rawValue: return "Speak requested text"
        case CompanionProtocolV1.DeviceEvent.notificationRequest.rawValue: return "Post requested notification"
        default: return "Handle request"
        }
    }

    private func perform(_ event: CompanionEnvelope) {
        switch event.t {
        case CompanionProtocolV1.DeviceEvent.cameraRequest.rawValue:
            capabilities.capturePhoto(isApplicationActive: scenePhase == .active) { state, url in
                var payload: [String: JSONValue] = ["state": .string(state.rawValue)]
                if url != nil { payload["stored-on-phone"] = .bool(true) }
                bluetooth.send(type: .cameraResult, correlationID: event.id, payload: payload)
            }

        case CompanionProtocolV1.DeviceEvent.ttsRequest.rawValue:
            let text = string("text", in: event.p) ?? ""
            let state = capabilities.speak(text)
            bluetooth.send(type: .ttsResult, correlationID: event.id, payload: ["state": .string(state.rawValue)])

        case CompanionProtocolV1.DeviceEvent.notificationRequest.rawValue:
            let title = string("title", in: event.p) ?? "Workshop OS"
            let body = string("body", in: event.p) ?? "Workshop needs attention."
            Task {
                let state = await capabilities.requestNotification(title: title, body: body)
                bluetooth.send(type: .notificationResult, correlationID: event.id, payload: ["state": .string(state.rawValue)])
            }

        default:
            break
        }
    }

    private func string(_ key: String, in payload: [String: JSONValue]?) -> String? {
        guard case .string(let value)? = payload?[key] else { return nil }
        return value
    }
}

#Preview {
    ContentView()
}
