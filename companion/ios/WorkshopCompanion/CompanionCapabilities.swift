import Foundation
import AVFoundation
import UserNotifications

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
    private let cameraSession = AVCaptureSession()
    private let photoOutput = AVCapturePhotoOutput()
    private var pendingPhotoCompletion: ((ResultState, URL?) -> Void)?

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

    func capturePhoto(isApplicationActive: Bool, completion: @escaping (ResultState, URL?) -> Void) {
        guard isApplicationActive else {
            completion(.foregroundRequired, nil)
            return
        }

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configureAndCapture(completion: completion)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                Task { @MainActor in
                    guard let self else { return }
                    guard granted else {
                        completion(.permissionDenied, nil)
                        return
                    }
                    self.configureAndCapture(completion: completion)
                }
            }
        case .denied, .restricted:
            completion(.permissionDenied, nil)
        @unknown default:
            completion(.unsupported, nil)
        }
    }

    private func configureAndCapture(completion: @escaping (ResultState, URL?) -> Void) {
        do {
            if cameraSession.inputs.isEmpty {
                cameraSession.beginConfiguration()
                cameraSession.sessionPreset = .photo
                guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
                    cameraSession.commitConfiguration()
                    completion(.unsupported, nil)
                    return
                }
                let input = try AVCaptureDeviceInput(device: camera)
                guard cameraSession.canAddInput(input), cameraSession.canAddOutput(photoOutput) else {
                    cameraSession.commitConfiguration()
                    completion(.failed, nil)
                    return
                }
                cameraSession.addInput(input)
                cameraSession.addOutput(photoOutput)
                cameraSession.commitConfiguration()
            }

            pendingPhotoCompletion = completion
            cameraActive = true
            if !cameraSession.isRunning {
                DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                    self?.cameraSession.startRunning()
                    Task { @MainActor in self?.takePhotoWhenReady() }
                }
            } else {
                takePhotoWhenReady()
            }
        } catch {
            lastError = error.localizedDescription
            completion(.failed, nil)
        }
    }

    private func takePhotoWhenReady() {
        let settings = AVCapturePhotoSettings()
        photoOutput.capturePhoto(with: settings, delegate: self)
    }

    private func finishPhoto(state: ResultState, url: URL?) {
        cameraActive = false
        lastPhotoURL = url
        let completion = pendingPhotoCompletion
        pendingPhotoCompletion = nil
        completion?(state, url)
    }
}

extension CompanionCapabilities: AVCapturePhotoCaptureDelegate {
    nonisolated func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        Task { @MainActor in
            if let error {
                self.lastError = error.localizedDescription
                self.finishPhoto(state: .failed, url: nil)
                return
            }
            guard let data = photo.fileDataRepresentation() else {
                self.finishPhoto(state: .failed, url: nil)
                return
            }
            do {
                let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
                    .appendingPathComponent("WorkshopCompanion", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                let url = directory.appendingPathComponent("capture-\(UUID().uuidString).jpg")
                try data.write(to: url, options: .atomic)
                self.finishPhoto(state: .completed, url: url)
            } catch {
                self.lastError = error.localizedDescription
                self.finishPhoto(state: .failed, url: nil)
            }
        }
    }
}
