import Foundation
import XCTest
@testable import VipiCore

final class ImmersionPresentationStateTests: XCTestCase {
    private let generation = UUID()
    private let value = ImmersionPresentation.complete(.init(original: "Hello", translation: "Hola", spans: []))
    private func identity(_ message: String = "message1", text: String = "Hello", source: String = "en",
                          target: String = "es", input: String? = nil, generation: UUID? = nil) -> ImmersionRequestIdentity {
        .init(messageID: message, text: text, source: source, target: target,
              inputLanguage: input, generation: generation ?? self.generation)
    }
    func testVisibleValueRequiresExactMessageTextDirectionInputAndGeneration() {
        let old = identity(); var state = ImmersionPresentationState()
        state.publish(value, for: old, current: old, paused: false)
        XCTAssertEqual(state.value(for: old), value)
        for changed in [identity("message2"), identity(text: "Changed"), identity(source: "fr"),
                        identity(target: "de"), identity(input: "en"), identity(generation: UUID())] {
            XCTAssertNil(state.value(for: changed))
        }
    }
    func testPausedOldDirectionCannotBecomeVisibleWhenResumed() {
        let old = identity(), current = identity(input: "es")
        var state = ImmersionPresentationState()
        state.publish(value, for: old, current: old, paused: true)
        state.resume(for: current)
        XCTAssertNil(state.value(for: current)); XCTAssertNil(state.value(for: old))
        state.publish(value, for: old, current: current, paused: false)
        XCTAssertNil(state.value(for: old)); XCTAssertNil(state.value(for: current))
    }
    func testPausedNilCompletionClearsOnlyCurrentVisibleValue() {
        let key = identity(); var state = ImmersionPresentationState()
        state.publish(value, for: key, current: key, paused: false)
        state.publish(nil, for: key, current: key, paused: true)
        XCTAssertEqual(state.value(for: key), value)
        state.resume(for: key); XCTAssertNil(state.value(for: key))
    }
    func testEveryPartialInsertionIsBoundedBeforeAnyProviderCompletion() {
        var cache = ImmersionPresentationCache()
        let partial = PartialImmersionResult(original: "Hello unknown", spans: [], references: [], nativeSourceTokenCount: 2)
        for index in 0..<300 {
            cache.remember(.partial(partial), key: "message\(index)")
            // Simulates a partial callback followed by provider cancellation:
            // there is deliberately NO completion insertion/eviction call.
            XCTAssertLessThanOrEqual(cache.count, 128)
        }
        XCTAssertNil(cache["message0"]); XCTAssertNotNil(cache["message299"])
        cache.remember(.partial(partial), key: "message299"); XCTAssertEqual(cache.count, 128)
        cache.removeAll(); XCTAssertEqual(cache.count, 0)
    }
    func testCacheHitPreservesOriginAndReportsZeroNewProviderCalls() throws {
        var cache = ImmersionPresentationCache()
        cache.remember(.init(result: value, origin: .lookupReference, status: .ready,
            localTranslationCalls: 0, fallbackStatus: nil), key: "known")
        let known = try XCTUnwrap(cache.cachedInvocation(key: "known"))
        XCTAssertTrue(known.cacheHit); XCTAssertEqual(known.origin, .lookupReference)
        cache.remember(.init(result: value, origin: .localFullContext, status: .ready,
            localTranslationCalls: 1, fallbackStatus: nil), key: "inferred")
        let inferred = try XCTUnwrap(cache.cachedInvocation(key: "inferred"))
        XCTAssertEqual(inferred.localTranslationCalls, 0); XCTAssertTrue(inferred.cacheHit)
        XCTAssertEqual(inferred.origin, .localFullContext)
    }
}
