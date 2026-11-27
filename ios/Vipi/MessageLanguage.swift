import Foundation
import NaturalLanguage

/// Native classification is advisory: the caller falls back to the configured
/// source whenever this device cannot identify short or ambiguous text.
@MainActor final class MessageLanguage {
    func identify(_ text: String, automatic: Bool = false) async throws -> String? {
        try Task.checkCancellation()
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= 32_768 else {
            return nil
        }
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(text)
        try Task.checkCancellation()
        guard let code = recognizer.dominantLanguage?.rawValue else { return nil }
        return LocalLanguageCatalog.canonicalCode(code)
    }
}
