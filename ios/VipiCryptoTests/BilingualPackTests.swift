import Foundation
import XCTest
import VipiCore
@testable import Vipi

final class BilingualPackTests: XCTestCase {
    func testJapaneseMixedScriptAndInflectionsKeepWholeMorphemes() {
        let mixed = "私の妹は銀行で働いています。 She will help me tomorrow."
        XCTAssertTrue(LocalImmersion.words(mixed, language: "ja").map { (mixed as NSString).substring(with: $0) }.contains("銀行"))
        let inflected = "18:30に会おう。生きています。"
        let words = LocalImmersion.words(inflected, language: "ja").map { (inflected as NSString).substring(with: $0) }
        XCTAssertFalse(words.contains("会")); XCTAssertFalse(words.contains("生"))
        XCTAssertTrue(words.contains("会おう")); XCTAssertTrue(words.contains("生き"))
    }
    private struct Fixture: Decodable {
        struct Sample: Decodable {
            let id: String; let source: String; let target: String; let text: String; let translation: String
            let expected: String; let written: String; let reading: String?
            let manifest: Data; let signature: Data; let database: Data
        }
        let purpose: String; let public_key: Data; let cases: [Sample]
    }
    func testSignedBilingualSenseAndReadingRoundTrip() async throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "bilingual-lookup", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        XCTAssertEqual(fixture.purpose, "SYNTHETIC BILINGUAL QA ONLY")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("bilingual-qa-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["synthetic-bilingual-qa": fixture.public_key])
        for sample in fixture.cases {
            let key = "pack-" + sample.id
            guard try KeychainStore.read(account: key) == nil else { throw XCTSkip("Preserve installed pack receipt") }
            do {
                let id = try await store.install(manifestBytes: sample.manifest, signature: sample.signature, database: sample.database)
                XCTAssertEqual(id, sample.id)
                let entries = try await store.entries(id: id, text: sample.text)
                let result = LocalImmersion.align(original: sample.text, translation: sample.translation, entries: entries, density: 1, source: sample.source, target: sample.target)
                XCTAssertEqual(result.spans.count, 1, sample.id)
                XCTAssertEqual(result.spans.first?.original, sample.expected)
                XCTAssertEqual(result.spans.first?.translated, sample.written)
                XCTAssertEqual(result.spans.first?.romanization, sample.reading)
                XCTAssertTrue(result.speech(source: sample.source, target: sample.target).contains { $0.text == sample.written && $0.language == sample.target })
                if sample.target == "fr" {
                    XCTAssertEqual(entries.filter { $0.source == "bank" }.count, 2, "Two bank senses must not merge")
                    XCTAssertTrue(entries.contains { $0.contextHints.contains("river") })
                    XCTAssertTrue(entries.filter { $0.source == "bank" }.allSatisfy(\.requiresContext))
                    XCTAssertTrue(LocalImmersion.align(original: "A bank.", translation: "Une banque.", entries: entries, density: 1, source: "en", target: "fr").spans.isEmpty)
                    let incorrect = LocalImmersion.align(original: sample.text, translation: "Une banque près du fleuve.", entries: entries, density: 1, source: "en", target: "fr")
                    XCTAssertTrue(incorrect.spans.isEmpty, "Source river context must veto the financial mistranslation")
                    let ambiguous = LocalImmersion.align(original: "A bank.", translation: "Une banque et une rive.", entries: entries, density: 1, source: "en", target: "fr")
                    XCTAssertTrue(ambiguous.spans.isEmpty)
                }
                if sample.target == "ja" {
                    let conflict = try await store.entries(id: id, text: "I read.")
                    let result = LocalImmersion.align(original: "I read.", translation: "読む。", entries: conflict, density: 1, source: "en", target: "ja")
                    XCTAssertTrue(result.spans.isEmpty, "Conflicting readings must abstain")
                }
                if sample.target == "zh" {
                    let missing = try await store.entries(id: id, text: "It is missing.")
                    let result = LocalImmersion.align(original: "It is missing.", translation: "丢失。", entries: missing, density: 1, source: "en", target: "zh")
                    XCTAssertTrue(result.spans.isEmpty, "Non-Roman immersion always requires a reading")
                }
                try await store.remove(id: id); KeychainStore.delete(account: key)
            } catch { try? await store.remove(id: sample.id); KeychainStore.delete(account: key); throw error }
        }
    }
}
