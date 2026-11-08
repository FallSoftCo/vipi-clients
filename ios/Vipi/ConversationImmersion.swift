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
    private var deadlines: [UUID: Task<Void, Never>] = [:]
    private var fullRequests: [ImmersionRequestIdentity: (UUID, Task<LookupFirstOutcome?, Never>)] = [:]
    private var cache = ImmersionPresentationCache()
    private var inputLanguages: [String: String] = [:]
    private let catalog = BundledImmersionCatalog()
    private let lexical = BundledLexicalCatalog.shared
    private var swahili: [String: SwahiliTranslation] = [:]
    private let language = MessageLanguage()
    private let modelStatus: (TranslationPair) async -> LocalLanguageAvailability
    private let fullTranslationTimeout: Duration
    #if DEBUG
    // Explicit qualification hook only; release builds cannot load research packs.
    private var qaSourceUnitVersion: String?
    private var qaSourceUnitLookup: ((String, TranslationPair, Double) throws -> PartialImmersionResult?)?
    func qualifySourceUnits(version: String,
        lookup: @escaping (String, TranslationPair, Double) throws -> PartialImmersionResult?) {
        precondition(!version.isEmpty)
        close()
        qaSourceUnitVersion = version; qaSourceUnitLookup = lookup
    }
    #endif

    private func cacheKey(text: String, inputLanguage: String?) -> String {
        let key = (inputLanguage ?? "auto") + ":" + text
        #if DEBUG
        return (qaSourceUnitVersion.map { $0 + "\0" } ?? "") + key
        #else
        return key
        #endif
    }

    init(modelStatus: @escaping (TranslationPair) async -> LocalLanguageAvailability = { await LanguagePreparation.nativeStatus($0) },
         fullTranslationTimeout: Duration = .seconds(30)) {
        precondition(fullTranslationTimeout > .zero && fullTranslationTimeout <= .seconds(30))
        self.modelStatus = modelStatus; self.fullTranslationTimeout = fullTranslationTimeout
    }

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
        return cache[cacheKey(text: text, inputLanguage: messageID.flatMap { inputLanguages[$0] })]
    }
    func refreshAvailability() async {
        let active = epoch
        let observed = await modelStatus(pair)
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
        await resolve(text: text, inputLanguage: inputLanguage, messageID: messageID,
                      intent: .automaticImmersion, onPartial: onPartial)?.result
    }
    /// One full-reference extension per exact message/configuration identity.
    /// Cancellation detaches the provider continuation immediately; a late native
    /// completion cannot publish into a changed conversation or language pair.
    func fullTranslation(for identity: ImmersionRequestIdentity) async -> LookupFirstOutcome? {
        guard !closed, identity == self.identity(messageID: identity.messageID, text: identity.text) else { return nil }
        let entry: (UUID, Task<LookupFirstOutcome?, Never>)
        if let pending = fullRequests[identity], !pending.1.isCancelled { entry = pending }
        else {
            let token = UUID()
            let task = Task { @MainActor [weak self] in
                await self?.resolve(text: identity.text, inputLanguage: identity.inputLanguage,
                    messageID: identity.messageID, intent: .fullTranslation)
            }
            entry = (token, task); fullRequests[identity] = entry
        }
        return await withTaskCancellationHandler {
            let outcome = await entry.1.value
            if fullRequests[identity]?.0 == entry.0 { fullRequests.removeValue(forKey: identity) }
            guard !Task.isCancelled, !closed,
                  identity == self.identity(messageID: identity.messageID, text: identity.text) else { return nil }
            return outcome
        } onCancel: { entry.1.cancel() }
    }
    private func resolve(text: String, inputLanguage: String?, messageID: String?,
                         intent: ImmersionRequestIntent,
                         onPartial: (PartialImmersionResult) -> Void = { _ in }) async -> LookupFirstOutcome? {
        lastOutcome = nil // Cancellation/early exit must not reuse prior telemetry.
        guard !closed, !Task.isCancelled, pair.valid else { return nil }
        let activeEpoch = epoch, activePair = pair, activeDensity = density
        func valid() -> Bool {
            !closed && activeEpoch == epoch && pair == activePair && !Task.isCancelled &&
                (messageID == nil || inputLanguages[messageID!] == inputLanguage)
        }
        guard valid() else { return nil }
        let key = cacheKey(text: text, inputLanguage: inputLanguage)
        // Automatic re-entry/model readiness cannot silently extend a useful
        // partial. Only the explicit whole-language action requests that work.
        if let saved = cache.cachedInvocation(key: key),
           intent == .automaticImmersion || saved.result?.translation != nil {
            lastOutcome = saved; return saved
        }
        do {
            let outcome = try await LookupFirst.resolve(
                .init(text: text, source: activePair.source, target: activePair.target,
                      inputLanguage: inputLanguage, intent: intent),
                valid: valid,
                reference: { original, source, target in
                    try await self.catalog.reference(original: original, pair: .init(source: source, target: target))
                },
                identify: { try await self.language.identify($0) },
                modelsReady: { source, target in
                    let observed = await self.modelStatus(.init(source: source, target: target))
                    guard valid() else { return false }
                    self.availability = observed
                    // Do NOT bump task revision here and cancel our own request.
                    return observed == .installed
                },
                translate: { original, source, target in
                    try await self.enqueue(original, pair: .init(source: source, target: target), epoch: activeEpoch,
                                           timeout: intent == .fullTranslation ? self.fullTranslationTimeout : nil)
                },
                align: { original, translated in
                    try await self.aligned(original: original, translation: translated, pair: activePair, density: activeDensity)
                },
                partialReference: { original, source, target in
                    let pair = TranslationPair(source: source, target: target)
                    if let accepted = try await self.catalog.partial(original: original, pair: pair, density: activeDensity) {
                        return accepted
                    }
                    #if DEBUG
                    return try self.qaSourceUnitLookup?(original, pair, activeDensity)
                    #else
                    return nil
                    #endif
                },
                onPartial: { partial in
                    guard valid() else { return }
                    self.remember(.partial(partial), key: key); onPartial(partial)
                })
            guard valid() else { return nil }
            lastOutcome = outcome
            cache.remember(outcome, key: key)
            return outcome
        } catch is CancellationError { return nil }
        catch { return valid() ? cache.cachedInvocation(key: key) : nil }
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
    private func enqueue(_ text: String, pair: TranslationPair, epoch active: UUID, timeout: Duration? = nil) async throws -> String {
        guard !closed, active == epoch, pair.valid, pending.count < 128 else { throw ProviderError.unavailable }
        let id = UUID()
        return try await withTaskCancellationHandler {
            let translated: String? = await withCheckedContinuation { continuation in
                guard !Task.isCancelled, !closed, active == epoch else { continuation.resume(returning: nil); return }
                replies[id] = continuation
                if let timeout {
                    deadlines[id] = Task { @MainActor [weak self] in
                        do { try await Task.sleep(for: timeout) } catch { return }
                        self?.cancel(id)
                    }
                }
                pending.append(.init(id: id, text: text, pair: pair, epoch: active)); next()
            }
            try Task.checkCancellation()
            guard let translated else { throw ProviderError.unavailable }
            return translated
        } onCancel: { Task { @MainActor [weak self] in self?.cancel(id) } }
    }
    private func next() { if request == nil, !pending.isEmpty { request = pending.removeFirst() } }
    private func cancel(_ id: UUID) {
        deadlines.removeValue(forKey: id)?.cancel()
        replies.removeValue(forKey: id)?.resume(returning: nil)
        pending.removeAll { $0.id == id }
        if request?.id == id { request = nil; next() }
    }
    func finish(_ active: Request, translation: String?) async {
        guard !closed, active.epoch == epoch, active.id == request?.id else { return }
        // Router owns literal/anchor/direction validation after this await.
        deadlines.removeValue(forKey: active.id)?.cancel()
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
        for (_, task) in fullRequests.values { task.cancel() }; fullRequests.removeAll()
        for task in deadlines.values { task.cancel() }; deadlines.removeAll()
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
    @State private var fullRequest: Task<Void, Never>?
    @State private var fullFailure: ImmersionStatus?
    @State private var fullFailureAvailability = LocalLanguageAvailability.checking
    private var inputLanguage: String? { immersion.inputLanguage(for: id) }
    private var identity: ImmersionRequestIdentity { immersion.identity(messageID: id, text: text) }
    private struct RunKey: Hashable { let identity: ImmersionRequestIdentity; let revision: Int }
    private func chooseMode(_ value: ReadingMode) {
        fullRequest?.cancel(); fullRequest = nil; fullFailure = nil
        mode = value
    }
    private func requestTranslation() {
        guard fullRequest == nil else { return }
        let produced = identity
        fullFailure = nil
        fullRequest = Task { @MainActor in
            let outcome = await immersion.fullTranslation(for: produced)
            guard !Task.isCancelled, produced == identity else { return }
            fullRequest = nil
            if let value = outcome?.result, value.translation != nil {
                presentation.publish(value, for: produced, current: identity, paused: currentlyPaused)
                mode = .translation
            } else {
                fullFailure = outcome?.fallbackStatus ?? outcome?.status ?? .error
                fullFailureAvailability = immersion.availability
            }
        }
    }
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
        VStack(alignment: .leading, spacing: 7) {
          Group {
            // Gate synchronously during rendering, not only in an onChange task:
            // SwiftUI can render the new message before cancellation is observed.
            if let result = presentation.value(for: identity) {
                ImmersionBubble(result: result, mode: mode, speech: speech,
                    sourceLanguage: identity.source, targetLanguage: identity.target,
                    messageID: id, interactionPaused: paused,
                    fullReading: result.translation.flatMap { SentenceReadings.reading($0, language: identity.target) },
                    embedded: true, onModeChange: chooseMode, metadata: metadata, onVoiceHelp: onVoiceHelp,
                    originalMessage: text, inputLanguage: inputLanguage,
                    onInputLanguage: { speech.stop(); immersion.selectInputLanguage($0, for: id) },
                    requestingTranslation: fullRequest != nil, onRequestTranslation: requestTranslation)
                    .id(identity) // Drop old reveal/selection/full-target action state.
            } else {
                VStack(alignment: .leading, spacing: 7) {
                    Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("message-body-" + id)
                    HStack {
                        metadata; Spacer(minLength: 8)
                        Menu {
                            Button("Show \(VipiLanguage.named(identity.target).name)", action: requestTranslation)
                                .disabled(fullRequest != nil)
                            MessageLanguageMenu(source: identity.source, target: identity.target,
                                selected: inputLanguage, select: { speech.stop(); immersion.selectInputLanguage($0, for: id) })
                            Button("Copy original message") { UIPasteboard.general.string = text }
                        } label: { Image(systemName: "ellipsis").font(.footnote).frame(width: 44, height: 44) }
                            .accessibilityLabel("Reading options")
                    }
                }
            }
          }
          if fullRequest != nil {
              HStack(spacing: 8) {
                  ProgressView().controlSize(.small)
                  Text("Translating on this device…").font(.footnote)
                  Button("Cancel") { fullRequest?.cancel(); fullRequest = nil }
              }.accessibilityIdentifier("full-translation-loading")
          } else if let fullFailure {
              VStack(alignment: .leading, spacing: 6) {
                  Text(fullFailure == .modelNotReady
                    ? (fullFailureAvailability == .unsupported
                       ? "Full translation for this language pair isn’t supported on this device. Your message stays here."
                       : "The full translation needs a prepared language pair.")
                    : "The full translation isn’t available yet. Your message stays here.")
                  HStack(spacing: 16) {
                      if fullFailure != .modelNotReady || fullFailureAvailability != .unsupported {
                          Button("Try again", action: requestTranslation)
                      }
                      if fullFailure == .modelNotReady && fullFailureAvailability == .downloadable {
                          NavigationLink("Prepare languages") { LanguageDownloadView() }
                      }
                      Button("Dismiss") { self.fullFailure = nil }
                  }
              }.font(.footnote).accessibilityIdentifier("full-translation-error")
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
            fullRequest?.cancel(); fullRequest = nil; fullFailure = nil
            presentation.invalidate(for: current); mode = .immersed
            if speech.activeMessage == id { speech.stop() }
        }
        .onDisappear { fullRequest?.cancel(); fullRequest = nil }
        .onChange(of: paused, initial: true) { _, paused in
            currentlyPaused = paused
            if !paused { presentation.resume(for: identity) }
        }
    }
}
