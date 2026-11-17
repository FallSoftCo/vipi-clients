import SwiftUI
import UIKit
import Observation
import VipiCore

/// One transient lookup per app, owned by a visible conversation row. The view
/// is nonmodal so UIKit's selection handles and Copy menu keep working.
@MainActor @Observable final class ManualLookupInteraction {
    private static weak var active: ManualLookupInteraction?
    private let immersion: ConversationImmersion
    let speech: SpeechPlayback
    let messageID: String
    private var original: String
    private var generation: UInt64 = 0
    private var task: Task<Void, Never>?
    private weak var anchor: ImmersionNativeTextView?
    private var sourceRange = NSRange(location: 0, length: 0)
    private var host: UIHostingController<ManualLookupPanel>?
    private(set) var request: ManualTranslationRequest?
    private(set) var outcome: ManualTranslationOutcome?
    private(set) var audioID: String?
    private(set) var audioError: String?
    private(set) var preparingAudio = false
    var foreground = true
    var interactionPaused = false
    private var coveredSource: String?
    private var coveredTarget: String?
    private var coveredReading: String?
    private var coveredLanguage: String?
    private var stoppedRange: NSRange?
    private var stoppedAt = Date.distantPast
    var onDownload: (() -> Void)?
    var onChooseLanguage: (() -> Void)?
    var onVoiceHelp: (() -> Void)?

