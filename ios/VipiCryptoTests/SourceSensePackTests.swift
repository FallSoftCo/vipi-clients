import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class SourceSensePackTests: XCTestCase {
    func testCapturedProviderErrorsRemainNative() async throws {
        struct Case: Decodable { let pair: String; let original: String; let translation: String; let rejected_source: String }
        struct Regression: Decodable { let cases: [Case]; let capture_sha256: String }
        let fixture = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("source-senses-regression")
        let regression = try JSONDecoder().decode(Regression.self, from: Data(contentsOf: fixture.appendingPathComponent("regression.json")))
        XCTAssertEqual(regression.cases.count, 3)
        XCTAssertEqual(regression.capture_sha256.count, 64)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("source-senses-regression-\(UUID())")
        let prefix = "ss-reg-" + UUID().uuidString.lowercased() + "-"
        defer {
            try? FileManager.default.removeItem(at: root)
            for item in regression.cases { try? KeychainStore.deleteChecked(account: prefix + item.pair) }
        }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["bilingual-qualification-007": Data(contentsOf: fixture.appendingPathComponent("signing-public-key.der"))], receiptPrefix: prefix)
        for item in regression.cases {
            let folder = fixture.appendingPathComponent(item.pair)
            func data(_ name: String) throws -> Data { try Data(contentsOf: folder.appendingPathComponent(name)) }
            _ = try await store.install(manifestBytes: data("manifest.json"), signature: data("manifest.sig"), database: data("vocabulary.sqlite"))
            let entries = try await store.entries(id: item.pair, text: item.original)
            let languages = item.pair.split(separator: "-").map(String.init)
            let result = LocalImmersion.align(original: item.original, translation: item.translation, entries: entries, density: 0.3, source: languages[0], target: languages[1])
            XCTAssertFalse(result.spans.contains { $0.original.lowercased() == item.rejected_source }, item.pair)
            if item.rejected_source == "lectura" {
                let meanings = entries.filter { $0.source == "lectura" }
                XCTAssertEqual(meanings.count, 4)
                XCTAssertEqual(meanings.filter { $0.targets.isEmpty }.count, 3)
            }
            try await store.remove(id: item.pair)
        }
    }

    func testUnmappedSensesSurviveSignedNativeLookup() async throws {
        let fixture = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("source-senses-fixture")
        func data(_ name: String) throws -> Data { try Data(contentsOf: fixture.appendingPathComponent(name)) }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("source-senses-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let prefix = "ss-test-" + UUID().uuidString.lowercased() + "-"
        defer { try? KeychainStore.deleteChecked(account: prefix + "en-es") }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["source-senses-test": data("signing-public-key.der")], receiptPrefix: prefix)
        _ = try await store.install(manifestBytes: data("manifest.json"), signature: data("manifest.sig"), database: data("vocabulary.sqlite"))
        let sentence = "Walk by the river bank."
        let entries = try await store.entries(id: "en-es", text: sentence)
        let banks = entries.filter { $0.source == "bank" }
        XCTAssertEqual(banks.count, 3)
        XCTAssertEqual(banks.filter { $0.targets.isEmpty }.count, 2)
        XCTAssertTrue(banks.allSatisfy(\.requiresContext))
        XCTAssertTrue(banks.filter { $0.targets.isEmpty }.allSatisfy { $0.contextHints.contains("river") })
        XCTAssertTrue(ImmersionEngine().align(original: sentence, translation: "Camina por el banco del río.", entries: entries, density: 1).spans.isEmpty)
        let coffee = try await store.entries(id: "en-es", text: "Coffee please.")
        XCTAssertEqual(ImmersionEngine().align(original: "Coffee please.", translation: "Café por favor.", entries: coffee, density: 1).spans.map(\.translated), ["Café"])
        let contractions = try await store.entries(id: "en-es", text: "Don't move. Don’t stop.")
        XCTAssertTrue(contractions.isEmpty)
        try await store.remove(id: "en-es")
    }
}
