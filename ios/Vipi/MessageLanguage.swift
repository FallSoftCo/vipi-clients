import Foundation
#if !targetEnvironment(simulator)
@preconcurrency import MLKitLanguageID

/// Bundled local classification. It never downloads or sends message text.
@MainActor final class MessageLanguage {
    private let identifier = LanguageIdentification.languageIdentification(options: LanguageIdentificationOptions(confidenceThreshold: 0.01))
    func identify(_ text: String) async throws -> String? {
        guard text.filter(\.isLetter).count >= 4 else { return nil }
        let value: String? = try await withCheckedThrowingContinuation { continuation in
            identifier.identifyPossibleLanguages(for: text) { values, error in
                if let error { continuation.resume(throwing: error); return }
                let ranked = (values ?? []).sorted { $0.confidence > $1.confidence }
                guard let first = ranked.first, first.languageTag != "und", !first.languageTag.hasSuffix("-Latn"),
                      first.confidence >= 0.85, (ranked.dropFirst().first?.confidence ?? 0) <= 0.10 else {
                    continuation.resume(returning: nil); return
                }
                continuation.resume(returning: first.languageTag)
            }
        }
        try Task.checkCancellation()
        return value
    }
}
#else
/// No arm64-simulator binary. Exact-reference UI tests still run; this adapter
/// does not pretend to classify unknown messages in simulator qualification.
@MainActor final class MessageLanguage {
    func identify(_ text: String) async throws -> String? { nil }
}
#endif
