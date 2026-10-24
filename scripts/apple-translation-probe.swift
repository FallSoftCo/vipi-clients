import Foundation
import Translation

/// macOS API probe only. It is not evidence that an iOS simulator can translate.
@main struct AppleTranslationProbe {
    static func main() async throws {
        let source = Locale.Language(identifier: "en")
        let target = Locale.Language(identifier: "es")
        let availability = await LanguageAvailability().status(from: source, to: target)
        guard availability == .installed else {
            print("English → Spanish: \(availability). No translation attempted; preparation needs native consent UI.")
            return
        }
        let session = TranslationSession(installedSource: source, target: target)
        let samples = ["Coffee tomorrow?", "The river flows past the village.", "My sister works at a bank."]
        for sample in samples { print(try await session.translate(sample).targetText) }
    }
}
