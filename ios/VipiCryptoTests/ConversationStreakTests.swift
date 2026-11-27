import XCTest
@testable import Vipi

final class ConversationStreakTests: XCTestCase {
    func testGroupInboxUsesOnlyVisibleAcceptedHistoryAcrossPages() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let owner = UUID(), peer = UUID(), group = UUID()
        let vault = try MessageVault(account: owner, directory: root)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: root)
            try? KeychainStore.deleteChecked(account: "messages-" + owner.uuidString.lowercased())
        }
        let store = GroupsStore(vault: vault)
        var read: Set<UUID> = []
        try vault.transaction {
            for i in 0..<70 {
                let message = GroupMessage(id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: peer,
                                           text: "Message \(i)", createdAt: Int64(i), delivery: .received)
                try store.saveMessageInTransaction(message)
                if i < 68 { read.insert(message.id) }
            }
            try store.saveMessageInTransaction(.init(id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: peer,
                                                     text: "Private held body", createdAt: 71, delivery: .withheld, withheldReason: "approval"))
            try store.saveMessageInTransaction(.init(id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: owner,
                                                     text: "Unsent", createdAt: 72, delivery: .queued))
            try store.saveMessageInTransaction(.init(id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: peer,
                                                     text: "Reaction", createdAt: 73, delivery: .received,
                                                     features: .init(reaction: .init(message_id: UUID(), target_sender_id: owner, sequence: 1, emoji: "❤️"))))
        }
        try store.markRead(group, visible: read)
        let summary = try await GroupInboxSummary.load(vault, group: group)
        XCTAssertEqual(summary.unread, 2)
        XCTAssertEqual(summary.latest?.line, "Message 69")
        XCTAssertEqual(summary.latest?.timestamp, 69)
    }

    func testDurableWholeHistoryDaysAndLegitimateDeliveryTransitions() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let owner = UUID(), peer = UUID(), other = UUID(), third = UUID()
        let vault = try MessageVault(account: owner, directory: root)
        defer {
            try? vault.close(); try? FileManager.default.removeItem(at: root)
            try? KeychainStore.deleteChecked(account: "messages-" + owner.uuidString.lowercased())
        }
        let day = ConversationStreak.millisecondsPerDay
        let journal = MessageJournal(vault: vault)
        // Write the pre-feature schema directly; no new on-write hooks may qualify these records.
        func legacy(_ id: UUID, from: UUID, state: String, at: Int64) throws {
            let incoming = from == peer, kind = incoming ? "incoming" : "outgoing"
            let row = StoredChat(envelope: .init(id: id, sender: from, recipient: incoming ? owner : peer, createdAt: at,
                type: 3, ciphertext: Data([1])), text: "Test", state: state)
            let key = id.uuidString.lowercased(), prefix = peer.uuidString.lowercased() + "/"
            try vault.put(kind, key, JSONEncoder().encode(row))
            try vault.put("history", prefix + String(format: "%019lld", at) + "/" + key, JSONEncoder().encode(ConversationHistory.Reference(kind: kind, id: id)))
        }
        let pending = UUID()
        try vault.transaction {
            for index in (1...105).reversed() {
                try legacy(UUID(), from: peer, state: "delivered", at: Int64(index) * day)
                try legacy(index == 104 ? pending : UUID(), from: owner, state: index == 104 ? "accepted" : "read", at: Int64(index + 1) * day - 1)
            }
            let restored = HistoryBackupMessage(id: UUID(), peer: peer, outgoing: true, createdAt: 104 * day, text: "Imported")
            try vault.put("imported", restored.id.uuidString.lowercased(), JSONEncoder().encode(restored))
            try ConversationHistory.record(vault, kind: "imported", id: restored.id, peer: peer, createdAt: restored.createdAt)
        }
        let loaded = try await ConversationStreak.load(vault, scope: .direct, id: peer, through: 104)
        XCTAssertEqual(loaded, 103)
        try journal.applyStatus(pending, state: "expired")
        XCTAssertEqual(try ConversationStreak.count(vault, scope: .direct, id: peer, through: 105), 1)
        try journal.applyStatus(pending, state: "delivered")
        try journal.applyStatus(pending, state: "delivered")
        for (today, expected): (Int64, Int) in [(104,104), (105,105), (106,105), (107,0)] {
            XCTAssertEqual(try ConversationStreak.count(vault, scope: .direct, id: peer, through: today), expected)
        }
        let store = GroupsStore(vault: vault)
        for index in [105,104] {
            for (sender, status): (UUID, GroupDelivery) in [(other,.received),(other,.received),(owner,.queued),(third,.withheld)] {
                try store.saveMessage(.init(id: UUID(), groupID: peer, epoch: 1, membershipRevision: 1, sender: sender, text: "G", createdAt: Int64(index)*day, delivery: status))
            }
        }
        XCTAssertEqual(try ConversationStreak.count(vault, scope: .group, id: peer, through: 105), 0)
        for (index, sender, status): (Int64, UUID, GroupDelivery) in [(105,third,.received),(104,owner,.accepted)] {
            try store.saveMessage(.init(id: UUID(), groupID: peer, epoch: 1, membershipRevision: 1, sender: sender, text: "G", createdAt: index*day, delivery: status))
        }
        let groupCount = try await ConversationStreak.load(vault, scope: .group, id: peer, through: 105)
        XCTAssertEqual(groupCount, 2)
        XCTAssertEqual(try ConversationStreak.count(vault, scope: .direct, id: peer, through: 105), 105)
        // Malformed derived data can be discarded without losing messages or blocking delivery.
        let bucketID = "direct/" + peer.uuidString.lowercased() + "/" + String(105 / 32)
        try vault.transaction { try vault.put("streak-days", bucketID, Data("broken".utf8)) }
        let rebuilt = try await ConversationStreak.load(vault, scope: .direct, id: peer, through: 105)
        XCTAssertEqual(rebuilt, 105)
    }
    func testLegacyEncryptedRestoreAndOtherAccountsRemainSeparate() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let owner = UUID(), peer = UUID(), unrelated = UUID(), password = "Synthetic backup for streak tests"
        let vault = try MessageVault(account: owner, directory: directory)
        let other = try MessageVault(account: unrelated, directory: directory)
        defer {
            try? vault.close(); try? other.close(); try? FileManager.default.removeItem(at: directory)
            for id in [owner,unrelated] { try? KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased()) }
        }
        let days: [Int64] = [1000, 1001], scale = ConversationStreak.millisecondsPerDay
        let url = directory.appendingPathComponent("synthetic.vipihistory")
        let writer = try HistoryBackupCodec.Writer(url: url, password: password, account: owner)
        try writer.append(.metadata(account: owner, createdAt: days[1]*scale))
        try writer.append(.peer(.init(id: peer, username: nil, displayName: nil)))
        var outgoing = [UUID]()
        for day in days {
            for sent in [false,true] {
                let id = UUID()
                if sent { outgoing.append(id) }
                try writer.append(.message(.init(id: id, peer: peer, outgoing: sent, createdAt: day*scale, text: "Test")))
            }
        }
        try writer.append(.end(records: 6, peers: 1, messages: 4))
        try writer.finish()
        let verified = try HistoryBackupCodec.inspect(url: url, password: password, account: owner)
        _ = try HistoryBackupStore.merge(vault: vault, staged: url, password: password, verified: verified)
        let imported = try await ConversationStreak.load(vault, scope: .direct, id: peer, through: days[1])
        XCTAssertEqual(imported, 0)
        // The original strict backup has no outgoing delivery proof. Only subsequent local proof supplies that side.
        let journal = MessageJournal(vault: vault)
        for (index, id) in outgoing.enumerated() {
            let at = days[index]*scale
            _ = try journal.queue(id: id, recipient: peer, text: "Test", createdAt: at, now: at) { _ in (3, Data(repeating: 1,count: 40)) }
            try journal.applyStatus(id, state: "delivered")
        }
        XCTAssertEqual(try ConversationStreak.count(vault, scope: .direct, id: peer, through: days[1]), 2)
        let empty = try await ConversationStreak.load(other, scope: .direct, id: peer, through: days[1])
        XCTAssertEqual(empty, 0)
    }

}
