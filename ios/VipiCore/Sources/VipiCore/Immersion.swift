import Foundation

/// Entries contain surface forms, not context-free substitutions. A candidate
/// must also occur unambiguously in the translation of this exact message.
public struct VocabularyEntry: Codable, Sendable, Equatable {
    public let source: String
    public let targets: [String]
    public let romanizations: [String: [String]]
    public init(source: String, targets: [String], romanizations: [String: [String]] = [:]) {
        self.source = source; self.targets = targets; self.romanizations = romanizations
    }
    private enum CodingKeys: String, CodingKey { case source, targets, romanizations }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        source = try values.decode(String.self, forKey: .source)
        targets = try values.decode([String].self, forKey: .targets)
        romanizations = try values.decodeIfPresent([String: [String]].self, forKey: .romanizations) ?? [:]
    }
}

public struct ImmersionSpan: Sendable, Equatable, Identifiable {
    public let range: NSRange
    public let original: String
    public let translated: String
    public let targetRange: NSRange
    public let romanization: String?
    public var id: Int { range.location }
    public var displayedTarget: String { romanization ?? translated }
}

public struct SpeechSpan: Sendable, Equatable {
    public let text: String
    public let language: String
    public init(text: String, language: String) { self.text = text; self.language = language }
}

public struct ImmersionResult: Sendable, Equatable {
    public let original: String
    public let translation: String
    public let spans: [ImmersionSpan]

    public func speech(source: String, target: String, revealed: Set<Int> = []) -> [SpeechSpan] {
        var result: [SpeechSpan] = []
        let ns = original as NSString
        var cursor = 0
        for span in spans {
            if span.range.location > cursor {
                result.append(.init(text: ns.substring(with: NSRange(location: cursor, length: span.range.location - cursor)), language: source))
            }
            let showOriginal = revealed.contains(span.id)
            result.append(.init(text: showOriginal ? span.original : span.translated, language: showOriginal ? source : target))
            cursor = NSMaxRange(span.range)
        }
        if cursor < ns.length { result.append(.init(text: ns.substring(from: cursor), language: source)) }
        return result
    }
}

public struct ImmersionEngine: Sendable {
    public init() {}

    public func align(original: String, translation: String, entries: [VocabularyEntry], density: Double, targetLanguage: String? = nil) -> ImmersionResult {
        let empty = ImmersionResult(original: original, translation: translation, spans: [])
        guard !original.isEmpty, !translation.isEmpty, density.isFinite, density > 0,
              original.utf16.count <= 16_384, translation.utf16.count <= 32_768 else { return empty }
        let protected = matches(#"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[\p{L}]{2,}|```[\s\S]*?```|`[^`]*`|[@#][\p{L}\p{N}_]+|\p{N}+(?:[.,:]\p{N}+)*"#, in: original)
        var candidates: [(span: ImmersionSpan, targetRange: NSRange)] = []
        for entry in entries where !entry.source.isEmpty && entry.source.utf16.count <= 128 {
            let sourceMatches = occurrences(entry.source, in: original)
            guard sourceMatches.count == 1, let range = sourceMatches.first,
                  !protected.contains(where: { NSIntersectionRange($0, range).length > 0 }) else { continue }
            // More than one viable sense, or repeated target occurrences, abstains.
            let targetMatches = Set(Set(entry.targets).flatMap { target -> [NSRange] in
                guard !target.isEmpty, target.utf16.count <= 128 else { return [] }
                return occurrences(target, in: translation)
            })
            guard targetMatches.count == 1, let targetRange = targetMatches.first else { continue }
            let targetSurface = (translation as NSString).substring(with: targetRange)
            let sourceSurface = (original as NSString).substring(with: range)
            guard sourceSurface.caseInsensitiveCompare(targetSurface) != .orderedSame else { continue }
            let needsReading = ["ar", "zh", "ja", "ko"].contains(targetLanguage?.components(separatedBy: "-")[0] ?? "")
            let readings = Set(entry.romanizations.filter { $0.key.caseInsensitiveCompare(targetSurface) == .orderedSame }.values.flatMap { $0 })
            let reading = readings.count == 1 ? readings.first : nil
            if needsReading {
                guard let reading, !reading.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      reading.utf16.count <= 256, reading.range(of: "^[A-Za-z][A-Za-z '’-]*$", options: .regularExpression) != nil else { continue }
            }
            candidates.append((ImmersionSpan(range: range, original: sourceSurface, translated: targetSurface,
                targetRange: targetRange, romanization: needsReading ? reading : nil), targetRange))
        }
        // A translated token cannot be claimed by two disjoint source spans.
        let unambiguous = candidates.filter { candidate in
            !candidates.contains { other in
                (other.span.range == candidate.span.range && (other.targetRange != candidate.targetRange || other.span.romanization != candidate.span.romanization)) ||
                (other.span.range != candidate.span.range &&
                NSIntersectionRange(other.span.range, candidate.span.range).length == 0 &&
                NSIntersectionRange(other.targetRange, candidate.targetRange).length > 0)
            }
        }.sorted { a, b in
            a.span.range.length == b.span.range.length ? a.span.range.location < b.span.range.location : a.span.range.length > b.span.range.length
        }
        let wordCount = matches(#"[\p{L}\p{M}]+"#, in: original).count
        let budget = max(1, Int(Double(wordCount) * min(density, 1)))
        var selected: [ImmersionSpan] = []
        var usedWords = 0
        for candidate in unambiguous {
            let count = max(1, matches(#"[\p{L}\p{M}]+"#, in: candidate.span.original).count)
            guard usedWords + count <= budget,
                  !selected.contains(where: { NSIntersectionRange($0.range, candidate.span.range).length > 0 }) else { continue }
            selected.append(candidate.span)
            usedWords += count
        }
        return ImmersionResult(original: original, translation: translation, spans: selected.sorted { $0.range.location < $1.range.location })
    }

    private func occurrences(_ phrase: String, in text: String) -> [NSRange] {
        let escaped = NSRegularExpression.escapedPattern(for: phrase)
        return matches("(?<![\\p{L}\\p{M}\\p{N}_])" + escaped + "(?![\\p{L}\\p{M}\\p{N}_])", in: text, options: [.caseInsensitive])
    }
    private func matches(_ pattern: String, in text: String, options: NSRegularExpression.Options = []) -> [NSRange] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return [] }
        return regex.matches(in: text, range: NSRange(location: 0, length: text.utf16.count)).map(\.range)
    }
}
