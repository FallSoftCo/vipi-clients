import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class VocabularyPackTests: XCTestCase {
    func testSignatureAndContentIntegrityWithNativeSQLiteLookup() async throws {
        func resource(_ name: String, _ type: String) throws -> Data {
            try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: type)))
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("vipi-pack-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["development-2026-10": resource("signing-public-key", "der")])
        let manifest = try resource("manifest", "json")
        let signature = try resource("manifest", "sig")
        let database = try resource("vocabulary", "sqlite")
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
