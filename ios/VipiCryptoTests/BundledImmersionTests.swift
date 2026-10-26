import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class BundledImmersionTests: XCTestCase {
    func testAppBundledCatalogAcrossAll110DirectionsAndOriginalPreservation() async throws {
        let root = try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        let index = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("catalog.json"))) as? [String: Any])
        let rows = try XCTUnwrap(index["references"] as? [[String: String]])
        let catalog = BundledImmersionCatalog(root: root)
        var pairs = Set<String>(), count = 0, selected = 0
        for row in rows {
            let pairID = try XCTUnwrap(row["pair"]), codes = pairID.split(separator: "-").map(String.init)
            let pair = TranslationPair(source: codes[0], target: codes[1])
            let original = try XCTUnwrap(row["original"]), translation = try XCTUnwrap(row["translation"])
            let reference = try await catalog.reference(original: original, pair: pair)
            XCTAssertEqual(reference, translation)
            let result = try await catalog.result(original: original, translation: translation, pair: pair, density: 1)
            XCTAssertEqual(result.original, original); XCTAssertEqual(result.translation, translation)
            XCTAssertEqual(result.speech(source: pair.source, target: pair.target, revealed: Set(result.spans.map(\.id))).map(\.text).joined(), original)
            if ["ar", "zh", "ja", "ko"].contains(pair.target) { XCTAssertTrue(result.spans.allSatisfy { $0.romanization != nil }) }
            selected += result.spans.count; count += 1; pairs.insert(pairID)
        }
        XCTAssertEqual(pairs.count, 110); XCTAssertEqual(count, 9073); XCTAssertGreaterThan(selected, 8600)
        let pair = TranslationPair(source: "en", target: "sw")
        let corrected = try await catalog.reference(original: "I am drinking water now.", pair: pair)
        XCTAssertEqual(corrected, "Ninakunywa maji sasa.")
        let differentPerson = try await catalog.reference(original: "We are drinking water now.", pair: pair)
        XCTAssertNil(differentPerson, "Never borrow an exact reference's person/tense")
        let embedded = try await catalog.result(original: "We are drinking water now.", translation: "Tunakunywa maji sasa.", pair: pair, density: 1)
        XCTAssertEqual(embedded.spans.count, 1)
        XCTAssertEqual(embedded.speech(source: "en", target: "sw").map(\.text).joined(), "We are drinking maji now.")
        let unrelated = try await catalog.result(original: "Book a room for us.", translation: "Tuwekee chumba.", pair: pair, density: 1)
        XCTAssertTrue(unrelated.spans.isEmpty)
        let paragraph = "I like music.\nI am drinking water now."
        let combined = try await catalog.reference(original: paragraph, pair: pair)
        XCTAssertEqual(combined, "Ninapenda muziki.\nNinakunywa maji sasa.")
        let unknown = try await catalog.reference(original: "I like music.\nDo not guess this sentence.", pair: pair)
        XCTAssertNil(unknown)
        let contextualPair = TranslationPair(source: "en", target: "es")
        let owned = try await catalog.result(original: "Can they bring our book?", translation: "¿Pueden traer nuestro libro?", pair: contextualPair, density: 1)
        XCTAssertEqual(owned.speech(source: "en", target: "es").map(\.text).joined(), "Can they bring our libro?")
        let office = try await catalog.result(original: "Niko ofisini.", translation: "I’m at the office.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(office.speech(source: "sw", target: "en").map(\.text).joined(), "Niko officeni.")
        let money = try await catalog.result(original: "I don’t have enough money.", translation: "Sina pesa za kutosha.", pair: .init(source: "en", target: "sw"), density: 1)
        XCTAssertEqual(money.speech(source: "en", target: "sw").map(\.text).joined(), "I don’t have enough pesa.")
        let request = try await catalog.result(original: "Natafuta hoteli karibu.", translation: "I am looking for a hotel nearby.", pair: .init(source: "sw", target: "en"), density: 1)
        XCTAssertEqual(request.speech(source: "sw", target: "en").map(\.text).joined(), "Natafuta hotel karibu.")
        let plural = try await catalog.result(original: "We are looking for a hotel nearby.", translation: "Tunatafuta hoteli karibu.", pair: pair, density: 1)
        XCTAssertEqual(plural.speech(source: "en", target: "sw").map(\.text).joined(), "We are looking for a hoteli nearby.")
        let ticket = try await catalog.result(original: "I need a train ticket.", translation: "Ninahitaji tiketi ya treni.", pair: pair, density: 0.25)
        XCTAssertEqual(ticket.speech(source: "en", target: "sw").map(\.text).joined(), "I need a tiketi ya treni.")
        let unsupportedNegative = try await catalog.result(original: "We are not sending an email tonight.", translation: "Hatutumi barua pepe leo usiku.", pair: pair, density: 1)
        XCTAssertTrue(unsupportedNegative.spans.isEmpty)
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("bundled-immersion-004.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        try JSONSerialization.data(withJSONObject: ["pairs":pairs.count, "references":count, "spans":selected,
            "runtime_path":"app-bundled-native-catalog", "independent_linguistic_acceptance":false], options: [.prettyPrinted,.sortedKeys])
            .write(to: output, options: .withoutOverwriting)
    }
}
