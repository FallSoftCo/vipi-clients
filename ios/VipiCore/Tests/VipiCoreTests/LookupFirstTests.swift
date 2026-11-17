import Foundation
import XCTest
@testable import VipiCore

// Authored development regressions, not sealed/held-out conversation evidence.
// Deterministic injected-provider checks; never presented as native model evidence.
@MainActor private final class LookupHarness {
    var current = true, ready = false
    var detected: String? = "en"
    var known: [String: String] = [:]
    var partial: PartialImmersionResult?
    var evidence: SourceLookupEvidence?
    var evidenceCalls = 0
    var translated = "Hola. Mensaje desconocido."
    var readinessCalls = 0, inferenceCalls = 0, alignCalls = 0
    var staleDuringReadiness = false, staleDuringTranslation = false, cancelTranslation = false
    var badAlignment = false
    var partialEvents: [PartialImmersionResult] = []
    func run(_ text: String = "Hello. Unknown message.", input: String? = "en", intent: ImmersionRequestIntent = .automaticImmersion, allowModelTranslation: Bool = true) async throws -> LookupFirstOutcome {
        try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: input, intent: intent, allowModelTranslation: allowModelTranslation),
            valid: { self.current },
            reference: { text, source, target in self.known[source + "-" + target + ":" + text] },
            identify: { _ in self.detected },
            modelsReady: { _, _ in
                self.readinessCalls += 1
                if self.staleDuringReadiness { self.current = false }
                return self.ready
            },
            translate: { _, _, _ in
                self.inferenceCalls += 1
                if self.cancelTranslation { throw CancellationError() }
                if self.staleDuringTranslation { self.current = false }
                return self.translated
            },
            align: { source, target, _ in
                self.alignCalls += 1
                return .init(original: self.badAlignment ? "wrong source" : source, translation: target, spans: [])
            },
            partialReference: { _, _, _ in self.partial },
            sourceEvidenceIdentity: evidence?.catalogIdentity,
            sourceEvidence: evidence.map { _ in { _, _, _ in self.evidenceCalls += 1; return self.evidence! } },
            onPartial: { self.partialEvents.append($0) })
    }
}

