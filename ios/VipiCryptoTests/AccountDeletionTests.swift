import Foundation
import XCTest
@testable import Vipi

@MainActor final class AccountDeletionTests: XCTestCase {
    private final class Store: DeletionStore {
        var record: DeletionRecord?
        var failSave = false
        var failLoad = false
        func load() throws -> DeletionRecord? { if failLoad { throw CocoaError(.fileReadUnknown) }; return record }
        func save(_ record: DeletionRecord) throws { if failSave { failSave = false; throw CocoaError(.fileWriteUnknown) }; self.record = record }
        func remove() throws { record = nil }
    }
    private final class Transport: DeletionTransport {
        var submitCount = 0
        var statusCount = 0
        var submitBlock: ((DeletionRecord) throws -> DeletionReply)?
        var statusBlock: ((DeletionRecord) throws -> DeletionReply)?
        func submit(_ record: DeletionRecord) async throws -> DeletionReply { submitCount += 1; return try submitBlock!(record) }
        func status(_ record: DeletionRecord) async throws -> DeletionReply {
            statusCount += 1
            if let statusBlock { return try statusBlock(record) }
            throw ServiceFailure(status: 404, code: "deletion_receipt_unavailable")
        }
    }
    func testLostResponseRecoversAfterRestartWithoutResubmission() async throws {
        let store = Store(), api = Transport(), account = UUID()
        var closed = false, erased = 0, signedOut = [String]()
        let first = AccountDeletion(store: store, service: api, erase: { _ in erased += 1 }, signOut: { signedOut.append($0) })
        try first.begin(account: account, userID: "user_deletion_qa") { closed = true }
        let saved = try XCTUnwrap(store.record)
        XCTAssertTrue(closed); XCTAssertEqual(saved.secret.count, 43)
        api.submitBlock = { record in
            XCTAssertEqual(store.record?.secret, record.secret)
            api.statusBlock = { receipt in
                XCTAssertEqual(receipt.secret, saved.secret)
                return DeletionReply(account_id: account, status: "deleted")
            }
            throw URLError(.networkConnectionLost)
        }
        await first.resume()
        XCTAssertEqual(erased, 0); XCTAssertEqual(first.pending?.phase, .prepared); XCTAssertNotNil(first.notice)
        let restarted = AccountDeletion(store: store, service: api, erase: { _ in erased += 1 }, signOut: { signedOut.append($0) })
        await restarted.resume()
        XCTAssertEqual(api.submitCount, 1); XCTAssertEqual(erased, 1)
        XCTAssertEqual(restarted.pending?.phase, .completed); XCTAssertEqual(signedOut, ["user_deletion_qa"])
        restarted.finish(); XCTAssertNil(store.record); XCTAssertFalse(restarted.active)
    }
    func testMismatchedReplyAndMissingReceiptNeverEraseOrInventSuccess() async throws {
        let store = Store(), api = Transport()
        let manager = AccountDeletion(store: store, service: api, erase: { _ in XCTFail("Unconfirmed deletion erased local data") }, signOut: { _ in XCTFail() })
        try manager.begin(account: UUID(), userID: "user_qa") {}
        api.submitBlock = { _ in DeletionReply(account_id: UUID(), status: "deleted") }
        await manager.resume(); XCTAssertEqual(manager.pending?.phase, .prepared); XCTAssertNotNil(manager.notice)
        let secret = store.record!.secret
        api.submitBlock = { _ in throw ServiceFailure(status: 401, code: "recent_sign_in_required") }
        await manager.resume(); XCTAssertTrue(manager.needsSignIn); XCTAssertEqual(store.record?.secret, secret)
        var old = store.record!; old = DeletionRecord(account: old.account, userID: old.userID, secret: old.secret, createdAt: Date(timeIntervalSinceNow: -8 * 86400))
        store.record = old
        let restart = AccountDeletion(store: store, service: api, erase: { _ in XCTFail() }, signOut: { _ in XCTFail() })
        let count = api.submitCount; await restart.resume()
        XCTAssertEqual(api.submitCount, count); XCTAssertTrue(restart.active); XCTAssertNotNil(restart.notice)
    }
    func testReceiptWriteAndCleanupFailuresRemainRecoverable() async throws {
        let store = Store(), api = Transport(); var eraseAttempts = 0
        let manager = AccountDeletion(store: store, service: api, erase: { _ in
            eraseAttempts += 1; if eraseAttempts == 1 { throw CocoaError(.fileWriteUnknown) }
        }, signOut: { _ in })
        try manager.begin(account: UUID(), userID: "user_qa") {}
        api.statusBlock = { DeletionReply(account_id: $0.account, status: "deleted") }
        store.failSave = true
        await manager.resume(); XCTAssertEqual(eraseAttempts, 0); XCTAssertEqual(manager.pending?.phase, .prepared)
        await manager.resume(); XCTAssertEqual(eraseAttempts, 1); XCTAssertEqual(manager.pending?.phase, .completed)
        XCTAssertFalse(manager.pending!.localErased); manager.finish(); XCTAssertTrue(manager.active)
        let checks = api.statusCount
        await manager.resume(); XCTAssertEqual(eraseAttempts, 2); XCTAssertEqual(api.statusCount, checks)
        XCTAssertTrue(manager.pending!.localErased); manager.finish(); XCTAssertFalse(manager.active)
        store.failLoad = true
        let unreadable = AccountDeletion(store: store, service: api, erase: { _ in XCTFail() }, signOut: { _ in XCTFail() })
        XCTAssertTrue(unreadable.active); XCTAssertTrue(unreadable.loadFailed)
    }
    func testErasureOnlyRemovesConfirmedAccountsFilesAndKeys() throws {
        let account = UUID(), other = UUID(), user = "delete-fixture-" + UUID().uuidString
        let target = try MessageVault(account: account), preserved = try MessageVault(account: other)
        let folder = target.url.deletingLastPathComponent(), otherFolder = preserved.url.deletingLastPathComponent()
        defer {
            try? target.close(); try? preserved.close()
            for id in [account, other] { KeychainStore.delete(account: "messages-" + id.uuidString.lowercased()) }
            KeychainStore.delete(account: "profile-" + user)
            try? FileManager.default.removeItem(at: folder); try? FileManager.default.removeItem(at: otherFolder)
        }
        try target.transaction { try target.put("test", "body", Data("secret".utf8)) }
        try preserved.transaction { try preserved.put("test", "body", Data("keep".utf8)) }
        try KeychainStore.save(Data("profile".utf8), account: "profile-" + user)
        let cacheRoot = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        let privateSpeech = cacheRoot.appendingPathComponent("vipi-speech", isDirectory: true)
        let unrelated = cacheRoot.appendingPathComponent("unrelated-deletion-qa-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: privateSpeech, withIntermediateDirectories: true)
        try Data("private spoken message".utf8).write(to: privateSpeech.appendingPathComponent("deletion-fixture.caf"))
        try Data("keep".utf8).write(to: unrelated)
        defer { try? FileManager.default.removeItem(at: unrelated) }
        try target.close()
        let record = DeletionRecord(account: account, userID: user, secret: String(repeating: "a", count: 43), createdAt: Date(), phase: .requested)
        try AccountDeletion.eraseLocal(record); try AccountDeletion.eraseLocal(record)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: privateSpeech.path))
        XCTAssertEqual(try Data(contentsOf: unrelated), Data("keep".utf8))
        XCTAssertNil(try KeychainStore.read(account: "messages-" + account.uuidString.lowercased()))
        XCTAssertNil(try KeychainStore.read(account: "profile-" + user))
        XCTAssertEqual(try preserved.transaction { try preserved.get("test", "body") }, Data("keep".utf8))
    }
    func testCannotFinishUntilSavedSignInIsRemoved() async throws {
        let store = Store(), api = Transport(); var attempts = 0
        let manager = AccountDeletion(store: store, service: api, erase: { _ in }, signOut: { _ in
            attempts += 1; if attempts == 1 { throw CocoaError(.fileWriteUnknown) }
        })
        try manager.begin(account: UUID(), userID: "user_qa") {}
        api.statusBlock = { DeletionReply(account_id: $0.account, status: "deleted") }
        await manager.resume(); manager.finish()
        XCTAssertTrue(manager.active); XCTAssertFalse(manager.pending!.localErased)
        await manager.resume(); manager.finish()
        XCTAssertFalse(manager.active); XCTAssertEqual(attempts, 2)
    }
}
