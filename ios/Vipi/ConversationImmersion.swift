import Foundation
import CryptoKit
import SwiftUI
@preconcurrency import Translation
import VipiCore

struct ChatMessageArrival {
    let id: String
    let peer: UUID?
    let load: @MainActor () -> String?
    init(id:String,peer:UUID? = nil,load:@escaping @MainActor () -> String?) {
        self.id = id; self.peer = peer; self.load = load
    }
    /// Bounded visible/test demand. Durable production arrivals use weak-vault
    /// loaders, so a queued account backlog never retains message bodies.
    init(id:String,text:String,peer:UUID? = nil) { self.init(id:id,peer:peer,load:{text}) }
}

/// Internal SDK boundary shared by onboarding and conversations. Qualification
/// may supply controlled SDK responses; the Release app constructs native defaults.
@MainActor final class MessageTranslationServices {
    let status: (TranslationPair) async -> LocalLanguageAvailability
    let translate: ((String, TranslationPair) async throws -> String)?
    let prepare: (@MainActor (TranslationPair) async throws -> Void)?
    init(status: @escaping (TranslationPair) async -> LocalLanguageAvailability = { await LanguagePreparation.nativeStatus($0) },
         translate: ((String, TranslationPair) async throws -> String)? = nil,
         prepare: (@MainActor (TranslationPair) async throws -> Void)? = nil) {
        self.status = status; self.translate = translate; self.prepare = prepare
    }
    func makeOwner() -> ConversationImmersion { ConversationImmersion(modelStatus:status,nativeTranslation:translate) }
    func makePreparation() -> LanguagePreparation { LanguagePreparation(status:{pair in await self.status(pair)},nativePrepare:prepare) }
}

