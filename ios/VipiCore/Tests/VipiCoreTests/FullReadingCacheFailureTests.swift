import XCTest
import VipiCore

private actor FailureReadingProbe {
    private(set) var count = 0
    let result: FullReading?
    init(_ result: FullReading?) { self.result = result }
    func read() -> FullReading? {
        count += 1
        return result
    }
}

@MainActor final class FullReadingCacheFailureTests: XCTestCase {
    func testOversizedOutputDropsTextButCachesBoundedStaticReason() async {
        let probe = FailureReadingProbe(
            .init(
                text: String(repeating: "x", count: FullMessageBudget.recordBytes + 1),
                provenance: .localTransliteration))
        let cache = FullReadingCache(policy: "output-limit") { _, _ in await probe.read() }
        let result = await cache.resolveDetailed(text: "明天", language: "zh")
        XCTAssertNil(result.value)
        XCTAssertEqual(result.failure, .outputLimit)
        XCTAssertNil(cache.cached(text: "明天", language: "zh"))
        XCTAssertEqual(cache.failure(text: "明天", language: "zh"), .outputLimit)
        XCTAssertEqual(cache.residentBytes, "明天".utf8.count + 128)
        let again = await cache.resolve(text: "明天", language: "zh")
        XCTAssertNil(again)
        let count = await probe.count
        XCTAssertEqual(count, 1)
        cache.removeResolved(text: "明天", language: "zh")
        XCTAssertNil(cache.failure(text: "明天", language: "zh"))
        XCTAssertEqual(cache.residentBytes, 0)
    }
    func testEmptyAndDetailedFailureNeverReturnAnAvailableReading() async {
        for value in [
            FullReading(text: " \n\t", provenance: .localTransliteration),
            FullReading(text: "partial 天", provenance: .localTransliteration, failure: .unresolved)
        ] {
            let cache = FullReadingCache(policy: "known-failure") { _, _ in value }
            let result = await cache.resolveDetailed(text: "明天", language: "zh")
            XCTAssertNil(result.value)
            XCTAssertEqual(result.failure, .unresolved)
            XCTAssertNil(cache.cached(text: "明天", language: "zh"))
            XCTAssertEqual(cache.residentBytes, "明天".utf8.count + 128)
        }
    }
    func testCompletedReasonSurvivesImmediateBudgetEviction() async {
        let cache = FullReadingCache(policy: "tiny", byteLimit: 1) { _, _ in
            .init(text: "", provenance: .localTransliteration, failure: .outputLimit)
        }
        let result = await cache.resolveDetailed(text: "明天", language: "zh")
        XCTAssertNil(result.value)
        XCTAssertEqual(result.failure, .outputLimit)
        XCTAssertEqual(cache.count, 0)
        XCTAssertEqual(cache.residentBytes, 0)
        XCTAssertNil(cache.failure(text: "明天", language: "zh"))
    }
    func testUnknownNilHasNoInventedStaticReason() async {
        let cache = FullReadingCache(policy: "unknown") { _, _ in nil }
        let result = await cache.resolveDetailed(text: "明天", language: "zh")
        XCTAssertNil(result.value)
        XCTAssertNil(result.failure)
        XCTAssertTrue(cache.hasResolved(text: "明天", language: "zh"))
    }
}
