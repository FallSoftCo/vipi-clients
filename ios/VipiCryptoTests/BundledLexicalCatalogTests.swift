import XCTest
@testable import Vipi

final class BundledLexicalCatalogTests: XCTestCase {
    func testSelectedPairRepairsDamageAndRejectsInvalidStreams() async throws {
        let resources = try XCTUnwrap(Bundle(for: Self.self).resourceURL?.appendingPathComponent("lexical-fixture"))
        let root = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("lexical-fixture-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = BundledLexicalCatalog(resources: resources, root: root)
        let pair = TranslationPair(source: "en", target: "es")
        let prepared = try await store.prepare(pair)
        XCTAssertTrue(prepared)
        func files() throws -> [URL] { try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) }
        XCTAssertEqual(try files().count, 3)
        XCTAssertFalse(try files().contains { $0.lastPathComponent.hasPrefix("d-pt-") })
        let entries = try await store.entries(original: "An apple.", translation: "Una manzana.", pair: pair)
        XCTAssertTrue(entries.contains { $0.source == "apple" && $0.targets.contains("manzana") })
        let file = try XCTUnwrap(try files().first { $0.lastPathComponent.hasPrefix("d-en-") })
        let expected = try Data(contentsOf: file)
        let initial = try file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate
        _ = try await store.prepare(.init(source: "es", target: "en"))
        XCTAssertEqual(initial, try file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate)
        try Data([0, 1]).write(to: file)
        _ = try await store.prepare(pair)
        XCTAssertEqual(expected, try Data(contentsOf: file))
        for target in ["fr", "de"] {
            do {
                _ = try await store.prepare(.init(source: "en", target: target))
                XCTFail("Invalid stream must fail")
            } catch {}
            XCTAssertEqual(try files().count, 3)
            XCTAssertFalse(try files().contains { $0.lastPathComponent.hasPrefix("prepare-") })
        }
        let retained = try await store.entries(original: "An apple.", translation: "Una manzana.", pair: pair)
        XCTAssertTrue(retained.contains { $0.source == "apple" })
    }
}
