import Foundation
import XCTest
@testable import VipiCore

/// Exact raw-encoded cache/request boundaries only. Not a linguistic matching policy.
final class ImmersionRawCacheIdentityTests: XCTestCase {
    private let nfc = "Hello. @caf\u{e9}", nfd = "Hello. @cafe\u{301}"
    private let generation = UUID()
    private func identity(_ text: String) -> ImmersionRequestIdentity {
        .init(
            messageID: "same-message", text: text, source: "en", target: "es", inputLanguage: "en",
            generation: generation)
    }
    private func full(_ text: String, target: String, origin: ImmersionOrigin = .lookupReference, calls: Int = 0)
        -> LookupFirstOutcome
    {
        .init(
            result: .complete(.init(original: text, translation: target, spans: [])), origin: origin,
            status: .ready, localTranslationCalls: calls, fallbackStatus: nil)
    }
    private func partial(_ text: String) throws -> ImmersionPresentation {
        .partial(
            try XCTUnwrap(
                SourceReferencePresentation.create(
                    original: text, target: "es",
                    units: [
                        .init(
                            range: .init(location: 0, length: 6), original: "Hello.", translated: "Hola.", reading: nil,
                            referenceID: "authored-cache-reference", catalogSHA256: String(repeating: "a", count: 64),
                            nativeSourceTokens: 1)
                    ],
                    density: 1, nativeSourceTokenCount: 2)))
    }
    func testCompleteRawKeysCannotHitOrReplaceCanonicalEquivalentMessage() throws {
        XCTAssertEqual(nfc, nfd)
        XCTAssertFalse(Array(nfc.utf8) == Array(nfd.utf8))
        var cache = ImmersionPresentationCache()
        cache.remember(full(nfc, target: "Hola. @caf\u{e9}"), key: "en:" + nfc)
        XCTAssertNil(cache["en:" + nfd])
        XCTAssertNil(cache.cachedInvocation(key: "en:" + nfd))
        cache.remember(full(nfd, target: "Hola. @cafe\u{301}", origin: .localFullContext, calls: 1), key: "en:" + nfd)
        XCTAssertEqual(cache.count, 2)
        let first = try XCTUnwrap(cache.cachedInvocation(key: "en:" + nfc))
        let second = try XCTUnwrap(cache.cachedInvocation(key: "en:" + nfd))
        XCTAssertEqual(Array((first.result?.original ?? "").utf8), Array(nfc.utf8))
        XCTAssertEqual(Array((second.result?.original ?? "").utf8), Array(nfd.utf8))
        XCTAssertEqual(Array((first.result?.translation ?? "").utf8), Array("Hola. @caf\u{e9}".utf8))
        XCTAssertEqual(Array((second.result?.translation ?? "").utf8), Array("Hola. @cafe\u{301}".utf8))
        XCTAssertEqual(first.origin, .lookupReference)
        XCTAssertEqual(second.origin, .localFullContext)
        XCTAssertTrue(first.cacheHit)
        XCTAssertTrue(second.cacheHit)
        XCTAssertEqual(first.localTranslationCalls, 0)
        XCTAssertEqual(second.localTranslationCalls, 0)
    }
    func testPartialRawKeysKeepBothEncodedOriginalsAndReferenceProofs() throws {
        var cache = ImmersionPresentationCache()
        cache.remember(try partial(nfc), key: "auto:" + nfc)
        XCTAssertNil(cache["auto:" + nfd])
        cache.remember(try partial(nfd), key: "auto:" + nfd)
        XCTAssertEqual(cache.count, 2)
        let first = try XCTUnwrap(cache.cachedInvocation(key: "auto:" + nfc))
        let second = try XCTUnwrap(cache.cachedInvocation(key: "auto:" + nfd))
        XCTAssertEqual(Array((first.result?.original ?? "").utf8), Array(nfc.utf8))
        XCTAssertEqual(Array((second.result?.original ?? "").utf8), Array(nfd.utf8))
        XCTAssertNil(first.result?.translation)
        XCTAssertNil(second.result?.translation)
        XCTAssertEqual(first.result?.spans.first?.targetRange, NSRange(location: 0, length: 5))
        XCTAssertEqual(first.origin, .sourceReferencePartial)
        XCTAssertEqual(second.origin, .sourceReferencePartial)
        XCTAssertTrue(first.cacheHit)
        XCTAssertEqual(first.localTranslationCalls, 0)
    }
    func testSameMessageRawEncodingIsPartOfEqualityAndHashCollectionIdentity() {
        let first = identity(nfc), second = identity(nfd)
        XCTAssertEqual(first.text, second.text)  // Swift canonical equivalence still exists.
        XCTAssertFalse(first == second)
        XCTAssertEqual(Set([first, second]).count, 2)
    }
    func testVisibleOriginalCannotSurviveSameMessageRawEncodingChange() {
        let first = identity(nfc), second = identity(nfd)
        var state = ImmersionPresentationState()
        state.publish(full(nfc, target: "Hola. @caf\u{e9}").result, for: first, current: first, paused: false)
        XCTAssertNil(state.value(for: second))
        state.invalidate(for: second)
        XCTAssertNil(state.value(for: first))
        XCTAssertNil(state.value(for: second))
        state.publish(full(nfc, target: "Hola. @caf\u{e9}").result, for: first, current: second, paused: false)
        XCTAssertNil(state.value(for: second))
    }
    func testPausedPendingCannotResumeAcrossSameMessageRawEncodingChange() {
        let first = identity(nfc), second = identity(nfd)
        var state = ImmersionPresentationState()
        state.publish(full(nfc, target: "Hola. @caf\u{e9}").result, for: first, current: first, paused: true)
        state.resume(for: second)
        XCTAssertNil(state.value(for: second))
        XCTAssertNil(state.value(for: first))
    }
    func testEncodedKeyOrderRetainsIndependentEntriesAnd128Bound() throws {
        var cache = ImmersionPresentationCache()
        for index in 0..<80 {
            let a = "\(index):" + nfc, b = "\(index):" + nfd
            cache.remember(full(a, target: a), key: "en:" + a)
            cache.remember(full(b, target: b), key: "en:" + b)
        }
        XCTAssertEqual(cache.count, 128)
        XCTAssertNil(cache["en:0:" + nfc])
        XCTAssertNil(cache["en:0:" + nfd])
        let first = try XCTUnwrap(cache["en:79:" + nfc]), second = try XCTUnwrap(cache["en:79:" + nfd])
        XCTAssertEqual(Array(first.original.utf8), Array(("79:" + nfc).utf8))
        XCTAssertEqual(Array(second.original.utf8), Array(("79:" + nfd).utf8))
    }
}
