import SwiftUI
import AVFAudio

/// Voice recording and draft previews can share the same in-process audio handoff.
@MainActor enum VoiceAudioHandoff {
    private static weak var owner: AnyObject?
    private static var yieldCurrent: (() -> Void)?

    static func owns(_ candidate: AnyObject) -> Bool { owner === candidate }
    static func claim(_ candidate: AnyObject, onYield: @escaping () -> Void) {
        if !owns(candidate) { stopCurrent() }
        owner = candidate
        yieldCurrent = onYield
    }
    static func release(_ candidate: AnyObject) {
        guard owns(candidate) else { return }
        owner = nil
        yieldCurrent = nil
    }
    static func stopCurrent() {
        let previous = yieldCurrent
        owner = nil
        yieldCurrent = nil
        previous?()
    }
}

/// Owns one decoded note and its temporary plaintext file only while that row is in use.
@MainActor final class VoiceNotePlayer: NSObject, ObservableObject, @preconcurrency AVAudioPlayerDelegate {
    enum State { case idle, loading, playing, paused, finished, failed }
    @Published private(set) var state = State.idle
    @Published private(set) var duration = 0.0
    private var savedPosition = 0.0
    private var player: AVAudioPlayer?
    private var file: URL?
    private var opening: Task<Void, Never>?
    private var ownsAudioSession = false
    var elapsed: Double { player?.currentTime ?? savedPosition }

    func toggle(load: @escaping @MainActor () async throws -> URL) {
        if state == .playing {
            pause()
            return
        }
        guard state != .loading else { return }
        VoiceAudioHandoff.claim(self) { [weak self] in self?.yieldPlayback() }
        if state == .finished { savedPosition = 0 }
        if player != nil {
            start()
            return
        }
        state = .loading
        opening = Task { [weak self] in
            do {
                let url = try await load()
                guard let self, !Task.isCancelled, VoiceAudioHandoff.owns(self) else {
                    try? FileManager.default.removeItem(at: url)
                    return
                }
                self.file = url
                let decoded = try AVAudioPlayer(contentsOf: url)
                guard decoded.duration.isFinite, decoded.duration > 0 else {
                    throw MediaCryptography.Failure.invalidFile
                }
                self.player = decoded
                decoded.delegate = self
                self.duration = decoded.duration
                decoded.currentTime = min(self.savedPosition, decoded.duration)
                self.start()
            } catch {
                guard let self, !Task.isCancelled else { return }
                self.fail()
            }
        }
    }
    private func start() {
        guard let player else { return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
            try session.setActive(true)
            ownsAudioSession = true
            guard player.play() else { throw MediaCryptography.Failure.invalidFile }
            state = .playing
        } catch { fail() }
    }
    private func releaseAudio() {
        if ownsAudioSession {
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            ownsAudioSession = false
        }
    }
    private func pause() {
        guard state == .playing else { return }
        player?.pause()
        savedPosition = elapsed
        state = .paused
        releaseAudio()
    }
    private func releaseFile() {
        opening?.cancel()
        opening = nil
        player?.delegate = nil
        player?.stop()
        player = nil
        if let file {
            try? FileManager.default.removeItem(at: file)
            self.file = nil
        }
        releaseAudio()
        VoiceAudioHandoff.release(self)
    }
    func yieldPlayback() {
        if state == .playing { pause() }
        releaseFile()
        if state == .loading { state = .idle }
    }
    func clear() {
        releaseFile()
        savedPosition = 0
        duration = 0
        state = .idle
    }
    private func fail() {
        releaseFile()
        state = .failed
    }
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        guard player === self.player else { return }
        savedPosition = flag ? player.duration : player.currentTime
        releaseFile()
        state = flag ? .finished : .failed
    }
    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        if player === self.player { fail() }
    }
}

struct InlineVoiceNote: View {
    let manifest: AttachmentManifest
    let available: Bool
    let load: @MainActor () async throws -> URL
    @StateObject private var playback = VoiceNotePlayer()
    @Environment(\.scenePhase) private var scenePhase
    private func time(_ seconds: Double) -> String {
        Duration.seconds(Int(max(0, seconds))).formatted(.time(pattern: .minuteSecond))
    }
    private var action: LocalizedStringKey {
        switch playback.state {
        case .failed: "Try again"
        case .playing: "Pause voice message"
        case .loading: "Opening attachment…"
        default: "Play voice message"
        }
    }
    var body: some View {
        let duration = playback.duration > 0 ? playback.duration : Double(manifest.durationMillis ?? 0) / 1000
        VStack(alignment: .leading, spacing: 4) {
            TimelineView(.periodic(from: .now, by: playback.state == .playing ? 0.2 : 3600)) { _ in
                let elapsed = min(max(0, playback.elapsed), duration)
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        playButton
                        VStack(alignment: .leading, spacing: 5) {
                            track(elapsed: elapsed, duration: duration)
                            position(elapsed: elapsed, duration: duration)
                                .fixedSize(horizontal: true, vertical: true)
                        }
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        playButton
                        track(elapsed: elapsed, duration: duration)
                        position(elapsed: elapsed, duration: duration)
                    }
                }
            }
            if playback.state == .failed { Text("Couldn’t play this attachment.").font(.footnote) }
        }
        // Include the inset in the width offered to the bubble. The track
        // and its final cap must stay clear of its curved trailing edge.
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .frame(maxWidth: 225, alignment: .leading)
        .onChange(of: available) { _, allowed in if !allowed { playback.clear() } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { playback.yieldPlayback() } }
        .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { note in
            if note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
                == AVAudioSession.InterruptionType.began.rawValue
            {
                playback.yieldPlayback()
            }
        }
        .onDisappear { playback.clear() }
    }
    private var playButton: some View {
        Button {
            playback.toggle(load: load)
        } label: {
            Group {
                if playback.state == .loading {
                    ProgressView()
                } else {
                    Image(
                        systemName: playback.state == .playing
                            ? "pause.fill" : playback.state == .failed ? "arrow.clockwise" : "play.fill")
                }
            }.frame(width: 44, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityLabel(Text(action))
        .accessibilityIdentifier("voice-note-control-" + manifest.id)
        .disabled(!available || playback.state == .loading)
    }

    private func track(elapsed: Double, duration: Double) -> some View {
        ProgressView(value: duration > 0 ? elapsed / duration : 0)
            .progressViewStyle(.linear)
            .frame(minWidth: 0, maxWidth: .infinity)
            .accessibilityHidden(true)
    }

    private func position(elapsed: Double, duration: Double) -> some View {
        Text(verbatim: time(elapsed) + " / " + time(duration))
            .font(.caption.monospacedDigit())
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("voice-playback-position")
    }

}
