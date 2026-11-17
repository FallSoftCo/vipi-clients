import XCTest
@testable import Vipi

final class OriginalTextSelectionTests: XCTestCase {
    func testCompressedAttachmentsPreserveWhichRepeatedWordWasSelected() {
        let source = "book and book"
        let segments = [OriginalTextSegment(displayed: NSRange(location: 0, length: 1), original: NSRange(location: 0, length: 4), atomic: true),
                        OriginalTextSegment(displayed: NSRange(location: 1, length: 5), original: NSRange(location: 4, length: 5)),
                        OriginalTextSegment(displayed: NSRange(location: 6, length: 1), original: NSRange(location: 9, length: 4), atomic: true)]
        XCTAssertEqual(OriginalTextSelection.range(for: NSRange(location: 6, length: 1), segments: segments, original: source), NSRange(location: 9, length: 4))
        XCTAssertEqual(OriginalTextSelection.range(for: NSRange(location: 0, length: 7), segments: segments, original: source), NSRange(location: 0, length: 13))
    }
    func testPhraseSpansAnAttachmentAndExactOriginalPunctuation() {
        let source = "Coffee tomorrow?"
        let segments = [OriginalTextSegment(displayed: NSRange(location: 0, length: 1), original: NSRange(location: 0, length: 6), atomic: true),
                        OriginalTextSegment(displayed: NSRange(location: 1, length: 10), original: NSRange(location: 6, length: 10))]
        let range = OriginalTextSelection.range(for: NSRange(location: 0, length: 11), segments: segments, original: source)
        XCTAssertEqual(range, NSRange(location: 0, length: 16))
        XCTAssertEqual(range.map { (source as NSString).substring(with: $0) }, source)
    }
    func testUnicodeSelectionExpandsToWholeOriginalGrapheme() {
        let source = "🙂 cafe\u{301}"
        let segments = [OriginalTextSegment(displayed: NSRange(location: 0, length: 8), original: NSRange(location: 0, length: 8))]
        XCTAssertEqual(OriginalTextSelection.range(for: NSRange(location: 1, length: 1), segments: segments, original: source), NSRange(location: 0, length: 2))
        XCTAssertEqual(OriginalTextSelection.range(for: NSRange(location: 7, length: 1), segments: segments, original: source), NSRange(location: 6, length: 2))
    }
    func testEmptyMissingAndMalformedSelectionsFailClosed() {
        let segments = [OriginalTextSegment(displayed: NSRange(location: 0, length: 4), original: NSRange(location: 0, length: 4))]
        XCTAssertNil(OriginalTextSelection.range(for: NSRange(location: 0, length: 0), segments: segments, original: "book"))
        XCTAssertNil(OriginalTextSelection.range(for: NSRange(location: NSNotFound, length: 1), segments: segments, original: "book"))
        XCTAssertNil(OriginalTextSelection.range(for: NSRange(location: 8, length: 1), segments: segments, original: "book"))
        XCTAssertNil(OriginalTextSelection.range(for: NSRange(location: 3, length: 2), segments: segments, original: "book"))
    }
}
