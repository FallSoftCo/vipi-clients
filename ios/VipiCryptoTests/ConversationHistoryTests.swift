import Foundation
import XCTest
@testable import Vipi

final class ConversationHistoryTests: XCTestCase {
    func testGroupedChronologyKeepsGapsAndDayBoundariesVisible() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
        let beforeMidnight = try XCTUnwrap(
            calendar.date(from: DateComponents(year: 2026, month: 11, day: 19, hour: 23, minute: 59)))
        XCTAssertNotNil(
            MessageTimelineMetadata.timeLabel(
                for: beforeMidnight, previous: nil, now: beforeMidnight, calendar: calendar))
        XCTAssertNil(
            MessageTimelineMetadata.timeLabel(
                for: beforeMidnight.addingTimeInterval(30), previous: beforeMidnight, now: beforeMidnight,
                calendar: calendar))
        XCTAssertNotNil(
            MessageTimelineMetadata.timeLabel(
                for: beforeMidnight.addingTimeInterval(60), previous: beforeMidnight, now: beforeMidnight,
                calendar: calendar))
        XCTAssertNotNil(
            MessageTimelineMetadata.timeLabel(
                for: beforeMidnight.addingTimeInterval(-300), previous: beforeMidnight.addingTimeInterval(-600),
                now: beforeMidnight, calendar: calendar))
        XCTAssertEqual(
            MessageTimelineMetadata.timeLabel(
                for: beforeMidnight, previous: nil, now: beforeMidnight.addingTimeInterval(86_400), calendar: calendar),
            beforeMidnight.formatted(date: .abbreviated, time: .shortened))
    }
    func testGroupingNeverHidesUnsentFailedOrImportedState() {
        for state in ["queued", "failed", "expired", "cancelled", "draft", "imported"] {
            XCTAssertTrue(MessageTimelineMetadata.showsFriendState(state, outgoing: true, latestOutgoing: false), state)
        }
        XCTAssertTrue(MessageTimelineMetadata.showsFriendState("imported", outgoing: false, latestOutgoing: false))
        for state in ["accepted", "delivered"] {
            XCTAssertFalse(MessageTimelineMetadata.showsFriendState(state, outgoing: true, latestOutgoing: false))
            XCTAssertTrue(MessageTimelineMetadata.showsFriendState(state, outgoing: true, latestOutgoing: true))
        }
    }
    private enum Interrupted: Error { case write }
    func testOversizedEditableDraftReopensButOutgoingLimitRemains() throws {
        let account = UUID(), peer = UUID()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "history-draft-limit-" + UUID().uuidString)
        let pasted = String(repeating: "界", count: 10_923)
        let vault = try MessageVault(account: account, directory: root)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        let history = try ConversationHistory(vault: vault)
        try history.saveComposeDraft(pasted, peer: peer)
        XCTAssertThrowsError(
            try MessageJournal(vault: vault).saveDraft(
                id: UUID(), recipient: peer, text: pasted, createdAt: 1_800_000_000_000, now: 1_800_000_000_000))
        XCTAssertTrue(try history.messages(peer: peer).isEmpty)
        let reopened = try MessageVault(account: account, directory: root)
        defer { try? reopened.close() }
        let restored = try ConversationHistory(vault: reopened)
        XCTAssertEqual(try restored.composeDraft(peer), pasted)
        let atLimit = String(repeating: "a", count: ConversationHistory.maximumDraftBytes)
        try restored.saveComposeDraft(atLimit, peer: peer)
        XCTAssertThrowsError(try restored.saveComposeDraft(atLimit + "a", peer: peer))
        XCTAssertEqual(try restored.composeDraft(peer), atLimit)
        try restored.saveComposeDraft("Shortened café ☕", peer: peer)
        XCTAssertEqual(try history.composeDraft(peer), "Shortened café ☕")
    }

    func testVoiceDraftIsConsumedExactlyOnceAndKeepsTextDraft() throws {
        let account = UUID(), peer = UUID(), now: Int64 = 1_800_000_000_000
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let vault = try MessageVault(account: account, directory: root)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        let history = try ConversationHistory(vault: vault)
        let journal = MessageJournal(vault: vault)
        let original = MediaPart(
            blobID: UUID().uuidString.lowercased(), role: "original", plaintextBytes: 40,
            ciphertextBytes: 68, ciphertextSHA256: String(repeating: "a", count: 64))
        let manifest = AttachmentManifest(
            version: 1, id: UUID().uuidString.lowercased(), kind: .voice,
            key: MediaCryptography.freshKey(), original: original, thumbnail: nil,
            filename: "Voice.m4a", contentType: "audio/mp4", width: nil, height: nil, durationMillis: 1300)
        try history.saveComposeDraft("Keep typing here", peer: peer)
        let key = peer.uuidString.lowercased()
        try vault.transaction { try vault.put("voice-compose", key, JSONEncoder().encode(manifest)) }
        func send(_ expected: String) throws {
            try journal.saveDraft(
                id: UUID(), recipient: peer, text: "Voice message", createdAt: now, now: now,
                consumeVoice: expected, attachments: [manifest])
        }
        XCTAssertThrowsError(try send("stale draft"))
        XCTAssertTrue(try history.messages(peer: peer).isEmpty)
        try send(manifest.id)
        XCTAssertThrowsError(try send(manifest.id))
        XCTAssertEqual(try history.messages(peer: peer).count, 1)
        XCTAssertEqual(try history.composeDraft(peer), "Keep typing here")
        XCTAssertNil(try vault.transaction { try vault.get("voice-compose", key) })
    }

    func testHistoryPaginationDraftsUnreadAndReceiptRecovery() throws {
        let account = UUID(), peer = UUID(), other = UUID(), now: Int64 = 1_800_000_000_000
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("HistoryQA/\(UUID())")
        let vault = try MessageVault(account: account, directory: root), journal = MessageJournal(vault: vault)
        let history = try ConversationHistory(vault: vault)
        try history.saveComposeDraft("Unsent café ☕", peer: peer)
        var identifiers: Set<UUID> = []
        for offset in 0..<27 {
            let id = UUID()
            identifiers.insert(id)
            try journal.saveDraft(
                id: id, recipient: peer, text: "History \(offset)", createdAt: now + Int64(offset / 3), now: now)
        }
        try journal.saveDraft(id: UUID(), recipient: other, text: "Other conversation", createdAt: now, now: now)
        let first = try history.messages(peer: peer, limit: 10)
        XCTAssertEqual(first.count, 10)
        let fresh = UUID()
        try journal.saveDraft(id: fresh, recipient: peer, text: "Arrived while paging", createdAt: now + 100, now: now)
        let second = try history.messages(peer: peer, before: first.last!.cursor, limit: 10)
        let third = try history.messages(peer: peer, before: second.last!.cursor, limit: 10)
        XCTAssertEqual(Set((first + second + third).map(\.id)), identifiers)
        XCTAssertEqual(first.count + second.count + third.count, 27)
        XCTAssertEqual(try history.messages(peer: peer).first?.id, fresh)
        XCTAssertEqual(try history.messages(peer: other).count, 1)
        XCTAssertThrowsError(try history.messages(peer: peer, limit: 101))
        XCTAssertEqual(
            try ConversationHistory(vault: MessageVault(account: account, directory: root)).composeDraft(peer),
            "Unsent café ☕")
        XCTAssertThrowsError(
            try journal.queue(id: fresh, recipient: peer, text: "Arrived while paging", createdAt: now + 100, now: now)
            { _ in throw Interrupted.write })
        XCTAssertEqual(try history.messages(peer: peer).first?.state, "queued")
        _ = try journal.queue(id: fresh, recipient: peer, text: "Arrived while paging", createdAt: now + 100, now: now)
        { _ in (2, Data(repeating: 7, count: 64)) }
        try journal.applyStatus(fresh, state: "delivered")
        XCTAssertEqual(try history.messages(peer: peer).first?.state, "delivered")
        XCTAssertEqual(try history.messages(peer: peer).count, 28, "Draft conversion must not duplicate the row")

        let id = UUID(),
            incoming = ChatEnvelope(
                id: id, sender: peer, recipient: account, createdAt: now - 1, type: 2,
                ciphertext: Data(repeating: 9, count: 64))
        let clear = try JSONSerialization.data(withJSONObject: [
            "version": 1, "id": id.uuidString.lowercased(), "sender": peer.uuidString.lowercased(),
            "recipient": account.uuidString.lowercased(), "createdAt": now - 1, "text": "An older reply"
        ])
        XCTAssertThrowsError(try journal.receive(incoming, now: now) { _, _ in throw Interrupted.write })
        XCTAssertTrue(try journal.pendingReceipts().isEmpty)
        _ = try journal.receive(incoming, now: now) { _, _ in clear }
        _ = try journal.receive(incoming, now: now) { _, _ in
            XCTFail("Duplicate decryption")
            return Data()
        }
        XCTAssertEqual(try history.threads().first?.latest.id, fresh)
        XCTAssertEqual(try history.threads().first?.unread, 1)
        let reopened = try MessageVault(account: account, directory: root),
            reopenedJournal = MessageJournal(vault: reopened)
        XCTAssertEqual(try reopenedJournal.pendingReceipts(), [id])
        try ConversationHistory(vault: reopened).markRead(peer)
        XCTAssertEqual(try history.threads().first?.unread, 0)
        try reopenedJournal.receiptAccepted(id)
        XCTAssertTrue(try journal.pendingReceipts().isEmpty)
        _ = try journal.receive(incoming, now: now) { _, _ in
            XCTFail("Duplicate decryption")
            return Data()
        }
        XCTAssertEqual(try history.threads().first?.unread, 0)
        XCTAssertEqual(try journal.pendingReceipts(), [id], "A repeated delivery must retry the lost receipt")
        // Upgrade from journals written before the index existed, without deleting content.
        try vault.transaction {
            for kind in ["history", "thread"] { for key in try vault.ids(kind) { try vault.remove(kind, key) } }
            try vault.remove("metadata", "history-index")
        }
        let upgraded = try ConversationHistory(vault: vault)
        XCTAssertEqual(try upgraded.messages(peer: peer).count, 29)
        XCTAssertEqual(try upgraded.threads().first?.unread, 0)
        XCTAssertEqual(try upgraded.messages(peer: peer).first?.state, "delivered")
        _ = try journal.pendingDrafts(now: now + MessageJournal.ttl + 100)
        XCTAssertEqual(try upgraded.messages(peer: peer).filter { $0.state == "expired" }.count, 27)
    }
}
