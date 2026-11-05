import Foundation
import SwiftUI
@preconcurrency import Translation
import VipiCore

/// Lookup-first native routing. Persisted/encrypted ChatItem text is never rewritten.
@MainActor @Observable final class ConversationImmersion {
    struct Request: Identifiable {
        let id: UUID; let text: String; let pair: TranslationPair; let epoch: UUID
    }
    private enum ProviderError: Error { case unavailable }
    private(set) var request: Request?
    private(set) var availability = LocalLanguageAvailability.checking
    private(set) var revision = 0
    private(set) var pair = TranslationPair(source: "en", target: "es")
    private(set) var lastOutcome: LookupFirstOutcome?
    private(set) var lexicalPreparation = "unmeasured"
    private var density = 0.25
    private var epoch = UUID()
    private var closed = false
    private var pending: [Request] = []
    private var replies: [UUID: CheckedContinuation<String?, Never>] = [:]
    private var cache = ImmersionPresentationCache()
    private var inputLanguages: [String: String] = [:]
    private let catalog = BundledImmersionCatalog()
    private let lexical = BundledLexicalCatalog.shared
    private var swahili: [String: SwahiliTranslation] = [:]
    private let language = MessageLanguage()

    func inputLanguage(for id: String) -> String? { inputLanguages[id] }
    func identity(messageID: String, text: String) -> ImmersionRequestIdentity {
        .init(messageID: messageID, text: text, source: pair.source, target: pair.target,
              inputLanguage: inputLanguages[messageID], generation: epoch)
    }
    func selectInputLanguage(_ language: String?, for id: String) {
        guard !closed, language == nil || [pair.source, pair.target].contains(language!),
              inputLanguages[id] != language else { return }
        inputLanguages[id] = language
        invalidateOutstanding()
        revision += 1
    }
    func cached(_ text: String, messageID: String? = nil) -> ImmersionPresentation? {
        guard !closed else { return nil }
        return cache[(messageID.flatMap { inputLanguages[$0] } ?? "auto") + ":" + text]
    }
    func refreshAvailability() async {
        let active = epoch
        let observed = await LanguagePreparation.nativeStatus(pair)
        guard !closed, active == epoch, !Task.isCancelled else { return }
        // Status only: lexical expansion belongs to actual target-dependent alignment.
        if availability != observed { availability = observed; revision += 1 }
    }
    func configure(pair: TranslationPair, density: Double) async {
        close(); closed = false; self.pair = pair; self.density = density
        availability = .checking; lexicalPreparation = "unmeasured"
        // No readiness gate, TranslationSession, translator factory or lexical
        // materialization before exact/source-only lookup has had its turn.
    }
    func result(for text: String, inputLanguage: String? = nil, messageID: String? = nil,
                onPartial: (PartialImmersionResult) -> Void = { _ in }) async -> ImmersionPresentation? {
        lastOutcome = nil // Cancellation/early exit must not reuse prior telemetry.
        guard !closed, !Task.isCancelled, pair.valid else { return nil }
        let activeEpoch = epoch, activePair = pair, activeDensity = density
        func valid() -> Bool {
            !closed && activeEpoch == epoch && pair == activePair && !Task.isCancelled &&
                (messageID == nil || inputLanguages[messageID!] == inputLanguage)
        }
        guard valid() else { return nil }
        let key = (inputLanguage ?? "auto") + ":" + text
        // A partial without full translation can be upgraded after a separately
        // signalled model-readiness change; never erase its known source faces.
        if let saved = cache.cachedInvocation(key: key), saved.result?.translation != nil {
            lastOutcome = saved; return saved.result
        }
        do {
            let outcome = try await LookupFirst.resolve(
                .init(text: text, source: activePair.source, target: activePair.target, inputLanguage: inputLanguage),
                valid: valid,
                reference: { original, source, target in
                    try await self.catalog.reference(original: original, pair: .init(source: source, target: target))
                },
                identify: { try await self.language.identify($0) },
                modelsReady: { source, target in
                    let observed = await LanguagePreparation.nativeStatus(.init(source: source, target: target))
                    guard valid() else { return false }
                    self.availability = observed
                    // Do NOT bump task revision here and cancel our own request.
                    return observed == .installed
                },
                translate: { original, source, target in
                    try await self.enqueue(original, pair: .init(source: source, target: target), epoch: activeEpoch)
                },
                align: { original, translated in
                    try await self.aligned(original: original, translation: translated, pair: activePair, density: activeDensity)
                },
                partialReference: { original, source, target in
                    try await self.catalog.partial(original: original, pair: .init(source: source, target: target), density: activeDensity)
                },
                onPartial: { partial in
                    guard valid() else { return }
                    self.remember(.partial(partial), key: key); onPartial(partial)
                })
            guard valid() else { return nil }
            lastOutcome = outcome
            cache.remember(outcome, key: key)
            return outcome.result
        } catch is CancellationError { return nil }
        catch { return valid() ? cache[key] : nil }
    }
    private func aligned(original: String, translation: String, pair: TranslationPair, density: Double) async throws -> ImmersionResult {
        let supplemental: [VocabularyEntry]
        do {
            supplemental = try await lexical.entries(original: original, translation: translation, pair: pair)
            lexicalPreparation = "ready"
        } catch is CancellationError { throw CancellationError() }
        catch { lexicalPreparation = "failed"; supplemental = [] }
        try Task.checkCancellation()
        return try await catalog.result(original: original, translation: translation, pair: pair,
            density: density, supplementalEntries: supplemental)
    }
    private func enqueue(_ text: String, pair: TranslationPair, epoch active: UUID) async throws -> String {
        guard !closed, active == epoch, pair.valid, pending.count < 128 else { throw ProviderError.unavailable }
        let id = UUID()
        return try await withTaskCancellationHandler {
            let translated: String? = await withCheckedContinuation { continuation in
                guard !Task.isCancelled, !closed, active == epoch else { continuation.resume(returning: nil); return }
                replies[id] = continuation
                pending.append(.init(id: id, text: text, pair: pair, epoch: active)); next()
            }
            try Task.checkCancellation()
            guard let translated else { throw ProviderError.unavailable }
            return translated
        } onCancel: { Task { @MainActor [weak self] in self?.cancel(id) } }
    }
    private func next() { if request == nil, !pending.isEmpty { request = pending.removeFirst() } }
    private func cancel(_ id: UUID) {
        replies.removeValue(forKey: id)?.resume(returning: nil)
        pending.removeAll { $0.id == id }
        if request?.id == id { request = nil; next() }
    }
    func finish(_ active: Request, translation: String?) async {
        guard !closed, active.epoch == epoch, active.id == request?.id else { return }
        // Router owns literal/anchor/direction validation after this await.
        replies.removeValue(forKey: active.id)?.resume(returning: translation)
        request = nil; next()
    }
    func translateSwahili(_ active: Request) async {
        guard !closed, active.epoch == epoch, active.id == request?.id else { return }
        let key = active.pair.source + "-" + active.pair.target
        if swahili[key] == nil { swahili[key] = try? SwahiliTranslation(pair: active.pair) }
        guard let translator = swahili[key] else { await finish(active, translation: nil); return }
        let translation = try? await translator.translate(active.text)
        await finish(active, translation: translation)
    }
    private func remember(_ result: ImmersionPresentation, key: String) {
        cache.remember(result, key: key)
    }
    private func invalidateOutstanding() {
        epoch = UUID(); request = nil; pending.removeAll()
        let outstanding = Array(replies.values); replies.removeAll()
        for reply in outstanding { reply.resume(returning: nil) }
    }
    func close() {
        closed = true; invalidateOutstanding(); cache.removeAll()
        swahili.removeAll(); inputLanguages.removeAll(); lastOutcome = nil; revision += 1
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
    @State private var presentation = ImmersionPresentationState()
    @State private var currentlyPaused = false
    @State private var mode: ReadingMode = .immersed
    private var inputLanguage: String? { immersion.inputLanguage(for: id) }
    private var identity: ImmersionRequestIdentity { immersion.identity(messageID: id, text: text) }
    private struct RunKey: Hashable { let identity: ImmersionRequestIdentity; let revision: Int }
    init(text: String, id: String, immersion: ConversationImmersion, speech: SpeechPlayback,
         paused: Bool, metadata: AnyView, onVoiceHelp: @escaping () -> Void) {
        self.text = text; self.id = id; self.immersion = immersion; self.speech = speech
        self.paused = paused; self.metadata = metadata; self.onVoiceHelp = onVoiceHelp
        var initial = ImmersionPresentationState()
        let binding = immersion.identity(messageID: id, text: text)
        initial.publish(immersion.cached(text, messageID: id), for: binding, current: binding, paused: false)
        _presentation = State(initialValue: initial)
        _currentlyPaused = State(initialValue: paused)
    }
    var body: some View {
        Group {
            // Gate synchronously during rendering, not only in an onChange task:
            // SwiftUI can render the new message before cancellation is observed.
            if let result = presentation.value(for: identity) {
                ImmersionBubble(result: result, mode: mode, speech: speech,
                    sourceLanguage: identity.source, targetLanguage: identity.target,
                    messageID: id, interactionPaused: paused,
                    fullReading: result.translation.flatMap { SentenceReadings.reading($0, language: identity.target) },
                    embedded: true, onModeChange: { mode = $0 }, metadata: metadata, onVoiceHelp: onVoiceHelp,
                    originalMessage: text, inputLanguage: inputLanguage,
                    onInputLanguage: { speech.stop(); immersion.selectInputLanguage($0, for: id) })
                    .id(identity) // Drop old reveal/selection/full-target action state.
            } else {
                VStack(alignment: .leading, spacing: 7) {
                    Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("message-body-" + id)
                    HStack {
                        metadata; Spacer(minLength: 8)
                        Menu {
                            MessageLanguageMenu(source: identity.source, target: identity.target,
                                selected: inputLanguage, select: { speech.stop(); immersion.selectInputLanguage($0, for: id) })
                            Button("Copy original message") { UIPasteboard.general.string = text }
                        } label: { Image(systemName: "ellipsis").font(.footnote).frame(width: 44, height: 44) }
                            .accessibilityLabel("Reading options")
                    }
                }
            }
        }.task(id: RunKey(identity: identity, revision: immersion.revision)) {
            let produced = identity
            presentation.invalidate(for: produced)
            let value = await immersion.result(for: produced.text, inputLanguage: produced.inputLanguage, messageID: produced.messageID) { partial in
                guard !Task.isCancelled else { return }
                presentation.publish(.partial(partial), for: produced, current: identity, paused: currentlyPaused)
            }
            guard !Task.isCancelled else { return }
            presentation.publish(value, for: produced, current: identity, paused: currentlyPaused)
        }
        .onChange(of: identity) { _, current in
            presentation.invalidate(for: current); mode = .immersed
            if speech.activeMessage == id { speech.stop() }
        }
        .onChange(of: paused, initial: true) { _, paused in
            currentlyPaused = paused
            if !paused { presentation.resume(for: identity) }
        }
    }
}
