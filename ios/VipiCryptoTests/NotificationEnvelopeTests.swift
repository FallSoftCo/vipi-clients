import Foundation
import XCTest
@testable import Vipi

final class NotificationEnvelopeTests: XCTestCase {
    func testFirstConversationAcrossTwoConnectionsCommitsBeforePresentation() throws {
        let friend = UUID(), account = UUID(), now = Int64(Date().timeIntervalSince1970 * 1000)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: root)
            for id in [friend, account] { KeychainStore.delete(account: "messages-" + id.uuidString.lowercased()) }
        }
        let friendVault = try MessageVault(account: friend, directory: root)
        let appVault = try MessageVault(account: account, directory: root)
        let sender = try MessagingCore(vault: friendVault)
        let receiver = try MessagingCore(vault: appVault)
        let history = try ConversationHistory(vault: appVault)
        let consent = NotificationConsent(now: Date(timeIntervalSinceNow: -2))
        try appVault.transaction {
            try appVault.put("local", "registered-device", Data(receiver.device.id.uuidString.lowercased().utf8))
            try appVault.put("local", "outside-previews", JSONEncoder().encode(consent))
        }
        let grant = NotificationGrant(account: account, epoch: consent.epoch, key: try XCTUnwrap(KeychainStore.read(account: "messages-" + account.uuidString.lowercased())))
        let extensionVault = try MessageVault(account: account, directory: root, previewKey: grant.key)
        let publication = try receiver.keys.publication(now: now)
        let request = UUID()
        let keys = ClaimedKeys(request_id: request, user_id: account, device_id: receiver.device.id, signal_device_id: 1,
                               registration_id: publication.registration_id, identity_key: publication.identity_key,
                               signed: publication.signed, one_time: publication.one_time[0])
        _ = try sender.keys.establish(peer: account, requestID: request, response: keys)
        let messages = try ["See you outside.", "Coffee at six?"].enumerated().map { index, text in
            try sender.queue(id: UUID(), peer: account, text: text, createdAt: now + Int64(index), now: now + Int64(index))
        }
        let date = ISO8601DateFormatter()
        date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let wire = messages.map { routed in
            RoutedMessage.Received(id: routed.envelope.id, sender_id: friend, sender_device_id: sender.device.id,
                                   recipient_device_id: receiver.device.id,
                                   created_at: date.string(from: Date(timeIntervalSince1970: Double(routed.envelope.createdAt) / 1000)),
                                   cipher_type: routed.envelope.type, ciphertext: routed.envelope.ciphertext)
        }
        let match = NotificationEnvelope(id: wire[1].id, peer: friend, display_name: "Sam", accepted_at: Double(now) / 1000, messages: wire)
        XCTAssertThrowsError(try match.preview(grant: grant, vault: extensionVault, device: receiver.device) { nil })
        XCTAssertEqual(try receiver.journal.pendingReceipts(), [])
        let preview = try match.preview(grant: grant, vault: extensionVault, device: receiver.device) { grant }
        XCTAssertEqual(preview.0, "Sam")
        XCTAssertEqual(preview.1, "Coffee at six?")
        XCTAssertEqual(Set(try receiver.journal.pendingReceipts()), Set(wire.map(\.id)))
        XCTAssertEqual(try history.threads().first?.unread, 2)
        XCTAssertEqual(try history.messages(peer: friend).map(\.text), ["Coffee at six?", "See you outside."])
        let duplicate = try match.preview(grant: grant, vault: extensionVault, device: receiver.device) { grant }
        XCTAssertTrue(duplicate.repeated)
        XCTAssertEqual(duplicate.body, preview.body)
        XCTAssertEqual(try history.threads().first?.unread, 2)
        try history.markRead(friend)
        try appVault.transaction { try appVault.remove("notification-shown", friend.uuidString.lowercased()) }
        XCTAssertThrowsError(try match.preview(grant: grant, vault: extensionVault, device: receiver.device) { grant })
    }

    func testOnlyInterruptedFirstCreationMayRecoverAnAbsentCanonicalDatabase() throws {
        let id = UUID(), name = id.uuidString.lowercased()
        defer {
            for prefix in ["messages-", "messages-initializing-", "notification-store-location-"] { KeychainStore.delete(account: prefix + name) }
            for root in [NotificationAccess.legacyRoot, NotificationAccess.root].compactMap({ $0 }) {
                try? FileManager.default.removeItem(at: root.appendingPathComponent(name))
            }
        }
        try KeychainStore.save(Data(repeating: 7, count: 32), account: "messages-" + name)
        XCTAssertThrowsError(try MessageVault(account: id))
        try KeychainStore.save(Data([1]), account: "messages-initializing-" + name)
        let created = try MessageVault(account: id)
        XCTAssertNotNil(try created.transaction { try created.notificationConsent() })
        XCTAssertNil(try KeychainStore.read(account: "messages-initializing-" + name))
        let folder = created.url.deletingLastPathComponent()
        try created.close()
        try FileManager.default.removeItem(at: folder)
        XCTAssertThrowsError(try MessageVault(account: id))
    }

    func testPinnedVaultLocationSurvivesRestartAndMissingEntitlement() throws {
        let id = UUID(), root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("legacy"), shared = root.appendingPathComponent("shared")
        let name = id.uuidString.lowercased()
        defer {
            KeychainStore.delete(account: "notification-store-location-" + name)
            try? FileManager.default.removeItem(at: root)
        }
        let old = legacy.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: old, withIntermediateDirectories: true)
        for name in ["messages.sqlite", "messages.sqlite-wal", "messages.sqlite-shm"] {
            try Data(name.utf8).write(to: old.appendingPathComponent(name))
        }
        XCTAssertEqual(try NotificationAccess.storageRoot(for: id, shared: nil, legacy: legacy), legacy)
        XCTAssertEqual(try NotificationAccess.storageRoot(for: id, shared: shared, legacy: legacy), shared)
        XCTAssertEqual(try NotificationAccess.storageRoot(for: id, shared: shared, legacy: legacy), shared)
        XCTAssertThrowsError(try NotificationAccess.storageRoot(for: id, shared: nil, legacy: legacy))
        XCTAssertFalse(FileManager.default.fileExists(atPath: old.path))
        for file in ["messages.sqlite", "messages.sqlite-wal", "messages.sqlite-shm"] {
            XCTAssertEqual(try Data(contentsOf: shared.appendingPathComponent(name).appendingPathComponent(file)), Data(file.utf8))
        }
    }

    func testLegacyVaultKeepsGenericPreviewUntilExplicitChoice() throws {
        let account = UUID(), root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
            try? FileManager.default.removeItem(at: root)
        }
        let initial = try MessageVault(account: account, directory: root)
        try initial.transaction {
            XCTAssertNotNil(try initial.notificationConsent())
            try initial.remove("local", "outside-previews")
            try initial.put("local", "foreground-previews", Data([1]))
        }
        try initial.close()
        let upgraded = try MessageVault(account: account, directory: root)
        try upgraded.transaction {
            XCTAssertNil(try upgraded.notificationConsent())
            XCTAssertEqual(try upgraded.get("local", "foreground-previews"), Data([1]))
        }
    }
}
