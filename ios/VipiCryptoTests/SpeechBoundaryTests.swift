import XCTest
@testable import Vipi

final class SpeechBoundaryTests: XCTestCase {
    func testAdjacentImportedWordsNeverSynthesizeAJoinedWord() {
        let spans = SpeechChunks.coalesced([
            ("明日、", "ja"), ("together", "en"), ("lunch", "en"), ("を食べませんか。", "ja")])
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
}
