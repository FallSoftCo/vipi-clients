import SwiftUI
import VipiCore

enum ReadingMode: String, CaseIterable, Identifiable {
    case immersed = "Immersed", original = "Original", translation = "Translation"
    var id: String { rawValue }
    var label: String { switch self { case .immersed: String(localized: "Word switching"); case .original: String(localized: "Original message"); case .translation: String(localized: "Full translation") } }
}

struct ImmersionBubble: View {
    let result: ImmersionPresentation
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
    var requestingTranslation = false
    var onRequestTranslation: (() -> Void)? = nil
    var onExposure: (([ImmersionSpan]) -> Void)? = nil
    var manual: ManualLookupInteraction? = nil
    var onReport: (() -> Void)? = nil
    var rawSourceLanguage: String? = nil
    var onLanguageHelp: (() -> Void)? = nil
    @State private var nativeAnchor = WeakImmersionAnchor()
    @State private var wordAudio: Task<Void, Never>?
    @State private var originalPhase = false
    @State private var overrides: [Int: Bool] = [:]
    @State private var paused = false
    @State private var script = false
    @State private var selecting = false
    @State private var choosingPace = false
    @State private var visible = false
    @State private var exposureVisible = false
    @State private var revision = 0
    @AppStorage("readingPace") private var pace = "balanced"
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var stackedControls: Bool { dynamicTypeSize.isAccessibilitySize && !embedded }
    private var controlLayout: AnyLayout {
        stackedControls ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout(spacing: 0))
    }

    private var effectiveMode: ReadingMode { mode == .translation && result.translation == nil ? .immersed : mode }
    private var speechMode: ImmersionSpeechMode {
        switch effectiveMode { case .original: .original; case .immersed: .immersed; case .translation: .fullTarget }
    }
    private var speechSpans: [SpeechSpan]? {
        let raw = originalMessage ?? result.original
        let actual = originalMessage == nil ? sourceLanguage : rawSourceLanguage
        if effectiveMode == .original { return actual.map { [SpeechSpan(text: raw, language: $0)] } }
        let sourceIsRaw = raw.utf8.elementsEqual(result.original.utf8)
        guard !sourceIsRaw || actual != nil else { return nil }
        return result.speech(mode: speechMode, source: sourceIsRaw ? (actual ?? sourceLanguage) : sourceLanguage, target: targetLanguage, revealed: revealed)
    }
    private var canListen: Bool { speechSpans != nil }
    private var revealed: Set<Int> { Set(result.spans.filter { overrides[$0.id] ?? originalPhase }.map(\.id)) }
    private var active: Bool { speech?.activeMessage == messageID }
    private var manualActive: Bool { manual?.loading == true || manual?.speaking == true || manual?.preparingAudio == true }
    private var eligible: Bool { visible && scenePhase == .active && !paused && !selecting && !choosingPace && !interactionPaused && speech?.activeMessage == nil && !voiceOver && effectiveMode == .immersed && !result.spans.isEmpty }
    private var clockKey: String { "\(eligible)-\(exposureVisible)-\(revision)-\(pace)" }
    #if DEBUG
    private var qualificationKey: String { "\(visible)|\(scenePhase)|\(paused)|\(selecting)|\(choosingPace)|\(interactionPaused)|\(speech?.activeMessage ?? "")|\(String(describing: speech?.state))|\(voiceOver)|\(effectiveMode)|\(result.spans.count)|\(originalPhase)|\(revision)" }
    private func recordLiveState() {
        LiveImmersionQualification.record(["message_id": messageID, "visible": visible, "scene_active": scenePhase == .active,
            "explicit_pause": paused, "selecting": selecting, "choosing_pace": choosingPace,
            "interaction_paused": interactionPaused, "speech_active": speech?.activeMessage != nil,
            "speech_state": String(describing: speech?.state), "speech_underruns": speech?.outputUnderruns ?? 0,
            "voiceover": voiceOver, "mode": effectiveMode.rawValue, "spans": result.spans.count,
            "original_phase": originalPhase, "eligible": eligible, "pace": pace])
    }
    #endif
    private func reveal(_ id: Int) {
        speech?.stop(); overrides[id] = !(overrides[id] ?? originalPhase); revision += 1
        if let word = result.spans.first(where: { $0.id == id }) {
            if let manual { manual.coveredWord(word, language: targetLanguage, from: nativeAnchor.value) }
            else if let speech {
                wordAudio?.cancel(); let produced = revision
                wordAudio = Task { @MainActor in
                    for _ in 0..<160 {
                        guard !Task.isCancelled, produced == revision, scenePhase == .active, !interactionPaused else { return }
                        if speech.state != .preparing { break }
                        try? await Task.sleep(for: .milliseconds(50))
                    }
                    guard !Task.isCancelled, produced == revision, scenePhase == .active, !interactionPaused, speech.state != .unavailable, speech.state != .preparing else { return }
                    speech.toggle(message: "word-\(messageID)-\(id)", spans: [(word.translated, targetLanguage)])
                }
            }
        }
        #if DEBUG
        VoiceOverQualification.record("manual_word", enabled: voiceOver, original: originalPhase)
        #endif
    }
    private func listen() {
        ManualLookupInteraction.cancelActive()
        guard let spans = speechSpans else { return }
        speech?.toggle(message: messageID, spans: spans.map { ($0.text, $0.language) })
    }

    private func playVisibleMessage() {
        if manualActive { manual?.cancel() }
        else if !canListen { onLanguageHelp?() }
        else if speech?.state == .unavailable { onVoiceHelp?() }
        else { listen() }
    }
    private func translateWhole() {
        if let manual { manual.beginWhole() }
        else if let speech, let target = result.translation {
            speech.toggle(message: "translation-" + messageID, spans: [(target, targetLanguage)])
        }
    }
    @ViewBuilder private var messageActions: some View {
                        Button("Copy original message") { ManualLookupInteraction.cancelActive(); if active { speech?.stop() }; UIPasteboard.general.string = originalMessage ?? result.original }
                        Button("Select text") { nativeAnchor.value?.selectTextFromMenu() }
                        Menu("Reading options") {
                            if effectiveMode == .immersed && !result.spans.isEmpty && !voiceOver {
                                Button(paused ? "Resume word switching" : "Pause word switching", systemImage: paused ? "play" : "pause") { paused.toggle(); revision += 1 }
                                Button("Word switching speed") { choosingPace = true }
                            }
                            if let onModeChange {
                                ForEach(ReadingMode.allCases.filter { $0 != .translation }) { value in
                                    Button(value.label, systemImage: effectiveMode == value ? "checkmark" : "text.bubble") { onModeChange(value) }
                                }
                            }
                            if (effectiveMode == .translation && fullReading != nil) || (effectiveMode == .immersed && result.spans.contains(where: { $0.romanization != nil })) {
                                Button(script ? "Show Latin letters" : "Show original script") { script.toggle(); revision += 1 }
                            }
                            if onModeChange == nil && effectiveMode == .immersed && !result.spans.isEmpty {
                                Button("Show original words now") { speech?.stop(); originalPhase = true; overrides = [:]; revision += 1 }
                            }
                            if let onInputLanguage {
                                MessageLanguageMenu(source: sourceLanguage, target: targetLanguage, selected: inputLanguage, select: onInputLanguage)
                            }
                        }
    }

    private var nativeMessage: StableImmersionText {
        let displayed: ImmersionPresentation = effectiveMode == .original ? .sourceOnly(original: originalMessage ?? result.original, target: targetLanguage) : result
        var view = StableImmersionText(result: displayed, revealed: revealed, script: script, onWord: reveal, onSelection: { selecting = $0 })
        if let manual {
            let lookup: (NSRange, ImmersionNativeTextView) -> Void = { range, native in
                guard let source = ManualSourceCoordinates.resolve(rawOriginal: originalMessage ?? result.original,
                    displayedSource: native.originalMessage, startUTF16: range.location, endUTF16: NSMaxRange(range)) else { return }
                #if DEBUG
                LiveImmersionQualification.recordSelection(raw: originalMessage ?? result.original, displayed: native.originalMessage, selected: range, mapped: source)
                #endif
                manual.begin(NSRange(location: source.startUTF16, length: source.endUTF16 - source.startUTF16), from: native)
            }
            view.onPlainWord = lookup
            view.onReleasedSelection = lookup
            view.onWhitespace = { native in manual.begin(NSRange(location: 0, length: (originalMessage ?? result.original).utf16.count), from: native) }
        }
        view.onSelectionGestureBegan = { ManualLookupInteraction.textGestureBegan(); if active { speech?.stop() } }
        view.onCopyRequested = { ManualLookupInteraction.cancelActive(); if active { speech?.stop() } }
        if embedded { view.onPlayMessage = { playVisibleMessage() } }
        view.onNativeView = { nativeAnchor.value = $0; $0.playbackControlRectInWindow = nativeAnchor.controlRect; manual?.bind($0) }
        return view
    }
    private var messageContent: some View {
        VStack(alignment: .leading, spacing: 4) {
            if effectiveMode != .translation {
                nativeMessage
            } else {
                Text(effectiveMode == .original ? result.original : (script ? (result.translation ?? result.original) : (fullReading ?? result.translation ?? result.original))).font(.body).lineSpacing(5)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }
            messageControls
        }
    }
    private var messageControls: some View {
            controlLayout {
                if embedded { metadata; Spacer(minLength: 8) }
                HStack(spacing: stackedControls ? 12 : 0) {
                if embedded, let speech, canListen || onLanguageHelp != nil {
                    Button(action: playVisibleMessage) {
                        if speech.state == .preparing && !manualActive { ProgressView().frame(width: 44, height: 44) }
                        else { Image(systemName: active || manualActive ? "stop.fill" : "speaker.wave.2").font(.body).frame(width: 44, height: 44) }
                    }.disabled(!manualActive && canListen && (speech.state == .preparing || (speech.state == .unavailable && onVoiceHelp == nil)))
                        .accessibilityLabel(LocalizedStringKey(active || manualActive ? "Stop listening" : !canListen ? "Message language" : speech.state == .unavailable ? "Set up voices" : "Play message"))
                        .accessibilityIdentifier("messageListen")
                        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { frame in
                            nativeAnchor.controlRect = frame; nativeAnchor.value?.playbackControlRectInWindow = frame
                        }
                }
                if !embedded && effectiveMode == .immersed && !result.spans.isEmpty && !voiceOver {
                    Button { paused.toggle(); revision += 1 } label: {
                        Image(systemName: paused ? "play" : "pause").font(.footnote).frame(width: 44, height: 44)
                    }.accessibilityLabel(paused ? "Resume word switching" : "Pause word switching")
                        .accessibilityIdentifier("immersionPause")
                }
                if !embedded && (!result.spans.isEmpty || fullReading != nil || onModeChange != nil) {
                    Menu { messageActions } label: { Image(systemName: "ellipsis").font(.footnote).frame(width: 44, height: 44) }
                        .accessibilityLabel("Reading options")
                }
                }
                if !embedded && !stackedControls { Spacer() }
                if !embedded, let speech, canListen {
                    Button {
                        listen()
                    } label: {
                        HStack(spacing: 7) {
                            if speech.state == .preparing || (active && speech.state == .rendering) { ProgressView().controlSize(.small) }
                            else { Image(systemName: active ? "stop.fill" : "speaker.wave.2") }
                            Text(LocalizedStringKey(active ? "Stop" : speech.state == .preparing ? "Preparing voices" : "Listen"))
                        }.font(.subheadline.weight(.medium)).frame(minWidth: 44, minHeight: 44)
                            .frame(maxWidth: stackedControls ? .infinity : nil, alignment: .leading)
                    }.disabled(speech.state == .preparing || speech.state == .unavailable)
                        .accessibilityIdentifier("messageListen")
                }
            }
    }
    var body: some View {
        messageContent.padding(.horizontal, embedded ? 15 : 20).padding(.top, embedded ? 12 : 20).padding(.bottom, embedded ? 12 : 6)
            .background {
                if selecting { Color.clear }
                else {
                    Color.clear.contentShape(Rectangle()).onTapGesture { translateWhole() }
                        .contextMenu { if embedded { messageActions; if let onReport { Button("Report message", systemImage: "flag", action: onReport) } } }
                }
            }
            .background(embedded ? Color.clear : (outgoing ? VipiDesign.outgoing : VipiDesign.surface), in: RoundedRectangle(cornerRadius: 23))
            .confirmationDialog("Word switching speed", isPresented: $choosingPace, titleVisibility: .visible) {
                Button("Slower") { pace = "relaxed" }
                Button("Standard") { pace = "balanced" }
                Button("Faster") { pace = "brisk" }
                Button("Cancel", role: .cancel) { }
            } message: { Text("Current speed: \(pace == "relaxed" ? "Slower" : pace == "brisk" ? "Faster" : "Standard")") }
            .onAppear { visible = true }
            #if DEBUG
            .onChange(of: qualificationKey, initial: true) { recordLiveState() }
            .onAppear { VoiceOverQualification.record("appeared", enabled: voiceOver, original: originalPhase) }
            .onChange(of: voiceOver) { VoiceOverQualification.record("voiceover_changed", enabled: voiceOver, original: originalPhase) }
            .onChange(of: originalPhase) { VoiceOverQualification.record("phase_changed", enabled: voiceOver, original: originalPhase) }
            #endif
            .onDisappear { visible = false; wordAudio?.cancel(); if active || speech?.activeMessage?.hasPrefix("word-" + messageID) == true { speech?.stop() } }
            .onScrollVisibilityChange(threshold: 0.1) { visible = $0 }
            .onScrollVisibilityChange(threshold: 0.95) { exposureVisible = $0 }
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
                        if !originalPhase && exposureVisible { onExposure?(result.spans.filter { !revealed.contains($0.id) }) }
                        originalPhase.toggle(); overrides = [:]
                    }
                } catch { /* Lifecycle changes cancel rather than catch up. */ }
            }
            // A separately arriving real full target must not erase the
            // already visible source-known faces or the user's reveal state.
            .onChange(of: result.spans) { overrides = [:]; originalPhase = false; revision += 1; if active { speech?.stop() } }
            .onChange(of: result.original) { overrides = [:]; originalPhase = false; revision += 1; if active { speech?.stop() } }
            .onChange(of: result.translation) { if active { speech?.stop() } }
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
                Button(VipiLanguage.named(language).localizedName, systemImage: selected == language ? "checkmark" : "text.bubble") { select(language) }
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

@MainActor private final class WeakImmersionAnchor { weak var value: ImmersionNativeTextView?; var controlRect = CGRect.null }
