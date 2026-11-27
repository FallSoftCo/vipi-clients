import Foundation
import XCTest
@testable import VipiCore

/// Shared eight-case sentence contract. Costs are explicit synthetic controls,
/// NOT a native tokenizer, real clipboard/VoiceOver or independent meaning run.
final class ImmersionPartialSentenceBoundaryTests: XCTestCase {
    private let text = "你好。下周见。未知。"
    private func partial(_ original: String = "你好。下周见。未知。", target: String = "en", density: Double = 1) throws
        -> PartialImmersionResult
    {
        let second = (original as NSString).range(of: "下周见。").location
        let ja = target == "ja"
        return try XCTUnwrap(
            SourceReferencePresentation.create(
                original: original, target: target,
                units: [
                    .init(
                        range: .init(location: 0, length: 3), original: "你好。", translated: ja ? "こんにちは。" : "Hello.",
                        reading: ja ? "konnichiwa." : nil, referenceID: "development-catalog-unit-1",
                        catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: 1),
                    .init(
                        range: .init(location: second, length: 4), original: "下周见。",
                        translated: ja ? "また来週。" : "See you next week.",
                        reading: ja ? "mata raishuu." : nil, referenceID: "development-catalog-unit-2",
                        catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: 2)
                ], density: density, nativeSourceTokenCount: 4))
    }
    /// Selection/gap fixture adapter, not a second separator algorithm. Before
    /// uses the ACTUAL V4 public run API (no sentence metadata existed); after
    /// uses the ACTUAL new production proof/face factory used by UIKit. Exact
    /// expected faces/ranges are identical. No UIKit interaction is simulated.
    private func project(
        _ value: ImmersionPresentation, revealed: Set<Int> = [], script: Bool = false,
        selection: NSRange? = nil
    ) -> String {
        let original = value.original as NSString
        let chosen = selection ?? NSRange(location: 0, length: original.length)
        if chosen.length == 0 { return "" }
        let end = NSMaxRange(chosen)
        var cursor = chosen.location, runs: [ImmersionCopyRun] = []
        for span in value.spans where span.range.location < end && NSMaxRange(span.range) > chosen.location {
            if span.range.location > cursor {
                runs.append(
                    .init(text: original.substring(with: .init(location: cursor, length: span.range.location - cursor)))
                )
            }
            let showingOriginal = revealed.contains(span.id)
            #if BEFORE_SENTENCE_BOUNDARY
            let face =
                showingOriginal
                ? original.substring(with: NSIntersectionRange(chosen, span.range))
                : (script ? span.translated : span.displayedTarget)
            runs.append(.init(text: face, slotID: span.id, showsOriginal: showingOriginal))
            #else
            runs.append(
                ImmersionCopyText.run(
                    for: span, in: value, showingOriginal: showingOriginal,
                    script: script, selectedOriginalRange: chosen))
            #endif
            cursor = min(NSMaxRange(span.range), end)
        }
        if cursor < end {
            runs.append(.init(text: original.substring(with: .init(location: cursor, length: end - cursor))))
        }
        return ImmersionCopyText.compose(runs)
    }
    func testDefaultAndFullDensityKeepUnknownTailAndReferenceCoordinates() throws {
        let low = try partial(density: 0.25)
        XCTAssertEqual(low.spans.count, 1)
        XCTAssertEqual(project(.partial(low)), "Hello.下周见。未知。")
        let full = try partial()
        XCTAssertEqual(full.spans.count, 2)
        XCTAssertEqual(project(.partial(full)), "Hello. See you next week.未知。")
        XCTAssertNil(full.completeTranslation)
        XCTAssertEqual(full.original, text)
        XCTAssertEqual(full.spans.map(\.range), [.init(location: 0, length: 3), .init(location: 3, length: 4)])
        XCTAssertEqual(full.spans.map(\.targetRange), [.init(location: 0, length: 6), .init(location: 0, length: 18)])
    }
    func testAllAndMixedOriginalFacesKeepAllOriginalBytesExact() throws {
        let p = try partial()
        XCTAssertEqual(project(.partial(p), revealed: [0]), "你好。 See you next week.未知。")
        XCTAssertEqual(project(.partial(p), revealed: [3]), "Hello. 下周见。未知。")
        XCTAssertEqual(project(.partial(p), revealed: [0, 3]), text)
        XCTAssertEqual(Array(project(.partial(p), revealed: [0, 3]).utf8), Array(text.utf8))
    }
    func testTargetScriptAndImportedReadingsHaveExplicitDistinctSentencePolicies() throws {
        let p = try partial(target: "ja")
        XCTAssertEqual(project(.partial(p)), "konnichiwa. mata raishuu.未知。")
        XCTAssertEqual(project(.partial(p), script: true), "こんにちは。また来週。未知。")
        XCTAssertEqual(project(.partial(p), revealed: [0], script: true), "你好。また来週。未知。")
        XCTAssertEqual(project(.partial(p), revealed: [0, 3], script: true), text)
        XCTAssertEqual(project(.partial(p), revealed: [0]), "你好。 mata raishuu.未知。")
    }
    func testSourceGapsPunctuationAndUnknownUnitsDisableSentenceSeparator() throws {
        for gap in [" ", "  ", "\t", "\n", ",", "、", "?!", "未知。"] {
            let original = "你好。" + gap + "下周见。未知。", p = try partial(original)
            XCTAssertEqual(project(.partial(p)), "Hello." + gap + "See you next week.未知。")
            XCTAssertEqual(Array(project(.partial(p), revealed: Set(p.spans.map(\.id))).utf8), Array(original.utf8))
        }
    }
    func testOrdinaryCompleteWordSlotsDoNotGainSentencePolicyAndC1Stays() throws {
        let p = try partial()
        let ordinary = ImmersionResult(original: p.original, translation: "unused-synthetic-full", spans: p.spans)
        XCTAssertEqual(project(.complete(ordinary)), "Hello.See you next week.未知。")
        let words = ImmersionResult(
            original: "甲乙", translation: "unused",
            spans: [
                .init(
                    range: .init(location: 0, length: 1), original: "甲", translated: "hello",
                    targetRange: .init(location: 0, length: 5), romanization: nil),
                .init(
                    range: .init(location: 1, length: 1), original: "乙", translated: "world",
                    targetRange: .init(location: 5, length: 5), romanization: nil)
            ])
        XCTAssertEqual(project(.complete(words)), "hello world")
    }
    func testSelectionKeepsImportedFacesAtomicAndClippedOriginalUnprefixed() throws {
        let p = try partial()
        XCTAssertEqual(project(.partial(p), selection: .init(location: 3, length: 4)), "See you next week.")
        XCTAssertEqual(project(.partial(p), revealed: [3], selection: .init(location: 3, length: 4)), "下周见。")
        XCTAssertEqual(project(.partial(p), selection: .init(location: 1, length: 5)), "Hello. See you next week.")
        XCTAssertEqual(
            project(.partial(p), revealed: [0], selection: .init(location: 1, length: 6)), "好。See you next week.")
        XCTAssertEqual(project(.partial(p), revealed: [3], selection: .init(location: 0, length: 5)), "Hello.下周")
        XCTAssertEqual(project(.partial(p), selection: .init(location: 3, length: 0)), "")
    }
    func testActualSeparateFullTargetNeverChangesFacesOrReferenceTargetBasis() throws {
        let p = try partial(), provided = "Hi. See you next week. Unknown."
        let withFull = p.withCompleteTranslation(provided)
        XCTAssertEqual(project(.partial(withFull)), "Hello. See you next week.未知。")
        XCTAssertEqual(withFull.completeTranslation, provided)
        XCTAssertEqual(withFull.spans, p.spans)
        XCTAssertEqual(withFull.references, p.references)
    }
    func testPartialTargetMetadataRejectsCrossDirectionStructuralProof() throws {
        let p = try partial()
        XCTAssertTrue(SourceReferencePresentation.validPartial(p, target: "en"))
        XCTAssertFalse(SourceReferencePresentation.validPartial(p, target: "es"))
    }
}
