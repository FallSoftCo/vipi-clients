import AVFoundation
import SwiftUI

@MainActor @Observable final class InlineVoiceComposer {
    enum Phase { case idle, starting, holding, locked, saving, preview, sending }
    private(set) var phase = Phase.idle
    private(set) var notice: String?
    private(set) var showHandsFree = false
    private(set) var denied = false
    private(set) var draft: AttachmentManifest?
    private(set) var playing = false
    let recorder = VoiceMessageRecorder()
    private var capture: ChosenMedia?
    private var player: AVAudioPlayer?
    private var playbackURL: URL?
    private var activation: Task<Void, Never>?
    private var playback: Task<Void, Never>?
    private var wantsLock = false
    private var sendWhenReady = false
    private var sending: Task<Void, Never>?
    private weak var chat: ChatSession?
    private var peer: UUID?
    private var onCommitted: (() -> Void)?
    private var foreground = true

    var active: Bool { phase != .idle }
    var reviewing: Bool { phase == .preview || phase == .sending }
    var locked: Bool { phase == .locked || (phase == .starting && wantsLock) }
    var duration: Double { draft?.durationMillis.map { Double($0)/1000 } ?? recorder.currentTime }
    func bind(_ chat: ChatSession, peer: UUID, committed: @escaping () -> Void) {
        self.chat = chat; self.peer = peer; onCommitted = committed; foreground = true
        if !active, let stored = try? chat.voiceDraft(peer: peer) {
            draft = stored
            phase = .preview
        }
    }
    func begin(lock: Bool = false) {
        guard !active, let chat, let peer, chat.canViewPhoto(peer: peer) else { return }
        showHandsFree = false
        wantsLock = lock; sendWhenReady = false; notice = nil; denied = false
        phase = .starting
        activation = Task { @MainActor in
            do {
                if !lock { try await Task.sleep(for: .milliseconds(230)) }
                try Task.checkCancellation()
                guard self.phase == .starting else { return }
                await self.recorder.begin()
                try Task.checkCancellation()
                guard self.phase == .starting else { return }
                switch self.recorder.phase {
                case .recording:
                    VoiceAudioHandoff.claim(self) { [weak self] in self?.interruption() }
                    self.phase = self.wantsLock ? .locked : .holding
                case .permissionReady:
                    self.notice = String(localized: "Microphone ready. Tap or hold to record."); self.phase = .idle
                case .denied:
                    self.denied = true; self.notice = String(localized: "Allow microphone access in Settings to record a voice message."); self.phase = .idle
                default:
                    self.notice = String(localized: "Couldn’t record that message."); self.phase = .idle
                }
            } catch {
                if !Task.isCancelled { self.notice = String(localized: "Attachments aren’t available for this chat right now."); self.phase = .idle }
            }
        }
    }
    func move(dx: CGFloat, dy: CGFloat) {
        guard (phase == .starting || phase == .holding), !wantsLock else { return }
        if dx <= -66, -dx >= -dy { discard() }
        else if dy <= -54 { wantsLock = true; if phase == .holding { phase = .locked } }
    }
    func release(held: TimeInterval) {
        guard !wantsLock else { return }
        switch phase {
        case .starting:
            discard()
            showHandsFree = true
        case .holding:
            if held >= 0.35 && recorder.currentTime >= 0.25 { finish(send: true) }
            else { discard(); showHandsFree = true }
        default: break
        }
    }
    func finish(send: Bool = false) {
        guard phase == .holding || phase == .locked else { return }
        VoiceAudioHandoff.release(self)
        recorder.stop()
        guard let audio = recorder.take() else {
            notice = String(localized: "Couldn’t record that message."); phase = .idle; return
        }
        capture = audio
        seal(send: send)
    }
    func recorderChanged() {
        if recorder.phase == .review && (phase == .holding || phase == .locked) { finish() }
        else if recorder.phase == .failed && (phase == .holding || phase == .locked) {
            VoiceAudioHandoff.release(self)
            phase = .idle; notice = String(localized: "Couldn’t record that message.")
        }
    }
    private func seal(send: Bool) {
        guard let chat, let peer, let account = chat.profile?.id, let audio = capture else { return }
        phase = .saving; sendWhenReady = send
        Task { @MainActor in
            do {
                let repo = try AttachmentRepository(account: account)
                let media = try await repo.prepare(source: audio.url, kind: .voice)
                do {
                    guard chat.profile?.id == account else { throw CancellationError() }
                    try chat.saveVoiceDraft(media, peer: peer)
                } catch { repo.discardPrepared(media); throw error }
                draft = media; capture?.discard(); capture = nil; phase = .preview
                if sendWhenReady && foreground { submit() }
            } catch {
                phase = .preview; sendWhenReady = false
                notice = String(localized: "Couldn’t prepare this attachment. Try again.")
            }
        }
    }
    func submit() {
        guard phase == .preview, let chat, let peer else { return }
        stopPlayback(); notice = nil
        guard let draft else { if capture != nil { seal(send: true) }; return }
        phase = .sending
        sending = Task { @MainActor in
            do {
                try await chat.confirmMediaCapability(peer)
                try Task.checkCancellation()
                guard foreground, phase == .sending else { throw CancellationError() }
                try chat.sendVoiceDraft(draft, peer: peer)
                self.draft = nil; phase = .idle; wantsLock = false; sendWhenReady = false
                onCommitted?()
            } catch {
                guard !Task.isCancelled else { return }
                phase = .preview; sendWhenReady = false
                notice = String(localized: "Couldn’t send. Your recording is saved here.")
            }
        }
    }
    func discard() {
        guard phase != .saving, phase != .sending else { return }
        activation?.cancel(); activation = nil
        stopPlayback(); recorder.cancel()
        if let draft, let chat, let peer {
            do { try chat.discardVoiceDraft(draft, peer: peer) }
            catch { notice = ChatSession.explanation(error); return }
        }
        capture?.discard(); capture = nil; draft = nil; phase = .idle; wantsLock = false; showHandsFree = false
        sendWhenReady = false; notice = nil; denied = false
    }
    func interruption(leaving: Bool = false) {
        if leaving { foreground = false; onCommitted = nil }
        sendWhenReady = false; stopPlayback()
        if phase == .holding || phase == .locked { finish() }
        else if phase == .starting { discard() }
        else if phase == .sending { sending?.cancel(); sending = nil; phase = .preview }
    }
    func togglePlayback() {
        if playing || playback != nil { stopPlayback(); return }
        guard phase == .preview, let chat, let peer else { return }
        VoiceAudioHandoff.claim(self) { [weak self] in self?.stopPlayback() }
        playback = Task { @MainActor in
            do {
                let url: URL
                if let capture { url = capture.url }
                else if let draft {
                    url = try await chat.openMedia(draft, peer: peer); playbackURL = url
                } else { return }
                try Task.checkCancellation()
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
                let audio = try AVAudioPlayer(contentsOf: url)
                player = audio
                try session.setActive(true)
                guard audio.play() else { throw MediaCryptography.Failure.invalidFile }
                playing = true
                while audio.isPlaying { try await Task.sleep(for: .milliseconds(120)) }
                stopPlayback()
            } catch {
                if !Task.isCancelled { stopPlayback(); notice = String(localized: "Couldn’t play this attachment.") }
            }
        }
    }
    private func stopPlayback() {
        VoiceAudioHandoff.release(self)
        playback?.cancel(); playback = nil
        if player != nil {
            player?.stop(); player = nil
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
        playing = false
        if let playbackURL { try? FileManager.default.removeItem(at: playbackURL); self.playbackURL = nil }
    }
}

/// Tracks the original finger in window coordinates while the editor is
/// replaced by recording controls. VoiceOver and Switch Control use activation.
private struct MicTouchSurface: UIViewRepresentable {
    var enabled: Bool
    var label: String
    var hint: String
    var began: () -> Void
    var moved: (CGFloat, CGFloat) -> Void
    var ended: (TimeInterval) -> Void
    var cancelled: () -> Void
    var activated: () -> Void
    func makeUIView(context: Context) -> Surface { Surface() }
    func updateUIView(_ view: Surface, context: Context) {
        view.owner = self; view.isUserInteractionEnabled = enabled
        view.isAccessibilityElement = true; view.accessibilityTraits = enabled ? .button : [.button,.notEnabled]
        view.accessibilityLabel = label; view.accessibilityHint = hint; view.accessibilityIdentifier = "voice-composer-action"
    }
    final class Surface: UIView {
        var owner: MicTouchSurface?
        private var origin: CGPoint?
        private var time: TimeInterval = 0
        override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
            guard let touch = touches.first, origin == nil else { return }
            origin = touch.location(in: window); time = touch.timestamp; owner?.began()
        }
        override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
            guard let touch = touches.first, let origin else { return }
            let p = touch.location(in: window); owner?.moved(p.x-origin.x, p.y-origin.y)
        }
        override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
            guard let touch = touches.first, origin != nil else { return }
            origin = nil; owner?.ended(max(0,touch.timestamp-time))
        }
        override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
            origin = nil; owner?.cancelled()
        }
        override func accessibilityActivate() -> Bool { guard owner?.enabled == true else { return false }; owner?.activated(); return true }
    }
}
struct InlineMicButton: View {
    let voice: InlineVoiceComposer
    let enabled: Bool
    let prepare: () -> Void
    @Environment(\.layoutDirection) private var direction
    @State private var press: Action?
    enum Action { case record, stop, send }
    private var action: Action { voice.reviewing ? .send : voice.locked ? .stop : .record }
    private var label: String {
        switch action {
        case .record: String(localized: "Record voice message")
        case .stop: String(localized: "Stop recording")
        case .send: String(localized: "Send voice message")
        }
    }
    var body: some View {
        ZStack {
            Image(systemName: action == .send ? "arrow.up" : action == .stop ? "stop.fill" : "mic.fill")
                .font(.body.weight(.semibold)).accessibilityHidden(true)
            MicTouchSurface(enabled: enabled && voice.phase != .sending && voice.phase != .saving, label: label,
                hint: action == .record ? String(localized: "Hold to record. Release to send.") : "",
                began: {
                    press = action
                    if action == .record && !voice.active { prepare(); voice.begin() }
                }, moved: { dx,dy in if press == .record { voice.move(dx: direction == .rightToLeft ? -dx : dx, dy: dy) } },
                ended: { held in
                    switch press {
                    case .record: voice.release(held: held)
                    case .stop: voice.finish()
                    case .send: voice.submit()
                    case nil: break
                    }
                    press = nil
                }, cancelled: { press = nil; voice.interruption() }, activated: {
                    switch action {
                    case .record: prepare(); voice.begin(lock: true)
                    case .stop: voice.finish()
                    case .send: voice.submit()
                    }
                })
        }
        .foregroundStyle(VipiDesign.onHighlight)
        .frame(width: 46, height: 46)
        .background(VipiDesign.highlight, in: Circle())
    }
}
struct InlineVoiceStatus: View {
    let voice: InlineVoiceComposer
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var elapsed: some View {
        TimelineView(.periodic(from: .now, by: 0.16)) { _ in
            let time = voice.reviewing ? voice.duration : voice.recorder.currentTime
            HStack(spacing: 8) {
                if !voice.reviewing, !reduceMotion {
                    let level = voice.recorder.level
                    HStack(spacing: 2) {
                        ForEach(0..<6) { n in
                            Capsule().fill(Double(n)/6 < level ? VipiDesign.highlight : VipiDesign.outline)
                                .frame(width: 3, height: CGFloat(5+n*2))
                        }
                    }.accessibilityHidden(true)
                }
                Text(Duration.seconds(time).formatted(.time(pattern:.minuteSecond)))
                    .font(.subheadline.monospacedDigit()).accessibilityLabel("Recording duration")
                    .accessibilityValue(Duration.seconds(time).formatted()).accessibilityIdentifier("voice-recording-elapsed")
            }
        }
    }
    var body: some View {
        HStack(spacing: 8) {
            if voice.locked || voice.reviewing {
                Button(role:.destructive) { voice.discard() } label: { Image(systemName:"trash").frame(minWidth:44,minHeight:44) }
                    .accessibilityLabel("Discard recording").accessibilityIdentifier("voice-discard")
                    .disabled(voice.phase == .sending)
            }
            if voice.reviewing {
                Button { voice.togglePlayback() } label: {
                    Image(systemName: voice.playing ? "pause.fill":"play.fill").frame(minWidth:44,minHeight:44)
                }.accessibilityLabel(voice.playing ? "Pause voice message":"Play voice message").accessibilityIdentifier("voice-draft-play")
            }
            if voice.phase == .starting || voice.phase == .saving || voice.phase == .sending { ProgressView().controlSize(.small) }
            else { elapsed }
            if voice.phase == .holding {
                ViewThatFits(in: .horizontal) {
                    Label("Slide to cancel", systemImage:"arrow.backward").font(.caption)
                    Image(systemName:"arrow.backward")
                }.foregroundStyle(VipiDesign.secondary)
                HStack(spacing: 2) {
                    Image(systemName: "arrow.up")
                    Image(systemName: "lock")
                }.font(.caption).foregroundStyle(VipiDesign.secondary).accessibilityLabel("Slide up to lock")
            }
        }.buttonStyle(.plain).frame(maxWidth: .infinity,alignment:.leading)
    }
}
