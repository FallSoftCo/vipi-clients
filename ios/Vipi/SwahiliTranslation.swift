import Foundation
#if !targetEnvironment(simulator)
@preconcurrency import MLKitTranslate
@preconcurrency import MLKitCommon

/// Downloading is an explicit preparation action. Translating never initiates
/// a download and never sends message text to a remote translator.
@MainActor final class SwahiliTranslation {
    enum Failure: Error { case invalidPair, modelsMissing, emptyResult }
    let pair: TranslationPair
    private let translator: Translator

    init(pair: TranslationPair) throws {
        guard pair.valid, pair.source == "sw" || pair.target == "sw" else { throw Failure.invalidPair }
        self.pair = pair
        translator = Translator.translator(options: TranslatorOptions(
            sourceLanguage: TranslateLanguage(rawValue: pair.source),
            targetLanguage: TranslateLanguage(rawValue: pair.target)))
    }

    static func installed(_ pair: TranslationPair) -> Bool {
        [pair.source, pair.target].allSatisfy { code in
            code == "en" || ModelManager.modelManager().isModelDownloaded(
                TranslateRemoteModel.translateRemoteModel(language: TranslateLanguage(rawValue: code)))
        }
    }

    func prepare() async throws {
        try Task.checkCancellation()
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            translator.downloadModelIfNeeded(with: ModelDownloadConditions(
                allowsCellularAccess: true, allowsBackgroundDownloading: false)) { error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume() }
            }
        }
        try Task.checkCancellation()
        guard Self.installed(pair) else { throw Failure.modelsMissing }
    }

    func translate(_ text: String) async throws -> String {
        try Task.checkCancellation()
        guard Self.installed(pair) else { throw Failure.modelsMissing }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              text.utf16.count <= 16_384 else { throw Failure.emptyResult }
        let result: String = try await withCheckedThrowingContinuation { continuation in
            translator.translate(text) { result, error in
                if let error { continuation.resume(throwing: error) }
                else if let result, !result.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    continuation.resume(returning: result)
                } else { continuation.resume(throwing: Failure.emptyResult) }
            }
        }
        try Task.checkCancellation()
        return result
    }

    static func removeDownloads(_ pair: TranslationPair) async throws {
        for code in Set([pair.source, pair.target]) where code != "en" {
            let model = TranslateRemoteModel.translateRemoteModel(language: TranslateLanguage(rawValue: code))
            guard ModelManager.modelManager().isModelDownloaded(model) else { continue }
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                ModelManager.modelManager().deleteDownloadedModel(model) { error in
                    if let error { continuation.resume(throwing: error) }
                    else { continuation.resume() }
                }
            }
        }
    }
}
#else
/// The pinned ML Kit binary has no arm64-simulator slice. Simulator UI and
/// bundled-reference tests remain useful; they must not fake model execution.
@MainActor final class SwahiliTranslation {
    enum Failure: Error { case requiresPhysicalDevice }
    init(pair: TranslationPair) throws { throw Failure.requiresPhysicalDevice }
    static func installed(_ pair: TranslationPair) -> Bool { false }
    func prepare() async throws { throw Failure.requiresPhysicalDevice }
    func translate(_ text: String) async throws -> String { throw Failure.requiresPhysicalDevice }
    static func removeDownloads(_ pair: TranslationPair) async throws { throw Failure.requiresPhysicalDevice }
}
#endif
