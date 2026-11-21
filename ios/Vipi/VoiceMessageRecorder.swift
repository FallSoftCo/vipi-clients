import SwiftUI
import AVFoundation

@MainActor @Observable final class VoiceMessageRecorder: NSObject, AVAudioRecorderDelegate {
    enum Phase { case idle, asking, recording, review, denied, failed }
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
        let allowed = await AVAudioApplication.requestRecordPermission()
        guard generation == attempt else { return }
        guard allowed else { phase = .denied; return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .mixWithOthers])
            try session.setActive(true)
            ownsSession = true
            let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("m4a")
            url = file
            let capture = try AVAudioRecorder(url: file, settings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 24_000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 48_000])
            recorder = capture
            capture.delegate = self
            guard capture.record(forDuration: 175) else { throw MediaCryptography.Failure.invalidFile }
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: file.path)
            phase = .recording
        } catch { cancel(); phase = .failed }
    }
    var currentTime: Double { recorder?.currentTime ?? seconds }
    func stop() {
        guard phase == .recording, let recorder else { return }
        seconds = recorder.currentTime
        recorder.stop()
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
        Task { @MainActor in if self.recorder === recorder { self.cancel(); self.phase = .failed } }
    }
    private func finish(success: Bool) {
        recorder = nil
        deactivate()
        if success { phase = .review }
        else { cancel(); phase = .failed }
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
        recorder?.delegate = nil; recorder?.stop(); recorder = nil
        if let url { try? FileManager.default.removeItem(at: url) }
        url = nil; seconds = 0; phase = .idle
        deactivate()
    }
}
struct VoiceCaptureView: View {
    var finished: (ChosenMedia?) -> Void
    @State private var recorder = VoiceMessageRecorder()
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                switch recorder.phase {
                case .recording:
                    TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                        Text(Duration.seconds(recorder.currentTime).formatted(.time(pattern: .minuteSecond)))
                            .font(.largeTitle.monospacedDigit()).accessibilityLabel("Recording duration")
                    }
                    Button("Stop recording", systemImage: "stop.fill") { recorder.stop() }.buttonStyle(.borderedProminent)
                case .review:
                    Text(Duration.seconds(recorder.seconds).formatted(.time(pattern: .minuteSecond))).font(.title.monospacedDigit())
                    Button("Use recording", systemImage: "checkmark") { finished(recorder.take()) }.buttonStyle(.borderedProminent)
                    Button("Record again") { Task { await recorder.begin() } }
                case .asking: ProgressView()
                case .denied:
                    Text("Allow microphone access in Settings to record a voice message.").multilineTextAlignment(.center)
                    Link("Open Settings", destination: URL(string: UIApplication.openSettingsURLString)!)
                case .failed, .idle:
                    if recorder.phase == .failed { Text("Couldn’t record that message.") }
                    Button("Record voice message", systemImage: "mic") { Task { await recorder.begin() } }.buttonStyle(.borderedProminent)
                }
            }.padding().navigationTitle("Voice message").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { finished(nil) } } }
            .onDisappear { recorder.cancel() }
            .onChange(of: scenePhase) { _, phase in if phase == .background { recorder.cancel() } }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { note in
                if (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) == AVAudioSession.InterruptionType.began.rawValue,
                   recorder.phase == .recording { recorder.stop() }
            }
        }
    }
}
