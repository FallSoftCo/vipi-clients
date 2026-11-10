import XCTest
import Foundation
import VipiCore
@testable import Vipi

/// New candidate qualification. Earlier comparisons and review labels stay frozen.
@MainActor final class SourceFrameProductionTests: XCTestCase {
    private func encoded(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }

    func testMalformedFramesAreRejected() throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_SOURCE_FRAME_PRODUCTION_QA"] else {
            throw XCTSkip("Explicit private production-candidate qualification")
        }
        let root = URL(fileURLWithPath: path)
        let data = try Data(contentsOf: root.appendingPathComponent("source-frames-en-ja-001.json"))
        let manifestData = try Data(contentsOf: root.appendingPathComponent("source-frames-en-ja-catalog.json"))
        let manifest = try XCTUnwrap(JSONSerialization.jsonObject(with: manifestData) as? [String: Any])
        _ = try SourceFrameLookup(bytes: data, manifestBytes: manifestData, target: "ja", baselineIdentity: "control")
        var wrongHash = manifest
        wrongHash["sha256"] = String(repeating: "0", count: 64)
        XCTAssertThrowsError(try SourceFrameLookup(bytes: data, manifestBytes: encoded(wrongHash), target: "ja", baselineIdentity: "control"))
        XCTAssertThrowsError(try SourceFrameLookup(bytes: Data(repeating: 32, count: 1_048_577), manifestBytes: manifestData,
                                                   target: "ja", baselineIdentity: "control"))
        XCTAssertThrowsError(try SourceFrameLookup(bytes: data, manifestBytes: Data(repeating: 32, count: 8_193),
                                                   target: "ja", baselineIdentity: "control"))
        XCTAssertThrowsError(try SourceFrameLookup(bytes: data, manifestBytes: manifestData, target: "ar", baselineIdentity: "control"))
        func rejects(_ mutate: (inout [String: Any]) -> Void) throws {
            var pack = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            var patterns = try XCTUnwrap(pack["patterns"] as? [[String: Any]])
            mutate(&patterns[0])
            pack["patterns"] = patterns
            let altered = try encoded(pack)
            var consistentManifest = manifest
            consistentManifest["sha256"] = JapaneseStarterLookup.digest(altered)
            consistentManifest["bytes"] = altered.count
            XCTAssertThrowsError(try SourceFrameLookup(bytes: altered, manifestBytes: encoded(consistentManifest),
                                                       target: "ja", baselineIdentity: "control"))
        }
        try rejects { $0["source_only_permission"] = false }
        try rejects { $0["reading"] = "" }
        try rejects { $0["pair"] = "en-sw" }
        try rejects { $0["variants"] = [["context": "bank account", "focus_utf16": [0, 4]]] }
        try rejects { $0["variants"] = [["context": "bank account", "focus_utf16": [-1, 12]]] }
    }

    func testConcurrentMessagesKeepTheirOwnCandidates() async throws {
        guard ProcessInfo.processInfo.environment["VIPI_SOURCE_FRAME_PRODUCTION_QA"] != nil else {
            throw XCTSkip("Explicit private production-candidate qualification")
        }
        XCTAssertTrue(SourceFrameLookup.promotionEnabled)
        let lookup = try XCTUnwrap(BundledStarterLookup.provider())
        let contexts = ["We need a phone charger and your phone number.",
                        "They need a train ticket and a door key."].map {
            SourceUnitLookup.Context(original: $0, pair: .init(source: "en", target: "ja"),
                                     density: 0.75, knownConceptIDs: [])
        }
        var expected: [SourceLookupEvidence] = []
        for context in contexts { expected.append(try await lookup.resolve(context)) }
        let tasks = contexts.map { context in Task { @MainActor in try await lookup.resolve(context) } }
        for (index, task) in tasks.enumerated() {
            let actual = try await task.value
            XCTAssertEqual(actual.original, contexts[index].original)
            XCTAssertEqual(actual.partial, expected[index].partial)
            XCTAssertFalse(actual.partial?.spans.isEmpty ?? true)
        }
    }

    func testBundledProductionRoute() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_SOURCE_FRAME_PRODUCTION_QA"] else {
            throw XCTSkip("Explicit private production-candidate qualification")
        }
        XCTAssertTrue(SourceFrameLookup.promotionEnabled)
        let root = URL(fileURLWithPath: path)
        let manifestData = try Data(contentsOf: root.appendingPathComponent("manifest.json"))
        let manifest = try XCTUnwrap(JSONSerialization.jsonObject(with: manifestData) as? [String: String])
        for (name, digest) in manifest {
            XCTAssertEqual(JapaneseStarterLookup.digest(try Data(contentsOf: root.appendingPathComponent(name))), digest)
        }
        let previous = try String(contentsOf: root.appendingPathComponent("prior-apple-routing.jsonl"), encoding: .utf8)
            .split(separator: "\n").map { try XCTUnwrap(JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]) }
        XCTAssertEqual(previous.count, 656)
        let output = root.appendingPathComponent("production-output.jsonl")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        FileManager.default.createFile(atPath: output.path, contents: nil)
        let handle = try FileHandle(forWritingTo: output)
        defer { try? handle.close() }
        let start = ProcessInfo.processInfo.systemUptime
        var rows = 0, correctedSpans = 0
        for prior in previous {
            let source = try XCTUnwrap(prior["source"] as? String)
            let pair = try XCTUnwrap(prior["pair"] as? String)
            let target = String(pair.dropFirst(3))
            let density = try XCTUnwrap(prior["density"] as? Double)
            let known = Set(try XCTUnwrap(prior["known_ids"] as? [String]))
            let route = try XCTUnwrap(prior["route"] as? [String: Any])
            let expectedRoute = try XCTUnwrap(route["candidate"] as? [String: Any])
            var expected = try XCTUnwrap(expectedRoute["spans"] as? [[String: Any]])
            if target == "sw", prior["routing_branch"] as? String == "reference_miss_frame_evidence" {
                let direct = try XCTUnwrap(prior["candidate"] as? [String: Any])
                let references = try XCTUnwrap(direct["references"] as? [[String: Any]])
                let corrections = ["frame-4dc1128ff5c7283136d7125c": "sherehe",
                                   "frame-43431e9665d734366a927b81": "nambari ya simu"]
                for index in expected.indices {
                    for reference in references where reference["scope"] as? [Int] == expected[index]["source_utf16"] as? [Int] {
                        for (identifier, face) in corrections where (reference["reference"] as? String)?.hasSuffix(":" + identifier) == true {
                            expected[index]["target"] = face
                            correctedSpans += 1
                        }
                    }
                }
            }
            // No provider/target/span injection: exercise the normal bundled factory.
            let owner = ConversationImmersion(modelStatus: { _ in .unsupported })
            await owner.configure(pair: .init(source: "en", target: target), density: density, knownConceptIDs: known)
            let messageID = "production-candidate-\(rows)"
            owner.selectInputLanguage("en", for: messageID)
            let presentation = await owner.result(for: source, inputLanguage: "en", messageID: messageID)
            let actual: [[String: Any]] = (presentation?.spans ?? []).map {
                ["source": $0.original, "target": $0.translated,
                 "reading": $0.romanization as Any? ?? NSNull(),
                 "source_utf16": [$0.range.location, NSMaxRange($0.range)]]
            }
            XCTAssertEqual(try encoded(actual), try encoded(expected), "\(pair) \(source)")
            XCTAssertEqual(owner.lastOutcome?.localTranslationCalls, 0)
            XCTAssertEqual(owner.lastOutcome?.origin?.rawValue, expectedRoute["origin"] as? String)
            try handle.write(contentsOf: encoded([
                "id": prior["id"]!, "pair": pair, "source": source, "state": prior["state"]!,
                "density": density, "spans": actual, "translation_calls": owner.lastOutcome?.localTranslationCalls ?? -1,
                "origin": owner.lastOutcome?.origin?.rawValue as Any? ?? NSNull()]) + Data([10]))
            owner.close()
            rows += 1
            guard try handle.offset() < 8 * 1024 * 1024, ProcessInfo.processInfo.systemUptime - start < 300 else {
                XCTFail("Bounded candidate capture exceeded"); return
            }
        }
        XCTAssertGreaterThan(correctedSpans, 0)
        try handle.synchronize()
        try encoded(["rows": rows, "corrected_display_spans": correctedSpans,
                     "seconds": ProcessInfo.processInfo.systemUptime - start,
                     "default_factory": true, "supplied_provider_or_spans": false])
            .write(to: root.appendingPathComponent("production-status.json"))
    }
}
