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
        func emit() {
            let value = waiting
            waiting = nil
            value?.resume()
        }
        func refreshAuthorization() async throws { refreshes += 1 }
        func close() {
            closed = true
            let value = waiting
            waiting = nil
            value?.resume(throwing: CancellationError())
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
        let events = ForegroundEvents(
            connect: {
                opens += 1
                return opens == 1 ? first : second
            }, hint: { hints += 1 })
        defer { events.stop() }
        events.start()
        events.start()
        try await until { first.waiting != nil }
        XCTAssertEqual(opens, 1)
        first.emit()
        try await until { hints == 1 && first.waiting != nil }
        events.stop()
        first.emit()
        events.start()
        try await until { second.waiting != nil }
        XCTAssertTrue(first.closed)
        XCTAssertEqual(opens, 2)
        XCTAssertEqual(hints, 1)
        second.emit()
        try await until { hints == 2 }
    }
    func testNetworkReconnectBackoffAndRestrictedDeviceStop() async throws {
        var opens = 0, ended = 0, delays: [Double] = []
        let events = ForegroundEvents(
            connect: {
                opens += 1
                let value = Socket()
                value.failImmediately = true
                value.failureCode = opens == 4 ? 4403 : 0
                return value
            }, hint: { XCTFail("No hint expected") }, authorizationEnded: { ended += 1 }, sleep: { delays.append($0) },
            jitter: { 0 })
        defer { events.stop() }
        events.start()
        try await until { events.blocked }
        XCTAssertEqual(opens, 4)
        XCTAssertEqual(delays, [1, 2, 4])
        XCTAssertEqual(ended, 1)
        events.start()
        await Task.yield()
        XCTAssertEqual(opens, 4)
    }
    func testExpiredBearerRefreshIsBoundedWithoutAcceptedConnection() async throws {
        let first = Socket(), second = Socket()
        first.failImmediately = true
        first.failureCode = 4401
        second.failImmediately = true
        second.failureCode = 401
        var opens = 0
        let events = ForegroundEvents(
            connect: {
                opens += 1
                return opens == 1 ? first : second
            },
            hint: {}, sleep: { _ in }, jitter: { 0 })
        defer { events.stop() }
        events.start()
        try await until { events.blocked }
        XCTAssertEqual(opens, 2)
        XCTAssertEqual(first.refreshes, 1)
        XCTAssertEqual(second.refreshes, 0)
    }
    func testOnlyBoundedContentlessHintIsAccepted() {
        XCTAssertTrue(NativeEventSocket.validHint("{\"event\":\"inbox_changed\"}"))
        for text in [
            "{}", "[]", "{\"event\":\"message\"}",
            "{\"event\":\"inbox_changed\",\"sender\":\"someone\"}",
            "{\"event\":\"inbox_changed\",\"text\":\"private\"}",
            String(repeating: " ", count: 513) + "{\"event\":\"inbox_changed\"}"
        ] {
            XCTAssertFalse(NativeEventSocket.validHint(text))
        }
    }
}

extension ForegroundEventsTests {
    func testVisibleReadSurvivesOfflineAndAcceptRaceWithoutScrolling() async throws {
        let account = UUID(), peer = UUID()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("chat-activity-" + UUID().uuidString)
        let vault = try MessageVault(account: account, directory: root)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        func message(from sender: UUID, to recipient: UUID, state: String) -> StoredChat {
            StoredChat(
                envelope: ChatEnvelope(
                    id: UUID(), sender: sender, recipient: recipient, createdAt: 1,
                    type: 3, ciphertext: Data([3])), text: "fixture", state: state)
        }
        let incoming = message(from: peer, to: account, state: "delivered")
        let hidden = message(from: peer, to: account, state: "delivered")
        let outgoing = message(from: account, to: peer, state: "queued")
        func put(_ bucket: String, _ item: StoredChat) throws {
            try vault.put(bucket, item.envelope.id.uuidString.lowercased(), JSONEncoder().encode(item))
        }
        try vault.transaction {
            try put("incoming", incoming)
            try put("incoming", hidden)
            try put("outgoing", outgoing)
        }
        var attempts = 0
        let offline = ChatActivityEvents(
            vault: vault, eligible: { $0 == peer }, sendTyping: { _, _ in },
            receipts: { _, _, _ in
                attempts += 1
                throw URLError(.notConnectedToInternet)
            }, changed: {})
        offline.visible(peer, incoming: [incoming.envelope.id], outgoing: [outgoing.envelope.id])
        try await until { attempts == 1 }
        offline.close()
        var seen = [UUID](), checked = [UUID](), updates = 0
        let restored = ChatActivityEvents(
            vault: vault, eligible: { $0 == peer }, sendTyping: { _, _ in },
            receipts: { _, ids, queries in
                seen.append(contentsOf: ids)
                checked.append(contentsOf: queries)
                return ChatReadReply(acknowledged: ids, read: queries)
            }, changed: { updates += 1 })
        defer { restored.close() }
        restored.visible(peer, incoming: [incoming.envelope.id], outgoing: [outgoing.envelope.id])
        try await until { seen == [incoming.envelope.id] }
        XCTAssertTrue(checked.isEmpty)
        let journal = MessageJournal(vault: vault)
        try journal.applyStatus(outgoing.envelope.id, state: "accepted")
        restored.outgoingAccepted(outgoing.envelope.id, peer: peer)
        try await until { updates == 1 }
        XCTAssertEqual(checked, [outgoing.envelope.id])
        XCTAssertFalse(seen.contains(hidden.envelope.id))
        try journal.applyStatus(outgoing.envelope.id, state: "delivered")
        XCTAssertEqual(try journal.outgoing(outgoing.envelope.id)?.state, "read")
    }
    func testTypedEventDecoderAcceptsOnlyBoundedMetadata() {
        let peer = UUID(), id = peer.uuidString.lowercased()
        XCTAssertEqual(
            ChatForegroundEvent.decode(#"{"event":"typing","peer":"\#(id)","active":true}"#), .typing(peer, true))
        XCTAssertEqual(ChatForegroundEvent.decode(#"{"event":"receipts_changed","peer":"\#(id)"}"#), .receipts(peer))
        for invalid in [
            #"{"event":"typing","peer":"\#(id)","active":1}"#,
            #"{"event":"typing","peer":"\#(id)","active":"true"}"#,
            #"{"event":"typing","peer":"\#(id)","active":true,"draft":"no"}"#,
            #"{"event":"receipts_changed","peer":"not-a-uuid"}"#,
            String(repeating: " ", count: 513) + #"{"event":"inbox_changed"}"#
        ] { XCTAssertNil(ChatForegroundEvent.decode(invalid)) }
    }
}
