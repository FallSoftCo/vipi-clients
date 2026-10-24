import Foundation
import NaturalLanguage
import VipiCore

enum LocalImmersion {
    static func words(_ text: String, language: String) -> [NSRange] {
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text; tokenizer.setLanguage(NLLanguage(rawValue: language))
        var ranges: [NSRange] = []
        tokenizer.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in
            if text[range].unicodeScalars.contains(where: { CharacterSet.letters.contains($0) }) { ranges.append(NSRange(range, in: text)) }
            return true
        }
        return ranges
    }
    static func align(original: String, translation: String, entries: [VocabularyEntry], density: Double, source: String, target: String) -> ImmersionResult {
        let sourceWords = words(original, language: source), targetWords = words(translation, language: target)
        return ImmersionEngine().align(original: original, translation: translation, entries: entries, density: density, targetLanguage: target,
            sourceBoundaries: Set(sourceWords.flatMap { [$0.location, NSMaxRange($0)] }),
            targetBoundaries: Set(targetWords.flatMap { [$0.location, NSMaxRange($0)] }), sourceTokenCount: sourceWords.count)
    }
}
