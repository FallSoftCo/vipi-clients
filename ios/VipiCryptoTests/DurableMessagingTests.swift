import Foundation
import XCTest
import LibSignalClient
import SQLite3
@testable import Vipi

final class DurableMessagingTests: XCTestCase {
    private enum Interrupted: Error { case write }
    func testAndroidHandshakeAndDurableSwiftReplies() throws {
        let resource = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "durable-handshake", withExtension: "json"))
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: resource)) as? [String: Any])
        XCTAssertEqual(fixture["purpose"] as? String, "SYNTHETIC DURABLE MESSAGING QA ONLY")
        func bytes(_ name: String) throws -> Data { try XCTUnwrap(Data(base64Encoded: XCTUnwrap(fixture[name] as? String))) }
        let aliceID = try XCTUnwrap(UUID(uuidString: XCTUnwrap(fixture["alice"] as? String)))
        let bobID = try XCTUnwrap(UUID(uuidString: XCTUnwrap(fixture["bob"] as? String)))
        let alice = try ProtocolAddress(name: aliceID.uuidString.lowercased(), deviceId: 1)
        let bob = try ProtocolAddress(name: bobID.uuidString.lowercased(), deviceId: 1)
        let envelope = try JSONDecoder().decode(ChatEnvelope.self, from: JSONSerialization.data(withJSONObject: XCTUnwrap(fixture["envelope"])))
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("DurableMessagingQA/\(UUID())")
        let context = NullContext()
        do {
            let vault = try MessageVault(account: bobID, directory: root)
            let store = try DurableSignalStore(vault: vault)
            try vault.transaction {
                try vault.put("local", "identity", bytes("bobIdentity"))
                try vault.put("local", "registration", Data("202".utf8))
                try store.storePreKey(PreKeyRecord(bytes: bytes("bobPreKey")), id: 1, context: context)
                try store.storeSignedPreKey(SignedPreKeyRecord(bytes: bytes("bobSignedPreKey")), id: 2, context: context)
                try store.storeKyberPreKey(KyberPreKeyRecord(bytes: bytes("bobKyberPreKey")), id: 3, context: context)
            }
            let journal = MessageJournal(vault: vault)
            func decrypt(_ type: Int, _ data: Data) throws -> Data {
                try signalDecryptPreKey(message: PreKeySignalMessage(bytes: data), from: alice, localAddress: bob, sessionStore: store, identityStore: store, preKeyStore: store, signedPreKeyStore: store, kyberPreKeyStore: store, context: context)
            }
            XCTAssertThrowsError(try journal.receive(envelope, now: envelope.createdAt) { type, data in _ = try decrypt(type, data); throw Interrupted.write })
            try vault.transaction {
                XCTAssertNotNil(try store.loadPreKey(id: 1, context: context))
                XCTAssertNil(try store.loadSession(for: alice, context: context))
            }
            let changed = ChatEnvelope(id: UUID(), sender: envelope.sender, recipient: envelope.recipient, createdAt: envelope.createdAt, type: envelope.type, ciphertext: envelope.ciphertext)
            XCTAssertThrowsError(try journal.receive(changed, now: envelope.createdAt, decrypt: decrypt))
            let received = try journal.receive(envelope, now: envelope.createdAt, decrypt: decrypt)
            XCTAssertEqual(received.text, "Persistent coffee by the river — café ☕ مرحباً")
            try vault.transaction {
                XCTAssertThrowsError(try store.loadPreKey(id: 1, context: context))
                XCTAssertThrowsError(try store.loadKyberPreKey(id: 3, context: context))
            }
        }
        var replies: [ChatEnvelope] = []
        for index in 0..<3 {
            // Reopen both database and protocol store between every reply.
            let vault = try MessageVault(account: bobID, directory: root)
            let store = try DurableSignalStore(vault: vault)
            let journal = MessageJournal(vault: vault)
            XCTAssertEqual(try journal.receive(envelope, now: envelope.createdAt) { _, _ in XCTFail("Duplicate decrypted"); throw Interrupted.write }.state, "delivered")
            let id = UUID(), text = "Durable Swift reply \(index) — río ☕"
            let before = try vault.transaction { try XCTUnwrap(store.loadSession(for: alice, context: context)).serialize() }
            XCTAssertThrowsError(try journal.queue(id: id, recipient: aliceID, text: text, createdAt: envelope.createdAt, now: envelope.createdAt) { clear in
                _ = try signalEncrypt(message: clear, for: alice, localAddress: bob, sessionStore: store, identityStore: store, context: context)
                throw Interrupted.write
            })
            XCTAssertEqual(try MessageJournal(vault: MessageVault(account: bobID, directory: root)).draft(id)?.text, text)
            XCTAssertEqual(before, try vault.transaction { try XCTUnwrap(store.loadSession(for: alice, context: context)).serialize() })
            let reply = try journal.queue(id: id, recipient: aliceID, text: text, createdAt: envelope.createdAt, now: envelope.createdAt) { clear in
                let encrypted = try signalEncrypt(message: clear, for: alice, localAddress: bob, sessionStore: store, identityStore: store, context: context)
                return (Int(encrypted.messageType.rawValue), encrypted.serialize())
            }
            XCTAssertNil(try journal.draft(id))
            let retry = try journal.queue(id: id, recipient: aliceID, text: text, createdAt: envelope.createdAt, now: envelope.createdAt) { _ in XCTFail("Retry encrypted twice"); throw Interrupted.write }
            XCTAssertEqual(reply.ciphertext, retry.ciphertext)
            try vault.transaction {
                let changed = IdentityKeyPair.generate().identityKey
                XCTAssertFalse(try store.isTrustedIdentity(changed, for: alice, direction: .sending, context: context))
                XCTAssertFalse(try store.isTrustedIdentity(changed, for: alice, direction: .receiving, context: context))
                XCTAssertThrowsError(try store.saveIdentity(changed, for: alice, context: context))
            }
            replies.append(reply)
        }
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("durable-swift-replies.json")
        try JSONEncoder().encode(["messages": replies]).write(to: output, options: .atomic)
    }

    func testConcurrentTransactionsDoNotLoseUpdates() throws {
        let account = UUID()
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("DurableMessagingQA/\(UUID())")
        let stores = try [MessageVault(account: account, directory: root), MessageVault(account: account, directory: root)]
        try stores[0].transaction { try stores[0].put("test", "counter", Data("0".utf8)) }
        DispatchQueue.concurrentPerform(iterations: 2) { index in
            do {
                let vault = stores[index]
                for _ in 0..<30 { try vault.transaction {
                    let data = try XCTUnwrap(vault.get("test", "counter"))
                    let count = try XCTUnwrap(Int(String(decoding: data, as: UTF8.self)))
                    try vault.put("test", "counter", Data(String(count + 1).utf8))
                } }
            } catch { XCTFail("Concurrent native transaction failed: \(error)") }
        }
        XCTAssertEqual(try stores[0].transaction { try stores[0].get("test", "counter") }, Data("60".utf8))
    }

    func testStorageIntegrityAndExpiry() throws {
        let account = UUID(), peer = UUID(), id = UUID()
        let now: Int64 = 1_800_000_000_000
        let marker = "PRIVATE CHAT TEXT MUST NEVER APPEAR IN SQLITE"
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("DurableMessagingQA/\(UUID())")
        var path: URL!
        do {
            let vault = try MessageVault(account: account, directory: root); path = vault.url
            XCTAssertThrowsError(try vault.put("test", "outside", Data([1])))
            try vault.transaction { try vault.put("test", "a", Data(marker.utf8)); try vault.put("test", "b", Data([2])) }
            let journal = MessageJournal(vault: vault)
            _ = try journal.queue(id: id, recipient: peer, text: marker, createdAt: now, now: now) { _ in (2, Data(repeating: 7, count: 64)) }
            let draftID = UUID()
            try journal.saveDraft(id: draftID, recipient: peer, text: "Waiting for a connection", createdAt: now, now: now)
            XCTAssertEqual(try journal.pendingDrafts(now: now).count, 1)
            XCTAssertTrue(try journal.pendingDrafts(now: now + MessageJournal.ttl).isEmpty)
            XCTAssertEqual(try journal.draft(draftID)?.state, "expired")
            try journal.applyStatus(id, state: "accepted")
            XCTAssertEqual(try journal.pending(now: now + MessageJournal.ttl - 1).count, 1)
            XCTAssertTrue(try journal.pending(now: now + MessageJournal.ttl).isEmpty)
            XCTAssertEqual(try journal.outgoing(id)?.state, "expired")
            XCTAssertThrowsError(try journal.queue(id: id, recipient: peer, text: marker, createdAt: now, now: now + MessageJournal.ttl) { _ in throw Interrupted.write })
            try journal.applyStatus(id, state: "delivered"); try journal.applyStatus(id, state: "accepted")
            XCTAssertEqual(try journal.outgoing(id)?.state, "delivered")
            let values = try path.deletingLastPathComponent().resourceValues(forKeys: [.isExcludedFromBackupKey])
            XCTAssertEqual(values.isExcludedFromBackup, true)
        }
        for file in try FileManager.default.contentsOfDirectory(at: path.deletingLastPathComponent(), includingPropertiesForKeys: nil) {
            XCTAssertNil(try Data(contentsOf: file).range(of: Data(marker.utf8)))
        }
        var database: OpaquePointer?
        XCTAssertEqual(sqlite3_open(path.path, &database), SQLITE_OK)
        XCTAssertEqual(sqlite3_exec(database, "UPDATE records SET value=(SELECT value FROM records WHERE kind='test' AND id='a') WHERE kind='test' AND id='b'", nil, nil, nil), SQLITE_OK)
        sqlite3_close(database)
        do {
            let reopened = try MessageVault(account: account, directory: root)
            XCTAssertThrowsError(try reopened.transaction { try reopened.get("test", "b") })
            XCTAssertEqual(try reopened.transaction { try reopened.get("test", "a") }, Data(marker.utf8))
        }
        KeychainStore.delete(account: "messages-\(account.uuidString.lowercased())")
        XCTAssertThrowsError(try MessageVault(account: account, directory: root))
        XCTAssertTrue(FileManager.default.fileExists(atPath: path.path))
    }
}
