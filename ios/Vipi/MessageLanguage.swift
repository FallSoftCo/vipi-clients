import Foundation
import NaturalLanguage
import VipiCore
import VipiLanguageDetector

/// Local classification; protected literals never influence either detector.
@MainActor final class MessageLanguage {
    func identify(_ text: String, automatic: Bool = false) async throws -> String? {
        try Task.checkCancellation()
        guard text.utf16.count <= 16_384 else { return nil }
        let masked = NSMutableString(string: text)
        for range in TranslationIntegrity.protectedLiteralRanges(text).reversed() {
            masked.replaceCharacters(in: range, with: " ")
        }
        let input = masked as String
        guard input.filter(\.isLetter).count >= 4, input.utf8.count <= 65_536 else { return nil }
        if automatic {
            let tokenizer = NLTokenizer(unit: .word)
            tokenizer.string = input
            var words = 0
            tokenizer.enumerateTokens(in: input.startIndex..<input.endIndex) { range, _ in
                if input[range].contains(where: \.isLetter) { words += 1 }
                return words < 2
            }
            guard words >= 2 else { return nil }
        }
        let value = input.withCString { bytes -> String? in
            guard let code = vipi_detect_language(bytes, input.utf8.count) else { return nil }
            return String(cString: code)
        }
        try Task.checkCancellation()
        if let value { return value }
        guard automatic else { return nil }
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(input)
        let top = recognizer.languageHypotheses(withMaximum: 1).first
        try Task.checkCancellation()
        return Self.nativeFallback(code: top?.key.rawValue, confidence: top?.value)
    }

    static func nativeFallback(code: String?, confidence: Double?) -> String? {
        guard let code, let confidence, confidence >= 0.70 else { return nil }
        let normalized = code == "zh-Hans" || code == "zh-Hant" ? "zh" : code
        return ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "ar", "sw"].contains(normalized) ? normalized : nil
    }
}
