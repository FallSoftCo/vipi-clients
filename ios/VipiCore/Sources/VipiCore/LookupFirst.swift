import Foundation

public enum ImmersionRequestIntent: Sendable, Equatable { case automaticImmersion, fullTranslation }
public struct LookupFirstRequest: Sendable {
    public let text: String, source: String, target: String
    public let inputLanguage: String?
    public let intent: ImmersionRequestIntent
    public let allowModelTranslation: Bool
    public init(text: String, source: String, target: String, inputLanguage: String? = nil,
                intent: ImmersionRequestIntent = .automaticImmersion, allowModelTranslation: Bool = true) {
        self.text = text; self.source = source; self.target = target; self.inputLanguage = inputLanguage
        self.intent = intent
        self.allowModelTranslation = allowModelTranslation
    }
}
public enum ImmersionOrigin: String, Sendable { case lookupReference, sourceReferencePartial, localFullContext }
public enum ImmersionStatus: String, Sendable {
    case ready, partial, invalidInput, invalidLanguage, modelNotReady, noLocalMatch, invalidResult, stale, error
}
public struct LookupFirstOutcome: Sendable {
    public let result: ImmersionPresentation?
    public let origin: ImmersionOrigin?
    public let status: ImmersionStatus
    public let localTranslationCalls: Int
    public let fallbackStatus: ImmersionStatus?
    public let cacheHit: Bool
    public let modelReadinessCalls: Int
    public let alignmentCalls: Int
    public let sourceConstraints: SourceLookupConstraints?
    public init(result: ImmersionPresentation?, origin: ImmersionOrigin?, status: ImmersionStatus,
                localTranslationCalls: Int, fallbackStatus: ImmersionStatus?, cacheHit: Bool = false,
                modelReadinessCalls: Int = 0, alignmentCalls: Int = 0,
                sourceConstraints: SourceLookupConstraints? = nil) {
        self.result = result; self.origin = origin; self.status = status
        self.localTranslationCalls = localTranslationCalls; self.fallbackStatus = fallbackStatus; self.cacheHit = cacheHit
        self.modelReadinessCalls = modelReadinessCalls; self.alignmentCalls = alignmentCalls
        self.sourceConstraints = sourceConstraints
    }
    /// A deterministic rejection of an actual local provider response can be
    /// reused for automatic presentation. Source/metadata failures and transient
    /// provider errors are deliberately excluded.
    public var isRejectedLocalTranslation: Bool {
        result == nil && status == .invalidResult && origin == .localFullContext && localTranslationCalls > 0
    }
    public func cachedInvocation() -> Self {
        .init(result: result, origin: origin, status: status, localTranslationCalls: 0,
              fallbackStatus: fallbackStatus, cacheHit: true, sourceConstraints: sourceConstraints)
    }
}

