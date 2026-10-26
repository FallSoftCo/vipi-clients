import Foundation
import SwiftUI
@preconcurrency import Translation
import VipiCore

/// One conversation owns a bounded transient cache and a serial translation
/// queue. Persisted/encrypted ChatItem text is never rewritten.
@MainActor @Observable final class ConversationImmersion {
    struct Request: Identifiable {
        let id: UUID; let text: String; let pair: TranslationPair; let epoch: UUID
        let reversed: Bool; let cacheKey: String
    }
    private(set) var request: Request?
    private(set) var availability = LocalLanguageAvailability.checking
    private(set) var revision = 0
    private(set) var pair = TranslationPair(source: "en", target: "es")
    private var density = 0.25
    private var epoch = UUID()
    private var pending: [Request] = []
    private var replies: [UUID: CheckedContinuation<ImmersionResult?, Never>] = [:]
    private var cache: [String: ImmersionResult] = [:]
    private var order: [String] = []
    private var inputLanguages: [String: String] = [:]
    private let catalog = BundledImmersionCatalog()
    private var swahili: [String: SwahiliTranslation] = [:]
    private let language = MessageLanguage()
    func inputLanguage(for id: String) -> String? { inputLanguages[id] }
    func selectInputLanguage(_ language: String?, for id: String) {
        guard language == nil || [pair.source, pair.target].contains(language!) else { return }
        inputLanguages[id] = language
    }
    func cached(_ text: String, messageID: String? = nil) -> ImmersionResult? {
        let selected = messageID.flatMap { inputLanguages[$0] } ?? "auto"
        return cache[selected + ":" + text]
    }

    func refreshAvailability() async {
        let active = epoch
        let observed = await LanguagePreparation.nativeStatus(pair)
        guard active == epoch, !Task.isCancelled else { return }
        if availability != observed { availability = observed; revision += 1 }
    }

    func configure(pair: TranslationPair, density: Double) async {
        close(); self.pair = pair; self.density = density; availability = .checking
        let active = epoch
        let observed = await LanguagePreparation.nativeStatus(pair)
        guard active == epoch, !Task.isCancelled else { return }
        if pair.usesMLKit {
            swahili[pair.source] = try? SwahiliTranslation(pair: pair)
            swahili[pair.target] = try? SwahiliTranslation(pair: .init(source: pair.target, target: pair.source))
        }
        availability = observed; revision += 1
    }
    func result(for text: String, inputLanguage: String? = nil) async -> ImmersionResult? {
        guard !Task.isCancelled, !text.isEmpty, text.utf16.count <= 16_384 else { return nil }
        if let inputLanguage, ![pair.source, pair.target].contains(inputLanguage) { return nil }
        let key = (inputLanguage ?? "auto") + ":" + text
        if let result = cache[key] { return result }
        let activeEpoch = epoch, activePair = pair
        let reversePair = TranslationPair(source: activePair.target, target: activePair.source)
        let forward = inputLanguage == pair.target ? nil : try? await catalog.reference(original: text, pair: activePair)
        let reverse = forward != nil || inputLanguage == pair.source ? nil : try? await catalog.reference(original: text, pair: reversePair)
        if let translation = forward ?? reverse {
            let reversed = forward == nil
            let result = try? await catalog.result(original: reversed ? translation : text, translation: reversed ? text : translation, pair: activePair, density: density)
            guard activeEpoch == epoch, !Task.isCancelled else { return nil }
            if let result { remember(result, key: key) }
            return result
        }
        guard activeEpoch == epoch, availability == .installed, !Task.isCancelled else { return nil }
        let detected: String?
        if let inputLanguage { detected = inputLanguage } else { detected = try? await language.identify(text) }
        guard activeEpoch == epoch, !Task.isCancelled, let detected,
              [activePair.source, activePair.target].contains(detected) else { return nil }
        let reversed = detected == activePair.target
        let id = UUID()
        return await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                guard !Task.isCancelled else { continuation.resume(returning: nil); return }
                replies[id] = continuation
                pending.append(Request(id: id, text: text, pair: reversed ? reversePair : activePair,
                    epoch: activeEpoch, reversed: reversed, cacheKey: key)); next()
            }
        } onCancel: { Task { @MainActor [weak self] in self?.cancel(id) } }
    }
    private func next() { if request == nil, !pending.isEmpty { request = pending.removeFirst() } }
    private func cancel(_ id: UUID) {
        replies.removeValue(forKey: id)?.resume(returning: nil)
        pending.removeAll { $0.id == id }
        if request?.id == id { request = nil; next() }
    }
    func finish(_ active: Request, translation: String?) async {
        guard active.epoch == epoch, active.id == request?.id else { return }
        var result: ImmersionResult?
        if let translation, !Task.isCancelled, TranslationIntegrity.preservesIdentifiers(original: active.text, translation: translation) {
            result = try? await catalog.result(original: active.reversed ? translation : active.text,
                translation: active.reversed ? active.text : translation, pair: pair, density: density)
        }
        guard active.epoch == epoch, active.id == request?.id else { return }
        if let result { remember(result, key: active.cacheKey) }
        replies.removeValue(forKey: active.id)?.resume(returning: result)
        request = nil; next()
    }
    func translateSwahili(_ active: Request) async {
        guard active.epoch == epoch, active.id == request?.id, let swahili = swahili[active.pair.source] else { return }
        let translation = try? await swahili.translate(active.text)
        await finish(active, translation: translation)
    }
    private func remember(_ result: ImmersionResult, key: String) {
        cache[key] = result; order.removeAll { $0 == key }; order.append(key)
        while order.count > 128 { cache.removeValue(forKey: order.removeFirst()) }
    }
    func close() {
        epoch = UUID(); request = nil; pending.removeAll(); cache.removeAll(); order.removeAll(); swahili.removeAll(); inputLanguages.removeAll()
        let outstanding = replies.values; replies.removeAll()
        for reply in outstanding { reply.resume(returning: nil) }
        revision += 1
    }
}

