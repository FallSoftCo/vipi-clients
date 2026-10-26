import SwiftUI
import VipiCore

enum ReadingMode: String, CaseIterable, Identifiable {
    case immersed = "Immersed", original = "Original", translation = "Translation"
    var id: String { rawValue }
}

struct ImmersionBubble: View {
    let result: ImmersionResult
    var outgoing = false
    var mode: ReadingMode = .immersed
    var speech: SpeechPlayback?
    var sourceLanguage = "en"
    var targetLanguage = "es"
    var messageID = "onboarding-example"
    var interactionPaused = false
    var fullReading: String? = nil
    var targetDwell: Duration = .milliseconds(4500)
    var meaningDwell: Duration = .seconds(3)
    var embedded = false
    var onModeChange: ((ReadingMode) -> Void)? = nil
    var metadata: AnyView? = nil
    var onVoiceHelp: (() -> Void)? = nil
    var originalMessage: String? = nil
    var inputLanguage: String? = nil
    var onInputLanguage: ((String?) -> Void)? = nil
    @State private var originalPhase = false
    @State private var overrides: [Int: Bool] = [:]
    @State private var paused = false
    @State private var script = false
    @State private var selecting = false
    @State private var choosingPace = false
    @State private var visible = false
    @State private var revision = 0
    @AppStorage("readingPace") private var pace = "balanced"
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver

