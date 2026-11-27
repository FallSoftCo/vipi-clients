import XCTest
@testable import Vipi

final class SpeechBoundaryTests: XCTestCase {
    func testAdjacentImportedWordsNeverSynthesizeAJoinedWord() {
        let spans = SpeechChunks.coalesced([
            ("明日、", "ja"), ("together", "en"), ("lunch", "en"), ("を食べませんか。", "ja")
        ])
        XCTAssertEqual(spans.map(\.text), ["明日、", "together", "lunch", "を食べませんか。"])
        XCTAssertEqual(spans.map(\.language), ["ja", "en", "en", "ja"])
    }
    func testNaturalBoundariesStillShareOneUtterance() {
        let spans = SpeechChunks.coalesced([("Have ", "en"), ("lunch", "en"), ("?", "ja"), ("明日", "ja")])
        XCTAssertEqual(spans.map(\.text), ["Have lunch?", "明日"])
    }
    func testArabicAndDecomposedLatinKeepUnitBoundaries() {
        let spans = SpeechChunks.coalesced([("معاً", "ar"), ("غداء", "ar"), ("cafe\u{301}", "fr"), ("demain", "fr")])
        XCTAssertEqual(spans.map(\.text), ["معاً", "غداء", "cafe\u{301}", "demain"])
    }
    func testLongPunctuationAndCombiningTextPreserveEveryChunkAndTail() {
        let text = "Beginning " + String(repeating: ". ", count: 400) + "cafe\u{301} 👩🏽‍💻 final tail."
        let chunks = SpeechChunks.plan([(text, "en")])
        XCTAssertTrue(chunks.flatMap { $0 }.map(\.text).joined().utf8.elementsEqual(text.utf8))
        XCTAssertTrue(chunks.allSatisfy { $0.reduce(0) { $0 + $1.text.count } <= 160 })
        XCTAssertTrue(chunks.last!.contains { $0.text.contains("final tail") })
        XCTAssertTrue(chunks.contains { !$0.contains { SpeechChunks.hasSpokenContent($0.text) } })
    }
    func testPlanningChecksCancellationWithoutCuttingAnExtendedGrapheme() throws {
        enum Cancelled: Error { case requested }
        var checks = 0
        XCTAssertThrowsError(
            try SpeechChunks.plan(
                [(String(repeating: "👩🏽‍💻", count: 1000), "en")],
                checkCancellation: {
                    checks += 1
                    if checks == 3 { throw Cancelled.requested }
                }))
        XCTAssertEqual(checks, 3)
    }

}
