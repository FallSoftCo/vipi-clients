import XCTest
import Foundation
import CryptoKit
import VipiCore
@testable import Vipi

@MainActor final class JapaneseStarterPromotionTests: XCTestCase {
    private func input(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_JAPANESE_STARTER_QA"])).appendingPathComponent(name))
    }
    private func loader() throws -> JapaneseStarterLookup {
        try JapaneseStarterLookup(data:input("starter-en-ja-002.json"),manifest:input("starter-catalog.json"))
    }
    func testMechanismsAndCapture() async throws {
        guard ProcessInfo.processInfo.environment["VIPI_JAPANESE_STARTER_QA"] != nil else {
            throw XCTSkip("Private starter capture is opt-in")
        }
        XCTAssertTrue(JapaneseStarterLookup.promotionEnabled)
        let owner = try loader()
        XCTAssertEqual(try XCTUnwrap(JapaneseStarterLookup.bundledIfPromoted()).identity,owner.identity)
        XCTAssertFalse(owner.pack.entries.contains { $0.source == "winter" })
        let bundledRoot = try XCTUnwrap(Bundle.main.resourceURL).appendingPathComponent("immersion")
        XCTAssertEqual(try Data(contentsOf:bundledRoot.appendingPathComponent("starter-en-ja-002.json")),try input("starter-en-ja-002.json"))
        XCTAssertEqual(try Data(contentsOf:bundledRoot.appendingPathComponent("starter-catalog.json")),try input("starter-catalog.json"))
        let raw = try input("japanese-starter-inputs-r01.json")
        XCTAssertEqual(JapaneseStarterLookup.digest(raw),"a4fe2868d2c341adb3360f5f80f535537ae1791ddbf0b7901fbbbc8ba63f03eb")
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with:raw) as? [String:Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String:Any]])
        let knownStates = try XCTUnwrap(fixture["known_states"] as? [[String]])
        let pair = TranslationPair(source:"en",target:"ja")
        func context(_ s:String,_ known:Set<String> = []) -> SourceUnitLookup.Context {
            .init(original:s,pair:pair,density:0.25,knownConceptIDs:known)
        }
        // Actual mask filtering, not a hash-only check.
        let allKnown = Set(owner.pack.entries.map(\.concept_id))
        let known = try owner.resolve(context("music",allKnown))
        XCTAssertNil(known.partial); XCTAssertFalse(known.recognitions.isEmpty)
        XCTAssertFalse(try XCTUnwrap(known.validated(text:"music",sourceLanguage:"en",targetLanguage:"ja",identity:owner.identity)).permits(range:NSRange(location:0,length:5)))
        let masked = try owner.resolve(context("music"),sourceMasks:[NSRange(location:0,length:5)])
        XCTAssertNil(masked.partial)
        XCTAssertFalse(try XCTUnwrap(masked.validated(text:"music",sourceLanguage:"en",targetLanguage:"ja",identity:owner.identity)).permits(range:NSRange(location:0,length:5),outputID:"word-en-ja-music@0:5"))
        XCTAssertNil(try owner.resolve(context("`music`")).partial)
        XCTAssertNil(try owner.resolve(context("I'm")).partial)
        XCTAssertTrue(JapaneseStarterLookup.whitespaceGap(" "))
        XCTAssertTrue(JapaneseStarterLookup.whitespaceGap("\n\t")) // Line wrapping is whitespace, not a sentence boundary.
        XCTAssertFalse(JapaneseStarterLookup.whitespaceGap(". "))
        XCTAssertFalse(JapaneseStarterLookup.whitespaceGap(",\n"))
        XCTAssertFalse(JapaneseStarterLookup.whitespaceGap(""))
        _ = try owner.resolve(context("What. kind of music do you like?"))
        XCTAssertTrue(owner.trace.contains { ($0["source"] as? String) == "What. kind" && ($0["reason"] as? String) == "noncontiguous_source_unit" })
        _ = try owner.resolve(context("What\nkind of music do you like?"))
        XCTAssertFalse(owner.trace.contains { ($0["source"] as? String) == "What\nkind" && ($0["reason"] as? String) == "noncontiguous_source_unit" })
        var corrupt = try input("starter-en-ja-002.json"); corrupt[0] ^= 1
        XCTAssertThrowsError(try JapaneseStarterLookup(data:corrupt,manifest:input("starter-catalog.json")))
        let smoke = ConversationImmersion(modelStatus:{ _ in .unsupported })
        await smoke.configure(pair:pair,density:0.25,knownConceptIDs:[])
        for (label,text) in [("starter","music"),("reference","hello"),("literal","`music`")] {
            smoke.selectInputLanguage("en",for:label)
            _ = await smoke.result(for:text,inputLanguage:"en",messageID:label)
            let outcome = try XCTUnwrap(smoke.lastOutcome)
            if label == "starter" { XCTAssertEqual(outcome.origin,.sourceReferencePartial);XCTAssertTrue(outcome.result?.spans.contains { $0.translated == "音楽" } == true) }
            if label == "reference" { XCTAssertEqual(outcome.origin,.lookupReference);XCTAssertNotNil(outcome.result) }
            if label == "literal" { XCTAssertTrue(outcome.result?.spans.isEmpty ?? true) }
            XCTAssertEqual(outcome.localTranslationCalls,0)
            let validSmoke = label == "starter" ? (outcome.origin == .sourceReferencePartial && outcome.result?.spans.contains { $0.translated == "音楽" } == true) : label == "reference" ? (outcome.origin == .lookupReference && outcome.result != nil) : (outcome.result?.spans.isEmpty ?? true)
            guard validSmoke && outcome.localTranslationCalls == 0 else { throw JapaneseStarterLookup.Invalid.input }
        }
        smoke.close()
        var results:[[String:Any]] = []
        var totalReadiness = 0
        let engine = ConversationImmersion(modelStatus:{ _ in totalReadiness += 1; return .unsupported })
        defer { engine.close() }
        for (stateIndex, words) in knownStates.enumerated() {
            await engine.configure(pair:pair,density:0.25,knownConceptIDs:Set(words))
            for c in cases {
                let id = try XCTUnwrap(c["id"] as? String), text = try XCTUnwrap(c["text"] as? String)
                engine.selectInputLanguage("en", for:id)
                owner.trace = []
                let began = ProcessInfo.processInfo.systemUptime
                _ = await engine.result(for:text,inputLanguage:"en",messageID:id)
                let elapsed = (ProcessInfo.processInfo.systemUptime-began)*1000
                let outcome = try XCTUnwrap(engine.lastOutcome)
                XCTAssertEqual(outcome.localTranslationCalls,0)
                XCTAssertFalse(outcome.cacheHit)
                let spans = outcome.result?.spans ?? []
                for span in spans {
                    XCTAssertEqual((text as NSString).substring(with:span.range),span.original)
                }
                _ = try owner.resolve(context(text,Set(words)))
                let trace = owner.trace
                let direct = try owner.resolve(context(text,Set(words)))
                XCTAssertTrue(direct.partial?.spans.allSatisfy { !($0.romanization?.isEmpty ?? true) } ?? true)
                _ = await engine.result(for:text,inputLanguage:"en",messageID:id)
                let repeatOutcome = try XCTUnwrap(engine.lastOutcome)
                if outcome.result != nil { XCTAssertTrue(repeatOutcome.cacheHit) }; XCTAssertEqual(repeatOutcome.localTranslationCalls,0)
                var row:[String:Any] = ["id":id,"stratum":c["stratum"]!,"original":text,"known_state":stateIndex,"known_ids":words,"density":0.25,
                    "elapsed_ms":elapsed,"status":outcome.status.rawValue,"origin":outcome.origin?.rawValue as Any? ?? NSNull(),
                    "translation_calls":outcome.localTranslationCalls,"readiness_calls":outcome.modelReadinessCalls,"alignment_calls":outcome.alignmentCalls,
                    "mixed":outcome.result?.speech(source:"en",target:"ja").map(\.text).joined() ?? text,
                    "full_reference":outcome.result?.translation as Any? ?? NSNull(),"cache_hit_on_repeat":repeatOutcome.cacheHit,
                    "native_words":LocalImmersion.words(text,language:"en").map{[$0.location,NSMaxRange($0)]},"trace":trace,
                    "recognitions":direct.recognitions.map{["rule":$0.ruleID,"mask":$0.mask.map{[$0.location,NSMaxRange($0)]} as Any? ?? NSNull(),"approved":$0.approvedOutputs.map(\.outputID)] as [String:Any]}]
                row["spans"] = spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]] as [String:Any]}
                row["starter_spans"] = direct.partial?.spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]] as [String:Any]} ?? []
                results.append(row)
            }
        }
        let output:[String:Any] = ["schema":1,"complete":true,"platform":"apple","input_sha256":JapaneseStarterLookup.digest(raw),"pack_sha256":owner.sha,"activation":true,"default_provider_path":true,"default_provider_identity":owner.identity,"model_policy":"explicit unavailable injection; no Translation calls","total_readiness_calls":totalReadiness,"cases":results]
        let data = try JSONSerialization.data(withJSONObject:output,options:[.sortedKeys])
        XCTAssertLessThan(data.count,16*1024*1024)
        let attachment = XCTAttachment(data:data,uniformTypeIdentifier:"public.json"); attachment.name="japanese-starter-output-r05.json";attachment.lifetime = .keepAlways;add(attachment)
    }
}
