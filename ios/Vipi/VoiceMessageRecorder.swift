import SwiftUI
import AVFoundation

@MainActor protocol VoiceCapture: AnyObject {
    var phase: VoiceMessageRecorder.Phase { get }
    var currentTime: Double { get }
    var level: Double { get }
    func begin() async
    func stop()
    func take() -> ChosenMedia?
    func cancel()
}

@MainActor @Observable final class VoiceMessageRecorder: NSObject, AVAudioRecorderDelegate, VoiceCapture {
    enum Phase { case idle, asking, permissionReady, recording, review, denied, failed }
    private(set) var phase = Phase.idle
    private(set) var seconds = 0.0
    private var recorder: AVAudioRecorder?
    private var url: URL?
    private var ownsSession = false
    private var generation = UUID()
    func begin() async {
        cancel()
        let attempt = generation
        phase = .asking
        let firstPermissionPrompt = AVAudioApplication.shared.recordPermission == .undetermined
        let allowed = await AVAudioApplication.requestRecordPermission()
        guard generation == attempt else { return }
        guard allowed else {
            phase = .denied
            return
        }
        // A permission dialog interrupts the original touch. A fresh user
        // gesture starts capture after the dialog goes away.
        if firstPermissionPrompt {
            phase = .permissionReady
            return
        }
        VoiceAudioHandoff.stopCurrent()
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .mixWithOthers])
            try session.setActive(true)
            ownsSession = true
            let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
                .appendingPathExtension("m4a")
            url = file
            let capture = try AVAudioRecorder(
                url: file,
                settings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 24_000, AVNumberOfChannelsKey: 1,
                    AVEncoderBitRateKey: 48_000
                ])
            capture.isMeteringEnabled = true
            recorder = capture
            capture.delegate = self
            guard capture.record(forDuration: 175) else { throw MediaCryptography.Failure.invalidFile }
            try FileManager.default.setAttributes(
                [.protectionKey: FileProtectionType.complete], ofItemAtPath: file.path)
            phase = .recording
        } catch {
            cancel()
            phase = .failed
        }
    }
    var currentTime: Double { recorder?.currentTime ?? seconds }
    var level: Double {
        guard let recorder, recorder.isRecording else { return 0 }
        recorder.updateMeters()
        return max(0, min(1, (Double(recorder.averagePower(forChannel: 0)) + 55) / 55))
    }
    func stop() {
        guard phase == .recording, let recorder else { return }
        seconds = recorder.currentTime
        recorder.stop()
        // Interruption can reset the recorder clock before the delegate fires.
        // The finished file retains the duration of the samples already recorded.
        if seconds <= 0.1, let audio = try? AVAudioPlayer(contentsOf: recorder.url) {
            seconds = min(175, audio.duration)
        }
        finish(success: seconds > 0.1)
    }
    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        Task { @MainActor in
            guard self.recorder === recorder, self.phase == .recording else { return }
            self.seconds = min(175, max(self.seconds, (try? AVAudioPlayer(contentsOf: recorder.url))?.duration ?? 0))
            self.finish(success: flag && self.seconds > 0.1)
        }
    }
    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        Task { @MainActor in
            if self.recorder === recorder {
                self.cancel()
                self.phase = .failed
            }
        }
    }
    private func finish(success: Bool) {
        recorder = nil
        deactivate()
        if success {
            phase = .review
        } else {
            cancel()
            phase = .failed
        }
    }
    private func deactivate() {
        if ownsSession {
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            ownsSession = false
        }
    }
    func take() -> ChosenMedia? {
        guard phase == .review, let file = url else { return nil }
        url = nil
        return ChosenMedia(url: file, kind: .voice)
    }
    func cancel() {
        generation = UUID()
        recorder?.delegate = nil
        recorder?.stop()
        recorder = nil
        if let url { try? FileManager.default.removeItem(at: url) }
        url = nil
        seconds = 0
        phase = .idle
        deactivate()
    }
}
