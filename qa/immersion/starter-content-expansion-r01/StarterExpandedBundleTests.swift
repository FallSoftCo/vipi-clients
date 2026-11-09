import XCTest
import Foundation
import VipiCore
@testable import Vipi

/// Final bundle and default conversation path, without an injected lookup provider.
@MainActor final class StarterExpandedBundleTests: XCTestCase {
    func testFinalBundlePreservesConflictingFormsAndUsesNewVocabulary() async throws {
        let expected = [
            "ja": (189, "26d499d87e12fbf6bb938fcbb095d084f2f09ef301ca2b60a9a0dc42b10480d0"),
            "sw": (213, "e474bfebae95e6f8a6f58c1eeaaf6be65582fad243ae33a6a83e9e1e1f785373")
        ]
        let controls: [(String, String?, String?)] = [
            ("A school of fish swam past us.", "school", nil),
            ("Schools of fish swim near the beach.", "Schools", "beach"),
            ("The schools have a garden.", "schools", "garden"),
            ("The school has a garden.", "school", "garden"),
            ("Apple announced a new phone.", "Apple", nil),
            ("apple announced a new phone.", "apple", nil),
            ("Jobs changed personal computing.", "Jobs", nil),
            ("jobs changed personal computing.", "jobs", nil),
            ("I cut an apple for lunch.", "apple", "lunch"),
            ("There are jobs near my house.", "jobs", "house"),
            ("I found a job near my house.", nil, "job"),
            ("Send coffee_today.txt and enjoy music.", "coffee_today.txt", "music"),
            ("The coffee and bread are for lunch.", nil, "lunch")
        ]
        var observations = [[String: Any]]()
        for target in ["ja", "sw"] {
            let root = try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
            let manifest = try Data(contentsOf: root.appendingPathComponent(target == "ja" ? "starter-catalog.json" : "starter-sw-catalog.json"))
            let meta = try XCTUnwrap(JSONSerialization.jsonObject(with: manifest) as? [String: Any])
            let file = try XCTUnwrap(meta["file"] as? String)
            let pack = try Data(contentsOf: root.appendingPathComponent(file))
            let (count, hash) = try XCTUnwrap(expected[target])
            XCTAssertEqual(JapaneseStarterLookup.digest(pack), hash)
            XCTAssertEqual(meta["entries"] as? Int, count)
            let provider = try XCTUnwrap(target == "ja" ? JapaneseStarterLookup.bundledIfPromoted() : SwahiliStarterLookup.bundledIfPromoted())
            XCTAssertTrue(provider.identity.contains(hash))
            XCTAssertTrue(provider.identity.hasSuffix(":packing-1"))

            let engine = ConversationImmersion(modelStatus: { _ in .unsupported })
            await engine.configure(pair: .init(source: "en", target: target), density: 0.75)
            defer { engine.close() }
            for (index, control) in controls.enumerated() {
                let (source, untouched, required) = control
                let id = "expanded-\(target)-\(index)"
                engine.selectInputLanguage("en", for: id)
                let value = await engine.result(for: source, inputLanguage: "en", messageID: id)
                let spans = value?.spans ?? []
                XCTAssertEqual(engine.lastOutcome?.localTranslationCalls, 0)
                if let untouched {
                    let range = (source as NSString).range(of: untouched)
                    XCTAssertNotEqual(range.location, NSNotFound)
                    XCTAssertFalse(spans.contains { NSIntersectionRange($0.range, range).length > 0 }, "Changed protected/withheld form: \(target): \(source)")
                }
                if let required {
                    let range = (source as NSString).range(of: required, options: .backwards)
                    XCTAssertTrue(spans.contains { $0.range == range }, "Lost ordinary vocabulary: \(target): \(source)")
                }
                var mixed = source
                for span in spans.reversed() {
                    mixed = (mixed as NSString).replacingCharacters(in: span.range, with: span.romanization ?? span.translated)
                }
                if index == controls.count - 1 {
                    XCTAssertEqual(mixed, target == "ja" ? "The kōhī and pan are for chuushoku." : "The kahawa na mkate are for chakula cha mchana.")
                }
                let rows: [[String: Any]] = spans.map { ["source": $0.original, "target": $0.translated,
                    "reading": $0.romanization as Any? ?? NSNull(), "scope": [$0.range.location, NSMaxRange($0.range)]] }
                observations.append(["pair": "en-" + target, "source": source, "mixed": mixed, "spans": rows,
                    "bundle_sha256": hash, "origin": engine.lastOutcome?.origin?.rawValue as Any? ?? NSNull(), "translation_calls": 0])
            }
        }
        let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: observations, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
        attachment.name = "expanded-bundle-default-route.json"; attachment.lifetime = .keepAlways; add(attachment)
    }
}