struct ConversationTranslationTask: View {
    let immersion: ConversationImmersion
    var body: some View {
        if let request = immersion.request {
            TranslationRequestTask(request: request, immersion: immersion).id(request.id)
        }
    }
}

private struct TranslationRequestTask: View {
    let request: ConversationImmersion.Request
    let immersion: ConversationImmersion
    var body: some View {
        if request.pair.usesMLKit {
            Color.clear.frame(width: 0, height: 0).accessibilityHidden(true)
                .task { await immersion.translateSwahili(request) }
        } else {
            Color.clear.frame(width: 0, height: 0).accessibilityHidden(true)
                .translationTask(source: .init(identifier: request.pair.source), target: .init(identifier: request.pair.target)) { session in
                    guard await LanguagePreparation.nativeStatus(request.pair) == .installed else {
                        await immersion.finish(request, translation: nil); return
                    }
                    let result = try? await session.translate(request.text)
                    await immersion.finish(request, translation: result?.targetText)
                }
        }
    }
}

struct ConversationImmersionText: View {
    let text: String
    let id: String
    let immersion: ConversationImmersion
    let speech: SpeechPlayback
    let paused: Bool
    let metadata: AnyView
    let onVoiceHelp: () -> Void
    @State private var result: ImmersionResult?
    @State private var waiting: ImmersionResult?
    @State private var hasWaiting = false
    @State private var currentlyPaused = false
    @State private var mode: ReadingMode = .immersed
    private var inputLanguage: String? { immersion.inputLanguage(for: id) }
    init(text: String, id: String, immersion: ConversationImmersion, speech: SpeechPlayback,
         paused: Bool, metadata: AnyView, onVoiceHelp: @escaping () -> Void) {
        self.text = text; self.id = id; self.immersion = immersion; self.speech = speech
        self.paused = paused; self.metadata = metadata; self.onVoiceHelp = onVoiceHelp
        _result = State(initialValue: immersion.cached(text, messageID: id))
    }
    var body: some View {
        Group {
            if let result {
                ImmersionBubble(result: result, mode: mode, speech: speech,
                    sourceLanguage: immersion.pair.source, targetLanguage: immersion.pair.target,
                    messageID: id, interactionPaused: paused, fullReading: SentenceReadings.reading(result.translation, language: immersion.pair.target),
                    embedded: true, onModeChange: { mode = $0 }, metadata: metadata, onVoiceHelp: onVoiceHelp,
                    originalMessage: text, inputLanguage: inputLanguage, onInputLanguage: { speech.stop(); immersion.selectInputLanguage($0, for: id) })
            } else {
                VStack(alignment: .leading, spacing: 7) {
                Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("message-body-" + id)
                HStack {
                    metadata; Spacer(minLength: 8)
                    Menu {
                        MessageLanguageMenu(source: immersion.pair.source, target: immersion.pair.target,
                            selected: inputLanguage, select: { immersion.selectInputLanguage($0, for: id) })
                        Button("Copy original message") { UIPasteboard.general.string = text }
                    } label: { Image(systemName: "ellipsis").font(.footnote).frame(width: 44, height: 44) }
                        .accessibilityLabel("Reading options")
                }
                }
            }
        }.task(id: "\(immersion.revision)-\(inputLanguage ?? "auto")-\(text)") {
                waiting = nil; hasWaiting = false
                let value = await immersion.result(for: text, inputLanguage: inputLanguage)
                guard !Task.isCancelled else { return }
                // Read current state after suspension, not the view value
                // captured before the user began drafting or scrolling.
                if currentlyPaused { waiting = value; hasWaiting = true } else { result = value }
            }
            .onChange(of: paused, initial: true) { _, paused in
                currentlyPaused = paused
                if !paused, hasWaiting { result = waiting; self.waiting = nil; hasWaiting = false }
            }
    }
}