    private var revealed: Set<Int> { Set(result.spans.filter { overrides[$0.id] ?? originalPhase }.map(\.id)) }
    private var active: Bool { speech?.activeMessage == messageID }
    private var eligible: Bool { visible && scenePhase == .active && !paused && !selecting && !choosingPace && !interactionPaused && speech?.activeMessage == nil && !voiceOver && mode == .immersed && !result.spans.isEmpty }
    private var clockKey: String { "\(eligible)-\(revision)-\(pace)" }
    private func reveal(_ id: Int) {
        speech?.stop(); overrides[id] = !(overrides[id] ?? originalPhase); revision += 1
        #if DEBUG
        VoiceOverQualification.record("manual_word", enabled: voiceOver, original: originalPhase)
        #endif
    }
    private func listen() {
        let spans: [(text: String, language: String)]
        switch mode {
        case .original: spans = [(result.original, sourceLanguage)]
        case .translation: spans = [(result.translation, targetLanguage)]
        case .immersed: spans = result.speech(source: sourceLanguage, target: targetLanguage, revealed: revealed).map { ($0.text, $0.language) }
        }
        speech?.toggle(message: messageID, spans: spans)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if mode == .immersed {
                StableImmersionText(result: result, revealed: revealed, script: script, onWord: reveal,
                    onSelection: { selecting = $0 })
            } else {
                Text(mode == .original ? result.original : (script ? result.translation : (fullReading ?? result.translation))).font(.body).lineSpacing(5)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: 0) {
                if embedded { metadata; Spacer(minLength: 8) }
                if !embedded && mode == .immersed && !result.spans.isEmpty && !voiceOver {
                    Button { paused.toggle(); revision += 1 } label: {
                        Image(systemName: paused ? "play" : "pause").font(.footnote).frame(width: 44, height: 44)
                    }.accessibilityLabel(paused ? "Resume word switching" : "Pause word switching")
                        .accessibilityIdentifier("immersionPause")
                }
                if !result.spans.isEmpty || fullReading != nil || onModeChange != nil {
                    Menu {
                        if embedded {
                            if let speech {
                                Button(active ? "Stop listening" : (speech.state == .preparing ? "Preparing voices…" : speech.state == .unavailable ? "Set up voices" : "Listen"), systemImage: active ? "stop.fill" : "speaker.wave.2") {
                                    if speech.state == .unavailable { onVoiceHelp?() } else { listen() }
                                }.disabled(speech.state == .preparing || (speech.state == .unavailable && onVoiceHelp == nil))
                            }
                            if mode == .immersed && !result.spans.isEmpty && !voiceOver {
                                Button(paused ? "Resume word switching" : "Pause word switching", systemImage: paused ? "play" : "pause") { paused.toggle(); revision += 1 }
                            }
                        }
                        if mode == .immersed && !result.spans.isEmpty && !voiceOver {
                            Button("Switching pace") { choosingPace = true }
                        }
                        if let onModeChange {
                            ForEach(ReadingMode.allCases) { value in
                                let label = !embedded || value == .immersed ? value.rawValue
                                    : VipiLanguage.named(value == .original ? sourceLanguage : targetLanguage).name
                                Button(label, systemImage: mode == value ? "checkmark" : "text.bubble") { onModeChange(value) }
                            }
                        }
                        if (mode == .translation && fullReading != nil) || (mode == .immersed && result.spans.contains(where: { $0.romanization != nil })) {
                            Button(script ? "Show transliteration" : "Show original script") { script.toggle(); revision += 1 }
                        }
                        if mode == .immersed && !result.spans.isEmpty { Button("Show meanings now") { speech?.stop(); originalPhase = true; overrides = [:]; revision += 1 } }
                        if let onInputLanguage {
                            MessageLanguageMenu(source: sourceLanguage, target: targetLanguage, selected: inputLanguage, select: onInputLanguage)
                        }
                        Button("Copy original message") { UIPasteboard.general.string = originalMessage ?? result.original }
                    } label: { Image(systemName: "ellipsis").font(.footnote).frame(width: 44, height: 44) }
                        .accessibilityLabel("Reading options")
                }
                if !embedded { Spacer() }
                if !embedded, let speech {
                    Button {
                        listen()
                    } label: {
                        HStack(spacing: 7) {
                            if speech.state == .preparing || (active && speech.state == .rendering) { ProgressView().controlSize(.small) }
                            else { Image(systemName: active ? "stop.fill" : "speaker.wave.2") }
                            Text(active ? "Stop" : speech.state == .preparing ? "Preparing voices" : "Listen")
                        }.font(.footnote.weight(.medium)).frame(minWidth: 44, minHeight: 44)
                    }.disabled(speech.state == .preparing || speech.state == .unavailable)
                        .accessibilityIdentifier("messageListen")
                }
            }
        }.padding(.horizontal, embedded ? 0 : 20).padding(.top, embedded ? 0 : 20).padding(.bottom, embedded ? 0 : 6)
            .background(embedded ? Color.clear : (outgoing ? VipiDesign.outgoing : VipiDesign.surface), in: RoundedRectangle(cornerRadius: 23))
            .confirmationDialog("Switching pace", isPresented: $choosingPace, titleVisibility: .visible) {
                Button("Relaxed") { pace = "relaxed" }
                Button("Balanced") { pace = "balanced" }
                Button("Brisk") { pace = "brisk" }
                Button("Cancel", role: .cancel) { }
            } message: { Text("Currently \(pace.capitalized)") }
            .onAppear { visible = true }
            #if DEBUG
            .onAppear { VoiceOverQualification.record("appeared", enabled: voiceOver, original: originalPhase) }
            .onChange(of: voiceOver) { VoiceOverQualification.record("voiceover_changed", enabled: voiceOver, original: originalPhase) }
            .onChange(of: originalPhase) { VoiceOverQualification.record("phase_changed", enabled: voiceOver, original: originalPhase) }
            #endif
            .onDisappear { visible = false; if active { speech?.stop() } }
            .onScrollVisibilityChange(threshold: 0.1) { visible = $0 }
            .task(id: clockKey) {
                guard eligible else { return }
                do {
                    if embedded {
                        let offset = messageID.utf8.reduce(UInt64(0)) { ($0 &* 31) &+ UInt64($1) } % 1200
                        try await Task.sleep(for: .milliseconds(Int(offset)))
                    }
                    while !Task.isCancelled {
                        let dwell = originalPhase ? meaningDwell : targetDwell
                        try await Task.sleep(for: pace == "relaxed" ? dwell * 2 : (pace == "brisk" ? dwell / 2 : dwell))
                        try Task.checkCancellation()
                        originalPhase.toggle(); overrides = [:]
                    }
                } catch { /* Lifecycle changes cancel rather than catch up. */ }
            }
            .onChange(of: result) { overrides = [:]; originalPhase = false; revision += 1; if active { speech?.stop() } }
            .onChange(of: mode) { if active { speech?.stop() }; overrides = [:]; selecting = false; choosingPace = false; revision += 1 }
    }
}

struct MessageLanguageMenu: View {
    let source: String
    let target: String
    let selected: String?
    let select: (String?) -> Void
    var body: some View {
        Menu("Message language") {
            Button("Detect automatically", systemImage: selected == nil ? "checkmark" : "text.bubble") { select(nil) }
            ForEach([source, target], id: \.self) { language in
                Button(VipiLanguage.named(language).name, systemImage: selected == language ? "checkmark" : "text.bubble") { select(language) }
            }
        }
    }
}

enum ImmersionPreview {
    // An original authored onboarding example. Not a downloaded production pack.
    static let result = ImmersionEngine().align(
        original: "Coffee tomorrow? I know a little place by the river.",
        translation: "¿Café mañana? Conozco un pequeño lugar junto al río.",
        entries: [.init(source: "Coffee", targets: ["Café"]), .init(source: "tomorrow", targets: ["mañana"]), .init(source: "river", targets: ["río"])],
        density: 0.3)
}
