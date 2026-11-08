import XCTest
@testable import Vipi

@MainActor final class ForegroundEventsTests: XCTestCase {
    private final class Socket: ForegroundEventSocket {
        var failureCode = 0
        var failImmediately = false
        var closed = false
        var refreshes = 0
        var waiting: CheckedContinuation<Void, Error>?
        func receiveHint() async throws {
            if failImmediately { throw URLError(.networkConnectionLost) }
            try await withCheckedThrowingContinuation { waiting = $0 }
        }
        func emit() { let value = waiting; waiting = nil; value?.resume() }
        func refreshAuthorization() async throws { refreshes += 1 }
        func close() {
            closed = true
            let value = waiting; waiting = nil; value?.resume(throwing: CancellationError())
        }
    }
    private func until(_ condition: @MainActor () -> Bool) async throws {
        for _ in 0..<100 {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("Foreground event state did not settle")
    }
    func testOneConnectionAndCancellationSuppressOldAccountHints() async throws {
        let first = Socket(), second = Socket()
        var opens = 0, hints = 0
        let events = ForegroundEvents(connect: { opens += 1; return opens == 1 ? first : second }, hint: { hints += 1 })
        defer { events.stop() }
        events.start(); events.start()
        try await until { first.waiting != nil }
        XCTAssertEqual(opens, 1)
        first.emit(); try await until { hints == 1 && first.waiting != nil }
        events.stop(); first.emit()
        events.start(); try await until { second.waiting != nil }
        XCTAssertTrue(first.closed); XCTAssertEqual(opens, 2); XCTAssertEqual(hints, 1)
        second.emit(); try await until { hints == 2 }
    }
    func testNetworkReconnectBackoffAndRestrictedDeviceStop() async throws {
        var opens = 0, ended = 0, delays: [Double] = []
        let events = ForegroundEvents(connect: {
            opens += 1
            let value = Socket(); value.failImmediately = true
            value.failureCode = opens == 4 ? 4403 : 0
            return value
        }, hint: { XCTFail("No hint expected") }, authorizationEnded: { ended += 1 }, sleep: { delays.append($0) }, jitter: { 0 })
        defer { events.stop() }
        events.start(); try await until { events.blocked }
        XCTAssertEqual(opens, 4); XCTAssertEqual(delays, [1, 2, 4]); XCTAssertEqual(ended, 1)
        events.start(); await Task.yield(); XCTAssertEqual(opens, 4)
    }
    func testExpiredBearerRefreshIsBoundedWithoutAcceptedConnection() async throws {
        let first = Socket(), second = Socket()
        first.failImmediately = true; first.failureCode = 4401
        second.failImmediately = true; second.failureCode = 401
        var opens = 0
        let events = ForegroundEvents(connect: { opens += 1; return opens == 1 ? first : second },
            hint: {}, sleep: { _ in }, jitter: { 0 })
        defer { events.stop() }
        events.start(); try await until { events.blocked }
        XCTAssertEqual(opens, 2); XCTAssertEqual(first.refreshes, 1); XCTAssertEqual(second.refreshes, 0)
    }
    func testOnlyBoundedContentlessHintIsAccepted() {
        XCTAssertTrue(NativeEventSocket.validHint("{\"event\":\"inbox_changed\"}"))
        for text in ["{}", "[]", "{\"event\":\"message\"}",
                     "{\"event\":\"inbox_changed\",\"sender\":\"someone\"}",
                     "{\"event\":\"inbox_changed\",\"text\":\"private\"}",
                     String(repeating: " ", count: 513) + "{\"event\":\"inbox_changed\"}"] {
            XCTAssertFalse(NativeEventSocket.validHint(text))
        }
    }
}
