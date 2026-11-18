import Foundation
import XCTest
@testable import Vipi

/// Real codec ciphertext, filesystem operations and account vaults. Every path
/// belongs to this test's temporary application-support root, never a live user.
final class HistoryBackupIsolationTests: XCTestCase {
    private let password = "private backup staging 2026"
    private enum GateFailure: Error { case timedOut }
    private final class CopyGate: @unchecked Sendable {
        let reached = DispatchSemaphore(value: 0)
        let resume = DispatchSemaphore(value: 0)
        private let point: HistoryBackupStore.StageCheckpoint
        private let lock = NSLock()
        private var used = false
        init(_ point: HistoryBackupStore.StageCheckpoint) { self.point = point }
        func checkpoint(_ value: HistoryBackupStore.StageCheckpoint) throws {
            guard value == point else { return }
            lock.lock(); let first = !used; used = true; lock.unlock()
            guard first else { return }
            reached.signal()
            guard resume.wait(timeout: .now() + 10) == .success else { throw GateFailure.timedOut }
        }
    }
    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("backup-isolation-" + UUID().uuidString, isDirectory: true)
            .standardizedFileURL.resolvingSymlinksInPath()
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    private func encrypted(_ url: URL, account: UUID, large: Bool = false) throws {
        let peer = UUID(), count = large ? 3 : 1
        // Three 24,000-byte messages cross the copy chunk boundary while each
        // remains below the real codec's 32,768-byte per-message limit.
        let text = large ? String(repeating: "Private 日本語 chat. ", count: 1000) : "Keep this private chat."
        let writer = try HistoryBackupCodec.Writer(url: url, password: password, account: account)
        try writer.append(.metadata(account: account, createdAt: 1_794_888_200_000))
        try writer.append(.peer(HistoryBackupPeer(id: peer, username: "backup_friend", displayName: "Backup Friend")))
        for index in 0..<count {
            try writer.append(.message(HistoryBackupMessage(id: UUID(), peer: peer, outgoing: false,
                createdAt: 1_794_888_100_000 + Int64(index), text: text)))
        }
        try writer.append(.end(records: 2 + count, peers: 1, messages: count)); try writer.finish()
    }
    private func vault(account: UUID, root: URL) throws -> MessageVault {
        let value = try MessageVault(account: account, directory: root.appendingPathComponent("Messages", isDirectory: true))
        addTeardownBlock {
            try? value.close()
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        return value
    }
    func testAccountErasurePreservesOtherEncryptedCopiesExternalExportAndUnattributedLegacy() throws {
        let root = try folder(), account = UUID(), other = UUID()
        let selected = root.appendingPathComponent("user-saved.vipihistory")
        try encrypted(selected, account: account)
        let sourceBytes = try Data(contentsOf: selected)
        let own = try HistoryBackupStore.directory(account: account, baseDirectory: root)
        let staged = try HistoryBackupStore.temporaryURL(account: account, baseDirectory: root)
        _ = try HistoryBackupStore.stage(selected, to: staged)
        XCTAssertEqual(try Data(contentsOf: staged), sourceBytes)
        let preview = try HistoryBackupCodec.inspect(url: staged, password: password, account: account)
        let store = try vault(account: account, root: root)
        XCTAssertEqual(try HistoryBackupStore.merge(vault: store, staged: staged, password: password, verified: preview).added, 1)
        let export = try HistoryBackupStore.exportURL(account: account, baseDirectory: root)
        try HistoryBackupStore.export(vault: store, password: password, to: export)
        XCTAssertEqual(try HistoryBackupCodec.inspect(url: export, password: password, account: account).messages, 1)
        let otherExport = try HistoryBackupStore.exportURL(account: other, baseDirectory: root)
        try encrypted(otherExport, account: other)
        let otherBytes = try Data(contentsOf: otherExport)
        let legacyRoot = root.appendingPathComponent("HistoryFiles", isDirectory: true)
        let legacy = legacyRoot.appendingPathComponent(UUID().uuidString + ".vipihistory")
        try sourceBytes.write(to: legacy)
        let legacyFolder = legacyRoot.appendingPathComponent(account.uuidString.lowercased(), isDirectory: true)
        try FileManager.default.createDirectory(at: legacyFolder, withIntermediateDirectories: false)
        let legacyExport = legacyFolder.appendingPathComponent("Vipi chat backup legacy.vipihistory")
        try sourceBytes.write(to: legacyExport)

        try HistoryBackupStore.erasePrivateFiles(account: account, baseDirectory: root)
        try HistoryBackupStore.erasePrivateFiles(account: account, baseDirectory: root) // retry is harmless
        XCTAssertFalse(FileManager.default.fileExists(atPath: own.path))
        XCTAssertEqual(try Data(contentsOf: selected), sourceBytes)
        XCTAssertEqual(try Data(contentsOf: legacy), sourceBytes)
        XCTAssertEqual(try Data(contentsOf: legacyExport), sourceBytes)
        XCTAssertEqual(try Data(contentsOf: otherExport), otherBytes)
        XCTAssertEqual(try HistoryBackupCodec.inspect(url: otherExport, password: password, account: other).messages, 1)
    }
    func testCleanupRejectsOtherAccountExternalAndTraversalURLs() throws {
        let root = try folder(), account = UUID(), other = UUID()
        let own = try HistoryBackupStore.directory(account: account, baseDirectory: root)
        let otherStage = try HistoryBackupStore.temporaryURL(account: other, baseDirectory: root)
        let otherExport = try HistoryBackupStore.exportURL(account: other, baseDirectory: root)
        let external = root.appendingPathComponent(UUID().uuidString + ".vipihistory")
        for url in [otherStage, otherExport, external] { try encrypted(url, account: other) }
        let preserved = try [otherStage, otherExport, external].map { ($0, try Data(contentsOf: $0)) }
        HistoryBackupStore.removeStaged(otherStage, account: account, baseDirectory: root)
        HistoryBackupStore.removeExport(otherExport, account: account, baseDirectory: root)
        HistoryBackupStore.removeStaged(external, account: account, baseDirectory: root)
        HistoryBackupStore.removeExport(external, account: account, baseDirectory: root)
        let traversal = own.appendingPathComponent("../" + other.uuidString.lowercased() + "/" + otherStage.lastPathComponent)
        HistoryBackupStore.removeStaged(traversal, account: account, baseDirectory: root)
        for (url, bytes) in preserved { XCTAssertEqual(try Data(contentsOf: url), bytes) }
        HistoryBackupStore.removeStaged(otherStage, account: other, baseDirectory: root)
        HistoryBackupStore.removeExport(otherExport, account: other, baseDirectory: root)
        XCTAssertFalse(FileManager.default.fileExists(atPath: otherStage.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: otherExport.deletingLastPathComponent().path))
    }
    func testSymlinkEscapesCannotAllocateStageOrUnlinkExternalBackups() throws {
        let root = try folder(), account = UUID()
        let support = root.appendingPathComponent("support", isDirectory: true)
        let own = try HistoryBackupStore.directory(account: account, baseDirectory: support)
        let external = root.appendingPathComponent("external", isDirectory: true)
        try FileManager.default.createDirectory(at: external, withIntermediateDirectories: true)
        let saved = external.appendingPathComponent("saved.vipihistory")
        try encrypted(saved, account: account); let bytes = try Data(contentsOf: saved)
        let link = own.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: external)
        HistoryBackupStore.removeExport(link.appendingPathComponent(saved.lastPathComponent), account: account, baseDirectory: support)
        let escaped = link.appendingPathComponent(UUID().uuidString + ".vipihistory")
        XCTAssertThrowsError(try HistoryBackupStore.stage(saved, to: escaped))
        XCTAssertFalse(FileManager.default.fileExists(atPath: external.appendingPathComponent(escaped.lastPathComponent).path))
        XCTAssertEqual(try Data(contentsOf: saved), bytes)
        try HistoryBackupStore.erasePrivateFiles(account: account, baseDirectory: support)
        XCTAssertEqual(try Data(contentsOf: saved), bytes) // nested symlink target survives recursive cleanup

        let escapedSupport = root.appendingPathComponent("escaped-support", isDirectory: true)
        try FileManager.default.createDirectory(at: escapedSupport, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(at: escapedSupport.appendingPathComponent("HistoryFiles"), withDestinationURL: external)
        XCTAssertThrowsError(try HistoryBackupStore.temporaryURL(account: account, baseDirectory: escapedSupport))
        XCTAssertThrowsError(try HistoryBackupStore.erasePrivateFiles(account: account, baseDirectory: escapedSupport))
        XCTAssertEqual(try Data(contentsOf: saved), bytes)
    }
    func testExistingExportDestinationIsRejectedWithoutDeletingUserSavedCiphertext() throws {
        let root = try folder(), account = UUID(), saved = root.appendingPathComponent("saved-by-user.vipihistory")
        try encrypted(saved, account: account); let before = try Data(contentsOf: saved)
        let store = try vault(account: account, root: root)
        XCTAssertThrowsError(try HistoryBackupStore.export(vault: store, password: password, to: saved))
        XCTAssertEqual(try Data(contentsOf: saved), before)
        XCTAssertEqual(try HistoryBackupCodec.inspect(url: saved, password: password, account: account).messages, 1)
    }
    func testCancelledEncryptedCopyRemovesPartialFileAndPreservesSource() async throws {
        try await cancelledCopy(at: .copiedChunk, eraseAccount: false)
    }
    func testCancelledSynchronizedCopyNeverPublishesStagedFile() async throws {
        try await cancelledCopy(at: .synchronized, eraseAccount: false)
    }
    func testAccountErasureDuringCancelledCopyDoesNotRecreateItsDirectory() async throws {
        try await cancelledCopy(at: .copiedChunk, eraseAccount: true)
    }
    private func cancelledCopy(at point: HistoryBackupStore.StageCheckpoint, eraseAccount: Bool) async throws {
        let root = try folder(), account = UUID(), other = UUID()
        let source = root.appendingPathComponent("external-source.vipihistory")
        try encrypted(source, account: account, large: true); let bytes = try Data(contentsOf: source)
        XCTAssertGreaterThan(bytes.count, 65_536)
        let staged = try HistoryBackupStore.temporaryURL(account: account, baseDirectory: root)
        let own = staged.deletingLastPathComponent()
        let otherStage = try HistoryBackupStore.temporaryURL(account: other, baseDirectory: root)
        try encrypted(otherStage, account: other); let otherBytes = try Data(contentsOf: otherStage)
        let gate = CopyGate(point)
        let task = Task.detached { try HistoryBackupStore.stage(source, to: staged, checkpoint: { try gate.checkpoint($0) }) }
        defer { gate.resume.signal(); task.cancel() }
        XCTAssertEqual(gate.reached.wait(timeout: .now() + 5), .success)
        XCTAssertTrue(FileManager.default.fileExists(atPath: staged.path))
        task.cancel()
        if eraseAccount { try HistoryBackupStore.erasePrivateFiles(account: account, baseDirectory: root) }
        gate.resume.signal()
        do { _ = try await task.value; XCTFail("A cancelled encrypted copy was published") }
        catch is CancellationError { }
        XCTAssertFalse(FileManager.default.fileExists(atPath: staged.path))
        if eraseAccount { XCTAssertFalse(FileManager.default.fileExists(atPath: own.path)) }
        XCTAssertEqual(try Data(contentsOf: source), bytes)
        XCTAssertEqual(try Data(contentsOf: otherStage), otherBytes)
        XCTAssertEqual(try HistoryBackupCodec.inspect(url: source, password: password, account: account).messages, 3)
    }
}