/// Routing, not a new matcher. Native readiness is async and direction-specific;
/// it remains MISS-only and never performs model preparation or lexical expansion.
public enum LookupFirst {
    @MainActor public static func resolve(
        _ request: LookupFirstRequest, valid: () -> Bool,
        reference: (String, String, String) async throws -> String?,
        identify: (String) async throws -> String?,
        modelsReady: (String, String) async throws -> Bool,
        translate: (String, String, String) async throws -> String,
        align: (String, String, SourceLookupConstraints?) async throws -> ImmersionResult,
        partialReference: (String, String, String) async throws -> PartialImmersionResult? = { _, _, _ in nil },
        sourceEvidenceIdentity: String? = nil,
        sourceEvidence: ((String, String, String) async throws -> SourceLookupEvidence)? = nil,
        onPartial: (PartialImmersionResult) -> Void = { _ in }
    ) async throws -> LookupFirstOutcome {
        var calls = 0
        var readinessCalls = 0, alignmentCalls = 0
        var origin: ImmersionOrigin?
        var partial: PartialImmersionResult?
        var constraints: SourceLookupConstraints?
        func stop(_ status: ImmersionStatus) -> LookupFirstOutcome {
            if let partial, valid(), status != .stale {
                return .init(result: .partial(partial), origin: .sourceReferencePartial, status: .partial,
                             localTranslationCalls: calls, fallbackStatus: status,
                             modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls, sourceConstraints: status == .stale ? nil : constraints)
            }
            return .init(result: nil, origin: origin, status: status, localTranslationCalls: calls, fallbackStatus: nil,
                         modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls, sourceConstraints: status == .stale ? nil : constraints)
        }
        guard valid() else { return stop(.stale) }
        let text = request.text, source = request.source, target = request.target, input = request.inputLanguage
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf16.count <= 16_384,
              source != target, input == nil || input == source || input == target else { return stop(.invalidInput) }
        do {
            let forward = input != target ? try await reference(text, source, target) : nil
            guard valid() else { return stop(.stale) }
            let reverse = forward == nil && input != source ? try await reference(text, target, source) : nil
            guard valid() else { return stop(.stale) }
            let sourcePartial = forward == nil && reverse == nil && input != target
                ? try await partialReference(text, source, target) : nil
            guard valid() else { return stop(.stale) }
            let detected: String?
            if forward != nil { detected = source }
            else if reverse != nil { detected = target }
            else if let input { detected = input }
            else { detected = try await identify(text) }
            guard valid() else { return stop(.stale) }
            guard detected == source || detected == target else { return stop(.invalidLanguage) }
            if detected == source {
                // Recognition is independent of display selection and also runs
                // on a forward whole-reference hit. Never run/apply it in reverse.
                var catalogPartial: PartialImmersionResult?
                if let sourceEvidence {
                    let evidence = try await sourceEvidence(text, source, target)
                    guard valid() else { return stop(.stale) }
                    guard let identity = sourceEvidenceIdentity,
                          let checked = evidence.validated(text: text, sourceLanguage: source,
                              targetLanguage: target, identity: identity) else { return stop(.invalidResult) }
                    constraints = checked
                    if forward == nil { catalogPartial = evidence.partial }
                }
                if let candidate = sourcePartial {
                    guard candidate.original.utf8.elementsEqual(text.utf8),
                          SourceReferencePresentation.validPartial(candidate, target: target) else { return stop(.invalidResult) }
                    if let constraints { partial = constraints.filterPartial(candidate) }
                    else { partial = candidate }
                }
                // A legacy face blocked by recognition must not hide an
                // independently approved source head or force unnecessary MT.
                if partial == nil, forward == nil, let catalogPartial {
                    if let constraints { partial = constraints.filterPartial(catalogPartial) }
                }
                if let partial { onPartial(partial) }
            }
            guard valid() else { return stop(.stale) }
            if let partial, !partial.spans.isEmpty, request.intent == .automaticImmersion {
                return .init(result: .partial(partial), origin: .sourceReferencePartial, status: .partial,
                             localTranslationCalls: 0, fallbackStatus: nil, sourceConstraints: constraints)
            }
            let reversed = detected == target
            let known = forward ?? reverse
            let from = reversed ? target : source, to = reversed ? source : target
            // A missing reviewed mapping is ordinary original-language text.
            // This guard precedes readiness checks and any inference provider.
            if known == nil && !request.allowModelTranslation { return stop(.noLocalMatch) }
            if known == nil {
                readinessCalls += 1
                let ready = try await modelsReady(from, to)
                guard valid() else { return stop(.stale) }
                guard ready else { return stop(.modelNotReady) }
            }
            guard valid() else { return stop(.stale) }
            origin = known != nil ? .lookupReference : .localFullContext
            let translated: String
            if let known { translated = known }
            else { calls += 1; translated = try await translate(text, from, to) }
            guard valid() else { return stop(.stale) }
            guard !translated.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  translated.utf16.count <= 32_768,
                  TranslationIntegrity.preservesIdentifiers(original: text, translation: translated) else { return stop(.invalidResult) }
            let original = reversed ? translated : text
            let targetText = reversed ? text : translated
            if let partial {
                return .init(result: .partial(partial.withCompleteTranslation(targetText)), origin: .sourceReferencePartial,
                             status: .partial, localTranslationCalls: calls, fallbackStatus: .ready,
                             modelReadinessCalls: readinessCalls, alignmentCalls: 0, sourceConstraints: constraints)
            }
            alignmentCalls += 1
            let aligned = try await align(original, targetText, constraints)
            guard valid() else { return stop(.stale) }
            guard aligned.original.utf8.elementsEqual(original.utf8), aligned.translation.utf8.elementsEqual(targetText.utf8),
                  anchored(aligned) else { return stop(.invalidResult) }
            let result = constraints?.filterLegacy(aligned) ?? aligned
            return .init(result: .complete(result), origin: origin, status: .ready,
                         localTranslationCalls: calls, fallbackStatus: nil,
                         modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls, sourceConstraints: constraints)
        } catch is CancellationError { throw CancellationError() }
        catch { return stop(valid() ? .error : .stale) }
    }

    private static func anchored(_ result: ImmersionResult) -> Bool {
        let source = result.original as NSString, target = result.translation as NSString
        var end = 0
        for span in result.spans {
            guard span.range.location >= end, span.range.location <= source.length,
                  span.range.length > 0, span.range.length <= source.length-span.range.location,
                  span.targetRange.location >= 0, span.targetRange.location <= target.length,
                  span.targetRange.length > 0, span.targetRange.length <= target.length-span.targetRange.location,
                  Range(span.range, in: result.original) != nil, Range(span.targetRange, in: result.translation) != nil,
                  source.substring(with: span.range) == span.original,
                  target.substring(with: span.targetRange) == span.translated else { return false }
            end = NSMaxRange(span.range)
        }
        return true
    }
}
