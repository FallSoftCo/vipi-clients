import XCTest
import VipiCore
import CryptoKit
@testable import Vipi

@MainActor final class ConversationImmersionTests: XCTestCase {
    /// Functional routing evidence for the separately frozen live conversation.
    /// Missing simulator ML Kit is an observed result, never a replay provider.
    func testFrozenLivePeerSwahiliRoutingWritesActualOutcomes() async throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("This receipt is specifically the simulator capability control")
        #else
        let texts = ["I need water.", "I am drinking coffee now.", "Can you meet me after work?",
            "I will be home in twenty minutes.", "Do you want to listen to some music?",
            "I like music.", "Let's have lunch tomorrow.", "That sounds good. See you soon."]
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("live-peer-sw-routing-r01.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path), "Retain the prior receipt before rerunning")
        guard !FileManager.default.fileExists(atPath: output.path) else { return }
        let pair = TranslationPair(source: "en", target: "sw")
        let observedAvailability = await LanguagePreparation.nativeStatus(pair)
        XCTAssertEqual(observedAvailability, .unsupported)
        let owner = ConversationImmersion()
        await owner.configure(pair: pair, density: 0.25)
        defer { owner.close() }
        func presentation(_ value: ImmersionPresentation) -> [String: Any] {
            var record: [String: Any] = ["original": value.original,
                "full_translation": value.translation as Any? ?? NSNull(),
                "mixed_text": value.speech(source: "en", target: "sw").map(\.text).joined(),
                "mixed_speech_spans": value.speech(source: "en", target: "sw").map { ["text": $0.text, "language": $0.language] },
                "spans": value.spans.map { span -> [String: Any] in
                    ["source_range_utf16": [span.range.location, NSMaxRange(span.range)],
                     "source": span.original, "target": span.translated,
                     "target_range_utf16": [span.targetRange.location, NSMaxRange(span.targetRange)],
                     "romanization": span.romanization as Any? ?? NSNull()]
                }]
            switch value {
            case .complete:
                record["kind"] = "complete"
                record["target_range_basis"] = "full_translation"
            case .partial(let partial):
                record["kind"] = "partial"
                record["target_range_basis"] = "corresponding_reference_translated"
                record["native_source_token_count"] = partial.nativeSourceTokenCount
                record["references"] = partial.references.map { reference -> [String: Any] in
                    ["source": reference.original, "translated": reference.translated,
                     "source_range_utf16": [reference.range.location, NSMaxRange(reference.range)],
                     "reference_id": reference.referenceID, "catalog_sha256": reference.catalogSHA256,
                     "native_source_tokens": reference.nativeSourceTokens,
                     "reading": reference.reading as Any? ?? NSNull()]
                }
            }
            return record
        }
        var rows: [[String: Any]] = []
        let runStarted = ContinuousClock.now
        var timedOut = false
        for pass in ["first_in_owner", "warm_repeat"] {
            for (index, text) in texts.enumerated() {
                let started = ContinuousClock.now
                var partials: [[String: Any]] = []
                let task = Task { @MainActor in
                    await owner.result(for: text) { partial in partials.append(presentation(.partial(partial))) }
                }
                let watchdog = Task { @MainActor in
                    do { try await Task.sleep(for: .seconds(15)) }
                    catch { return }
                    timedOut = true
                    task.cancel()
                }
                let value = await task.value
                watchdog.cancel()
                let elapsed = started.duration(to: .now).components
                let outcome = owner.lastOutcome
                rows.append(["id": String(format: "live-sw-peer-r01-%02d", index + 1), "text": text,
                    "pass": pass, "input_language": "auto", "density": 0.25,
                    "elapsed_ms": Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15,
                    "availability_after": String(describing: owner.availability),
                    "lexical_preparation": owner.lexicalPreparation,
                    "status": outcome?.status.rawValue as Any? ?? NSNull(),
                    "origin": outcome?.origin?.rawValue as Any? ?? NSNull(),
                    "fallback_status": outcome?.fallbackStatus?.rawValue as Any? ?? NSNull(),
                    "local_translation_calls": outcome?.localTranslationCalls as Any? ?? NSNull(),
                    "cache_hit": outcome?.cacheHit as Any? ?? NSNull(),
                    "result": value.map(presentation) as Any? ?? NSNull(),
                    "partial_events": partials, "timed_out": timedOut])
                XCTAssertNil(owner.request, "Unsupported simulator must not enqueue a fabricated provider")
                XCTAssertEqual(outcome?.localTranslationCalls ?? 0, 0)
                if timedOut { break }
            }
            if timedOut { break }
        }
        let elapsed = runStarted.duration(to: .now).components
        var voices: [[String: Any]] = []
        for language in ["en", "sw"] {
            do {
                let voice = try LocalVoice(language: language)
                voices.append(["language": language, "identifier": voice.identifier, "synthesis_requested": false])
            } catch {
                voices.append(["language": language, "error": String(describing: error), "synthesis_requested": false])
            }
        }
        let speechRoot = MessageSpeechCache.directory
        let cachedURLs = (try? FileManager.default.contentsOfDirectory(at: speechRoot,
            includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey, .isRegularFileKey])) ?? []
        var cachedFiles: [[String: Any]] = []
        for file in cachedURLs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) where file.pathExtension.lowercased() == "caf" {
            let metadata = try file.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey, .isRegularFileKey])
            guard metadata.isRegularFile == true else { continue }
            var entry: [String: Any] = ["filename": file.lastPathComponent,
                "bytes": metadata.fileSize as Any? ?? NSNull(),
                "modified_unix": metadata.contentModificationDate?.timeIntervalSince1970 as Any? ?? NSNull()]
            if (metadata.fileSize ?? Int.max) <= 50 * 1024 * 1024 {
                let bytes = try Data(contentsOf: file, options: .mappedIfSafe)
                entry["sha256"] = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            } else { entry["hash_status"] = "larger_than_50MiB_read_bound" }
            cachedFiles.append(entry)
        }
        let report: [String: Any] = ["schema": "vipi-live-peer-sw-routing-1",
            "protocol_sha256": "4ccee4cd1b9e79a60e018902af278e85bc34377c75162eef066960b6aa4d0e6e",
            "provider_injection": false, "model_preparation_requested": false,
            "simulator": true, "native_pair_availability": String(describing: observedAvailability),
            "coverage_claim": false, "semantic_acceptance": false,
            "voices": voices, "existing_speech_cache_directory": speechRoot.path,
            "existing_speech_cache_files": cachedFiles,
            "speech_cache_observation": "Read-only enumeration and bounded hashing after routing; this test never renders or plays audio.",
            "timing_caveat": "First owner invocation is not a guaranteed process/model cold start; warm repeat retains conversation cache.",
            "elapsed_ms": Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15,
            "complete": rows.count == 16 && !timedOut, "rows": rows]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: output, options: .withoutOverwriting)
        XCTAssertFalse(timedOut)
        XCTAssertEqual(rows.count, 16)
        #endif
    }

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
