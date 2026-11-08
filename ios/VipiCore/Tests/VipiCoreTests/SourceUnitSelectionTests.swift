import Foundation
import XCTest
@testable import VipiCore

final class SourceUnitSelectionTests: XCTestCase {
    private let text = "The water and music water"
    private let words = [NSRange(location: 0, length: 3), .init(location: 4, length: 5),
        .init(location: 10, length: 3), .init(location: 14, length: 5), .init(location: 20, length: 5)]
    private func candidate(_ source: String, _ target: String, start: Int, concept: String,
                           rank: Int = 1, cost: Int = 1, id: String? = nil,
                           category: SourceUnitSelection.Category = .content,
                           reading: String? = nil) -> SourceUnitSelection.Candidate {
        let id = id ?? concept + "-" + String(start)
        return .init(unit: .init(range: .init(location: start, length: source.utf16.count),
            original: source, translated: target, reading: reading, referenceID: "qa:" + id,
            catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: cost, conceptID: concept),
            lexiconID: id, category: category, rank: rank)
    }
    private var candidates: [SourceUnitSelection.Candidate] {
        [candidate("water", "agua", start: 4, concept: "water"),
         candidate("and", "y", start: 10, concept: "and", rank: 0, category: .function),
         candidate("music", "música", start: 14, concept: "music", rank: 2),
         candidate("water", "agua", start: 20, concept: "water")]
    }
    func testContentRankDedupAndKnownSnapshotApplyBeforeSelection() throws {
        func select(_ known: Set<String>) throws -> SourceUnitSelection.Result {
            try XCTUnwrap(SourceUnitSelection.select(original: text, target: "es", candidates: candidates,
                nativeWordRanges: words, protectedRanges: [], density: 0.4, knownConceptIDs: known))
        }
        let first = try select([]), later = try select(["water"])
        XCTAssertEqual(first.selectedConceptIDs, ["water", "music"])
        XCTAssertEqual(first.usedSourceTokens, 2); XCTAssertEqual(first.budget, 2)
        XCTAssertEqual(first.rejected["same_concept"], 1)
        XCTAssertEqual(later.selectedConceptIDs, ["and", "music"])
        XCTAssertEqual(later.rejected["known_concept"], 2)
        XCTAssertEqual(first.partial?.references.map(\.conceptID), ["water", "music"])
    }
    func testScopedProtectionRejectsEveryCandidateAtThatOccurrenceOnly() throws {
        let both = candidates + [candidate("music", "música", start: 14, concept: "other-music", rank: 0)]
        let value = try XCTUnwrap(SourceUnitSelection.select(original: text, target: "es", candidates: both,
            nativeWordRanges: words, protectedRanges: [.init(location: 14, length: 5)], density: 1))
        XCTAssertEqual(value.selectedConceptIDs, ["water", "and"])
        XCTAssertEqual(value.rejected["protected_source_scope"], 2)
        XCTAssertEqual(value.partial?.original, text)
    }
    func testNativeBudgetNeverUsesWholeUnitOverrideAndWholeWordCanFillOneToken() throws {
        let compound = candidate("water and", "agua y", start: 4, concept: "compound", cost: 2)
        let result = try XCTUnwrap(SourceUnitSelection.select(original: text, target: "es", candidates: [compound],
            nativeWordRanges: words, protectedRanges: [], density: 0.1))
        XCTAssertNil(result.partial); XCTAssertEqual(result.rejected["unit_exceeds_budget"], 1)
        let one = try XCTUnwrap(SourceUnitSelection.select(original: "water", target: "ja",
            candidates: [candidate("water", "水", start: 0, concept: "water", reading: "mizu")],
            nativeWordRanges: [.init(location: 0, length: 5)], protectedRanges: [], density: 0.1))
        XCTAssertEqual(one.usedSourceTokens, 1); XCTAssertEqual(one.partial?.spans.first?.romanization, "mizu")
        XCTAssertNil(one.partial?.completeTranslation)
        let partial = try XCTUnwrap(one.partial)
        XCTAssertEqual(ImmersionPresentation.partial(partial).speech(mode: .original, source: "en", target: "ja"),
            [.init(text: "water", language: "en")])
    }
    func testNativeEdgesRawUnicodeAndExistingReadingGuardRemainRequired() throws {
        let partialWord = candidate("wate", "agua", start: 4, concept: "water")
        let bad = try XCTUnwrap(SourceUnitSelection.select(original: text, target: "es", candidates: [partialWord],
            nativeWordRanges: words, protectedRanges: [], density: 1))
        XCTAssertEqual(bad.rejected["native_source_scope"], 1); XCTAssertNil(bad.partial)
        let source = "cafe\u{301}"
        let changed = candidate("café", "kahawa", start: 0, concept: "coffee")
        XCTAssertNil(SourceUnitSelection.select(original: source, target: "sw", candidates: [changed],
            nativeWordRanges: [.init(location: 0, length: 5)], protectedRanges: [], density: 1)?.partial)
        let unreadable = try XCTUnwrap(SourceUnitSelection.select(original: "water", target: "ja",
            candidates: [candidate("water", "水", start: 0, concept: "water")],
            nativeWordRanges: [.init(location: 0, length: 5)], protectedRanges: [], density: 1))
        XCTAssertNil(unreadable.partial); XCTAssertEqual(unreadable.rejected["presentation_rejected"], 1)
    }
}
