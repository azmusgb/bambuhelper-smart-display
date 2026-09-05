import Foundation
import AVFoundation
import UserNotifications

private enum CameraCaptureOutcome: Sendable {
    case completed(URL)
    case unsupported
    case failed(String)
}

/// Owns every AVCaptureSession/AVCapturePhotoOutput mutation on one serial queue.
/// AVFoundation's capture types are not Sendable, so this object is the explicit
/// synchronization boundary and never exposes them to MainActor/UI code.
private final class CameraCaptureService: NSObject, @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.azmusgb.WorkshopCompanion.camera", qos: .userInitiated)
    private let session = AVCaptureSession()
    private let photoOutput = AVCapturePhotoOutput()
    private var configured = false
    private var pendingCompletion: (@Sendable (CameraCaptureOutcome) -> Void)?

    func capture(completion: @escaping @Sendable (CameraCaptureOutcome) -> Void) {
        queue.async { [self] in
            guard pendingCompletion == nil else {
                completion(.failed("A camera capture is already in progress."))
                return
            }

            switch configureIfNeeded() {
            case .success:
                pendingCompletion = completion
                if !session.isRunning {
                    session.startRunning()
                }
                photoOutput.capturePhoto(with: AVCapturePhotoSettings(), delegate: self)
            case .unsupported:
                completion(.unsupported)
            case .failed(let message):
                completion(.failed(message))
            }
        }
    }

    private func configureIfNeeded() -> CameraCaptureOutcome {
        if configured { return .success }

        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .photo

        guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
            return .unsupported
        }

        do {
            let input = try AVCaptureDeviceInput(device: camera)
            guard session.canAddInput(input), session.canAddOutput(photoOutput) else {
                return .failed("The camera session could not add its input or photo output.")
            }
            session.addInput(input)
            session.addOutput(photoOutput)
            configured = true
            return .success
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    private func finish(_ outcome: CameraCaptureOutcome) {
        let completion = pendingCompletion
        pendingCompletion = nil
        completion?(outcome)
    }

    private func persist(_ data: Data) -> CameraCaptureOutcome {
        do {
            let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
                .appendingPathComponent("WorkshopCompanion", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let url = directory.appendingPathComponent("capture-\(UUID().uuidString).jpg")
            try data.write(to: url, options: .atomic)
            return .completed(url)
        } catch {
            return .failed(error.localizedDescription)
        }
    }
}

extension CameraCaptureService: AVCapturePhotoCaptureDelegate {
    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        let outcome: CameraCaptureOutcome
        if let error {
            outcome = .failed(error.localizedDescription)
        } else if let data = photo.fileDataRepresentation() {
            outcome = persist(data)
        } else {
            outcome = .failed("The camera did not return JPEG data.")
        }

        // Keep completion serialization on the same queue that owns capture state.
        queue.async { [self] in
            finish(outcome)
        }
    }
}

private extension CameraCaptureOutcome {
    static var success: CameraCaptureOutcome { .completed(URL(fileURLWithPath: "/dev/null")) }
}

@MainActor
final class CompanionCapabilities: NSObject, ObservableObject {
    enum ResultState: String {
        case completed
        case cancelled
        case permissionDenied = "permission-denied"
        case foregroundRequired = "foreground-required"
        case unsupported
        case failed
    }

    @Published private(set) var cameraActive = false
    @Published private(set) var lastPhotoURL: URL?
    @Published private(set) var lastError: String?

    private let speech = AVSpeechSynthesizer()
    private let camera = CameraCaptureService()

    func speak(_ text: String) -> ResultState {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .failed }
        speech.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: trimmed)
        speech.speak(utterance)
        return .completed
    }

    func requestNotification(title: String, body: String) async -> ResultState {
        let center = UNUserNotificationCenter.current()
        do {
            let settings = await center.notificationSettings()
            if settings.authorizationStatus == .notDetermined {
                let granted = try await center.requestAuthorization(options: [.alert, .sound])
                guard granted else { return .permissionDenied }
            } else if settings.authorizationStatus == .denied {
                return .permissionDenied
            }

            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            try await center.add(request)
            return .completed
        } catch {
            lastError = error.localizedDescription
            return .failed
        }
    }

    func capturePhoto(
        isApplicationActive: Bool,
        completion: @escaping @MainActor @Sendable (ResultState, URL?) -> Void
    ) {
        guard isApplicationActive else {
            completion(.foregroundRequired, nil)
            return
        }

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            beginCapture(completion: completion)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                Task { @MainActor in
                    guard let self else { return }
                    guard granted else {
                        completion(.permissionDenied, nil)
                        return
                    }
                    self.beginCapture(completion: completion)
                }
            }
        case .denied, .restricted:
            completion(.permissionDenied, nil)
        @unknown default:
            completion(.unsupported, nil)
        }
    }

    private func beginCapture(
        completion: @escaping @MainActor @Sendable (ResultState, URL?) -> Void
    ) {
        cameraActive = true
        camera.capture { [weak self] outcome in
            Task { @MainActor in
                guard let self else { return }
                self.cameraActive = false
                switch outcome {
                case .completed(let url):
                    self.lastPhotoURL = url
                    completion(.completed, url)
                case .unsupported:
                    completion(.unsupported, nil)
                case .failed(let message):
                    self.lastError = message
                    completion(.failed, nil)
                }
            }
        }
    }
}
