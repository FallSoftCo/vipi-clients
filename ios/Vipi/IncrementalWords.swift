import Foundation
import NaturalLanguage
import VipiCore

/// Segmentation selects one source word, never an invented alignment with a
/// full translation. There is deliberately no phrase dictionary or word quota.
enum IncrementalWords {
    struct Token {
        let range: NSRange
        let text: String
        let key: String
        let preferred: Bool
    }
    static func normalized(_ word: String, language: String) -> String {
        word.precomposedStringWithCanonicalMapping.lowercased(with: Locale(identifier: language))
    }
    static func tokens(_ text: String, language: String) -> [Token] {
        let whole = NSRange(text.startIndex..<text.endIndex, in: text)
        var protected: [NSRange] = []
        if let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) {
            protected += detector.matches(in: text, range: whole).map(\.range)
        }
        if let literals = try? NSRegularExpression(pattern: #"(?s)```.*?```|`[^`]*`|(?:[@#][\p{L}\p{N}_]+)|\S*\d\S*"#) {
            protected += literals.matches(in: text, range: whole).map(\.range)
        }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        tokenizer.setLanguage(NLLanguage(rawValue: language))
        let tagger = NLTagger(tagSchemes: [.lexicalClass, .nameType])
        tagger.string = text
        tagger.setLanguage(NLLanguage(rawValue: language), range: text.startIndex..<text.endIndex)
        var values: [Token] = []
        tokenizer.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in
            let ns = NSRange(range, in: text), word = String(text[range])
            guard word.unicodeScalars.contains(where: CharacterSet.letters.contains),
                !protected.contains(where: { NSIntersectionRange($0, ns).length > 0 }),
                SourceOrthography.permitsReplacement(in: text, range: ns)
            else { return true }
            let name = tagger.tag(at: range.lowerBound, unit: .word, scheme: .nameType).0
            if name == .personalName || name == .placeName || name == .organizationName { return true }
            let kind = tagger.tag(at: range.lowerBound, unit: .word, scheme: .lexicalClass).0
            values.append(
                Token(
                    range: ns, text: word, key: normalized(word, language: language),
                    preferred: kind == .noun || kind == .verb || kind == .adjective || kind == .adverb))
            return true
        }
        return values
    }
}

struct IntroducedWord: Codable, Equatable {
    let source: String
    let target: String
    let key: String
    let translation: String
    let reading: String?
}

/// Individually indexed, encrypted records grow with actual vocabulary. Only
/// the small working cache is bounded; no product limit discards learned words.
@MainActor final class IntroducedWords {
    weak var vault: MessageVault?
    private var transient: [String: IntroducedWord] = [:]
    private func identity(source: String, target: String, key: String) -> String {
        let value = source + "\u{0}" + target + "\u{0}" + key
        return vault?.opaqueID(scope: "introduced-word-v1", value: value) ?? value
    }
    func word(source: String, target: String, key: String) throws -> IntroducedWord? {
        let id = identity(source: source, target: target, key: key)
        guard let vault else { return transient[id] }
        return try vault.transaction {
            guard let bytes = try vault.get("introduced-word", id) else { return nil }
            let result = try JSONDecoder().decode(IntroducedWord.self, from: bytes)
            guard result.source == source, result.target == target, result.key == key else {
                throw MessageVault.Failure.invalidRecord
            }
            return result
        }
    }
    /// Caller owns the vault transaction containing the immutable message plan.
    func commit(_ word: IntroducedWord) throws {
        let id = identity(source: word.source, target: word.target, key: word.key)
        if let vault { try vault.put("introduced-word", id, JSONEncoder().encode(word)) } else { transient[id] = word }
    }
    func close() {
        vault = nil
        transient.removeAll()
    }
}