    init(immersion: ConversationImmersion, speech: SpeechPlayback, messageID: String, original: String) {
        self.immersion = immersion; self.speech = speech; self.messageID = messageID; self.original = original
    }
    static func cancelActive() { active?.cancel() }
    static func coversActivePanel(_ touch: UITouch) -> Bool {
        guard let panel = active?.host?.view, panel.window != nil else { return false }
        return panel.bounds.contains(touch.location(in: panel))
    }
    static func textGestureBegan() { active?.haltForTouch() }
    private func haltForTouch() {
        let interrupted = loading || speaking || preparingAudio
        let previous = sourceRange
        cancel()
        if interrupted { stoppedRange = previous; stoppedAt = Date() }
    }
    private func consumedStop(_ range: NSRange) -> Bool {
        guard stoppedRange == range, Date().timeIntervalSince(stoppedAt) < 0.7 else { return false }
        stoppedRange = nil; return true
    }
    var canDownload: Bool { outcome?.status == .modelNotReady && immersion.availability == .downloadable && onDownload != nil }
    func download() { let action = onDownload; cancel(); action?() }
    func chooseLanguage() { let action = onChooseLanguage; cancel(); action?() }
    func voiceHelp() { let action = onVoiceHelp; cancel(); action?() }
    func bind(_ view: ImmersionNativeTextView) { if host == nil { anchor = view } }
    func reset(original: String) { cancel(); self.original = original }
    func beginWhole() {
        if loading || speaking || preparingAudio { cancel(); return }
        guard let anchor else { return }
        begin(NSRange(location: 0, length: original.utf16.count), from: anchor)
    }
    var loading: Bool { request != nil && outcome == nil }
    var speaking: Bool { audioID != nil && speech.activeMessage == audioID }
    var sourceText: String {
        if let result = outcome?.result { return result.sourceContextText }
        if let request { return ManualTranslationResolver.slice(request) ?? "" }
        return coveredSource ?? ""
    }
    var targetText: String? { outcome?.result?.targetText ?? coveredTarget }
    var reading: String? {
        guard let result = outcome?.result else { return coveredReading }
        return result.sourceLanguage == result.request.learningLanguage ? result.sourceReading?.text : result.reading?.text
    }
    var pronunciationText: String? {
        guard let result = outcome?.result else { return coveredTarget }
        return result.sourceLanguage == result.request.learningLanguage ? result.sourceContextText : result.targetText
    }
    var pronunciationLanguage: String? {
        guard let result = outcome?.result else { return coveredLanguage }
        return result.request.learningLanguage
    }
    var meaningText: String {
        guard let result = outcome?.result else { return sourceText }
        return result.sourceLanguage == result.request.learningLanguage ? result.targetText : result.sourceContextText
    }
    var targetLanguage: String? { outcome?.result?.targetLanguage ?? coveredLanguage }
    var missingReading: Bool { ["ar", "zh", "ja", "ko"].contains(pronunciationLanguage ?? "") && reading == nil && pronunciationText != nil }
    var failure: String? {
        guard let status = outcome?.status, status != .ready else { return nil }
        switch status {
        case .modelNotReady: return immersion.availability == .unsupported
            ? String(localized: "Translation isn’t supported for this language pair on this device.")
            : String(localized: "Translation needs a language download.")
        case .invalidLanguage: return String(localized: "Choose the message language.")
        case .timeout: return String(localized: "Translation took too long. Try again.")
        case .invalidInput: return String(localized: "Select a word or phrase to translate.")
        default: return String(localized: "Translation isn’t available right now.")
        }
    }
    private func record(_ event: String) {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") else { return }
        LiveImmersionQualification.record(["event": event, "message_id": messageID, "generation": generation,
            "start_utf16": sourceRange.location, "end_utf16": NSMaxRange(sourceRange),
            "availability": String(describing: immersion.availability), "foreground": foreground,
            "audio_language": pronunciationLanguage ?? "", "audio_uses_source_context": outcome?.result.map { $0.sourceLanguage == $0.request.learningLanguage } ?? false])
        #endif
    }
    func cancel() {
        if request != nil || audioID != nil || preparingAudio { record("manual_cancelled") }
        generation &+= 1; task?.cancel(); task = nil
        if let audioID, speech.activeMessage == audioID { speech.stop() }
        audioID = nil; request = nil; outcome = nil; preparingAudio = false; audioError = nil
        coveredSource = nil; coveredTarget = nil; coveredReading = nil; coveredLanguage = nil; stoppedRange = nil
        host?.view.removeFromSuperview(); host = nil; anchor = nil
        if Self.active === self { Self.active = nil }
    }
    private func activate() { Self.active?.cancel(); cancel(); Self.active = self; speech.stop() }
    func begin(_ range: NSRange, from view: ImmersionNativeTextView) {
        if consumedStop(range) { return }
        if request?.startUTF16 == range.location, request?.endUTF16 == NSMaxRange(range), loading || speaking { cancel(); return }
        activate(); anchor = view; sourceRange = range
        let produced = immersion.makeManualRequest(messageID: messageID, originalText: original,
            startUTF16: range.location, endUTF16: NSMaxRange(range), generation: generation)
        request = produced; record("manual_started"); updatePanel()
        task = Task { @MainActor in
            let value = await immersion.manualTranslation(produced)
            guard !Task.isCancelled, request == produced, foreground else { return }
            guard value.status != .stale else { cancel(); return }
            outcome = value; record("manual_" + String(describing: value.status)); updatePanel()
            if let result = value.result, result.request == produced {
                #if DEBUG
                LiveImmersionQualification.recordResult(result)
                #endif
                let text = result.sourceLanguage == result.request.learningLanguage ? result.sourceContextText : result.targetText
                await play(text: text, language: result.request.learningLanguage, expectedGeneration: generation)
            }
        }
    }
    func coveredWord(_ word: ImmersionSpan, language: String, from view: ImmersionNativeTextView?) {
        if consumedStop(word.range) { return }
        activate(); anchor = view; sourceRange = word.range
        coveredSource = word.original; coveredTarget = word.translated
        coveredReading = word.romanization; coveredLanguage = language
        let produced = generation
        task = Task { @MainActor in await play(text: word.translated, language: language, expectedGeneration: produced) }
    }
    private func play(text: String, language: String, expectedGeneration: UInt64) async {
        guard foreground, !interactionPaused, generation == expectedGeneration else { return }
        audioError = nil
        preparingAudio = speech.state == .preparing; updatePanel(ifVisible: true)
        for _ in 0..<160 {
            guard !Task.isCancelled, generation == expectedGeneration, foreground, !interactionPaused else { return }
            if speech.state != .preparing { break }
            try? await Task.sleep(for: .milliseconds(50))
        }
        guard !Task.isCancelled, generation == expectedGeneration, foreground, !interactionPaused else { return }
        preparingAudio = false
        guard speech.state != .preparing && speech.state != .unavailable else {
            audioError = speech.error ?? String(localized: "Voices aren’t ready yet."); updatePanel(); return
        }
        let key = "manual-\(messageID)-\(expectedGeneration)"; audioID = key
        // Script is the synthesis input. A Latin reading is display metadata.
        speech.toggle(message: key, spans: [(text, language)]); record("manual_audio_requested"); updatePanel(ifVisible: true)
        while speech.activeMessage == key {
            try? await Task.sleep(for: .milliseconds(80))
            guard !Task.isCancelled, generation == expectedGeneration, foreground, !interactionPaused else { return }
        }
        guard !Task.isCancelled, generation == expectedGeneration, foreground, !interactionPaused,
              speech.activeMessage == nil else { return }
        if let error = speech.error {
            audioError = error; record("manual_audio_failed"); updatePanel()
        }
    }
    func toggleAudio() {
        if speaking || preparingAudio { task?.cancel(); preparingAudio = false; speech.stop(); return }
        guard let text = pronunciationText, let language = pronunciationLanguage else { return }
        let produced = generation
        task?.cancel(); task = Task { @MainActor in await play(text: text, language: language, expectedGeneration: produced) }
    }
    func retry() {
        guard let anchor else { return }
        begin(sourceRange, from: anchor)
    }
    func updatePanel(ifVisible: Bool = false) {
        if ifVisible && host == nil { return }
        guard let anchor, let window = anchor.window else { return }
        if host == nil {
            let controller = UIHostingController(rootView: ManualLookupPanel(interaction: self))
            controller.view.backgroundColor = .clear; controller.view.accessibilityViewIsModal = false
            host = controller; window.addSubview(controller.view)
        }
        let width = min(460, window.bounds.width - 24)
        let traits = anchor.traitCollection
        func height(_ text: String, style: UIFont.TextStyle) -> CGFloat {
            let font = UIFont.preferredFont(forTextStyle: style, compatibleWith: traits)
            return ceil((text as NSString).boundingRect(with: CGSize(width: width - 40, height: .greatestFiniteMagnitude),
                options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: [.font: font], context: nil).height)
        }
        var desired: CGFloat = 72
        if let learning = pronunciationText {
            desired += height(learning, style: .title3) + 12 + height(meaningText, style: .subheadline)
        } else { desired += height(sourceText, style: .subheadline) }
        if let reading { desired += 8 + height(reading, style: .body) }
        if missingReading { desired += 8 + height(String(localized: "Reading guide unavailable."), style: .subheadline) }
        if let error = failure ?? audioError { desired += 12 + height(error, style: .body) + (canDownload || outcome?.status == .invalidLanguage || audioError != nil ? 44 : 0) }
        if loading || preparingAudio { desired += 44 }
        let height = min(max(150, desired), window.bounds.height * 0.48)
        let sameSource = original.utf8.elementsEqual(anchor.originalMessage.utf8)
        let displayedRange = request != nil && !sameSource ? NSRange(location: 0, length: anchor.originalMessage.utf16.count) : sourceRange
        let selected = anchor.windowRect(forOriginalRange: displayedRange)
        let top = window.safeAreaInsets.top + 50
        let bottom = window.bounds.height - window.safeAreaInsets.bottom - 76
        let below = selected.maxY + 56
        let y = below + height <= bottom ? below : max(top, min(selected.minY - height - 64, bottom - height))
        host?.view.frame = CGRect(x: (window.bounds.width - width) / 2, y: y, width: width, height: height)
    }
}

