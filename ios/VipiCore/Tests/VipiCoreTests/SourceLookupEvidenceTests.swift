import Foundation
import XCTest
@testable import VipiCore

/// Synthetic safety/orchestration checks. No new catalog or provider-quality claim.
@MainActor final class SourceLookupEvidenceTests: XCTestCase {
    let text = "hot dog water", translated = "caliente perro agua"
    let sha = String(repeating: "a", count: 64), identity = "synthetic-constraints-v1"
    func recognition(_ mask: NSRange = .init(location: 0, length: 7),
                     context: NSRange = .init(location: 0, length: 7),
                     mode: SourceAtomicMode = .atomic,
                     outputs: [SourceApprovedOutput] = []) -> SourceRecognition {
        .init(ruleID: "compound", recordSHA256: sha, context: context, mask: mode == .none ? nil : mask,
              mode: mode, approvedOutputs: outputs)
    }
    func evidence(_ recognitions: [SourceRecognition]? = nil, partial: PartialImmersionResult? = nil,
                  original: String? = nil, catalog: String? = nil) -> SourceLookupEvidence {
        .init(original: original ?? text, source: "en", target: "es", catalogIdentity: catalog ?? identity,
              partial: partial, recognitions: recognitions ?? [recognition()])
    }
    func checked(_ value: SourceLookupEvidence? = nil) throws -> SourceLookupConstraints {
        try XCTUnwrap((value ?? evidence()).validated(text: text, sourceLanguage: "en", targetLanguage: "es", identity: identity))
    }
    var entries: [VocabularyEntry] {
        [.init(source: "hot dog", targets: ["caliente perro"]), .init(source: "hot", targets: ["caliente"]),
         .init(source: "dog", targets: ["perro"]), .init(source: "water", targets: ["agua"])]
    }
    func aligned(_ constraints: SourceLookupConstraints?, density: Double = 1,
                 supplemental: Bool = false) -> ImmersionResult {
        let extra = supplemental ? [VocabularyEntry(source: "water", targets: ["agua"],
            sourceScope: .init(original: text, start: 8, end: 13),
            targetScope: .init(translation: translated, start: 15, end: 19))] : []
        return ImmersionEngine().align(original: text, translation: translated,
            entries: supplemental ? Array(entries.dropLast()) : entries, density: density, targetLanguage: "es",
            sourceTokenCount: 3, supplementalEntries: extra, sourceConstraints: constraints)
    }
    func partial(output: String? = "compound:hot_dog") throws -> PartialImmersionResult {
        try XCTUnwrap(SourceReferencePresentation.create(original: text, target: "es",
            units: [.init(range: .init(location: 0, length: 7), original: "hot dog", translated: "perrito",
                reading: nil, referenceID: "synthetic", catalogSHA256: sha, nativeSourceTokens: 2,
                conceptID: "hot_dog", outputID: output)], density: 1, nativeSourceTokenCount: 3))
    }
    func testEmptySelectedFacesProtectPrimaryAndSupplementalWithoutSpendingSafeBudget() throws {
        let constraint = try checked()
        for supplemental in [false, true] {
            for density in [0.1, 0.5, 1.0] {
                XCTAssertEqual(aligned(constraint, density: density, supplemental: supplemental).spans.map(\.original), ["water"])
            }
        }
        XCTAssertEqual(aligned(nil).translation, translated)
        XCTAssertTrue(aligned(nil).spans.contains { $0.original == "hot dog" })
        let foreign = ImmersionEngine().align(original: "different water", translation: translated, entries: entries,
            density: 1, targetLanguage: "es", sourceConstraints: constraint)
        XCTAssertTrue(foreign.spans.isEmpty); XCTAssertEqual(foreign.translation, translated)
    }
    func testEveryOverlapNeedsExactApprovedIDAndScopeAndAmbiguityAbstains() throws {
        let permitted = SourceApprovedOutput(outputID: "compound:hot_dog", range: .init(location: 0, length: 7))
        let approved = try checked(evidence([recognition(outputs: [permitted])]))
        XCTAssertEqual(approved.filterPartial(try partial())?.spans.map(\.original), ["hot dog"])
        XCTAssertNil(approved.filterPartial(try partial(output: nil)))
        XCTAssertNil(approved.filterPartial(try partial(output: "other")))
        XCTAssertFalse(approved.permits(range: .init(location: 4, length: 3), outputID: permitted.outputID))
        // Text equality cannot upgrade a legacy aligned candidate to an approval.
        XCTAssertEqual(aligned(approved).spans.map(\.original), ["water"])
        let conflict = try checked(evidence([recognition(outputs: [permitted]), recognition(outputs: [
            .init(outputID: "animal:dog", range: permitted.range)])]))
        XCTAssertNil(conflict.filterPartial(try partial()))
        let crossing = try checked(evidence([recognition(outputs: [permitted]),
            recognition(.init(location: 4, length: 9), context: .init(location: 0, length: 13), mode: .ambiguous)]))
        XCTAssertNil(crossing.filterPartial(try partial())); XCTAssertTrue(aligned(crossing).spans.isEmpty)
        let larger = try checked(evidence([recognition(outputs: [permitted]),
            recognition(context: .init(location: 0, length: 13), mode: .none)]))
        XCTAssertNotNil(larger.filterPartial(try partial())) // Outer context never erases the inner mask.
    }
    func testMalformedBindingsRangesAndGraphemesFailClosed() throws {
        XCTAssertNil(evidence(catalog: "other").validated(text: text, sourceLanguage: "en", targetLanguage: "es", identity: identity))
        XCTAssertNil(evidence().validated(text: text, sourceLanguage: "es", targetLanguage: "en", identity: identity))
        for range in [NSRange(location: -1, length: 1), .init(location: Int.max, length: 9),
                      .init(location: 0, length: 0), .init(location: 12, length: 2)] {
            XCTAssertNil(evidence([recognition(range)]).validated(text: text, sourceLanguage: "en", targetLanguage: "es", identity: identity))
        }
        for source in ["😀 water", "e\u{301} water", "👨‍👩‍👧 water"] {
            let invalid = SourceLookupEvidence(original: source, source: "en", target: "es", catalogIdentity: identity,
                partial: nil, recognitions: [recognition(.init(location: 0, length: 1), context: .init(location: 0, length: source.utf16.count))])
            XCTAssertNil(invalid.validated(text: source, sourceLanguage: "en", targetLanguage: "es", identity: identity))
        }
        let normalized = SourceLookupEvidence(original: "é", source: "en", target: "es", catalogIdentity: identity, partial: nil, recognitions: [])
        XCTAssertNil(normalized.validated(text: "e\u{301}", sourceLanguage: "en", targetLanguage: "es", identity: identity))
        let dog = SourceApprovedOutput(outputID: "dog", range: .init(location: 4, length: 3))
        for bad in [recognition(outputs: [dog]), recognition(mode: .ambiguous, outputs: [dog]),
                    recognition(context: .init(location: 0, length: 13), mode: .headBackoff,
                                outputs: [.init(outputID: "water", range: .init(location: 8, length: 5))])] {
            XCTAssertNil(evidence([bad]).validated(text: text, sourceLanguage: "en", targetLanguage: "es", identity: identity))
        }
        let goodHead = try checked(evidence([recognition(mode: .headBackoff, outputs: [dog])]))
        XCTAssertTrue(goodHead.permits(range: dog.range, outputID: dog.outputID))
        XCTAssertNil(evidence(Array(repeating: recognition(), count: 4097)).validated(text: text, sourceLanguage: "en", targetLanguage: "es", identity: identity))
    }
    func testKnownAndDensityWithheldFacesKeepRecognitionBeforeAnyProviderWork() async throws {
        for reason in ["known", "density", "target-unavailable"] {
            var ready = 0, translate = 0, align = 0
            let outcome = try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: "en"),
                valid: { true }, reference: { _, _, _ in nil }, identify: { _ in "en" },
                modelsReady: { _, _ in ready += 1; return false }, translate: { _, _, _ in translate += 1; return self.translated },
                align: { _, _, _ in align += 1; return self.aligned(nil) },
                sourceEvidenceIdentity: identity, sourceEvidence: { _, _, _ in self.evidence() })
            XCTAssertEqual(outcome.status, .modelNotReady, reason)
            XCTAssertEqual(outcome.sourceConstraints?.recognitions.count, 1)
            XCTAssertNil(outcome.result); XCTAssertEqual(ready, 1); XCTAssertEqual(translate, 0); XCTAssertEqual(align, 0)
            XCTAssertEqual(outcome.cachedInvocation().sourceConstraints?.recognitions.count, 1)
        }
    }
    func testForwardWholeReferenceStillConstrainedAndReverseNeverReusesSourceRanges() async throws {
        for reverse in [false, true] {
            var recognitions = 0
            let outcome = try await LookupFirst.resolve(.init(text: reverse ? translated : text, source: "en", target: "es", inputLanguage: reverse ? "es" : "en"),
                valid: { true }, reference: { _, source, _ in source == "en" ? self.translated : self.text },
                identify: { _ in XCTFail("known reference"); return nil },
                modelsReady: { _, _ in XCTFail("known reference"); return false },
                translate: { _, _, _ in XCTFail("known reference"); return "" },
                align: { original, target, constraints in
                    XCTAssertEqual(original, self.text); XCTAssertEqual(target, self.translated)
                    XCTAssertEqual(constraints == nil, reverse)
                    return self.aligned(constraints)
                }, sourceEvidenceIdentity: identity, sourceEvidence: { _, _, _ in
                    recognitions += 1; return self.evidence()
                })
            XCTAssertEqual(recognitions, reverse ? 0 : 1)
            XCTAssertEqual(outcome.result?.translation, translated)
            if !reverse { XCTAssertEqual(outcome.result?.spans.map(\.original), ["water"]) }
            else { XCTAssertTrue(outcome.result?.spans.contains { $0.original == "hot dog" } == true) }
        }
    }
    func testInvalidEvidenceAndStaleAcquisitionNeverReachModelsOrPublish() async throws {
        for stale in [false, true] {
            var current = true
            let outcome = try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: "en"),
                valid: { current }, reference: { _, _, _ in nil }, identify: { _ in "en" },
                modelsReady: { _, _ in XCTFail("must stop"); return false },
                translate: { _, _, _ in XCTFail("must stop"); return "" },
                align: { _, _, _ in XCTFail("must stop"); return self.aligned(nil) },
                sourceEvidenceIdentity: identity, sourceEvidence: { _, _, _ in
                    if stale { current = false }; return self.evidence(catalog: stale ? self.identity : "wrong")
                })
            XCTAssertEqual(outcome.status, stale ? .stale : .invalidResult)
            XCTAssertNil(outcome.result); XCTAssertNil(outcome.sourceConstraints)
        }
    }
    func testFilteredPartialDoesNotShortCircuitUnmaskedFallbackOrForgeCompleteTarget() async throws {
        var calls = 0
        let outcome = try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: "en"),
            valid: { true }, reference: { _, _, _ in nil }, identify: { _ in "en" }, modelsReady: { _, _ in true },
            translate: { _, _, _ in calls += 1; return self.translated }, align: { _, _, constraints in self.aligned(constraints) },
            sourceEvidenceIdentity: identity, sourceEvidence: { _, _, _ in self.evidence(partial: try self.partial()) },
            onPartial: { _ in XCTFail("masked face must not publish") })
        XCTAssertEqual(calls, 1); XCTAssertEqual(outcome.result?.spans.map(\.original), ["water"])
        XCTAssertEqual(outcome.result?.translation, translated)
    }
    func testEmptyTranslationRetainsMasksButPublishesNoFabricatedTarget() async throws {
        let outcome = try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: "en"),
            valid: { true }, reference: { _, _, _ in nil }, identify: { _ in "en" }, modelsReady: { _, _ in true },
            translate: { _, _, _ in "" }, align: { _, _, _ in XCTFail("empty target"); return self.aligned(nil) },
            sourceEvidenceIdentity: identity, sourceEvidence: { _, _, _ in self.evidence() })
        XCTAssertEqual(outcome.status, .invalidResult); XCTAssertNil(outcome.result)
        XCTAssertEqual(outcome.sourceConstraints?.recognitions.count, 1)
    }
    func testBlockedLegacyPartialDoesNotHideApprovedProviderHead() async throws {
        let accepted = try partial(), legacy = try partial(output: nil)
        let permit = SourceApprovedOutput(outputID: "compound:hot_dog", range: .init(location: 0, length: 7))
        var events = 0
        let outcome = try await LookupFirst.resolve(.init(text: text, source: "en", target: "es", inputLanguage: "en"),
            valid: { true }, reference: { _, _, _ in nil }, identify: { _ in "en" },
            modelsReady: { _, _ in XCTFail("approved partial"); return false },
            translate: { _, _, _ in XCTFail("approved partial"); return "" },
            align: { _, _, _ in XCTFail("approved partial"); return self.aligned(nil) },
            partialReference: { _, _, _ in legacy }, sourceEvidenceIdentity: identity,
            sourceEvidence: { _, _, _ in self.evidence([self.recognition(outputs: [permit])], partial: accepted) },
            onPartial: { value in events += 1; XCTAssertEqual(value.references.first?.outputID, permit.outputID) })
        XCTAssertEqual(outcome.status, .partial); XCTAssertEqual(events, 1)
        XCTAssertEqual(outcome.result?.spans.map(\.translated), ["perrito"])
        XCTAssertNil(outcome.result?.translation); XCTAssertEqual(outcome.modelReadinessCalls, 0)
    }

}
