import Foundation

/// One native whole-message tokenization supplies BOTH the denominator and
/// every sentence's cost. This does not tokenize, normalize or infer mappings.
public struct NativeSourceTokenBasis: Sendable {
    private let original: String
    private let words: [NSRange]
    public var count: Int { words.count }
    public init?(original: String, wordRanges: [NSRange]) {
        guard original.utf16.count <= 16_384, wordRanges.count <= 16_384 else { return nil }
        var end = 0
        for word in wordRanges {
            guard word.location >= end, word.location <= original.utf16.count,
                  word.length > 0, word.length <= original.utf16.count-word.location,
                  Range(word, in: original) != nil else { return nil }
            end = NSMaxRange(word)
        }
        self.original = original; words = wordRanges
    }
    public func cost(for unit: NSRange) -> Int? {
        guard unit.location >= 0, unit.location <= original.utf16.count,
              unit.length > 0, unit.length <= original.utf16.count-unit.location,
              Range(unit, in: original) != nil else { return nil }
        let touched = words.filter { NSIntersectionRange($0, unit).length > 0 }
        guard !touched.isEmpty, touched.allSatisfy({ NSIntersectionRange($0, unit) == $0 }) else { return nil }
        return touched.count
    }
    /// Word/phrase candidates must cover exact native word edges. Sentence
    /// references use `cost(for:)` because they also include punctuation.
    public func exactWordCost(for unit: NSRange) -> Int? {
        guard unit.location >= 0, unit.location <= original.utf16.count,
              unit.length > 0, unit.length <= original.utf16.count-unit.location,
              Range(unit, in: original) != nil else { return nil }
        func lowerBound(_ offset: Int) -> Int {
            var low = 0, high = words.count
            while low < high {
                let middle = low + (high-low)/2
                if words[middle].location < offset { low = middle+1 } else { high = middle }
            }
            return low
        }
        let first = lowerBound(unit.location), after = lowerBound(NSMaxRange(unit))
        guard first < after, first < words.count, words[first].location == unit.location,
              NSMaxRange(words[after-1]) == NSMaxRange(unit) else { return nil }
        return after-first
    }
}

public struct SourceReferenceUnit: Sendable, Equatable {
    public let range: NSRange
    public let original: String
    public let translated: String
    public let reading: String?
    public let referenceID: String
    public let catalogSHA256: String
    public let nativeSourceTokens: Int
    /// Present only when the supplying catalog has a qualified stable concept
    /// identity. Sentence references and legacy aligned spans do not infer one.
    public let conceptID: String?
    /// Explicit catalog proof only; legacy/aligned text never infers an ID.
    public let outputID: String?
    /// Only a verified reviewed frame can supply this stable exposure identity.
    public let reviewedFrameIdentity: ReviewedFrameIdentity?

    public init(range: NSRange, original: String, translated: String, reading: String?,
                referenceID: String, catalogSHA256: String, nativeSourceTokens: Int,
                conceptID: String? = nil, outputID: String? = nil,
                reviewedFrameIdentity: ReviewedFrameIdentity? = nil) {
        self.range = range; self.original = original; self.translated = translated
        self.reading = reading; self.referenceID = referenceID; self.catalogSHA256 = catalogSHA256
        self.nativeSourceTokens = nativeSourceTokens
        self.conceptID = conceptID; self.outputID = outputID; self.reviewedFrameIdentity = reviewedFrameIdentity
    }
}

/// Each targetRange indexes its corresponding reference.translated, NEVER a
/// fabricated/full-message translation, even after fullTranslation is supplied.
public struct PartialImmersionResult: Sendable, Equatable {
    public let original: String
    public let spans: [ImmersionSpan]
    public let references: [SourceReferenceUnit]
    public let nativeSourceTokenCount: Int
    public let targetLanguage: String
    public let completeTranslation: String?

    init(original: String, spans: [ImmersionSpan], references: [SourceReferenceUnit],
         nativeSourceTokenCount: Int, targetLanguage: String, completeTranslation: String? = nil) {
        self.original = original; self.spans = spans; self.references = references
        self.nativeSourceTokenCount = nativeSourceTokenCount
        self.targetLanguage = targetLanguage
        self.completeTranslation = completeTranslation
    }

    public func withCompleteTranslation(_ actual: String) -> Self {
        .init(original: original, spans: spans, references: references,
              nativeSourceTokenCount: nativeSourceTokenCount, targetLanguage: targetLanguage, completeTranslation: actual)
    }
}

public enum ImmersionSpeechMode: Sendable { case original, immersed, fullTarget }

/// Native enum adapter: Swift cannot use a stored nonoptional translation as an
/// optional protocol witness. The existing complete DTO stays source-compatible.
public enum ImmersionPresentation: Sendable, Equatable {
    case complete(ImmersionResult)
    case partial(PartialImmersionResult)

    public var original: String {
        switch self { case .complete(let value): value.original; case .partial(let value): value.original }
    }
    public var translation: String? {
        switch self { case .complete(let value): value.translation; case .partial(let value): value.completeTranslation }
    }
    public var spans: [ImmersionSpan] {
        switch self { case .complete(let value): value.spans; case .partial(let value): value.spans }
    }
    public var completeResult: ImmersionResult? {
        if case .complete(let value) = self { return value }; return nil
    }