private struct ManualLookupPanel: View {
    @Bindable var interaction: ManualLookupInteraction
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Spacer(minLength: 8)
                if interaction.targetText != nil {
                    Button { interaction.toggleAudio() } label: {
                        Image(systemName: interaction.speaking || interaction.preparingAudio ? "stop.fill" : "speaker.wave.2").frame(width: 44, height: 44)
                    }.accessibilityLabel(LocalizedStringKey(interaction.speaking || interaction.preparingAudio ? "Stop" : "Play again"))
                }
                Button { interaction.cancel() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Close")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if let learning = interaction.pronunciationText {
                        Text(learning).font(.title3.weight(.semibold)).textSelection(.enabled)
                        if let reading = interaction.reading { Text(reading).font(.body).foregroundStyle(VipiDesign.secondary).textSelection(.enabled) }
                        if interaction.missingReading { Text("Reading guide unavailable.").font(.subheadline).foregroundStyle(VipiDesign.secondary) }
                        Text(interaction.meaningText).font(.subheadline).foregroundStyle(VipiDesign.secondary).textSelection(.enabled)
                    } else {
                        Text(interaction.sourceText).font(.subheadline).foregroundStyle(VipiDesign.secondary).textSelection(.enabled)
                    }
                    if interaction.loading || interaction.preparingAudio { ProgressView { Text(LocalizedStringKey(interaction.loading ? "Translating on this device…" : "Preparing voices")) } }
                    if let error = interaction.failure ?? interaction.audioError { Text(error).font(.body).foregroundStyle(VipiDesign.secondary) }
                    if interaction.canDownload { Button("Download languages") { interaction.download() }.frame(minHeight: 44) }
                    else if interaction.outcome?.status == .invalidLanguage, interaction.onChooseLanguage != nil {
                        Button("Message language") { interaction.chooseLanguage() }.frame(minHeight: 44)
                    } else if interaction.failure != nil && interaction.outcome?.status != .modelNotReady {
                        Button("Try again") { interaction.retry() }.frame(minHeight: 44)
                    }
                    if interaction.audioError != nil, interaction.speech.state == .unavailable, interaction.onVoiceHelp != nil {
                        Button("Set up voices") { interaction.voiceHelp() }.frame(minHeight: 44)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(.bottom, 4)
            }
        }.padding(.horizontal, 16).padding(.bottom, 14)
            .foregroundStyle(VipiDesign.ink).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(VipiDesign.secondary.opacity(0.2)))
            .shadow(color: .black.opacity(0.14), radius: 16, y: 5)
            .accessibilityIdentifier("manual-translation-panel")
            .onChange(of: typeSize) { interaction.updatePanel() }
    }
}