/// Every immutable chat message requests a complete on-device translation.
/// Model output is derivative display state; encrypted stored text is never rewritten.
@MainActor @Observable final class ConversationImmersion {
    struct Request: Identifiable { let id: UUID; let text: String; let pair: TranslationPair; let epoch: UUID }
    enum Phase: Equatable { case translating, ready, needsDownload, unsupported, failed, timedOut }
    enum ProviderError: Error { case unavailable, timedOut, cancelled, modelNotReady, unsupported, preparation }
    private(set) var request: Request?
    private(set) var availability = LocalLanguageAvailability.checking
    private(set) var revision = 0
    private(set) var pair = TranslationPair(source: "en", target: "es")
    private(set) var lastOutcome: LookupFirstOutcome?
    // Retained native diagnostic field: no lexical preparation runs in this path.
    var lexicalPreparation: String { "not used: full on-device translation" }
    private var epoch = UUID()
    private var closed = false
    #if DEBUG
    // Read-only identity/task capture for the explicitly owned root fixture.
    // Retain the real Tasks before close clears its registry; never create work here.
    var pendingPairQualificationClosed: Bool { closed }
    var pendingPairQualificationTasks: [(ImmersionRequestIdentity, Task<FullMessageTranslation?, Never>)] {
        inFlight.map { ($0.key, $0.value.1) }
    }
    #endif
    private var inputLanguages: [String: String] = [:]
    private var translations: [ImmersionRequestIdentity: FullMessageTranslation] = [:]
    private weak var cacheVault: MessageVault?
    private struct CachedTranslation: Codable {
        let policy:String; let messageID:String; let source:String; let target:String
        let value:FullMessageTranslation
    }
    private struct CachedFailure: Codable {
        let policy:String; let messageID:String; let source:String; let target:String
        let originalSHA256:String; let phase:String
    }
    private func savedFailure(_ identity:ImmersionRequestIdentity) -> Phase? {
        guard let vault = cacheVault,
              let data = try? vault.transaction({ try vault.get("full-message-translation-failure",durableKey(identity)) }),
              let saved = try? JSONDecoder().decode(CachedFailure.self,from:data),
              saved.policy == cachePolicy,saved.messageID.utf8.elementsEqual(identity.messageID.utf8),
              saved.source == identity.source,saved.target == identity.target,
              saved.originalSHA256 == SHA256.hash(data:Data(identity.text.utf8)).map({String(format:"%02x",$0)}).joined() else { return nil }
        return saved.phase == "failed" ? .failed : saved.phase == "timedOut" ? .timedOut : nil
    }
    private func saveFailure(_ phase:Phase,identity:ImmersionRequestIdentity) {
        guard let vault = cacheVault,phase == .failed || phase == .timedOut,
              let data = try? JSONEncoder().encode(CachedFailure(policy:cachePolicy,messageID:identity.messageID,
                source:identity.source,target:identity.target,
                originalSHA256:SHA256.hash(data:Data(identity.text.utf8)).map{String(format:"%02x",$0)}.joined(),
                phase:phase == .failed ? "failed":"timedOut")) else { return }
        try? vault.transaction { try vault.put("full-message-translation-failure",durableKey(identity),data) }
    }
    private let cachePolicy: String
    func attachCache(_ vault:MessageVault) { cacheVault = vault }
    private func durableKey(_ identity:ImmersionRequestIdentity) -> String {
        let parts = [cachePolicy,identity.messageID,identity.source,identity.target,identity.inputLanguage ?? "auto",identity.text]
        var bytes = Data()
        for part in parts { var count = UInt64(part.utf8.count).bigEndian; withUnsafeBytes(of:&count) { bytes.append(contentsOf:$0) }; bytes.append(contentsOf:part.utf8) }
        let message = SHA256.hash(data:Data(identity.messageID.utf8)).map{String(format:"%02x",$0)}.joined()
        return message+"/"+SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined()
    }
    /// Explicit conversation deletion removes every pair's derivative cache,
    /// and rejects late model completions for those immutable message IDs.
    func forget(messageIDs:Set<String>) throws {
        for key in inFlight.keys.filter({messageIDs.contains($0.messageID)}) { inFlight.removeValue(forKey:key)?.1.cancel() }
        for key in readingTasks.keys.filter({messageIDs.contains($0.messageID)}) { readingTasks.removeValue(forKey:key)?.1.cancel() }
        for key in phases.keys.filter({messageIDs.contains($0.messageID)}) { translations.removeValue(forKey:key); phases.removeValue(forKey:key); requiredPairs.removeValue(forKey:key) }
        warmQueue.removeAll{messageIDs.contains($0.id)}; warmKnown.subtract(messageIDs)
        for key in residentCosts.keys.filter({messageIDs.contains($0.messageID)}) { residentCosts.removeValue(forKey:key) }
        residentOrder.removeAll{messageIDs.contains($0.messageID)}; readings.removeAll(); readingRevision += 1; revision += 1
        if let vault = cacheVault {
            try vault.transaction {
                for id in messageIDs {
                    let prefix = SHA256.hash(data:Data(id.utf8)).map{String(format:"%02x",$0)}.joined()+"/"
                    for namespace in ["full-message-translation","full-message-translation-failure"] {
                        while true {
                            let keys = try vault.pageIDs(namespace,prefix:prefix,before:nil,limit:100)
                            for key in keys { try vault.remove(namespace,key) }
                            if keys.count < 100 { break }
                        }
                    }
                }
            }
        }
    }
    private func savedTranslation(_ identity:ImmersionRequestIdentity) -> FullMessageTranslation? {
        guard let vault = cacheVault,
              let bytes = try? vault.transaction({try vault.get("full-message-translation",durableKey(identity))}),
              let saved = try? JSONDecoder().decode(CachedTranslation.self,from:bytes),
              saved.policy == cachePolicy, saved.messageID.utf8.elementsEqual(identity.messageID.utf8),
              saved.source == identity.source,saved.target == identity.target,
              saved.value.original.utf8.elementsEqual(identity.text.utf8),
              saved.value.practiceLanguage == identity.target,saved.value.meaningLanguage == identity.source,
              !saved.value.practiceText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              !saved.value.meaningText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              bytes.count <= FullMessageBudget.recordBytes else { return nil }
        return saved.value
    }
    private func encodedTranslation(_ value:FullMessageTranslation,identity:ImmersionRequestIdentity) -> Data? {
        guard let bytes = try? JSONEncoder().encode(CachedTranslation(policy:cachePolicy,messageID:identity.messageID,source:identity.source,target:identity.target,value:value)),
              bytes.count <= FullMessageBudget.recordBytes else { return nil }
        return bytes
    }
    private func saveTranslation(_ value:FullMessageTranslation,identity:ImmersionRequestIdentity) {
        guard let vault = cacheVault,let bytes = encodedTranslation(value,identity:identity) else { return }
        // Derivative cache failure cannot replace or erase the committed message.
        try? vault.transaction {
            try vault.put("full-message-translation",durableKey(identity),bytes)
            try vault.remove("full-message-translation-failure",durableKey(identity))
        }
    }
    private var residentOrder: [ImmersionRequestIdentity] = []
    private var residentCosts: [ImmersionRequestIdentity:Int] = [:]
    private let memoryCacheLimit: Int
    private let memoryCacheByteLimit: Int
    private var visibleTranslations: [ImmersionRequestIdentity:Int] = [:]
    var memoryCacheCount: Int { translations.count }
    var residentStateCount: Int { residentCosts.count }
    var residentMemoryBytes: Int { residentCosts.values.reduce(0,+) }
    private func touchResident(_ identity:ImmersionRequestIdentity) {
        let value = translations[identity]
        residentCosts[identity] = identity.text.utf8.count + identity.messageID.utf8.count + 128
            + (value?.practiceText.utf8.count ?? 0) + (value?.meaningText.utf8.count ?? 0) + (value?.practiceReading?.utf8.count ?? 0)
        residentOrder.removeAll{$0 == identity}; residentOrder.append(identity)
        trimMemoryCache()
    }
    func retainVisible(_ identity:ImmersionRequestIdentity) {
        guard !closed,identity == self.identity(messageID:identity.messageID,text:identity.text) else { return }
        visibleTranslations[identity,default:0] += 1
    }
    func releaseVisible(_ identity:ImmersionRequestIdentity) {
        if let count = visibleTranslations[identity] {
            if count > 1 { visibleTranslations[identity] = count - 1 } else { visibleTranslations.removeValue(forKey:identity) }
        }
        trimMemoryCache()
    }
    private func remember(_ value:FullMessageTranslation,for identity:ImmersionRequestIdentity) {
        translations[identity] = value; phases[identity] = .ready
        touchResident(identity)
    }
    private func trimMemoryCache() {
        // Mounted rows own their completed display until they leave the viewport.
        // Whole-history replay may retain only the bounded, unmounted cache.
        while residentCosts.count > memoryCacheLimit || residentMemoryBytes > memoryCacheByteLimit {
            guard let index = residentOrder.firstIndex(where:{visibleTranslations[$0] == nil && inFlight[$0] == nil}) else { return }
            let old = residentOrder.remove(at:index)
            residentCosts.removeValue(forKey:old)
            translations.removeValue(forKey:old); phases.removeValue(forKey:old); requiredPairs.removeValue(forKey:old)
        }
    }
    private var phases: [ImmersionRequestIdentity: Phase] = [:]
    private var requiredPairs: [ImmersionRequestIdentity: TranslationPair] = [:]
    private var inFlight: [ImmersionRequestIdentity: (UUID, Task<FullMessageTranslation?, Never>)] = [:]
    private var pending: [Request] = []
    private var replies: [UUID: CheckedContinuation<String?, Never>] = [:]
    private var deadlines: [UUID: Task<Void, Never>] = [:]
    private var requestTimeouts: [UUID: Duration] = [:]
    private struct WarmWork { let id:String; let load:@MainActor () -> String? }
    private var warmQueue: [WarmWork] = []
    private var warmKnown = Set<String>()
    private var warmTask: Task<Void,Never>?
    private var timedOutRequests = Set<UUID>()
    private var providerFailures: [UUID:ProviderError] = [:]
    private let identify: (String) async throws -> String?
    private let nativeTranslation: ((String, TranslationPair) async throws -> String)?
    private let modelStatus: (TranslationPair) async -> LocalLanguageAvailability
    private let fullTranslationTimeout: Duration
    private let readings: FullReadingCache
    private var readingRevision = 0
    private var readingTasks: [ImmersionRequestIdentity: (UUID, Task<Void, Never>)] = [:]
    private var swahili: [String: SwahiliTranslation] = [:]

