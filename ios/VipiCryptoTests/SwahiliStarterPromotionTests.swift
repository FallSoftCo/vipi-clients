import XCTest
import Foundation
import CryptoKit
import VipiCore
@testable import Vipi

@MainActor final class SwahiliStarterPromotionTests: XCTestCase {
    private func input(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_SWAHILI_STARTER_QA"])).appendingPathComponent(name))
    }
    private func loader() throws -> SwahiliStarterLookup {
        try SwahiliStarterLookup(data:input("starter-en-sw-001.json"),manifest:input("starter-sw-catalog.json"))
    }
    func testMechanismsAndCapture() async throws {
        guard ProcessInfo.processInfo.environment["VIPI_SWAHILI_STARTER_QA"] != nil else {
            throw XCTSkip("Private starter capture is opt-in")
        }
        XCTAssertTrue(SwahiliStarterLookup.promotionEnabled)
        let owner = try loader()
        let japanese = try XCTUnwrap(JapaneseStarterLookup.bundledIfPromoted())
        XCTAssertEqual(try XCTUnwrap(SwahiliStarterLookup.bundledIfPromoted()).identity,owner.identity)
        let combined = try XCTUnwrap(BundledStarterLookup.compose(japanese:japanese,swahili:owner.provider()))
        XCTAssertEqual(try XCTUnwrap(BundledStarterLookup.provider()).identity,combined.identity)
        let wrong = try await combined.resolve(.init(original:"music",pair:.init(source:"fr",target:"sw"),density:0.25,knownConceptIDs:[]))
        XCTAssertNil(wrong.partial);XCTAssertTrue(wrong.recognitions.isEmpty)
        let invalid = SourceUnitLookup(identity:"invalid-fixture") { c in
            SourceLookupEvidence(original:"different",source:c.pair.source,target:c.pair.target,catalogIdentity:"invalid-fixture",partial:nil,recognitions:[])
        }
        do {
            _ = try await XCTUnwrap(BundledStarterLookup.compose(japanese:japanese,swahili:invalid)).resolve(.init(original:"music",pair:.init(source:"en",target:"sw"),density:0.25,knownConceptIDs:[]))
            XCTFail("invalid provider evidence admitted")
        } catch { }
        let jaFixture = try XCTUnwrap(JSONSerialization.jsonObject(with:input("japanese-starter-inputs-r01.json")) as? [String:Any])
        let jaReference = try XCTUnwrap(JSONSerialization.jsonObject(with:input("japanese-parity-reference.json")) as? [String:Any])
        let jaRows = try XCTUnwrap(jaReference["cases"] as? [[String:Any]])
        let jaCases = try XCTUnwrap(jaFixture["cases"] as? [[String:Any]])
        let jaStates = try XCTUnwrap(jaFixture["known_states"] as? [[String]])
        let jaEngine = ConversationImmersion(modelStatus:{ _ in .unsupported })
        var parityCount = 0
        for (state, ids) in jaStates.enumerated() {
            await jaEngine.configure(pair:.init(source:"en",target:"ja"),density:0.25,knownConceptIDs:Set(ids))
            for c in jaCases {
                let id = try XCTUnwrap(c["id"] as? String),text = try XCTUnwrap(c["text"] as? String)
                jaEngine.selectInputLanguage("en",for:id)
                _ = await jaEngine.result(for:text,inputLanguage:"en",messageID:id)
                let outcome = try XCTUnwrap(jaEngine.lastOutcome)
                let actual:[[String:Any]] = (outcome.result?.spans ?? []).map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]]}
                let expected = try XCTUnwrap(jaRows.first{($0["id"] as? String)==id && ($0["known_state"] as? Int)==state})
                XCTAssertEqual(try JSONSerialization.data(withJSONObject:actual,options:.sortedKeys),try JSONSerialization.data(withJSONObject:expected["spans"]!,options:.sortedKeys))
                XCTAssertEqual(outcome.localTranslationCalls,0);parityCount += 1
            }
        }
        jaEngine.close();XCTAssertEqual(parityCount,384)
        XCTAssertFalse(owner.pack.entries.contains { $0.source == "winter" })
        let bundledRoot = try XCTUnwrap(Bundle.main.resourceURL).appendingPathComponent("immersion")
        XCTAssertEqual(try Data(contentsOf:bundledRoot.appendingPathComponent("starter-en-sw-001.json")),try input("starter-en-sw-001.json"))
        XCTAssertEqual(try Data(contentsOf:bundledRoot.appendingPathComponent("starter-sw-catalog.json")),try input("starter-sw-catalog.json"))
        let raw = try input("swahili-starter-inputs-r01.json")
        XCTAssertEqual(SwahiliStarterLookup.digest(raw),"15c4470fbf74c5a0410361aaf4ecf2e36306dc2b6ac5f1b0e1eda0b1f432709f")
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with:raw) as? [String:Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String:Any]])
        let knownStates = try XCTUnwrap(fixture["known_states"] as? [[String]])
        let pair = TranslationPair(source:"en",target:"sw")
        func context(_ s:String,_ known:Set<String> = []) -> SourceUnitLookup.Context {
            .init(original:s,pair:pair,density:0.25,knownConceptIDs:known)
        }
        // Actual mask filtering, not a hash-only check.
        let allKnown = Set(owner.pack.entries.map(\.concept_id))
        let known = try owner.resolve(context("music",allKnown))
        XCTAssertNil(known.partial); XCTAssertFalse(known.recognitions.isEmpty)
        XCTAssertFalse(try XCTUnwrap(known.validated(text:"music",sourceLanguage:"en",targetLanguage:"sw",identity:owner.identity)).permits(range:NSRange(location:0,length:5)))
        let masked = try owner.resolve(context("music"),sourceMasks:[NSRange(location:0,length:5)])
        XCTAssertNil(masked.partial)
        XCTAssertFalse(try XCTUnwrap(masked.validated(text:"music",sourceLanguage:"en",targetLanguage:"sw",identity:owner.identity)).permits(range:NSRange(location:0,length:5),outputID:"word-en-ja-music@0:5"))
        XCTAssertNil(try owner.resolve(context("`music`")).partial)
        XCTAssertNil(try owner.resolve(context("I'm")).partial)
        XCTAssertTrue(SwahiliStarterLookup.whitespaceGap(" "))
        XCTAssertTrue(SwahiliStarterLookup.whitespaceGap("\n\t")) // Line wrapping is whitespace, not a sentence boundary.
        XCTAssertFalse(SwahiliStarterLookup.whitespaceGap(". "))
        XCTAssertFalse(SwahiliStarterLookup.whitespaceGap(",\n"))
        XCTAssertFalse(SwahiliStarterLookup.whitespaceGap(""))
        _ = try owner.resolve(context("What. kind of music do you like?"))
        XCTAssertTrue(owner.trace.contains { ($0["source"] as? String) == "What. kind" && ($0["reason"] as? String) == "noncontiguous_source_unit" })
        _ = try owner.resolve(context("What\nkind of music do you like?"))
        XCTAssertFalse(owner.trace.contains { ($0["source"] as? String) == "What\nkind" && ($0["reason"] as? String) == "noncontiguous_source_unit" })
        var corrupt = try input("starter-en-sw-001.json"); corrupt[0] ^= 1
        XCTAssertThrowsError(try SwahiliStarterLookup(data:corrupt,manifest:input("starter-sw-catalog.json")))
        let smoke = ConversationImmersion(modelStatus:{ _ in .unsupported })
        await smoke.configure(pair:pair,density:0.25,knownConceptIDs:[])
        for (label,text) in [("starter","music"),("reference","hello"),("literal","`music`")] {
            smoke.selectInputLanguage("en",for:label)
            _ = await smoke.result(for:text,inputLanguage:"en",messageID:label)
            let outcome = try XCTUnwrap(smoke.lastOutcome)
            if label == "starter" { XCTAssertEqual(outcome.origin,.sourceReferencePartial);XCTAssertTrue(outcome.result?.spans.contains { $0.translated == "muziki" } == true) }
            if label == "reference" { XCTAssertEqual(outcome.origin,.lookupReference);XCTAssertNotNil(outcome.result) }
            if label == "literal" { XCTAssertTrue(outcome.result?.spans.isEmpty ?? true) }
            XCTAssertEqual(outcome.localTranslationCalls,0)
            let validSmoke = label == "starter" ? (outcome.origin == .sourceReferencePartial && outcome.result?.spans.contains { $0.translated == "muziki" } == true) : label == "reference" ? (outcome.origin == .lookupReference && outcome.result != nil) : (outcome.result?.spans.isEmpty ?? true)
            guard validSmoke && outcome.localTranslationCalls == 0 else { throw SwahiliStarterLookup.Invalid.input }
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
                XCTAssertTrue(direct.partial?.spans.allSatisfy { $0.romanization == nil } ?? true)
                _ = await engine.result(for:text,inputLanguage:"en",messageID:id)
                let repeatOutcome = try XCTUnwrap(engine.lastOutcome)
                if outcome.result != nil { XCTAssertTrue(repeatOutcome.cacheHit) }; XCTAssertEqual(repeatOutcome.localTranslationCalls,0)
                var row:[String:Any] = ["id":id,"stratum":c["stratum"]!,"original":text,"known_state":stateIndex,"known_ids":words,"density":0.25,
                    "elapsed_ms":elapsed,"status":outcome.status.rawValue,"origin":outcome.origin?.rawValue as Any? ?? NSNull(),
                    "translation_calls":outcome.localTranslationCalls,"readiness_calls":outcome.modelReadinessCalls,"alignment_calls":outcome.alignmentCalls,
                    "mixed":outcome.result?.speech(source:"en",target:"sw").map(\.text).joined() ?? text,
                    "full_reference":outcome.result?.translation as Any? ?? NSNull(),"cache_hit_on_repeat":repeatOutcome.cacheHit,
                    "native_words":LocalImmersion.words(text,language:"en").map{[$0.location,NSMaxRange($0)]},"trace":trace,
                    "recognitions":direct.recognitions.map{["rule":$0.ruleID,"mask":$0.mask.map{[$0.location,NSMaxRange($0)]} as Any? ?? NSNull(),"approved":$0.approvedOutputs.map(\.outputID)] as [String:Any]}]
                row["spans"] = spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]] as [String:Any]}
                row["starter_spans"] = direct.partial?.spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]] as [String:Any]} ?? []
                results.append(row)
            }
        }
        let output:[String:Any] = ["schema":1,"complete":true,"platform":"apple","input_sha256":SwahiliStarterLookup.digest(raw),"pack_sha256":owner.sha,"activation":true,"default_provider_path":true,"candidate_dispatcher_identity":combined.identity,"japanese_parity_rows":parityCount,"model_policy":"explicit unavailable injection; no Translation calls","total_readiness_calls":totalReadiness,"cases":results]
        let data = try JSONSerialization.data(withJSONObject:output,options:[.sortedKeys])
        XCTAssertLessThan(data.count,16*1024*1024)
        let attachment = XCTAttachment(data:data,uniformTypeIdentifier:"public.json"); attachment.name="swahili-starter-output-r02.json";attachment.lifetime = .keepAlways;add(attachment)
    }
}
