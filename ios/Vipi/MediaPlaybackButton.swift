import SwiftUI
import AVKit

struct LocalMediaPlayer: View {
    let url: URL
    let video: Bool
    @State private var player: AVPlayer?
    @State private var playing = false
    @State private var ownsSession = false
    @State private var failed = false
    @State private var duration = 0.0
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        VStack(spacing: 14) {
            if let player {
                if video {
                    VideoPlayer(player: player).aspectRatio(16 / 9, contentMode: .fit)
                } else {
                    Button {
                        if playing {
                            pause()
                        } else {
                            do {
                                try activate()
                                if duration > 0, player.currentTime().seconds >= duration - 0.02 {
                                    player.seek(to: .zero)
                                }
                                player.play()
                                playing = true
                            } catch {
                                failed = true
                                pause()
                            }
                        }
                    } label: {
                        Label(
                            playing ? "Pause voice message" : "Play voice message",
                            systemImage: playing ? "pause.circle.fill" : "play.circle.fill")
                    }
                    if duration > 0 {
                        TimelineView(.animation(minimumInterval: 0.25, paused: !playing)) { _ in
                            let elapsed = player.currentTime().seconds
                            let position = elapsed.isFinite ? min(max(0, elapsed), duration) : 0
                            Text(
                                verbatim:
                                    "\(Duration.seconds(position).formatted(.time(pattern: .minuteSecond))) / \(Duration.seconds(duration).formatted(.time(pattern: .minuteSecond)))"
                            )
                            .monospacedDigit().accessibilityIdentifier("voice-playback-position")
                        }
                    }
                }
            } else if !failed {
                ProgressView()
            }
            if failed { Text("Couldn’t play this attachment.") }
        }
        .task(id: url) {
            do {
                let asset = AVURLAsset(url: url)
                guard try await asset.load(.isPlayable) else { throw MediaCryptography.Failure.invalidFile }
                duration = try await asset.load(.duration).seconds
                try Task.checkCancellation()
                if video { try activate() }
                player = AVPlayer(playerItem: AVPlayerItem(asset: asset))
            } catch { if !Task.isCancelled { failed = true } }
        }
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime)) { note in
            guard let player, let item = note.object as? AVPlayerItem, item === player.currentItem else { return }
            pause()
        }
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemFailedToPlayToEndTime)) { note in
            if let item = note.object as? AVPlayerItem, item === player?.currentItem {
                pause()
                failed = true
            }
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { pause() } }
        .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { note in
            if (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt)
                == AVAudioSession.InterruptionType.began.rawValue
            {
                pause()
            }
        }
        .onDisappear {
            pause()
            player = nil
        }
    }
    private func activate() throws {
        guard !ownsSession else { return }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .default, options: .mixWithOthers)
        try session.setActive(true)
        ownsSession = true
    }
    private func pause() {
        player?.pause()
        playing = false
        if ownsSession {
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            ownsSession = false
        }
    }
}
struct MediaPlaybackButton: View {
    let manifest: AttachmentManifest
    let available: Bool
    let load: () async throws -> URL
    @State private var showing = false
    @State private var file: URL?
    @State private var failed = false
    @State private var attempt = 0
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        if manifest.kind == .voice {
            InlineVoiceNote(manifest: manifest, available: available, load: load)
        } else {
            videoButton
        }
    }
    private var videoButton: some View {
        Button {
            showing = true
        } label: {
            Label {
                if let ms = manifest.durationMillis {
                    Text(
                        "\(manifest.kind == .voice ? String(localized: "Voice message") : String(localized: "Video")) · \(Duration.milliseconds(ms).formatted(.time(pattern: .minuteSecond)))"
                    )
                } else {
                    Text(manifest.kind == .voice ? "Voice message" : "Video")
                }
            } icon: {
                Image(systemName: "play.circle")
            }
        }
        .disabled(!available)
        .sheet(isPresented: $showing, onDismiss: clear) {
            NavigationStack {
                Group {
                    if let file {
                        LocalMediaPlayer(url: file, video: true)
                    } else if failed {
                        VStack {
                            Text("Couldn’t open this attachment.")
                            Button("Try again") { attempt += 1 }
                        }
                    } else {
                        ProgressView("Opening attachment…")
                    }
                }.padding().navigationTitle("Video")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Close") { showing = false } } }
                    .task(id: attempt) {
                        failed = false
                        do {
                            let opened = try await load()
                            guard !Task.isCancelled, showing else {
                                try? FileManager.default.removeItem(at: opened)
                                return
                            }
                            file = opened
                        } catch { if !Task.isCancelled { failed = true } }
                    }
            }
        }
        .onChange(of: available) { _, value in if !value { showing = false } }
        .onChange(of: scenePhase) { _, value in if value != .active { showing = false } }
    }
    private func clear() {
        if let file { try? FileManager.default.removeItem(at: file) }
        file = nil
        failed = false
    }
}
