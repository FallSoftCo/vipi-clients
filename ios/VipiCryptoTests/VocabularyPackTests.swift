import Foundation
import CryptoKit
import SQLite3
import VipiCore
import XCTest
@testable import Vipi

final class VocabularyPackTests: XCTestCase {
    private struct ActivationFixture: Sendable {
        let manifest: Data, signature: Data, database: Data
        let revision: Int, hash: String
    }
    private struct Injected: Error {}
    private final class Gate: @unchecked Sendable {
        let entered = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        func block() throws {
            entered.signal()
            guard release.wait(timeout: .now() + 5) == .success else { throw Injected() }
        }
        func observed() async -> Bool {
            await withCheckedContinuation { continuation in
                DispatchQueue.global().async { continuation.resume(returning: self.entered.wait(timeout: .now() + 4) == .success) }
            }
        }
    }
    private func fixture(_ revision: Int, target: String, key: P256.Signing.PrivateKey) throws -> ActivationFixture {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent("activation-input-\(UUID()).sqlite")
        defer { try? FileManager.default.removeItem(at: path) }
        var handle: OpaquePointer?
        guard sqlite3_open(path.path, &handle) == SQLITE_OK, let db = handle else { throw Injected() }
        defer { sqlite3_close(db) }
        let sql = "PRAGMA application_id=1447645257; PRAGMA user_version=1; CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT); INSERT INTO metadata VALUES('pack_id','en-es'); CREATE TABLE vocabulary(source TEXT,target TEXT); INSERT INTO vocabulary VALUES('coffee','\(target)');"
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw Injected() }
        let database = try Data(contentsOf: path)
        let hash = SHA256.hash(data: database).map { String(format: "%02x", $0) }.joined()
        let manifest = try JSONSerialization.data(withJSONObject: ["pack_id": "en-es", "source_language": "en", "target_language": "es",
            "revision": revision, "schema_version": 1, "normalization": "unicode-nfc-lower", "file": "vocabulary.sqlite",
            "bytes": database.count, "sha256": hash, "key_id": "atomic-qa", "signature_algorithm": "ECDSA-P256-SHA256"], options: [.sortedKeys])
        return .init(manifest: manifest, signature: try key.signature(for: manifest).derRepresentation, database: database, revision: revision, hash: hash)
    }
    private func directory() throws -> URL {
        let value = FileManager.default.temporaryDirectory.appendingPathComponent("activation-store-\(UUID())")
        try FileManager.default.createDirectory(at: value, withIntermediateDirectories: true); return value
    }
    private func pack(_ root: URL, prefix: String, key: P256.Signing.PrivateKey) throws -> VocabularyPackStore {
        try VocabularyPackStore(root: root, trustedKeys: ["atomic-qa": key.publicKey.derRepresentation], receiptPrefix: prefix)
    }
    private func install(_ fixture: ActivationFixture, into store: VocabularyPackStore) async throws {
        let id = try await store.install(manifestBytes: fixture.manifest, signature: fixture.signature, database: fixture.database)
        XCTAssertEqual(id, "en-es")
    }
    private func targets(_ store: VocabularyPackStore) async throws -> [String] {
        try await store.entries(id: "en-es", text: "coffee").flatMap(\.targets)
    }
    private func retain(_ name: String, fixtures: [ActivationFixture], key: P256.Signing.PrivateKey) throws {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("pack-activation-qa-r01").appendingPathComponent(name + "-" + UUID().uuidString.lowercased())
        guard !FileManager.default.fileExists(atPath: root.path) else { throw Injected() }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try key.publicKey.derRepresentation.write(to: root.appendingPathComponent("public-key.der"))
        for (i, value) in fixtures.enumerated() {
            try value.manifest.write(to: root.appendingPathComponent("\(i)-manifest.json"))
            try value.signature.write(to: root.appendingPathComponent("\(i)-manifest.sig"))
            try value.database.write(to: root.appendingPathComponent("\(i)-vocabulary.sqlite"))
        }
        try JSONSerialization.data(withJSONObject: ["case": name, "passed": true,
            "faults": "explicit injected checkpoints; no device power-loss claim",
            "revisions": fixtures.map(\.revision), "payload_sha256": fixtures.map(\.hash)], options: [.sortedKeys])
            .write(to: root.appendingPathComponent("receipt.json"))
    }

    func testAtomicActivationUpgradeIntegrityAndMissingFileRecovery() async throws {
        let root = try directory(), prefix = "activation-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let one = try fixture(1, target: "cafe-one", key: key), two = try fixture(2, target: "cafe-two", key: key)
        let store = try pack(root, prefix: prefix, key: key)
        try await install(one, into: store); try await install(two, into: store)
        let reopened = try pack(root, prefix: prefix, key: key)
        let actual = try await targets(reopened); XCTAssertEqual(actual, ["cafe-two"])
        let raw = try XCTUnwrap(KeychainStore.read(account: prefix + "en-es"))
        let record = try XCTUnwrap(JSONSerialization.jsonObject(with: raw) as? [String: Any])
        let active = try XCTUnwrap(record["active"] as? [String: Any])
        XCTAssertEqual(Data(base64Encoded: try XCTUnwrap(active["manifestBytes"] as? String)), two.manifest)
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("en-es.json").path))
        let conflicting = try fixture(2, target: "conflict", key: key)
        do { try await install(conflicting, into: store); XCTFail("Same revision conflict") } catch VocabularyPackError.rollback {}
        var damaged = two.database; damaged[damaged.count-1] ^= 1
        do { _ = try await store.install(manifestBytes: two.manifest, signature: two.signature, database: damaged); XCTFail("Corrupt input") } catch {}
        let untrusted = try pack(root, prefix: prefix, key: P256.Signing.PrivateKey())
        do { try await install(two, into: untrusted); XCTFail("Untrusted signing key") } catch {}
        let file = root.appendingPathComponent("en-es-2-\(two.hash).sqlite")
        let mtime = try XCTUnwrap(FileManager.default.attributesOfItem(atPath: file.path)[.modificationDate] as? Date)
        try damaged.write(to: file)
        try FileManager.default.setAttributes([.modificationDate: mtime], ofItemAtPath: file.path)
        do { _ = try await targets(reopened); XCTFail("Same-size corruption with restored mtime") } catch {}
        do { _ = try await reopened.status(id: "en-es"); XCTFail("Corrupt payload must not report active") } catch {}
        try FileManager.default.removeItem(at: file)
        do { _ = try await targets(reopened); XCTFail("Missing active payload") } catch {}
        do { _ = try await pack(root, prefix: prefix, key: key).status(id: "en-es"); XCTFail("Missing payload after reopen must not report active") } catch {}
        try await install(two, into: store)
        let repaired = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(repaired, ["cafe-two"])
        try retain("upgrade-integrity-recovery", fixtures: [one, two, conflicting], key: key)
    }
    func testPrecommitFailureAndCancellationKeepAcceptedPack() async throws {
        let root = try directory(), prefix = "activation-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let one = try fixture(1, target: "old", key: key), two = try fixture(2, target: "new", key: key)
        let store = try pack(root, prefix: prefix, key: key); try await install(one, into: store)
        let originalRecord = try KeychainStore.read(account: prefix + "en-es")
        await store.qualifyFailure { if $0 == .beforeActivation { throw Injected() } }
        do { try await install(two, into: store); XCTFail("Injected record failure") } catch is Injected {}
        XCTAssertEqual(try KeychainStore.read(account: prefix + "en-es"), originalRecord)
        let old = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(old, ["old"])
        await store.qualifyFailure { if $0 == .beforeDirectorySync { throw Injected() } }
        do { try await install(two, into: store); XCTFail("Directory synchronization failure before activation") } catch is Injected {}
        XCTAssertEqual(try KeychainStore.read(account: prefix + "en-es"), originalRecord)
        let afterSyncFailure = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(afterSyncFailure, ["old"])
        await store.qualifyFailure { if $0 == .staged { withUnsafeCurrentTask { $0?.cancel() } } }
        let cancelled = Task { try await store.install(manifestBytes: two.manifest, signature: two.signature, database: two.database) }
        do { _ = try await cancelled.value; XCTFail("Cancelled precommit") } catch is CancellationError {}
        XCTAssertEqual(try KeychainStore.read(account: prefix + "en-es"), originalRecord)
        let stillOld = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(stillOld, ["old"])
        await store.qualifyFailure { _ in }; try await install(two, into: store)
        let secondRecord = try KeychainStore.read(account: prefix + "en-es")
        await store.qualifyFailure { if $0 == .beforeRemoval { throw Injected() } }
        do { try await store.remove(id: "en-es"); XCTFail("Removal before trusted commit") } catch is Injected {}
        XCTAssertEqual(try KeychainStore.read(account: prefix + "en-es"), secondRecord)
        try retain("precommit-failure-cancellation", fixtures: [one, two], key: key)
    }
    func testCommittedInstallAndRemovalExposeCleanupFailure() async throws {
        let root = try directory(), prefix = "activation-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let one = try fixture(1, target: "old", key: key), two = try fixture(2, target: "new", key: key)
        let store = try pack(root, prefix: prefix, key: key); try await install(one, into: store)
        await store.qualifyFailure { if $0 == .cleanup { throw Injected() } }
        try await install(two, into: store)
        let reopened = try pack(root, prefix: prefix, key: key)
        let new = try await targets(reopened); XCTAssertEqual(new, ["new"])
        let pending = try await reopened.status(id: "en-es"); XCTAssertTrue(pending.active); XCTAssertFalse(pending.cleanupPendingFiles.isEmpty)
        do { try await store.remove(id: "en-es"); XCTFail("Cleanup failure must be observable") } catch VocabularyPackError.cleanupPending {}
        let removed = try await targets(reopened); XCTAssertTrue(removed.isEmpty)
        let inactive = try await reopened.status(id: "en-es")
        XCTAssertFalse(inactive.active); XCTAssertEqual(inactive.acceptedRevision, 2); XCTAssertFalse(inactive.cleanupPendingFiles.isEmpty)
        let inactiveBytes = try XCTUnwrap(KeychainStore.read(account: prefix + "en-es"))
        let inactiveRecord = try XCTUnwrap(JSONSerialization.jsonObject(with: inactiveBytes) as? [String: Any])
        XCTAssertTrue(inactiveRecord["active"] is NSNull)
        do { try await install(one, into: reopened); XCTFail("Rollback after removal") } catch VocabularyPackError.rollback {}
        try await install(two, into: reopened)
        let repaired = try await targets(reopened); XCTAssertEqual(repaired, ["new"])
        let clean = try await reopened.status(id: "en-es"); XCTAssertTrue(clean.cleanupPendingFiles.isEmpty)
        let three = try fixture(3, target: "committed", key: key)
        await reopened.qualifyFailure { if $0 == .cleanup { withUnsafeCurrentTask { $0?.cancel() }; try Task.checkCancellation() } }
        let lateCancellation = Task { try await reopened.install(manifestBytes: three.manifest, signature: three.signature, database: three.database) }
        let committed = try await lateCancellation.value; XCTAssertEqual(committed, "en-es")
        let latest = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(latest, ["committed"])
        try retain("postcommit-cleanup-removal", fixtures: [one, two, three], key: key)
    }
    func testLegacyRequiresVerifiedReinstallWithoutTrustingPointer() async throws {
        let root = try directory(), prefix = "activation-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let one = try fixture(1, target: "old", key: key), two = try fixture(2, target: "accepted", key: key)
        let legacy = try JSONSerialization.data(withJSONObject: ["revision": 2, "hash": two.hash])
        try KeychainStore.save(legacy, account: prefix + "en-es")
        try Data("{\"file\":\"forged.sqlite\",\"manifest\":{}}".utf8).write(to: root.appendingPathComponent("en-es.json"))
        let store = try pack(root, prefix: prefix, key: key)
        let status = try await store.status(id: "en-es"); XCTAssertTrue(status.reinstallRequired); XCTAssertEqual(status.acceptedRevision, 2)
        do { _ = try await targets(store); XCTFail("Unsigned pointer migration") } catch VocabularyPackError.reinstallRequired {}
        do { try await store.remove(id: "en-es"); XCTFail("Legacy reset") } catch VocabularyPackError.reinstallRequired {}
        XCTAssertEqual(try KeychainStore.read(account: prefix + "en-es"), legacy)
        do { try await install(one, into: store); XCTFail("Legacy rollback") } catch VocabularyPackError.rollback {}
        try await install(two, into: store)
        let result = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(result, ["accepted"])
        let trusted = try XCTUnwrap(KeychainStore.read(account: prefix + "en-es"))
        var malformed = try XCTUnwrap(JSONSerialization.jsonObject(with: trusted) as? [String: Any])
        malformed.removeValue(forKey: "active")
        try KeychainStore.save(JSONSerialization.data(withJSONObject: malformed), account: prefix + "en-es")
        do { _ = try await targets(store); XCTFail("Missing active field is not inactive") } catch {}
        var wrongBinding = try XCTUnwrap(JSONSerialization.jsonObject(with: trusted) as? [String: Any])
        wrongBinding["accepted"] = ["revision": 2, "hash": String(repeating: "0", count: 64)]
        try KeychainStore.save(JSONSerialization.data(withJSONObject: wrongBinding), account: prefix + "en-es")
        do { _ = try await pack(root, prefix: prefix, key: key).status(id: "en-es"); XCTFail("Trusted accepted hash must match original signed manifest") } catch {}
        try KeychainStore.save(trusted, account: prefix + "en-es")
        try retain("legacy-verified-reinstall", fixtures: [one, two], key: key)
    }
    func testConcurrentHandlesSerializeHighwaterAndCleanup() async throws {
        let root = try directory(), prefix = "activation-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let one = try fixture(1, target: "old", key: key), two = try fixture(2, target: "new", key: key)
        let a = try pack(root, prefix: prefix, key: key), b = try pack(root, prefix: prefix, key: key)
        let firstGate = Gate(); await a.qualifyFailure { if $0 == .staged { try firstGate.block() } }
        let high = Task { try await a.install(manifestBytes: two.manifest, signature: two.signature, database: two.database) }
        let entered = await firstGate.observed(); XCTAssertTrue(entered)
        let contender = Gate(); await b.qualifyFailure { if $0 == .waitingForNamespace { contender.entered.signal() } }
        let low = Task { try await b.install(manifestBytes: one.manifest, signature: one.signature, database: one.database) }
        let waiting = await contender.observed(); XCTAssertTrue(waiting)
        firstGate.release.signal(); _ = try await high.value
        do { _ = try await low.value; XCTFail("Concurrent downgrade") } catch VocabularyPackError.rollback {}
        let secondGate = Gate(); await a.qualifyFailure { if $0 == .cleanup { try secondGate.block() } }
        let removal = Task { try await a.remove(id: "en-es") }
        let removing = await secondGate.observed(); XCTAssertTrue(removing)
        let reinstallation = Task { try await b.install(manifestBytes: two.manifest, signature: two.signature, database: two.database) }
        let installing = await contender.observed(); XCTAssertTrue(installing)
        secondGate.release.signal(); try await removal.value; _ = try await reinstallation.value
        let result = try await targets(try pack(root, prefix: prefix, key: key)); XCTAssertEqual(result, ["new"])
        try retain("cross-handle-serialization", fixtures: [one, two], key: key)
    }
    func testSignatureAndContentIntegrityWithNativeSQLiteLookup() async throws {
        let root = try directory(), prefix = "integrity-" + UUID().uuidString.lowercased() + "-", key = P256.Signing.PrivateKey()
        defer { try? FileManager.default.removeItem(at: root); KeychainStore.delete(account: prefix + "en-es") }
        let store = try pack(root, prefix: prefix, key: key)
        let signed = try fixture(1, target: "café", key: key)
        let manifest = signed.manifest, signature = signed.signature, database = signed.database
        let id = try await store.install(manifestBytes: manifest, signature: signature, database: database)
        XCTAssertEqual(id, "en-es")
        let original = "Coffee tomorrow? I know a little place by the river."
        let entries = try await store.entries(id: id, text: original)
        XCTAssertTrue(entries.contains(where: { $0.source == "coffee" && $0.targets.contains("café") }))
        let result = ImmersionEngine().align(original: original, translation: "¿Café mañana? Conozco un pequeño lugar junto al río.", entries: entries, density: 0.3)
        XCTAssertTrue(result.spans.contains(where: { $0.translated == "Café" }))
        var damaged = database; damaged[damaged.count - 1] ^= 1
        do { _ = try await store.install(manifestBytes: manifest, signature: signature, database: damaged); XCTFail("Accepted corrupt database") } catch { }
        var fakeSignature = signature; fakeSignature[fakeSignature.count - 1] ^= 1
        do { _ = try await store.install(manifestBytes: manifest, signature: fakeSignature, database: database); XCTFail("Accepted invalid signature") } catch { }
        let unchanged = try await store.entries(id: id, text: original)
        XCTAssertEqual(entries, unchanged)
        try await store.remove(id: id)
        let removed = try await store.entries(id: id, text: original)
        XCTAssertTrue(removed.isEmpty)
    }
}
