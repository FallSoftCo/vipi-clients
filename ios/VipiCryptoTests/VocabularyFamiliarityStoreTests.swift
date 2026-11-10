import Foundation
import XCTest
import VipiCore
import CryptoKit
@testable import Vipi

final class VocabularyFamiliarityStoreTests: XCTestCase {
    func testEncryptedExposureSurvivesReopenAndSeparatesPairs() throws {
        let account = UUID()
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("FamiliarityQA/\(account)")
        defer {
            if FileManager.default.fileExists(atPath: root.path) { try? FileManager.default.removeItem(at: root) }
            KeychainStore.delete(account: "messages-\(account.uuidString.lowercased())")
        }
        let spans = try XCTUnwrap(SourceReferencePresentation.create(original: "tea", target: "sw",
            units: [.init(range: NSRange(location: 0, length: 3), original: "tea", translated: "chai",
                reading: nil, referenceID: "qa-tea", catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: 1)],
            density: 1, nativeSourceTokenCount: 1)).spans
        let vault: MessageVault
        do { vault = try MessageVault(account: account, directory: root) }
        catch {
            let failure = error as NSError
            XCTFail("Vault prerequisite failed: \(failure.domain) code \(failure.code)")
            return
        }
        let store = VocabularyFamiliarityStore(vault: vault)
        for day in 100...103 {
            XCTAssertTrue(store.observe(spans, source: "en", target: "sw", day: day))
            XCTAssertTrue(store.observe(spans, source: "en", target: "sw", day: day))
        }
        XCTAssertEqual(store.targetMilliseconds(spans, source: "en", target: "sw", day: 103), 6000)
        try vault.close()
        XCTAssertFalse(store.observe(spans, source: "en", target: "sw", day: 104))
        let reopened = try MessageVault(account: account, directory: root)
        defer { try? reopened.close() }
        let restored = VocabularyFamiliarityStore(vault: reopened)
        XCTAssertEqual(restored.targetMilliseconds(spans, source: "en", target: "sw", day: 103), 6000)
        XCTAssertEqual(restored.targetMilliseconds(spans, source: "en", target: "es", day: 103), 4500)
        try reopened.transaction {
            let ids = try reopened.ids("immersion-exposure")
            XCTAssertEqual(ids.count, 1); XCTAssertEqual(ids.first?.count, 64)
            let guessable = SHA256.hash(data: Data("v1\0en\0sw\0tea\0chai".utf8)).map { String(format: "%02x", $0) }.joined()
            XCTAssertNotEqual(ids.first, guessable)
            XCTAssertEqual(try reopened.get("immersion-metadata", "id-key-v1")?.count, 32)
            let bytes = try XCTUnwrap(reopened.get("immersion-exposure", ids[0]))
            let record = try JSONDecoder().decode(VocabularyFamiliarity.self, from: bytes)
            XCTAssertEqual(record.exposureDays, 4)
            XCTAssertFalse(String(decoding: bytes, as: UTF8.self).contains("tea"))
        }
    }
}
