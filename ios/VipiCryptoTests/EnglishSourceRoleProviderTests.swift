import Foundation
import NaturalLanguage
import CryptoKit
import Darwin
import XCTest
@testable import Vipi

/// Runtime/geometry diagnostics; no POS prediction is treated as semantic gold.
final class EnglishSourceRoleProviderTests: XCTestCase {
    static func words(_ text: String) -> [NSRange] { LocalImmersion.words(text, language: "en") }
    static func span(_ r: NSRange) -> [Int] { [r.location, NSMaxRange(r)] }
    static func payload(_ s: EnglishSourceRoleProvider.Snapshot) -> [String: Any] {
        ["status": s.status.rawValue, "word_ranges": s.wordRanges.map(span),
         "supplied_protection": s.suppliedProtection.map(span), "detected_names": s.detectedNames.map(span),
         "protection_union": s.protectedRanges.map(span), "available_schemes": s.availableSchemes,
         "observations": s.observations.map { v -> [String: Any] in
            ["utf16": span(v.range), "source": v.original, "role": v.role.rawValue,
             "raw_lexical_tag": v.rawLexicalTag as Any? ?? NSNull(), "unknown_reason": v.unknownReason as Any? ?? NSNull(),
             "overlaps_protection": v.overlapsProtection, "noun_eligible": v.nounEligible]
         }]
    }
    static func rss() -> UInt64? {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let status = withUnsafeMutablePointer(to: &info) { ptr in
            ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return status == KERN_SUCCESS ? UInt64(info.resident_size) : nil
    }
    static func controls(_ provider: EnglishSourceRoleProvider) -> [[String: Any]] {
        var result: [[String: Any]] = []
        func check(_ name: String, _ pass: Bool) { result.append(["case": name, "passed": pass]) }
        check("empty", provider.inspect(original: "", language: "en", wordRanges: [], protectedRanges: []).status == .empty)
        check("unsupported", provider.inspect(original: "cat", language: "sw", wordRanges: [NSRange(location: 0,length: 3)], protectedRanges: []).status == .unsupportedLanguage)
        check("mid_surrogate", provider.inspect(original: "😀 cat", language: "en", wordRanges: [NSRange(location: 1,length: 1)], protectedRanges: []).status == .invalidInput)
        check("overlapping_words", provider.inspect(original: "cat coat", language: "en", wordRanges: [NSRange(location: 0,length: 3),NSRange(location: 2,length: 3)], protectedRanges: []).status == .invalidInput)
        let astral = "😀 cat, dog."; let ar = words(astral)
        let a = provider.inspect(original: astral, language: "en", wordRanges: ar, protectedRanges: [])
        check("astral_punctuation_geometry", ar == [NSRange(location: 3,length: 3),NSRange(location: 8,length: 3)] && (a.status == .lexicalSchemeUnavailable || a.observations.map(\.range) == ar))
        let protected = NSRange(location: 4,length: 3)
        let p = provider.inspect(original: "the dog", language: "en", wordRanges: words("the dog"), protectedRanges: [protected])
        check("supplied_mask_survives", p.protectedRanges.contains(protected) && p.observations.filter { NSIntersectionRange($0.range,protected).length > 0 }.allSatisfy { $0.overlapsProtection && !$0.nounEligible })
        check("oversized", provider.inspect(original: String(repeating: "x",count: 16_385), language: "en", wordRanges: [], protectedRanges: []).status == .invalidInput)
        let composed = "café"; let cr = words(composed)
        let s = provider.inspect(original: composed, language: "en", wordRanges: cr, protectedRanges: [])
        check("exact_snapshot_identity", s.matches(original: composed,language: "en",wordRanges: cr,protectedRanges: []) && !s.matches(original: "cafe\u{301}",language: "en",wordRanges: cr,protectedRanges: []) && !s.matches(original: composed,language: "en",wordRanges: cr,protectedRanges: [NSRange(location:0,length:4)]))
        return result
    }

    func testFrozenSourceGeometryProtectionAndSnapshotIdentity() throws {
        let data = try XCTUnwrap(Data(base64Encoded: EnglishSourceRoleFixture.base64))
        XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), EnglishSourceRoleFixture.sha256)
        let input = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let rows = try XCTUnwrap(input["cases"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 52)
        let provider = EnglishSourceRoleProvider()
        var results: [[String: Any]] = []
        var first: [String: Data] = [:]
        for pass in 1...3 {
            for row in rows {
                let text = try XCTUnwrap(row["source"] as? String)
                let id = try XCTUnwrap(row["case_id"] as? String)
                func ranges(_ key: String) throws -> [NSRange] {
                    try XCTUnwrap(row[key] as? [[Int]]).map { values in
                        XCTAssertEqual(values.count, 2)
                        return NSRange(location: values[0], length: values[1]-values[0])
                    }
                }
                let retained = try ranges("native_words_utf16")
                let masks = try ranges("protected_ranges_utf16")
                let actual = Self.words(text)
                let before = Self.rss()
                let start = DispatchTime.now().uptimeNanoseconds
                let snapshot = provider.inspect(original: text, language: "en", wordRanges: retained, protectedRanges: masks)
                let elapsed = DispatchTime.now().uptimeNanoseconds-start
                XCTAssertTrue(snapshot.matches(original: text, language: "en", wordRanges: retained, protectedRanges: masks))
                XCTAssertFalse(snapshot.matches(original: text+" ", language: "en", wordRanges: retained, protectedRanges: masks))
                XCTAssertFalse(snapshot.matches(original: text, language: "sw", wordRanges: retained, protectedRanges: masks))
                if actual != retained {
                    XCTAssertEqual(snapshot.status, .nativeGeometryMismatch)
                    XCTAssertTrue(snapshot.observations.isEmpty)
                }
                for mask in masks {
                    XCTAssertTrue(snapshot.protectedRanges.contains { NSIntersectionRange($0, mask) == mask })
                }
                for observation in snapshot.observations {
                    XCTAssertEqual((text as NSString).substring(with: observation.range), observation.original)
                    if observation.role == .unknown {
                        XCTAssertFalse(observation.nounEligible)
                        XCTAssertNotNil(observation.unknownReason)
                    }
                    if observation.overlapsProtection { XCTAssertFalse(observation.nounEligible) }
                    if observation.nounEligible {
                        XCTAssertEqual(observation.role, .noun)
                        XCTAssertEqual(observation.rawLexicalTag, NLTag.noun.rawValue)
                        XCTAssertEqual(snapshot.status, .ready)
                    }
                }
                let payload = Self.payload(snapshot)
                let canonical = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
                if pass == 1 { first[id] = canonical }
                XCTAssertEqual(first[id], canonical, "Repeat annotations changed for \(id)")
                var usage = rusage(); getrusage(RUSAGE_SELF, &usage)
                results.append(["case_id": id, "source_id": row["source_id"]!, "source": text,
                    "source_sha256": SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined(),
                    "pass": pass, "native_geometry_equal": actual == retained,
                    "actual_native_words": actual.map(Self.span), "annotation": payload,
                    "same_as_first_pass": first[id] == canonical, "elapsed_ns": elapsed,
                    "rss_before_bytes": before as Any? ?? NSNull(), "rss_after_bytes": Self.rss() as Any? ?? NSNull(),
                    "process_peak_rss_bytes": usage.ru_maxrss])
            }
        }
        let controls = Self.controls(provider)
        for control in controls { XCTAssertEqual(control["passed"] as? Bool, true, control["case"] as? String ?? "control") }
        // Omitted native words must abstain even if all supplied spans are valid.
        XCTAssertEqual(provider.inspect(original: "the dog", language: "en", wordRanges: [], protectedRanges: []).status, .nativeGeometryMismatch)
        let output: [String: Any] = ["schema": "vipi.ios-source-role-provider.r01", "platform": "iOS Simulator",
            "os": ProcessInfo.processInfo.operatingSystemVersionString, "input_sha256": EnglishSourceRoleFixture.sha256,
            "cases": results, "controls": controls, "omitted_words_rejected": true,
            "limits": "Actual app provider via @testable import; uncalled customer path. Reused diagnostics, no semantic gold, translation, catalog selection, model download or physical-device evidence. Timing excludes caller tokenization and serialization. RSS includes the app/test host. First pass is process-initial, not OS-cold."]
        let outputData = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        XCTAssertLessThanOrEqual(outputData.count, 4*1024*1024)
        let attachment = XCTAttachment(data: outputData, uniformTypeIdentifier: "public.json")
        attachment.name = "english-source-role-simulator-r01.json"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
