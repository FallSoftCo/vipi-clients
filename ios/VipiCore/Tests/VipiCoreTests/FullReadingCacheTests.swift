import XCTest
@testable import VipiCore

private actor ReadingProbe {
    private(set) var calls: [String: Int] = [:]
    private var held: [CheckedContinuation<Void, Never>] = []
    func read(_ text: String, _ language: String) async -> FullReading? {
        calls[text + language, default: 0] += 1
        if text == "held" { await withCheckedContinuation { held.append($0) } }
        return text == "unknown" ? nil : FullReading(text: text + language, provenance: .authored)
    }
    func count(_ text: String, _ language: String) -> Int { calls[text + language, default: 0] }
    func waiting() -> Int { held.count }
    func release() { let all = held; held.removeAll(); for value in all { value.resume() } }
}

@MainActor final class FullReadingCacheTests: XCTestCase {
    private func waitForHeld(_ probe: ReadingProbe, count: Int) async throws {
        for _ in 0..<200 {
            if await probe.waiting() == count { return }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("Bounded producer did not reach its explicit test gate")
    }
    func testCoalescesAndCachesUnavailableWithoutBlockingIndependentText() async throws {
        let probe = ReadingProbe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
        let first = Task { await cache.resolve(text: "held", language: "zh") }
        let second = Task { await cache.resolve(text: "held", language: "zh") }
        try await waitForHeld(probe, count: 1)
        let other = await cache.resolve(text: "other", language: "ja")
        XCTAssertEqual(other?.text, "otherja")
        await probe.release()
        let a = await first.value, b = await second.value
        XCTAssertEqual(a, b)
        let calls = await probe.count("held", "zh"); XCTAssertEqual(calls, 1)
        for _ in 0..<3 { let missing = await cache.resolve(text: "unknown", language: "zh"); XCTAssertNil(missing) }
        let misses = await probe.count("unknown", "zh"); XCTAssertEqual(misses, 1)
        XCTAssertEqual(cache.count, 3)
    }
    func testResetRejectsLateCompletionAndStartsFreshGeneration() async throws {
        let probe = ReadingProbe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
        let old = Task { await cache.resolve(text: "held", language: "zh") }
        try await waitForHeld(probe, count: 1)
        cache.removeAll()
        let new = Task { await cache.resolve(text: "held", language: "zh") }
        try await waitForHeld(probe, count: 2)
        await probe.release()
        let obsolete = await old.value, fresh = await new.value
        XCTAssertNil(obsolete); XCTAssertEqual(fresh?.text, "heldzh")
        XCTAssertEqual(cache.count, 1)
        XCTAssertEqual(cache.cached(text: "held", language: "zh"), fresh)
    }
    func testCancelledWaiterDoesNotCancelAnotherRow() async throws {
        let probe = ReadingProbe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
        let first = Task { await cache.resolve(text: "held", language: "zh") }
        let second = Task { await cache.resolve(text: "held", language: "zh") }
        try await waitForHeld(probe, count: 1)
        first.cancel(); await probe.release()
        let a = await first.value, b = await second.value
        XCTAssertNil(a); XCTAssertEqual(b?.text, "heldzh")
        XCTAssertEqual(cache.cached(text: "held", language: "zh"), b)
    }
    func testExactEncodingLanguageAndBoundedEviction() async {
        let probe = ReadingProbe(), cache = FullReadingCache(policy: "test") { await probe.read($0, $1) }
        for text in ["é", "e\u{301}"] { _ = await cache.resolve(text: text, language: "zh") }
        _ = await cache.resolve(text: "é", language: "ja")
        XCTAssertEqual(cache.count, 3) // Swift canonical String equality is not the cache key.
        for index in 0..<129 { _ = await cache.resolve(text: "row\(index)", language: "zh") }
        XCTAssertEqual(cache.count, 128)
        XCTAssertNil(cache.cached(text: "é", language: "zh"))
        XCTAssertEqual(cache.cached(text: "row128", language: "zh")?.text, "row128zh")
        let tooLong = await cache.resolve(text: String(repeating: "x", count: FullMessageBudget.recordBytes + 1), language: "zh")
        let unsupported = await cache.resolve(text: "hello", language: "en")
        XCTAssertNil(tooLong); XCTAssertNil(unsupported); XCTAssertEqual(cache.count, 128)
        cache.removeAll(); XCTAssertEqual(cache.count, 0)
    }
    func testDerivedReadingKeepsCompleteUnicodeTailAndBoundsResidentBytes() async {
        let cache = FullReadingCache(policy:"long",byteLimit:900) { text,_ in
            .init(text:text + " café\u{301} 👩🏽‍💻 tail",provenance:.localTransliteration)
        }
        for index in 0..<8 {
            let original = String(repeating:"字",count:60) + "\(index)"
            let value = await cache.resolve(text:original,language:"zh")
            XCTAssertEqual(value?.text,original + " café\u{301} 👩🏽‍💻 tail")
            XCTAssertLessThanOrEqual(cache.residentBytes,900)
        }
        let full = FullReadingCache(policy:"expanded") { text,_ in .init(text:String(repeating:"hàn ",count:text.count),provenance:.localTransliteration) }
        let text = String(repeating:"汉",count:22_000)
        let expanded = await full.resolve(text:text,language:"zh")
        XCTAssertEqual(expanded?.text,String(repeating:"hàn ",count:22_000))
    }

}
