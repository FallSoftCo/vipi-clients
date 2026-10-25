import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class SignedLanguageLookupTests: XCTestCase {
    struct Fixture: Decodable {
        let purpose: String; let public_key: Data; let cases: [Sample]
        struct Sample: Decodable { let id: String; let text: String; let expected: String; let partial: String; let manifest: Data; let signature: Data; let database: Data }
    }
    func testNativeReadingFormatKeepsToneMarksAndRejectsIPA() {
        for (reading, accepted) in [("kāfēi", true), ("ɡa", false), ("...", false)] {
            let entries = [VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": [reading]])]
            let result = LocalImmersion.align(original: "Want coffee?", translation: "明天喝咖啡。", entries: entries, density: 1, source: "en", target: "zh")
            XCTAssertEqual(!result.spans.isEmpty, accepted)
            if accepted {
                XCTAssertEqual(result.spans.first?.displayedTarget, reading)
                XCTAssertTrue(result.speech(source: "en", target: "zh").contains { $0.text == "咖啡" })
            }
        }
    }
    func testSignedDictionaryLookupUsesNativeBoundaries() async throws {
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "signed-lookup", withExtension: "json"))))
        XCTAssertEqual(fixture.purpose, "SYNTHETIC NATIVE WORD LOOKUP QA ONLY")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("lookup-qa-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["synthetic-lookup-qa":fixture.public_key])
        for sample in fixture.cases {
            let key = "pack-" + sample.id
            // A fixture never replaces a real pack's anti-rollback receipt.
            guard try KeychainStore.read(account: key) == nil else { throw XCTSkip("Existing language pack receipt must be preserved") }
            do {
                let id = try await store.install(manifestBytes: sample.manifest, signature: sample.signature, database: sample.database)
                let entries = try await store.entries(id: id, text: sample.text)
                XCTAssertTrue(entries.contains { $0.source == sample.expected && $0.targets.contains("coffee") }, sample.id)
                XCTAssertFalse(entries.contains { $0.source == sample.partial }, sample.id)
                try await store.remove(id: id); KeychainStore.delete(account: key)
            } catch { KeychainStore.delete(account: key); throw error }
        }
    }
}
