import Foundation
import XCTest
@testable import Vipi

/// Explicit QA invocation only. Real hash-bound pack/dictionaries, no fabricated bindings.
final class FrozenContextPackTests: XCTestCase {
    func testFrozenRuleWinnerParityWithoutAdmission() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["VIPI_FROZEN_CONTEXT_QA_DIRECTORY"] != nil,
                          "Explicit qualification requires the hash-bound private dictionary inputs")
        let root = URL(fileURLWithPath: try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_FROZEN_CONTEXT_QA_DIRECTORY"]))
        let config = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("native-bindings.json"))) as? [String: Any])
        let expectedMeta = try XCTUnwrap(config["expected_metadata"] as? [String: String])
        let en = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
        let pack = try FrozenContextPack(url: root.appendingPathComponent("context.sqlite"),
            expectedSHA256: "cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",
            expectedMetadata: expectedMeta, dictionaryURLs: ["en": en, "es": root.appendingPathComponent("d-es.sqlite")])
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("context-sidecars-"+UUID().uuidString)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let alias = scratch.appendingPathComponent("context.sqlite")
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: root.appendingPathComponent("context.sqlite"))
        for suffix in ["-wal", "-shm", "-journal"] {
            let sidecar = URL(fileURLWithPath: alias.path+suffix)
            try Data().write(to: sidecar)
            XCTAssertThrowsError(try FrozenContextPack(url: alias,
                expectedSHA256: "cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",
                expectedMetadata: expectedMeta, dictionaryURLs: ["en": en, "es": root.appendingPathComponent("d-es.sqlite")])) { error in
                guard case FrozenContextPack.Failure.identity = error else { return XCTFail("Wrong sidecar rejection") }
            }
            try FileManager.default.removeItem(at: sidecar)
        }
        XCTAssertEqual(pack.rules.count, 1157)
        XCTAssertEqual(pack.heads.count, 453)
        XCTAssertEqual(pack.rules.filter { $0.headIDs.isEmpty }.count, 23)
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("rule-fixtures.json"))) as? [String: Any])
        let rows = try XCTUnwrap(fixture["rows"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 1157)
        var observations: [[String: Any]] = []
        for row in rows {
            let source = try XCTUnwrap(row["source"] as? String), id = try XCTUnwrap(row["rule_id"] as? String)
            guard row["roundtrip"] as? Bool == true else {
                observations.append(["rule_id":id,"status":"fixture_retokenization_changed"]); continue
            }
            let ranges = try XCTUnwrap(row["ranges"] as? [[Int]]).map { NSRange(location:$0[0],length:$0[1]) }
            let focusArray = try XCTUnwrap(row["focus"] as? [Int])
            let focus = NSRange(location:focusArray[0],length:focusArray[1])
            let native = LocalImmersion.words(source, language:"en")
            guard native.contains(focus) else {
                observations.append(["rule_id":id,"status":"native_geometry_difference",
                    "actual_native_ranges":native.map { [$0.location,$0.length] }]); continue
            }
            let tick = DispatchTime.now().uptimeNanoseconds
            let assessment = try pack.assess(original:source,nativeWordRanges:native,focus:focus,
                sourceKeys:try XCTUnwrap(row["source_keys"] as? [String]))
            let winner = assessment.winner
            let elapsed = DispatchTime.now().uptimeNanoseconds-tick
            if native != ranges {
                observations.append(["rule_id":id,"status":"native_geometry_difference","winner":winner?.rule.id as Any? ?? NSNull(),"geometry_rejected_rule_ids":assessment.rawMatches.filter { !$0.contextGeometryCompatible }.map { $0.rule.id }]);continue
            }
            if let expected = row["winner"] as? [String:Any] {
                let winner = try XCTUnwrap(winner)
                XCTAssertEqual(winner.rule.id,expected["id"] as? String)
                XCTAssertEqual(winner.rule.headIDs,expected["head_ids"] as? [String])
                XCTAssertEqual([winner.contextRange.location,winner.contextRange.length],expected["context_range"] as? [Int])
                // No eligible-head/target argument exists: empty winner cannot trigger a shorter retry.
                observations.append(["rule_id":id,"status":"matched","winner":winner.rule.id,
                    "heads":winner.rule.headIDs,"context_geometry_compatible":winner.contextGeometryCompatible,"whole_native_geometry_equal":native == ranges,"elapsed_ns":elapsed])
            } else { XCTAssertNil(winner); observations.append(["rule_id":id,"status":"no_match","elapsed_ns":elapsed]) }
        }
        // Actual native geometry on retained complete messages; not synthetic rule spans.
        let sourceFixture = try JSONSerialization.jsonObject(with: Data(base64Encoded: EnglishSourceRoleFixture.base64)!) as! [String: Any]
        var fullSources: [[String: Any]] = []
        var keysBySpelling: [Data: [String]] = [:]
        for key in Dictionary(grouping:pack.rules.map(\.sourceKey),by:{Data($0.utf8)}).values.map({$0[0]}) {
            let parts = try JSONSerialization.jsonObject(with: Data(key.utf8)) as! [Any]
            keysBySpelling[Data((parts[0] as! String).utf8), default: []].append(key)
        }
        let fullTokenizer = try FrozenContextTokenizer()
        for row in sourceFixture["cases"] as! [[String: Any]] {
            let source = row["source"] as! String
            let current = LocalImmersion.words(source, language:"en")
            let retained = (row["native_words_utf16"] as! [[Int]]).map { NSRange(location:$0[0],length:$0[1]-$0[0]) }
            var focuses: [[String: Any]] = []
            for focus in current {
                let piece = (source as NSString).substring(with: focus)
                let key = try fullTokenizer.normalize(piece)
                let keys = keysBySpelling[Data(key.utf8)] ?? []
                if keys.isEmpty { continue }
                let a = try pack.assess(original:source,nativeWordRanges:current,focus:focus,sourceKeys:keys)
                let prior = retained.contains(focus) ? try pack.assess(original:source,nativeWordRanges:retained,focus:focus,sourceKeys:keys) : nil
                focuses.append(["focus":[focus.location,focus.length],"source":piece,
                    "current_winner":a.winner?.rule.id as Any? ?? NSNull(),
                    "retained_geometry_winner":prior?.winner?.rule.id as Any? ?? NSNull(),
                    "retained_contains_focus":retained.contains(focus),
                    "current_geometry_rejections":a.rawMatches.filter { !$0.contextGeometryCompatible }.map { $0.rule.id }])
            }
            fullSources.append(["case_id":row["case_id"]!,"source_id":row["source_id"]!,"source":source,
                "current_native_ranges":current.map { [$0.location,$0.length] },"retained_geometry_equal":current == retained,
                "focuses":focuses,"scope":"All source-spelling keys diagnostic, not eligible-head candidate set; no catalog selection, role inference, source-mask approval or output admission"])
        }
        let attachment = XCTAttachment(data:try JSONSerialization.data(withJSONObject:["schema":"vipi.context-pack-match-parity.r01",
            "pack_sha256":pack.contentSHA256,"observations":observations,"full_sources":fullSources,
            "permission":"disabled_research_only; no SourceLookupEvidence outputs or mask changes"],options:[.sortedKeys]),uniformTypeIdentifier:"public.json")
        attachment.name="frozen-context-pack-match-parity-r01";attachment.lifetime = .keepAlways;add(attachment)
    }
}