@MainActor final class LookupFirstTests: XCTestCase {
    private func partial(_ original: String = "Hello. Unknown message.") throws -> PartialImmersionResult {
        try XCTUnwrap(SourceReferencePresentation.create(original: original, target: "es",
            units: [.init(range: NSRange(location: 0, length: 6), original: "Hello.", translated: "Hola.",
                reading: nil, referenceID: "authored-reference", catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: 1)],
            density: 1, nativeSourceTokenCount: 3))
    }
    func testActualInputLanguageSurvivesReverseCacheAndLocalMissButNeverStale() async throws {
        let h=LookupHarness();h.known["es-en:Hola."]="Hello."
        let reverse=try await h.run("Hola.",input:"es")
        XCTAssertEqual(reverse.result?.original,"Hello.");XCTAssertEqual(reverse.result?.translation,"Hola.")
        XCTAssertEqual(reverse.resolvedInputLanguage,"es");XCTAssertEqual(reverse.cachedInvocation().resolvedInputLanguage,"es")
        let unknown=LookupHarness();unknown.detected="es"
        let miss=try await unknown.run("Una frase desconocida.",input:nil,allowModelTranslation:false)
        XCTAssertEqual(miss.status,.noLocalMatch);XCTAssertEqual(miss.resolvedInputLanguage,"es")
        let invalid=try await unknown.run(input:"fr");XCTAssertNil(invalid.resolvedInputLanguage)
        unknown.detected="fr"
        let unsupported=try await unknown.run(input:nil);XCTAssertNil(unsupported.resolvedInputLanguage)
        let stale=LookupHarness();stale.staleDuringReadiness=true
        let dropped=try await stale.run(input:"es");XCTAssertEqual(dropped.status,.stale);XCTAssertNil(dropped.resolvedInputLanguage)
        let rejected=LookupHarness();rejected.ready=true;rejected.badAlignment=true
        let failed=try await rejected.run(input:"es");XCTAssertEqual(failed.status,.invalidResult);XCTAssertEqual(failed.resolvedInputLanguage,"es")
    }
    func testLocalOnlyMissNeverUsesModelsEvenWhenInstalled() async throws {
        for intent in [ImmersionRequestIntent.automaticImmersion, .fullTranslation] {
            let h = LookupHarness(); h.ready = true
            let outcome = try await h.run(intent: intent, allowModelTranslation: false)
            XCTAssertEqual(outcome.status, .noLocalMatch); XCTAssertNil(outcome.result)
            XCTAssertEqual(h.readinessCalls, 0); XCTAssertEqual(h.inferenceCalls, 0); XCTAssertEqual(h.alignCalls, 0)
        }
    }
    func testLocalOnlyKeepsReviewedPartialAndKnownReference() async throws {
        let h = LookupHarness(); h.partial = try partial()
        let partialResult = try await h.run(allowModelTranslation: false)
        XCTAssertEqual(partialResult.result?.spans, h.partial?.spans)
        h.known["en-es:Hello."] = "Hola."
        let exact = try await h.run("Hello.", allowModelTranslation: false)
        XCTAssertEqual(exact.result?.translation, "Hola."); XCTAssertEqual(h.inferenceCalls, 0)
    }
    func testApprovedAutomaticPartialNeverInspectsOrInvokesProvider() async throws {
        for installed in [false, true] {
            let h = LookupHarness(); h.partial = try partial(); h.ready = installed
            let outcome = try await h.run()
            XCTAssertEqual(outcome.status, .partial); XCTAssertNil(outcome.fallbackStatus)
            XCTAssertEqual(outcome.result?.spans, h.partial?.spans); XCTAssertNil(outcome.result?.translation)
            XCTAssertEqual(h.readinessCalls, 0); XCTAssertEqual(h.inferenceCalls, 0); XCTAssertEqual(h.alignCalls, 0)
            XCTAssertEqual(outcome.modelReadinessCalls, 0); XCTAssertEqual(outcome.alignmentCalls, 0)
            XCTAssertEqual(h.partialEvents.count, 1)
        }
    }
    func testKnownForwardBypassesModelAndInference() async throws {
        let h = LookupHarness(); h.known["en-es:Hello."] = "Hola."
        let outcome = try await h.run("Hello.")
        XCTAssertEqual(outcome.status, .ready); XCTAssertEqual(outcome.origin, .lookupReference)
        XCTAssertEqual(outcome.result?.translation, "Hola.")
        XCTAssertEqual(h.readinessCalls, 0); XCTAssertEqual(h.inferenceCalls, 0)
    }
    func testForwardReferenceUsesQualifiedAutomaticPartialButKeepsFullAndReverse() async throws {
        let text = "Hello. Unknown message."
        let candidate = try partial(text)
        let h = LookupHarness()
        h.known["en-es:" + text] = "Hola. Mensaje desconocido."
        h.evidence = .init(original: text, source: "en", target: "es", catalogIdentity: "test-provider",
                           partial: candidate, recognitions: [])
        let automatic = try await h.run(text)
        XCTAssertEqual(automatic.status, .partial)
        XCTAssertEqual(automatic.result?.spans, candidate.spans)
        let full = try await h.run(text, intent: .fullTranslation)
        XCTAssertEqual(full.status, .ready)
        XCTAssertEqual(full.result?.translation, "Hola. Mensaje desconocido.")
        XCTAssertEqual(h.inferenceCalls, 0)
        let beforeReverse = h.evidenceCalls
        h.known["es-en:Hola."] = "Hello."
        let reverse = try await h.run("Hola.", input: "es")
        XCTAssertEqual(reverse.result?.translation, "Hola.")
        XCTAssertEqual(h.evidenceCalls, beforeReverse)
        h.evidence = .init(original: text, source: "en", target: "es", catalogIdentity: "test-provider",
                           partial: nil, recognitions: [])
        let fallback = try await h.run(text)
        XCTAssertEqual(fallback.status, .ready)
        XCTAssertEqual(fallback.result?.translation, "Hola. Mensaje desconocido.")
    }
    func testKnownReverseKeepsCanonicalSourceAndIncomingTarget() async throws {
        let h = LookupHarness(); h.known["es-en:Hola."] = "Hello."
        let outcome = try await h.run("Hola.", input: "es")
        XCTAssertEqual(outcome.result?.original, "Hello."); XCTAssertEqual(outcome.result?.translation, "Hola.")
        XCTAssertEqual(h.readinessCalls, 0); XCTAssertEqual(h.inferenceCalls, 0)
        // UI original-copy must use incoming "Hola.", not canonical result.original.
    }
    func testMissingModelsRetainsKnownUnitAndExactUnknownText() async throws {
        let h = LookupHarness(); h.partial = try partial()
        let outcome = try await h.run(intent: .fullTranslation)
        XCTAssertEqual(outcome.status, .partial); XCTAssertEqual(outcome.fallbackStatus, .modelNotReady)
        XCTAssertNil(outcome.result?.translation); XCTAssertEqual(outcome.result?.original, "Hello. Unknown message.")
        XCTAssertEqual(outcome.result?.spans.map(\.original), ["Hello."])
        XCTAssertEqual(h.partialEvents.count, 1); XCTAssertEqual(h.inferenceCalls, 0)
    }
    func testActualFullTargetIsSeparateFromReferenceTargetBasis() async throws {
        let h = LookupHarness(); let initial = try partial(); h.partial = initial; h.ready = true
        h.translated = "Un mensaje desconocido después de saludar."
        let outcome = try await h.run(intent: .fullTranslation)
        guard case .partial(let value)? = outcome.result else { return XCTFail("expected explicit partial presentation") }
        XCTAssertEqual(value.completeTranslation, h.translated)
        XCTAssertEqual(value.spans, initial.spans); XCTAssertEqual(value.references, initial.references)
        XCTAssertEqual(value.spans.first?.targetRange, NSRange(location: 0, length: 5))
        XCTAssertEqual(value.references.first?.translated, "Hola.")
        XCTAssertEqual(h.inferenceCalls, 1); XCTAssertEqual(outcome.localTranslationCalls, 1)
        XCTAssertEqual(h.alignCalls, 0); XCTAssertEqual(outcome.alignmentCalls, 0)
    }
    func testReverseUnknownDoesNotInventCanonicalPartial() async throws {
        let h = LookupHarness(); h.partial = try partial()
        let outcome = try await h.run("Hola. Texto desconocido.", input: "es")
        XCTAssertNil(outcome.result); XCTAssertEqual(outcome.status, .modelNotReady)
        XCTAssertTrue(h.partialEvents.isEmpty); XCTAssertEqual(h.inferenceCalls, 0)
    }
    func testWrongLanguageNeverPublishesPreparedPartial() async throws {
        let h = LookupHarness(); h.partial = try partial(); h.detected = "ja"
        let outcome = try await h.run(input: nil)
        XCTAssertEqual(outcome.status, .invalidLanguage); XCTAssertNil(outcome.result)
        XCTAssertTrue(h.partialEvents.isEmpty); XCTAssertEqual(h.readinessCalls, 0)
    }
    func testStaleBeforeLookupNeverCallsProvider() async throws {
        let h = LookupHarness(); h.current = false
        let outcome = try await h.run()
        XCTAssertEqual(outcome.status, .stale); XCTAssertNil(outcome.result); XCTAssertEqual(h.readinessCalls, 0)
    }
    func testStaleAfterReadinessNeverRunsTranslationOrReturnsPartial() async throws {
        let h = LookupHarness(); h.partial = try partial(); h.ready = true; h.staleDuringReadiness = true
        let outcome = try await h.run(intent: .fullTranslation)
        XCTAssertEqual(outcome.status, .stale); XCTAssertNil(outcome.result); XCTAssertEqual(h.inferenceCalls, 0)
    }
    func testStaleAfterTranslationNeverAlignsOrReturnsOldDirection() async throws {
        let h = LookupHarness(); h.ready = true; h.staleDuringTranslation = true
        let outcome = try await h.run()
        XCTAssertEqual(outcome.status, .stale); XCTAssertNil(outcome.result); XCTAssertEqual(h.alignCalls, 0)
    }
    func testCancelledProviderIsPropagatedNotConvertedToCompleteTranslation() async throws {
        let h = LookupHarness(); h.partial = try partial(); h.ready = true; h.cancelTranslation = true
        do { _ = try await h.run(intent: .fullTranslation); XCTFail("cancellation must propagate") }
        catch is CancellationError { XCTAssertEqual(h.partialEvents.count, 1); XCTAssertEqual(h.inferenceCalls, 1) }
    }
    func testUnsafeFullTargetKeepsOnlySourceAuthorizedPartial() async throws {
        let h = LookupHarness(); h.partial = try partial(); h.ready = true; h.translated = "Hola @invented"
        let outcome = try await h.run(intent: .fullTranslation)
        XCTAssertEqual(outcome.fallbackStatus, .invalidResult); XCTAssertNil(outcome.result?.translation)
        XCTAssertEqual(outcome.result?.spans, h.partial?.spans); XCTAssertEqual(h.alignCalls, 0)
    }
    func testWrongAlignedSourceRejectsProviderResult() async throws {
        let h = LookupHarness(); h.ready = true; h.badAlignment = true
        let outcome = try await h.run()
        XCTAssertEqual(outcome.status, .invalidResult); XCTAssertNil(outcome.result)
    }
    func testExplicitInvalidDirectionDoesNotReachModels() async throws {
        let h = LookupHarness(); let outcome = try await h.run(input: "fr")
        XCTAssertEqual(outcome.status, .invalidInput); XCTAssertEqual(h.readinessCalls, 0)
    }
    func testInvalidReferenceLocalPartialAnchorNeverPublishesOrRequestsModels() async throws {
        let h = LookupHarness(), good = try partial()
        let span = try XCTUnwrap(good.spans.first)
        h.partial = .init(original: good.original, spans: [.init(range: span.range, original: span.original,
            translated: span.translated, targetRange: .init(location: 1, length: span.targetRange.length),
            romanization: span.romanization)], references: good.references, nativeSourceTokenCount: good.nativeSourceTokenCount, targetLanguage: "es")
        let outcome = try await h.run()
        XCTAssertEqual(outcome.status, .invalidResult); XCTAssertNil(outcome.result)
        XCTAssertTrue(h.partialEvents.isEmpty); XCTAssertEqual(h.readinessCalls, 0)
    }
    func testCanonicalEquivalentProtectedLiteralMutationKeepsOnlySourceKnownPartial() async throws {
        let h = LookupHarness(); h.partial = try partial("Hello. @cafe\u{301}")
        h.ready = true; h.translated = "Hola. @caf\u{e9}"
        let outcome = try await h.run("Hello. @cafe\u{301}", intent: .fullTranslation)
        XCTAssertEqual(outcome.fallbackStatus, .invalidResult)
        XCTAssertNil(outcome.result?.translation); XCTAssertEqual(h.alignCalls, 0)
        XCTAssertEqual(Array((outcome.result?.original ?? "").utf8), Array("Hello. @cafe\u{301}".utf8))
    }

}
