import Foundation
import XCTest
@testable import VipiCore

final class SourceReferencePresentationTests: XCTestCase {
    private func unit(_ source: String, _ target: String, start: Int = 0, cost: Int = 1,
                      reading: String? = nil, hash: String = String(repeating: "a", count: 64)) -> SourceReferenceUnit {
        .init(range: NSRange(location: start, length: source.utf16.count), original: source, translated: target,
              reading: reading, referenceID: "authored-reference-\(start)", catalogSHA256: hash, nativeSourceTokens: cost)
    }
    func testUnknownSuffixNeverBecomesInventedFullTarget() throws {
        let original = "Hello. This sentence is unknown."
        let value = try XCTUnwrap(SourceReferencePresentation.create(original: original, target: "es",
            units: [unit("Hello.", "Hola.")], density: 0.25, nativeSourceTokenCount: 6))
        XCTAssertEqual(value.original, original); XCTAssertNil(value.completeTranslation)
        XCTAssertEqual(value.spans.map(\.range), [NSRange(location: 0, length: 6)])
        XCTAssertEqual(value.references.map(\.translated), ["Hola."])
        XCTAssertEqual(ImmersionPresentation.partial(value).speech(source: "en", target: "es", revealed: [0]),
            [.init(text: "Hello.", language: "en"), .init(text: " This sentence is unknown.", language: "en")])
    }
    func testNativePerUnitTokenCostUsesSameWholeMessageDenominator() throws {
        // Deliberately not a tokenizer test: explicit native cost inputs make
        // the old regex-one-CJK-run versus native-count mismatch observable.
        let source = "長い文章。短文。未知文。"
        let units = [unit("長い文章。", "Long text.", cost: 5), unit("短文。", "Short.", start: 5, cost: 2)]
        let value = try XCTUnwrap(SourceReferencePresentation.create(original: source, target: "en",
            units: units, density: 0.25, nativeSourceTokenCount: 12))
        XCTAssertEqual(value.spans.map(\.original), ["短文。"])
        XCTAssertEqual(value.references.map(\.nativeSourceTokens), [2])
    }
    func testActualNativeBasisCountsOnceAndRejectsStraddlingUnits() throws {
        let source = "甲乙丙丁。未知。"
        let basis = try XCTUnwrap(NativeSourceTokenBasis(original: source, wordRanges: [
            .init(location: 0, length: 1), .init(location: 1, length: 1),
            .init(location: 2, length: 2), .init(location: 5, length: 2)]))
        XCTAssertEqual(basis.count, 4)
        XCTAssertEqual(basis.cost(for: .init(location: 0, length: 5)), 3)
        XCTAssertEqual(basis.cost(for: .init(location: 5, length: 3)), 1)
        XCTAssertNil(basis.cost(for: .init(location: 0, length: 3)))
        XCTAssertNil(NativeSourceTokenBasis(original: source, wordRanges: [.init(location: 0, length: 3), .init(location: 2, length: 2)]))
    }
    func testAtomicFallbackChoosesOneSmallestSafeWholeUnit() throws {
        let source = "Hello world. Good morning. Unknown."
        let units = [unit("Hello world.", "Hola mundo.", cost: 2), unit("Good morning.", "Buenos días.", start: 13, cost: 2)]
        let value = try XCTUnwrap(SourceReferencePresentation.create(original: source, target: "es",
            units: units, density: 0.01, nativeSourceTokenCount: 5))
        XCTAssertEqual(value.spans.map(\.original), ["Hello world."])
        XCTAssertNil(SourceReferencePresentation.create(original: source, target: "es", units: units,
            density: 0, nativeSourceTokenCount: 5))
    }
    func testInvalidProofAndOverlappingOrChangedSourceAbstain() {
        for units in [[unit("Hello.", "Hola.", hash: "not-a-hash")],
                      [unit("Wrong.", "Hola.")],
                      [unit("Hello.", "Hola."), unit("Hello.", "Hola.")],
                      [unit("Hello.", "Hola.", cost: 0)]] {
            XCTAssertNil(SourceReferencePresentation.create(original: "Hello. Unknown.", target: "es",
                units: units, density: 1, nativeSourceTokenCount: 2))
        }
    }
    func testNonRomanUnitRequiresExistingReadableRomanization() throws {
        XCTAssertNil(SourceReferencePresentation.create(original: "Water. Unknown.", target: "ja",
            units: [unit("Water.", "水。")], density: 1, nativeSourceTokenCount: 2))
        let value = try XCTUnwrap(SourceReferencePresentation.create(original: "Water. Unknown.", target: "ja",
            units: [unit("Water.", "水。", reading: "mizu.")], density: 1, nativeSourceTokenCount: 2))
        XCTAssertEqual(value.spans.first?.romanization, "mizu.")
    }
    func testProtectedLiteralMutationIsNotSourceAuthorization() {
        XCTAssertNil(SourceReferencePresentation.create(original: "Hi @Cafe\u{301}. Unknown.", target: "es",
            units: [unit("Hi @Cafe\u{301}.", "Hola @Cafe.")], density: 1, nativeSourceTokenCount: 3))
        XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: "Hi #cafe\u{301}", translation: "Hola #cafe"))
        XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: "a\u{301}@example.test", translation: "a@example.test"))
    }
    func testOversizeSourceOrWholeUnitDoesNotExpandReferencePolicy() {
        let long = String(repeating: "a", count: 129)
        XCTAssertNil(SourceReferencePresentation.create(original: long, target: "es", units: [unit(long, "Hola")],
            density: 1, nativeSourceTokenCount: 1))
        XCTAssertNil(SourceReferencePresentation.create(original: String(repeating: "a", count: 16_385), target: "es",
            units: [unit("a", "Hola")], density: 1, nativeSourceTokenCount: 1))
    }
    func testUnknownOrInconsistentNativeCountsNeverFallBackToRegex() {
        for count in [0, 1, -1] {
            XCTAssertNil(SourceReferencePresentation.create(original: "Hello world. Unknown.", target: "es",
                units: [unit("Hello world.", "Hola mundo.", cost: 2)], density: 1, nativeSourceTokenCount: count))
        }
    }
    func testReferenceSentenceJoiningPreservesSourceGapsAndTargetConventions() {
        let source = "甲。乙。", ranges = [NSRange(location: 0, length: 2), NSRange(location: 2, length: 2)]
        let values = ["甲。": "Hello.", "乙。": "World."]
        XCTAssertEqual(ReferenceComposition.compose(original: source, sentences: ranges, target: "en", lookup: { values[$0] }), "Hello. World.")
        XCTAssertEqual(ReferenceComposition.compose(original: source, sentences: ranges, target: "ja", lookup: { values[$0] }), "Hello.World.")
        XCTAssertEqual(ReferenceComposition.compose(original: "甲。\n乙。", sentences: [ranges[0], .init(location: 3, length: 2)],
            target: "en", lookup: { values[$0] }), "Hello.\nWorld.")
        XCTAssertNil(ReferenceComposition.compose(original: source, sentences: ranges, target: "en", lookup: { $0 == "甲。" ? "Hello." : nil }))
    }
}