    init(modelStatus: @escaping (TranslationPair) async -> LocalLanguageAvailability = { await LanguagePreparation.nativeStatus($0) },
         fullTranslationTimeout: Duration = .seconds(30),
         memoryCacheLimit: Int = 128,
         memoryCacheByteLimit: Int = FullMessageBudget.residentBytes,
         identify: @escaping (String) async throws -> String? = { try await MessageLanguage().identify($0) },
         nativeTranslation: ((String, TranslationPair) async throws -> String)? = nil,
         fullReadingProducer: @escaping FullReadingCache.Producer = { FullSentenceReadings.resolveDetailed($0, language: $1) }) {
        precondition(fullTranslationTimeout > .zero && fullTranslationTimeout <= .seconds(30))
        precondition(memoryCacheLimit > 0 && memoryCacheByteLimit > 0)
        self.memoryCacheLimit = memoryCacheLimit; self.memoryCacheByteLimit = memoryCacheByteLimit
        self.modelStatus = modelStatus; self.fullTranslationTimeout = fullTranslationTimeout; self.identify = identify; self.nativeTranslation = nativeTranslation
        cachePolicy = (nativeTranslation == nil ? "native-full-message-1:" : "controlled-sdk-full-message-1:") + FullSentenceReadings.translationCacheCompatibilitySuffix
        readings = FullReadingCache(policy: FullSentenceReadings.policy, producer: fullReadingProducer)
    }
    func identity(messageID: String, text: String) -> ImmersionRequestIdentity {
        .init(messageID: messageID, text: text, source: pair.source, target: pair.target,
              inputLanguage: inputLanguages[messageID], generation: epoch)
    }
    func inputLanguage(for id: String) -> String? { inputLanguages[id] }
    func selectInputLanguage(_ language: String?, for id: String) {
        guard !closed, language == nil || [pair.source,pair.target].contains(language!), inputLanguages[id] != language else { return }
        inputLanguages[id] = language; invalidateOutstanding(); revision += 1
    }
    func resolvedInputLanguage(for identity: ImmersionRequestIdentity) -> String? { translations[identity]?.inputLanguage }
    func translation(for identity: ImmersionRequestIdentity) -> FullMessageTranslation? {
        guard !closed, identity == self.identity(messageID: identity.messageID, text: identity.text) else { return nil }
        return translations[identity]
    }
    func phase(for identity: ImmersionRequestIdentity) -> Phase { phases[identity] ?? .translating }
    func requiredPair(for identity: ImmersionRequestIdentity) -> TranslationPair { requiredPairs[identity] ?? pair }
    func cached(_ text: String, messageID: String? = nil) -> ImmersionPresentation? {
        translation(for: identity(messageID: messageID ?? "anonymous", text: text))?.presentation
    }
    func configure(pair:TranslationPair) async {
        close(); closed = false; self.pair = pair; availability = .checking
    }
    func refreshAvailability() async {
        let active = epoch, value = await modelStatus(pair)
        guard !closed, active == epoch, !Task.isCancelled else { return }
        availability = value; revision += 1
    }
    func retry(_ identity: ImmersionRequestIdentity) {
        guard !closed, identity == self.identity(messageID: identity.messageID, text: identity.text) else { return }
        inFlight.removeValue(forKey: identity)?.1.cancel(); phases.removeValue(forKey: identity)
        if let vault = cacheVault { try? vault.transaction { try vault.remove("full-message-translation-failure",durableKey(identity)) } }
        revision += 1
    }
    func fullReading(for result: ImmersionPresentation, identity: ImmersionRequestIdentity) -> FullReading? {
        guard !closed, identity == self.identity(messageID: identity.messageID, text: identity.text), let translated = result.translation else { return nil }
        _ = readingRevision
        return readings.cached(text: translated, language: identity.target)
    }
    func reading(for value: FullMessageTranslation) -> String? {
        _ = readingRevision
        return value.readingState?.status == .available ? value.practiceReading : nil
    }
    private func hasCurrentReadingState(_ value:FullMessageTranslation) -> Bool {
        let reading = value.practiceReading.map { FullReading(text:$0,provenance:.localTransliteration) }
        let failure:FullReading.Failure? = value.readingState?.failure == .outputLimit ? .outputLimit : value.readingState?.failure == .unresolved ? .unresolved : nil
        let expected = FullSentenceReadings.state(text:value.practiceText,language:value.practiceLanguage,reading:reading,failure:failure)
        return value.readingState == expected && (expected.status == .available || value.practiceReading == nil)
    }
    private func refreshReading(_ value:FullMessageTranslation,for identity:ImmersionRequestIdentity) async -> FullMessageTranslation {
        let preliminary = FullSentenceReadings.state(text:value.practiceText,language:value.practiceLanguage,reading:nil)
        let reading:FullReading?, failure:FullReading.Failure?
        if preliminary.canRetry {
            let resolved = await readings.resolveDetailed(text:value.practiceText,language:value.practiceLanguage)
            reading = resolved.value; failure = resolved.failure
        } else { reading = nil; failure = nil }
        let state = FullSentenceReadings.state(text:value.practiceText,language:value.practiceLanguage,reading:reading,failure:failure)
        let updated = value.withReading(state.status == .available ? reading?.text : nil,state:state)
        // A guide that fits its own cap can still overflow the complete encrypted
        // derivative. Drop only the guide, preserving translation/audio readiness.
        if state.status == .available,encodedTranslation(updated,identity:identity) == nil {
            return value.withReading(nil,state:.init(status:.unavailable,failure:.outputLimit,policy:FullSentenceReadings.statePolicy))
        }
        return updated
    }
    func readingRetryPending(for identity:ImmersionRequestIdentity) -> Bool { readingTasks[identity] != nil }
    @discardableResult func retryReading(_ identity:ImmersionRequestIdentity) -> Task<Void,Never>? {
        guard !closed,identity == self.identity(messageID:identity.messageID,text:identity.text),
              let value = translations[identity],value.readingState?.canRetry == true,readingTasks[identity] == nil else { return nil }
        let token = UUID()
        readings.removeResolved(text:value.practiceText,language:value.practiceLanguage)
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { if readingTasks[identity]?.0 == token { readingTasks.removeValue(forKey:identity); readingRevision += 1 } }
            let updated = await refreshReading(value,for:identity)
            guard !closed,!Task.isCancelled,identity == self.identity(messageID:identity.messageID,text:identity.text),
                  readingTasks[identity]?.0 == token else { return }
            saveTranslation(updated,identity:identity); remember(updated,for:identity); readingRevision += 1
        }
        readingTasks[identity] = (token,task); readingRevision += 1
        return task
    }
    func translatedMessage(for identity: ImmersionRequestIdentity) async -> FullMessageTranslation? {
        guard !closed, identity == self.identity(messageID: identity.messageID, text: identity.text), !Task.isCancelled else { return nil }
        if let saved = translations[identity] {
            lastOutcome = .init(result: saved.presentation, origin: .localFullContext, status: .ready,
                                localTranslationCalls: 0, fallbackStatus: nil, cacheHit: true, resolvedInputLanguage: saved.inputLanguage)
            return saved
        }
        let stored = savedTranslation(identity)
        if stored == nil {
            if phases[identity] == nil,let saved = savedFailure(identity) {
                phases[identity] = saved; touchResident(identity); return nil
            }
            // Visibility, foreground and history replay are not retry intents.
            // Keep a failed message actionable until the user explicitly retries it.
            if inFlight[identity] == nil,let phase = phases[identity],phase == .failed || phase == .timedOut { return nil }
        }
        let entry: (UUID, Task<FullMessageTranslation?, Never>)
        if let pending = inFlight[identity] { entry = pending }
        else {
            let token = UUID()
            // Cache-hit reading refresh has the same message-scoped lifetime as
            // model work: forget must cancel it before any derivative can commit.
            let task = Task<FullMessageTranslation?,Never> { @MainActor [weak self] in
                guard let self else { return nil }
                if let stored { return await restoreCachedTranslation(stored,for:identity) }
                return await translateMessage(identity)
            }
            entry = (token,task); inFlight[identity] = entry
        }
        // Request lifetime belongs to the conversation, not a disappearing lazy row.
        // A cancelled waiter must not cancel another visible row or autoplay.
        let value = await entry.1.value
            if inFlight[identity]?.0 == entry.0 { inFlight.removeValue(forKey: identity); trimMemoryCache() }
            guard !Task.isCancelled, !closed, identity == self.identity(messageID: identity.messageID, text: identity.text) else { return nil }
        return value
    }
    private func restoreCachedTranslation(_ stored:FullMessageTranslation,for identity:ImmersionRequestIdentity) async -> FullMessageTranslation? {
        guard !closed,!Task.isCancelled,identity == self.identity(messageID:identity.messageID,text:identity.text) else { return nil }
        let needsRefresh = !hasCurrentReadingState(stored)
        let saved = needsRefresh ? await refreshReading(stored,for:identity) : stored
        guard !closed,!Task.isCancelled,identity == self.identity(messageID:identity.messageID,text:identity.text) else { return nil }
        if needsRefresh { saveTranslation(saved,identity:identity) }
        remember(saved,for:identity); readingRevision += 1
        lastOutcome = .init(result:saved.presentation,origin:.localFullContext,status:.ready,
            localTranslationCalls:0,fallbackStatus:nil,cacheHit:true,resolvedInputLanguage:saved.inputLanguage)
        return saved
    }
    private func translateMessage(_ identity: ImmersionRequestIdentity) async -> FullMessageTranslation? {
        let active = epoch
        var readinessCalls = 0
        func valid() -> Bool { !closed && active == epoch && !Task.isCancelled && identity == self.identity(messageID: identity.messageID, text: identity.text) }
        func fail(_ phase: Phase, status: ImmersionStatus, calls: Int, input: String? = nil) -> FullMessageTranslation? {
            guard valid() else { return nil }
            phases[identity] = phase
            // A provider failure remains an explicit retry across eviction and
            // restart. Cancellation/model availability never becomes durable.
            if calls > 0 && (phase == .failed || phase == .timedOut) { saveFailure(phase,identity:identity) }
            touchResident(identity)
            lastOutcome = .init(result: nil, origin: .localFullContext, status: status, localTranslationCalls: calls,
                                fallbackStatus: nil, modelReadinessCalls: readinessCalls, resolvedInputLanguage: input)
            return nil
        }
        guard valid(), pair.valid else { return nil }
        phases[identity] = .translating; touchResident(identity); lastOutcome = nil
        guard !identity.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, identity.text.utf8.count <= FullMessageBudget.sourceBytes else { return fail(.failed,status:.invalidInput,calls:0) }
        // Classification supports direction. Short/unknown text never vetoes translation.
        let detected:String?
        if let selected = identity.inputLanguage { detected = selected }
        else { detected = try? await identify(identity.text) }
        guard valid() else { return nil }
        let supported = detected.flatMap { code in VipiLanguage.initial.contains(where: { $0.id == code }) ? code : nil }
        let input = supported ?? pair.source
        let from = input, to = input == pair.target ? pair.source : pair.target
        let requestedPair = TranslationPair(source: from,target: to); requiredPairs[identity] = requestedPair
        readinessCalls += 1
        let observed = await modelStatus(requestedPair)
        guard valid() else { return nil }
        availability = observed
        guard observed == .installed else { return fail(observed == .unsupported ? .unsupported : .needsDownload,status:.modelNotReady,calls:0,input:input) }
        var providerCalls = 0
        do {
            providerCalls += 1
            let actual = try await enqueue(identity.text,pair:requestedPair,epoch:active,timeout:fullTranslationTimeout)
            guard valid() else { return nil }
            guard !actual.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty, actual.utf8.count <= FullMessageBudget.recordBytes else { return fail(.failed,status:.invalidResult,calls:1,input:input) }
            let reversed = input == pair.target
            var meaning = reversed ? actual : identity.text
            if input != pair.source && !reversed {
                // A third-language original is not the user's native-language meaning.
                let meaningPair = TranslationPair(source: input, target: pair.source)
                requiredPairs[identity] = meaningPair; readinessCalls += 1
                let meaningAvailability = await modelStatus(meaningPair)
                guard valid() else { return nil }
                availability = meaningAvailability
                guard meaningAvailability == .installed else { return fail(meaningAvailability == .unsupported ? .unsupported : .needsDownload,status:.modelNotReady,calls:providerCalls,input:input) }
                providerCalls += 1
                meaning = try await enqueue(identity.text,pair:meaningPair,epoch:active,timeout:fullTranslationTimeout)
                guard valid() else { return nil }
                guard !meaning.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty, meaning.utf8.count <= FullMessageBudget.recordBytes else { return fail(.failed,status:.invalidResult,calls:providerCalls,input:input) }
            }
            let practice = reversed ? identity.text : actual
            let base = FullMessageTranslation(original:identity.text,practiceText:practice,meaningText:meaning,inputLanguage:input,
                practiceLanguage:pair.target,meaningLanguage:pair.source)
            let value = await refreshReading(base,for:identity)
            guard valid() else { return nil }
            guard encodedTranslation(value,identity:identity) != nil else { return fail(.failed,status:.invalidResult,calls:providerCalls,input:input) }
            readingRevision += 1
            saveTranslation(value,identity:identity)
            remember(value,for:identity)
            lastOutcome = .init(result:value.presentation,origin:.localFullContext,status:.ready,localTranslationCalls:providerCalls,
                fallbackStatus:nil,modelReadinessCalls:readinessCalls,resolvedInputLanguage:input)
            return value
        } catch is CancellationError { return nil }
        catch ProviderError.cancelled { return nil }
        catch ProviderError.modelNotReady { return fail(.needsDownload,status:.modelNotReady,calls:0,input:input) }
        catch ProviderError.unsupported { return fail(.unsupported,status:.modelNotReady,calls:0,input:input) }
        catch ProviderError.preparation { return fail(.failed,status:.error,calls:0,input:input) }
        catch ProviderError.timedOut { return fail(.timedOut,status:.error,calls:providerCalls,input:input) }
        catch { return fail(.failed,status:.error,calls:providerCalls,input:input) }
    }
    /// Newly loaded/sent/received messages translate even when their rows are
    /// outside the lazy viewport. One bounded feeder avoids model queue floods.
    @discardableResult func warm(_ messages: [(id:String,text:String)]) -> Task<Void,Never>? {
        guard !closed else { return nil }
        // Only the bounded, currently loaded viewport supplies raw text here.
        let unseen = messages.reversed().filter { translations[identity(messageID:$0.id,text:$0.text)] == nil && warmKnown.insert($0.id).inserted }
            .map { message in WarmWork(id:message.id,load:{message.text}) }
        warmQueue.insert(contentsOf:unseen,at:0); startWarming()
        return warmTask
    }
    func warmStored(id:String,load:@escaping @MainActor () -> String?) {
        guard !closed,warmKnown.insert(id).inserted else { return }
        warmQueue.append(.init(id:id,load:load)); startWarming()
    }
    private func startWarming() {
        guard warmTask == nil,!warmQueue.isEmpty else { return }
        let active = epoch
        warmTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { if epoch == active { warmTask = nil } }
            while !Task.isCancelled,!closed,epoch == active,!warmQueue.isEmpty {
                let next = warmQueue.removeFirst()
                if let text = next.load() { _ = await translatedMessage(for:identity(messageID:next.id,text:text)) }
                warmKnown.remove(next.id)
            }
        }
    }
    func prepareStoredMessage(id:String,text:String) async {
        guard !closed else { return }
        _ = await translatedMessage(for:identity(messageID:id,text:text))
    }
    private func enqueue(_ text: String, pair: TranslationPair, epoch active: UUID, timeout: Duration) async throws -> String {
        if let nativeTranslation {
            try Task.checkCancellation()
            let value = try await nativeTranslation(text,pair)
            try Task.checkCancellation()
            return value
        }
        guard !closed, active == epoch, pair.valid, pending.count < 128 else { throw ProviderError.preparation }
        let id = UUID()
        return try await withTaskCancellationHandler {
            let translated: String? = await withCheckedContinuation { continuation in
                guard !Task.isCancelled, !closed, active == epoch else { continuation.resume(returning:nil); return }
                replies[id] = continuation
                requestTimeouts[id] = timeout
                pending.append(.init(id:id,text:text,pair:pair,epoch:active)); next()
            }
            let timedOut = timedOutRequests.remove(id) != nil
            let failure = providerFailures.removeValue(forKey:id)
            try Task.checkCancellation()
            if timedOut { throw ProviderError.timedOut }
            if let failure { throw failure }
            guard let translated else { throw ProviderError.unavailable }
            return translated
        } onCancel: { Task { @MainActor [weak self] in self?.cancel(id) } }
    }
    private func next() {
        guard request == nil, !pending.isEmpty else { return }
        let active = pending.removeFirst(); request = active
        if let timeout = requestTimeouts[active.id] {
            deadlines[active.id] = Task { @MainActor [weak self] in
                do { try await Task.sleep(for:timeout) } catch { return }
                self?.cancel(active.id,timedOut:true)
            }
        }
    }
    private func cancel(_ id: UUID, timedOut: Bool = false) {
        if timedOut { timedOutRequests.insert(id) }
        requestTimeouts.removeValue(forKey:id)
        deadlines.removeValue(forKey:id)?.cancel(); replies.removeValue(forKey:id)?.resume(returning:nil)
        pending.removeAll { $0.id == id }; if request?.id == id { request = nil; next() }
    }
    func finish(_ active: Request, translation: String?, failure:ProviderError = .unavailable) async {
        guard !closed, active.epoch == epoch, active.id == request?.id else { return }
        requestTimeouts.removeValue(forKey:active.id)
        if translation == nil { providerFailures[active.id] = failure }
        deadlines.removeValue(forKey:active.id)?.cancel(); replies.removeValue(forKey:active.id)?.resume(returning:translation)
        request = nil; next()
    }
    func translateSwahili(_ active: Request) async {
        guard !closed, active.epoch == epoch, active.id == request?.id else { return }
        let key = active.pair.source + "-" + active.pair.target
        if swahili[key] == nil { swahili[key] = try? SwahiliTranslation(pair:active.pair) }
        guard let translator = swahili[key] else { await finish(active,translation:nil); return }
        await finish(active,translation:try? await translator.translate(active.text))
    }
    private func invalidateOutstanding() {
        warmTask?.cancel(); warmTask = nil; warmQueue.removeAll(); warmKnown.removeAll(); requestTimeouts.removeAll()
        for entry in inFlight.values { entry.1.cancel() }; inFlight.removeAll()
        for task in deadlines.values { task.cancel() }; deadlines.removeAll()
        for entry in readingTasks.values { entry.1.cancel() }; readingTasks.removeAll()
        epoch = UUID(); readings.removeAll(); readingRevision += 1; request = nil; pending.removeAll()
        let outstanding = Array(replies.values); replies.removeAll(); for reply in outstanding { reply.resume(returning:nil) }
        timedOutRequests.removeAll(); providerFailures.removeAll(); translations.removeAll(); residentOrder.removeAll(); residentCosts.removeAll(); visibleTranslations.removeAll(); phases.removeAll(); requiredPairs.removeAll()
    }
    func close() { cacheVault = nil; closed = true; invalidateOutstanding(); inputLanguages.removeAll(); swahili.removeAll(); lastOutcome = nil; revision += 1 }
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
                    let readiness = await LanguagePreparation.nativeStatus(request.pair)
                    guard readiness == .installed else {
                        await immersion.finish(request,translation:nil,failure:readiness == .unsupported ? .unsupported:.modelNotReady); return
                    }
                    var attemptedTranslation = false
                    do {
                        try await session.prepareTranslation()
                        try Task.checkCancellation()
                        attemptedTranslation = true
                        let result = try await session.translate(request.text)
                        await immersion.finish(request,translation:result.targetText)
                    } catch is CancellationError {
                        await immersion.finish(request,translation:nil,failure:.cancelled)
                    } catch {
                        await immersion.finish(request,translation:nil,failure:attemptedTranslation ? .unavailable:.preparation)
                    }
                }
        }
    }
}


