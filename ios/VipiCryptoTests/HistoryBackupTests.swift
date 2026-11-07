import XCTest
import CryptoKit
import Darwin
@testable import Vipi

final class HistoryBackupTests: XCTestCase {
    private let account = UUID(uuidString: "11111111-1111-4111-8111-111111111111")!
    private let peer = UUID(uuidString: "22222222-2222-4222-8222-222222222222")!
    private let password = "correct horse vipi 2026"
    private func peakResidentBytes() -> Int64 {
        var value = rusage(); _ = getrusage(RUSAGE_SELF, &value)
        return Int64(value.ru_maxrss) // Darwin reports bytes, not Linux KiB.
    }
    private func metric(_ values: [String: Any]) throws {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("history-backup-metrics.json")
        var all = (try? JSONSerialization.jsonObject(with: Data(contentsOf: url))) as? [String: Any] ?? [:]
        all.merge(values) { _, new in new }
        try JSONSerialization.data(withJSONObject: all, options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
    }
    private func fixture(_ name: String) throws -> URL {
        try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "vipihistory"))
    }
    private func folder() throws -> URL {
        let value = FileManager.default.temporaryDirectory.appendingPathComponent("history-test-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: value, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: value) }
        return value
    }
    private func records() throws -> [HistoryBackupRecord] {
        var rows: [HistoryBackupRecord] = []
        _ = try HistoryBackupCodec.inspect(url: fixture("ascii"), password: password, account: account) { rows.append($0) }
        return rows
    }
    private func write(_ records: [HistoryBackupRecord], to url: URL) throws {
        let writer = try HistoryBackupCodec.Writer(url: url, password: password, account: account)
        for record in records { try writer.append(record) }
        try writer.finish()
    }
    func testIndependentVectorsUnicodeNormalizationAndAndroidExport() throws {
        for (name, password) in [("ascii", self.password), ("unicode", "Vipi cafe\u{301} 日本語 🔐 2026"), ("android-history-v1", "Vipi café 日本語 🔐 2026")] {
            var rows: [HistoryBackupRecord] = []
            let summary = try HistoryBackupCodec.inspect(url: fixture(name), password: password, account: account) { rows.append($0) }
            XCTAssertEqual(summary.peers, 1); XCTAssertEqual(summary.messages, 2); XCTAssertEqual(rows.count, 5)
            guard case .message(let incoming) = rows[2], case .message(let outgoing) = rows[3] else { return XCTFail("Missing fixture messages") }
            XCTAssertEqual(incoming.text, "Habari! Tutaonana kesho. 👋"); XCTAssertFalse(incoming.outgoing)
            XCTAssertEqual(outgoing.text, "See you tomorrow. 日本語 العربية café"); XCTAssertTrue(outgoing.outgoing)
        }
        let start = ContinuousClock.now
        let key = try HistoryBackupCodec.deriveKey(password: "Vipi cafe\u{301} 日本語 🔐 2026", salt: Data(0..<16))
        let elapsed = start.duration(to: .now).components
        try metric(["pbkdf2_iterations": 600000, "pbkdf2_seconds": Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18,
                    "process_high_water_bytes_after_vectors": peakResidentBytes(), "memory_scope": "Entire native test-host process; not codec-only allocation"])
        XCTAssertEqual(key.map { String(format: "%02x", $0) }.joined(), "f7b46c2cabeabad5ea88a382849c969ce422aebeaf3ab637440b076d6ef2d1b3")
    }
    func testDeterministicReferenceEncodingAndNativeInterchangeFile() throws {
        let rows = try records(), exact = try folder().appendingPathComponent("exact.vipihistory")
        let writer = try HistoryBackupCodec.Writer(url: exact, password: password, account: account, salt: Data(0..<16), noncePrefix: Data(160..<168))
        for row in rows { try writer.append(row) }; try writer.finish()
        XCTAssertEqual(try Data(contentsOf: exact), try Data(contentsOf: fixture("ascii")))
        // Public test-only fixture, retained for actual Android codec import.
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("ios-history-v1.vipihistory")
        try? FileManager.default.removeItem(at: output)
        let native = try HistoryBackupCodec.Writer(url: output, password: "Vipi café 日本語 🔐 2026", account: account)
        for row in rows { try native.append(row) }; try native.finish()
        XCTAssertEqual(try HistoryBackupCodec.inspect(url: output, password: "Vipi cafe\u{301} 日本語 🔐 2026", account: account).messages, 2)
    }
    func testAuthenticationFramingAndAccountFailures() throws {
        let original = try Data(contentsOf: fixture("ascii")), directory = try folder()
        var offsets = [Int](), offset = 36
        while offset < original.count {
            offsets.append(offset)
            let size = original[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) }
            offset += 4 + size
        }
        var header = original; header[28] ^= 1
        var cipher = original; cipher[55] ^= 1
        var iterations = original; iterations.replaceSubrange(8..<12, with: [0, 0, 0, 1])
        var oversized = original; oversized.replaceSubrange(36..<40, with: [0, 4, 0, 17])
        let reordered = original.prefix(36) + original[offsets[1]..<offsets[2]] + original[offsets[0]..<offsets[1]] + original.suffix(from: offsets[2])
        let invalid: [Data] = [Data(original.dropLast()), Data(original.prefix(offsets.last!)), original + Data([0]), header, cipher, iterations, oversized, reordered]
        for (index, bytes) in invalid.enumerated() {
            let url = directory.appendingPathComponent("invalid-\(index).vipihistory"); try bytes.write(to: url)
            XCTAssertThrowsError(try HistoryBackupCodec.inspect(url: url, password: password, account: account))
        }
        XCTAssertThrowsError(try HistoryBackupCodec.inspect(url: fixture("ascii"), password: "wrong password 2026", account: account))
        XCTAssertThrowsError(try HistoryBackupCodec.inspect(url: fixture("ascii"), password: password, account: peer)) { error in
            guard case HistoryBackupCodec.Failure.differentAccount = error else { return XCTFail("Expected account isolation") }
        }
    }
    func testAuthenticatedDuplicateAndUnknownJSONFieldsAreRejected() throws {
        let original = try Data(contentsOf: fixture("ascii")), header = Data(original.prefix(36))
        let key = SymmetricKey(data: try HistoryBackupCodec.deriveKey(password: password, salt: header.subdata(in: 12..<28)))
        let valid = "{\"type\":\"metadata\",\"version\":1,\"account_id\":\"11111111-1111-4111-8111-111111111111\",\"created_at_ms\":1794089000000}"
        let malformed = [valid.replacingOccurrences(of: "\"version\":1", with: "\"version\":1,\"ver\\u0073ion\":1"),
                         valid.replacingOccurrences(of: "\"version\":1", with: "\"version\":1.0"),
                         valid.replacingOccurrences(of: "1794089000000", with: "true"),
                         valid.replacingOccurrences(of: "1794089000000", with: "1e3"),
                         String(valid.dropLast()) + ",\"unknown\":null}"]
        func big(_ value: UInt32) -> Data { Data([UInt8((value >> 24) & 255), UInt8((value >> 16) & 255), UInt8((value >> 8) & 255), UInt8(value & 255)]) }
        for (index, metadata) in malformed.enumerated() {
            var file = header
            for (sequence, row) in [metadata, "{\"type\":\"end\",\"record_count\":1,\"peer_count\":0,\"message_count\":0}"].enumerated() {
                let bytes = Data(row.utf8), counter = big(UInt32(sequence)), length = big(UInt32(bytes.count + 16))
                let sealed = try AES.GCM.seal(bytes, using: key, nonce: AES.GCM.Nonce(data: header.suffix(8) + counter), authenticating: header + counter + length)
                file += length + sealed.ciphertext + sealed.tag
            }
            let url = try folder().appendingPathComponent("schema-\(index).vipihistory"); try file.write(to: url)
            XCTAssertThrowsError(try HistoryBackupCodec.inspect(url: url, password: password, account: account))
        }
    }
    func testAtomicMergeDeduplicatesWithoutTransportState() throws {
        let vault = try MessageVault(account: account, directory: folder()); defer { try? vault.close() }
        let history = try ConversationHistory(vault: vault)
        try vault.transaction { try vault.put("local", "device", Data("unchanged runtime sentinel".utf8)) }
        let source = try fixture("ascii"), preview = try HistoryBackupCodec.inspect(url: source, password: password, account: account)
        let first = try HistoryBackupStore.merge(vault: vault, staged: source, password: password, verified: preview)
        XCTAssertEqual(first.added, 2); XCTAssertEqual(first.existing, 0)
        let again = try HistoryBackupStore.merge(vault: vault, staged: source, password: password, verified: preview)
        XCTAssertEqual(again.added, 0); XCTAssertEqual(again.existing, 2)
        XCTAssertEqual(try history.messages(peer: peer).count, 2)
        XCTAssertTrue(try history.messages(peer: peer).allSatisfy { $0.state == "imported" })
        XCTAssertEqual(try history.threads().first?.unread, 0)
        try vault.transaction {
            XCTAssertEqual(try vault.get("local", "device"), Data("unchanged runtime sentinel".utf8))
            for kind in ["incoming", "outgoing", "pending", "receipt", "draft", "signal"] { XCTAssertTrue(try vault.ids(kind).isEmpty) }
        }
        try vault.close()
        let reopened = try MessageVault(account: account, directory: vault.url.deletingLastPathComponent().deletingLastPathComponent())
        defer { try? reopened.close() }
        XCTAssertEqual(try ConversationHistory(vault: reopened).messages(peer: peer).count, 2)
    }
    func testFooterTamperingAndIDConflictRollBackAllEarlierWrites() throws {
        let directory = try folder(), source = directory.appendingPathComponent("staged.vipihistory")
        try Data(contentsOf: fixture("ascii")).write(to: source)
        let preview = try HistoryBackupCodec.inspect(url: source, password: password, account: account)
        var damaged = try Data(contentsOf: source); damaged[damaged.count - 1] ^= 1; try damaged.write(to: source)
        let vault = try MessageVault(account: account, directory: directory); defer { try? vault.close() }
        _ = try ConversationHistory(vault: vault)
        XCTAssertThrowsError(try HistoryBackupStore.merge(vault: vault, staged: source, password: password, verified: preview))
        try vault.transaction {
            XCTAssertTrue(try vault.ids("imported").isEmpty); XCTAssertTrue(try vault.ids("imported-peer").isEmpty)
            XCTAssertTrue(try vault.ids("history").isEmpty); XCTAssertTrue(try vault.ids("thread").isEmpty)
        }
        let conflict = HistoryBackupMessage(id: UUID(uuidString: "44444444-4444-4444-8444-444444444444")!, peer: peer, outgoing: true, createdAt: 1794088100000, text: "Existing different text")
        try vault.transaction { try vault.put("imported", conflict.id.uuidString.lowercased(), JSONEncoder().encode(conflict)) }
        XCTAssertThrowsError(try HistoryBackupStore.merge(vault: vault, staged: fixture("ascii"), password: password, verified: preview))
        try vault.transaction {
            XCTAssertEqual(try vault.ids("imported"), [conflict.id.uuidString.lowercased()])
            XCTAssertTrue(try vault.ids("imported-peer").isEmpty); XCTAssertTrue(try vault.ids("history").isEmpty)
        }
    }
    func testUnknownPeerAndPagedExportExcludeUnsentDrafts() throws {
        let directory = try folder(), vault = try MessageVault(account: account, directory: directory)
        defer { try? vault.close() }
        let history = try ConversationHistory(vault: vault)
        try vault.transaction {
            for index in 0..<1001 {
                let row = HistoryBackupMessage(id: UUID(), peer: peer, outgoing: index % 2 == 0, createdAt: 1794088100000 + Int64(index), text: String(repeating: "日本語 café ", count: 1000))
                try vault.put("imported", row.id.uuidString.lowercased(), JSONEncoder().encode(row))
                try ConversationHistory.record(vault, kind: "imported", id: row.id, peer: peer, createdAt: row.createdAt)
            }
        }
        let journal = MessageJournal(vault: vault), now = Int64(Date().timeIntervalSince1970 * 1000)
        try journal.saveDraft(id: UUID(), recipient: peer, text: "Private unsent draft", createdAt: now, now: now)
        XCTAssertEqual(try history.threads().count, 1)
        let output = directory.appendingPathComponent("paged.vipihistory")
        let memoryBefore = peakResidentBytes(), start = ContinuousClock.now
        try HistoryBackupStore.export(vault: vault, password: password, to: output)
        var sawUnknown = false
        let result = try HistoryBackupCodec.inspect(url: output, password: password, account: account) { record in
            if case .peer(let peer) = record { sawUnknown = peer.username == nil && peer.displayName == nil }
            if case .message(let row) = record { XCTAssertNotEqual(row.text, "Private unsent draft") }
        }
        XCTAssertTrue(sawUnknown); XCTAssertEqual(result.messages, 1001)
        let elapsed = start.duration(to: .now).components
        try metric(["paged_messages": 1001, "paged_file_bytes": try output.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0,
                    "paged_export_and_verify_seconds": Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18,
                    "process_high_water_bytes_before_paged_export": memoryBefore, "process_high_water_bytes_after_paged_export": peakResidentBytes()])
    }
    func testPeerEnumerationPagesOpaqueIDsWithoutLoadingLatestPlaintext() throws {
        let directory = try folder(), vault = try MessageVault(account: account, directory: directory)
        defer { try? vault.close() }
        let history = try ConversationHistory(vault: vault)
        let peers = (0..<257).map { UUID(uuidString: String(format: "00000000-0000-4000-8000-%012x", $0))! }
        try vault.transaction {
            // Deliberately unavailable latest records make any accidental full
            // ChatThread construction fail; ID-only backup discovery is valid.
            for peer in peers { try vault.put("thread", peer.uuidString.lowercased(), Data("unavailable summary".utf8)) }
        }
        XCTAssertEqual(Set(try history.backupPeerIDs()), Set(peers))
        let output = directory.appendingPathComponent("peers.vipihistory")
        try HistoryBackupStore.export(vault: vault, password: password, to: output)
        let summary = try HistoryBackupCodec.inspect(url: output, password: password, account: account)
        XCTAssertEqual(summary.peers, 257); XCTAssertEqual(summary.messages, 0)
    }
}