// Carry both failed Android host gate concepts as NATIVE UNRUN regressions.
// The unchanged native matcher must be tested; no pass or shared fix is implied.
final class ImmersionUnicodeContractTests: XCTestCase {
    func testTargetFormCannotDropTrailingCombiningMark() {
        let target = "cafe\u{301}"
        let intact = VocabularyEntry(source: "coffee", targets: [target],
            sourceScope: .init(original: "coffee", start: 0, end: 6),
            targetForms: [.init(surface: target, target: target, start: 0, end: 5)])
        XCTAssertEqual(ImmersionEngine().align(original: "coffee", translation: target, entries: [intact], density: 1).spans.count, 1)
        let split = VocabularyEntry(source: "coffee", targets: ["cafe"],
            sourceScope: .init(original: "coffee", start: 0, end: 6),
            targetForms: [.init(surface: target, target: "cafe", start: 0, end: 4)])
        XCTAssertTrue(ImmersionEngine().align(original: "coffee", translation: target, entries: [split], density: 1).spans.isEmpty)
    }
    func testTargetFormCannotTakeSurrogateHalf() {
        let target = "🙂", ns = target as NSString
        for start in [0, 1] {
            let half = ns.substring(with: NSRange(location: start, length: 1))
            let split = VocabularyEntry(source: "smile", targets: [half],
                sourceScope: .init(original: "smile", start: 0, end: 5),
                targetForms: [.init(surface: target, target: half, start: start, end: start + 1)])
            XCTAssertTrue(ImmersionEngine().align(original: "smile", translation: target, entries: [split], density: 1).spans.isEmpty)
        }
    }
}