    /// Full-target speech alone needs a real full translation. Original and
    /// visible-span speech do not require a Translation model; the UI retains
    /// its separate ordinary voice-readiness controls.
    public func speech(mode: ImmersionSpeechMode, source: String, target: String,
                       revealed: Set<Int> = []) -> [SpeechSpan]? {
        switch mode {
        case .original: return [.init(text: original, language: source)]
        case .immersed: return speech(source: source, target: target, revealed: revealed)
        case .fullTarget:
            guard let translation else { return nil }
            return [.init(text: translation, language: target)]
        }
    }

    /// Low-level visible-span composition; never fabricates a full translation.
    public func speech(source: String, target: String, revealed: Set<Int> = []) -> [SpeechSpan] {
        if case .complete(let value) = self { return value.speech(source: source, target: target, revealed: revealed) }
        var output: [SpeechSpan] = []
        let text = original as NSString
        var cursor = 0
        for span in spans {
            if cursor < span.range.location {
                output.append(.init(text: text.substring(with: NSRange(location: cursor, length: span.range.location-cursor)), language: source))
            }
            let showingOriginal = revealed.contains(span.id)
            output.append(.init(text: showingOriginal ? span.original : span.translated,
                                language: showingOriginal ? source : target))
            cursor = NSMaxRange(span.range)
        }
        if cursor < text.length { output.append(.init(text: text.substring(from: cursor), language: source)) }
        return output
    }
}

/// Independently qualified exact source units enter this factory. Structural
/// validation does not approve new meanings. Legacy context/frame/dictionary
/// candidates still require their existing target witness.
public enum SourceReferencePresentation {
    /// Revalidate callback shape, including the reference-local target basis.
    /// This structural proof is NOT independent meaning/catalog attestation.
    public static func validPartial(_ value: PartialImmersionResult, target: String) -> Bool {
        guard value.targetLanguage == target, value.completeTranslation == nil, value.spans.count == value.references.count,
              let checked = create(original: value.original, target: target, units: value.references,
                  density: 1, nativeSourceTokenCount: value.nativeSourceTokenCount) else { return false }
        return checked.spans == value.spans && checked.references == value.references
    }
    public static func create(original: String, target: String, units: [SourceReferenceUnit],
                              density: Double, nativeSourceTokenCount: Int) -> PartialImmersionResult? {
        guard !original.isEmpty, original.utf16.count <= 16_384, !units.isEmpty, units.count <= 128,
              density.isFinite, density > 0, (1...16_384).contains(nativeSourceTokenCount) else { return nil }
        let text = original as NSString
        var previous = 0
        for unit in units {
            guard unit.range.location >= previous, unit.range.location <= text.length,
                  unit.range.length > 0, unit.range.length <= text.length-unit.range.location,
                  Range(unit.range, in: original) != nil,
                  text.substring(with: unit.range) == unit.original, unit.original.utf16.count <= 128,
                  !unit.translated.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  unit.translated.utf16.count <= 128,
                  (1...128).contains(unit.nativeSourceTokens),
                  !unit.referenceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  unit.catalogSHA256.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil,
                  TranslationIntegrity.preservesIdentifiers(original: unit.original, translation: unit.translated) else { return nil }
            previous = NSMaxRange(unit.range)
        }
        guard units.reduce(0, { $0 + $1.nativeSourceTokens }) <= nativeSourceTokenCount else { return nil }
        // Private target coordinate basis for existing matcher validation and
        // selection only. It is NEVER a returned full-message translation.
        let basis = units.map(\.translated).joined(separator: "\n")
        guard basis.utf16.count <= 32_768 else { return nil }
        var offset = 0
        let entries = units.map { unit -> VocabularyEntry in
            let start = offset; offset += unit.translated.utf16.count + 1
            return .init(source: unit.original, targets: [unit.translated],
                romanizations: unit.reading.map { [unit.translated: [$0]] } ?? [:],
                sourceScope: .init(original: original, start: unit.range.location, end: NSMaxRange(unit.range)),
                targetScope: .init(translation: basis, start: start, end: start + unit.translated.utf16.count))
        }
        let selected = ImmersionEngine().align(original: original, translation: basis, entries: entries,
            density: density, targetLanguage: target, sourceTokenCount: nativeSourceTokenCount,
            sourceUnitTokenCounts: Dictionary(uniqueKeysWithValues: units.map { ($0.range, $0.nativeSourceTokens) })).spans
        guard !selected.isEmpty else { return nil }
        let proofs = selected.compactMap { span in units.first { $0.range == span.range } }
        guard proofs.count == selected.count else { return nil }
        return .init(original: original, spans: selected.map {
            .init(range: $0.range, original: $0.original, translated: $0.translated,
                  targetRange: .init(location: 0, length: $0.translated.utf16.count), romanization: $0.romanization)
        }, references: proofs, nativeSourceTokenCount: nativeSourceTokenCount, targetLanguage: target)
    }
}
