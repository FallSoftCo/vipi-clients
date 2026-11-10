import Foundation
import VipiCore
import VipiLanguageDetector

/// Bundled local classification; protected literals never influence the detector.
@MainActor final class MessageLanguage {
    func identify(_ text: String) async throws -> String? {
        try Task.checkCancellation()
        guard text.utf16.count <= 16_384 else { return nil }
        let masked = NSMutableString(string: text)
        for range in TranslationIntegrity.protectedLiteralRanges(text).reversed() {
            masked.replaceCharacters(in: range, with: " ")
        }
        let input = masked as String
        guard input.filter(\.isLetter).count >= 4, input.utf8.count <= 65_536 else { return nil }
        let value = input.withCString { bytes -> String? in
            guard let code = vipi_detect_language(bytes, input.utf8.count) else { return nil }
            return String(cString: code)
        }
        try Task.checkCancellation()
        return value
    }
}
