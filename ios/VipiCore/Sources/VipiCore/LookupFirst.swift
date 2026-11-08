import Foundation

public enum ImmersionRequestIntent: Sendable, Equatable { case automaticImmersion, fullTranslation }
public struct LookupFirstRequest: Sendable {
    public let text: String, source: String, target: String
    public let inputLanguage: String?
    public let intent: ImmersionRequestIntent
    public init(text: String, source: String, target: String, inputLanguage: String? = nil,
                intent: ImmersionRequestIntent = .automaticImmersion) {
        self.text = text; self.source = source; self.target = target; self.inputLanguage = inputLanguage
        self.intent = intent
    }
}
public enum ImmersionOrigin: String, Sendable { case lookupReference, sourceReferencePartial, localFullContext }
public enum ImmersionStatus: String, Sendable {
    case ready, partial, invalidInput, invalidLanguage, modelNotReady, invalidResult, stale, error
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
    public init(result: ImmersionPresentation?, origin: ImmersionOrigin?, status: ImmersionStatus,
                localTranslationCalls: Int, fallbackStatus: ImmersionStatus?, cacheHit: Bool = false,
                modelReadinessCalls: Int = 0, alignmentCalls: Int = 0) {
        self.result = result; self.origin = origin; self.status = status
        self.localTranslationCalls = localTranslationCalls; self.fallbackStatus = fallbackStatus; self.cacheHit = cacheHit
        self.modelReadinessCalls = modelReadinessCalls; self.alignmentCalls = alignmentCalls
    }
    public func cachedInvocation() -> Self {
        .init(result: result, origin: origin, status: status, localTranslationCalls: 0,
              fallbackStatus: fallbackStatus, cacheHit: true)
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
        align: (String, String) async throws -> ImmersionResult,
        partialReference: (String, String, String) async throws -> PartialImmersionResult? = { _, _, _ in nil },
        onPartial: (PartialImmersionResult) -> Void = { _ in }
    ) async throws -> LookupFirstOutcome {
        var calls = 0
        var readinessCalls = 0, alignmentCalls = 0
        var origin: ImmersionOrigin?
        var partial: PartialImmersionResult?
        func stop(_ status: ImmersionStatus) -> LookupFirstOutcome {
            if let partial, valid(), status != .stale {
                return .init(result: .partial(partial), origin: .sourceReferencePartial, status: .partial,
                             localTranslationCalls: calls, fallbackStatus: status,
                             modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls)
            }
            return .init(result: nil, origin: origin, status: status, localTranslationCalls: calls, fallbackStatus: nil,
                         modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls)
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
            if detected == source, let sourcePartial {
                guard sourcePartial.original == text,
                      SourceReferencePresentation.validPartial(sourcePartial, target: target) else { return stop(.invalidResult) }
                partial = sourcePartial; onPartial(sourcePartial)
            }
            guard valid() else { return stop(.stale) }
            if let partial, !partial.spans.isEmpty, request.intent == .automaticImmersion {
                return .init(result: .partial(partial), origin: .sourceReferencePartial, status: .partial,
                             localTranslationCalls: 0, fallbackStatus: nil)
            }
            let reversed = detected == target
            let known = forward ?? reverse
            let from = reversed ? target : source, to = reversed ? source : target
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
                             modelReadinessCalls: readinessCalls, alignmentCalls: 0)
            }
            alignmentCalls += 1
            let result = try await align(original, targetText)
            guard valid() else { return stop(.stale) }
            guard result.original == original, result.translation == targetText, anchored(result) else { return stop(.invalidResult) }
            return .init(result: .complete(result), origin: origin, status: .ready,
                         localTranslationCalls: calls, fallbackStatus: nil,
                         modelReadinessCalls: readinessCalls, alignmentCalls: alignmentCalls)
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
