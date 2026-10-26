import XCTest
@testable import Vipi

@MainActor final class ConversationImmersionTests: XCTestCase {
    func testInputLanguageChoiceBelongsToMessageAndSurvivesRowRecreation() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        let text = "Ninapenda muziki."
        owner.selectInputLanguage("sw", for: "message-one")
        let value = await owner.result(for: text, inputLanguage: owner.inputLanguage(for: "message-one"))
        XCTAssertNotNil(value)
        XCTAssertEqual(owner.cached(text, messageID: "message-one"), value)
        XCTAssertNil(owner.cached(text, messageID: "message-two"))
        XCTAssertNil(owner.inputLanguage(for: "message-two"))
        owner.selectInputLanguage("de", for: "message-one")
        XCTAssertEqual(owner.inputLanguage(for: "message-one"), "sw")
        owner.selectInputLanguage(nil, for: "message-one")
        XCTAssertNil(owner.inputLanguage(for: "message-one"))
        owner.selectInputLanguage("sw", for: "message-one")
        owner.close()
        XCTAssertNil(owner.inputLanguage(for: "message-one"))
        XCTAssertNil(owner.cached(text, messageID: "message-one"))
    }
    func testLearningLanguageReferencesUseNativeBaselineWithoutChangingTargetText() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        defer { owner.close() }
        let result = await owner.result(for: "Ninapenda muziki.")
        let value = try XCTUnwrap(result)
        XCTAssertEqual(value.original, "I like music.")
        XCTAssertEqual(value.translation, "Ninapenda muziki.")
        XCTAssertEqual(value.speech(source: "en", target: "sw").map(\.text).joined(), "I like muziki.")
        let forced = await owner.result(for: "Ninapenda muziki.", inputLanguage: "sw")
        XCTAssertEqual(forced, value)
        let unsupported = await owner.result(for: "Ninapenda muziki.", inputLanguage: "de")
        XCTAssertNil(unsupported)
    }

    func testBundledClassifierRecognizesElevenNativeParagraphsAndRejectsShortInput() async throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Bundled ML Kit language identification requires physical arm64")
        #else
        let examples = try XCTUnwrap(ConversationExamples.examples)
        let identifier = MessageLanguage()
        var results: [String: String] = [:]
        for language in VipiLanguage.initial {
            let text = try XCTUnwrap(examples.languages[language.id]?.text)
            let guess = try await identifier.identify(text)
            results[language.id] = guess ?? "und"
            XCTAssertEqual(guess, language.id)
        }
        for text in ["ok", "no", "42", "🙂"] {
            let guess = try await identifier.identify(text); XCTAssertNil(guess)
        }
        let path = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("message-language-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: path.path))
        try JSONSerialization.data(withJSONObject: ["authored_paragraphs":results, "independent_accuracy":false], options: [.prettyPrinted, .sortedKeys]).write(to: path, options: .withoutOverwriting)
        #endif
    }

    func testUnseenSwahiliUsesActualReverseTranslatorAndKeepsNativeSentence() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        guard owner.availability == .installed else { throw XCTSkip("Requires explicitly prepared physical Swahili models") }
        defer { owner.close() }
        let task = Task { await owner.result(for: "Tunakunywa maji sasa.") }
        let request = try await pending(owner)
        XCTAssertEqual(request.pair.source, "sw"); XCTAssertEqual(request.pair.target, "en")
        await owner.translateSwahili(request)
        let result = await task.value
        let value = try XCTUnwrap(result)
        XCTAssertEqual(value.translation, "Tunakunywa maji sasa.")
        XCTAssertTrue(value.spans.contains { $0.original.lowercased() == "water" && $0.translated == "maji" })
        let short = await owner.result(for: "ok"); XCTAssertNil(short)
        let foreign = await owner.result(for: "Das ist ein langer deutscher Satz über unsere gemeinsame Reise.")
        XCTAssertNil(foreign)
    }

    private func pending(_ owner: ConversationImmersion) async throws -> ConversationImmersion.Request {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while ContinuousClock.now < deadline {
            if let request = owner.request { return request }
            try await Task.sleep(for: .milliseconds(10))
        }
        return try XCTUnwrap(owner.request, "The installed pair should enqueue local translation")
    }

    func testCancellationAndLanguageChangesNeverApplyStaleTranslation() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        guard owner.availability == .installed else { throw XCTSkip("Requires explicitly prepared physical-device Swahili models") }
        defer { owner.close() }
        let cancelled = Task { await owner.result(for: "We are drinking water now.") }
        let old = try await pending(owner)
        cancelled.cancel()
        let cancelledValue = await cancelled.value
        XCTAssertNil(cancelledValue)
        XCTAssertNil(owner.request)

        let current = Task { await owner.result(for: "We are drinking water now.") }
        let active = try await pending(owner)
        XCTAssertNotEqual(active.id, old.id)
        await owner.finish(old, translation: "Ninakunywa maji sasa.")
        XCTAssertEqual(owner.request?.id, active.id, "A cancelled reply must not finish the next request")
        await owner.finish(active, translation: "Tunakunywa maji sasa.")
        let value = await current.value
        XCTAssertEqual(value?.speech(source: "en", target: "sw").map(\.text).joined(), "We are drinking maji now.")

        let switching = Task { await owner.result(for: "They are drinking water now.") }
        let stale = try await pending(owner)
        await owner.configure(pair: .init(source: "en", target: "es"), density: 1)
        let switchedValue = await switching.value
        XCTAssertNil(switchedValue)
        await owner.finish(stale, translation: "Wanakunywa maji sasa.")
        XCTAssertNil(owner.request)
        let spanish = await owner.result(for: "I like music.")
        XCTAssertEqual(spanish?.translation, "Me gusta la música.")
    }

    func testLocalReferenceParagraphsWorkWithoutAnAttachedTranslationTask() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        defer { owner.close() }
        let original = "I like music.\nI am drinking water now."
        let value = await owner.result(for: original)
        XCTAssertEqual(value?.translation, "Ninapenda muziki.\nNinakunywa maji sasa.")
        XCTAssertEqual(value?.original, original)
        XCTAssertNil(owner.request)
    }
}