/// Sent, received and Bot rows share the same full local translation path.
struct ConversationImmersionText: View {
    let text: String
    let id: String
    let immersion: ConversationImmersion
    let speech: SpeechPlayback
    let paused: Bool
    let metadata: AnyView
    let onVoiceHelp: () -> Void
    var onTranslationSetup: ((TranslationPair) -> Void)? = nil
    var onReport: (() -> Void)? = nil
    var playback: ChatAutoplay? = nil
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var frame = CGRect.zero
    @State private var retainedIdentity: ImmersionRequestIdentity?
    private func retainMountedTranslation() {
        guard retainedIdentity != identity else { return }
        if let old = retainedIdentity { immersion.releaseVisible(old) }
        retainedIdentity = identity; immersion.retainVisible(identity)
    }
    private var identity: ImmersionRequestIdentity { immersion.identity(messageID:id,text:text) }
    private struct RunKey: Equatable { let identity: ImmersionRequestIdentity; let revision: Int; let foreground: Bool }
    private func pendingActivation(_ start: Bool) -> Bool {
        switch immersion.phase(for:identity) {
        case .needsDownload,.unsupported:
            onTranslationSetup?(immersion.requiredPair(for:identity)); return true
        case .failed,.timedOut:
            immersion.retry(identity); return false
        default: return false
        }
    }
    private func registerPending() {
        guard immersion.translation(for:identity) == nil else { return }
        state.chatReading.register(.init(identity:identity,frame:frame,activate:pendingActivation))
    }
    private var failureText: String {
        switch immersion.phase(for:identity) {
        case .needsDownload: String(localized:"Translation needs a language download.")
        case .unsupported: String(localized:"Translation isn’t supported for this language pair on this device.")
        case .timedOut: String(localized:"Translation took too long. Try again.")
        default: String(localized:"Translation failed. Tap to retry.")
        }
    }
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            if let value = immersion.translation(for:identity) {
                ImmersionBubble(result:value.presentation,speech:speech,sourceLanguage:value.meaningLanguage,
                    targetLanguage:value.practiceLanguage,messageID:id,interactionPaused:paused,
                    fullReading:immersion.reading(for:value),
                    readingUnavailable:value.readingState?.status == .unavailable,
                    readingCanRetry:value.readingState?.canRetry == true,
                    readingRetryPending:immersion.readingRetryPending(for:identity),
                    onReadingRetry:{ _ = immersion.retryReading(identity) },embedded:true,metadata:metadata,
                    onVoiceHelp:onVoiceHelp,originalMessage:value.original,inputLanguage:value.inputLanguage,
                    onReport:onReport,reading:state.chatReading,identity:identity)
                if let failure = playback?.failure(for:id) {
                    Button { state.chatReading.activate(identity) } label: {
                        Text(failure).font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            .fixedSize(horizontal:false,vertical:true).frame(minHeight:44,alignment:.leading).contentShape(Rectangle())
                    }.buttonStyle(.plain).padding(.horizontal,15).accessibilityIdentifier("message-playback-retry")
                }
            } else {
                VStack(alignment:.leading,spacing:6) {
                    Text(text).font(.body).fixedSize(horizontal:false,vertical:true)
                    if immersion.phase(for:identity) == .translating {
                        HStack(spacing:7) { ProgressView(); Text("Translating…").font(.subheadline) }
                            .foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("message-translation-pending")
                    } else {
                        Button { state.chatReading.activate(identity) } label: {
                            Text(failureText).font(.subheadline).fixedSize(horizontal:false,vertical:true)
                                .frame(minHeight:44,alignment:.leading).contentShape(Rectangle())
                        }.buttonStyle(.plain).foregroundStyle(VipiDesign.secondary)
                            .accessibilityIdentifier("message-translation-retry")
                    }
                    metadata
                }.padding(.horizontal,15).padding(.vertical,12)
            }
        }
        .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame = $0; registerPending() }
        .onAppear { retainMountedTranslation(); registerPending() }
        .task(id:RunKey(identity:identity,revision:immersion.revision,foreground:scenePhase == .active)) {
            guard scenePhase == .active else { return }
            retainMountedTranslation()
            _ = await immersion.translatedMessage(for:identity)
        }
        .onChange(of:identity) { old,_ in
            retainMountedTranslation()
            state.chatReading.remove(old)
        }
        .onDisappear {
            if let retainedIdentity { immersion.releaseVisible(retainedIdentity) }
            retainedIdentity = nil
            state.chatReading.remove(identity)
        }
        .onChange(of:scenePhase) { _,phase in if phase != .active { state.chatReading.cancelInteractions();  } }
    }
}
