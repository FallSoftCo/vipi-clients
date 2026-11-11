import Foundation
import XCTest
import SwiftUI
import VipiCore
@testable import Vipi

@MainActor final class AcceptedContentDefaultTests: XCTestCase {
    private func render(_ result: ImmersionPresentation?, original: String) -> [String: Any] {
        let base = result?.original ?? original
        let mixed = NSMutableString(string: base), reading = NSMutableString(string: base)
        for span in (result?.spans ?? []).reversed() {
            mixed.replaceCharacters(in: span.range, with: span.translated)
            reading.replaceCharacters(in: span.range, with: span.romanization ?? span.translated)
        }
        let refs: [SourceReferenceUnit]
        if case .partial(let partial) = result { refs = partial.references } else { refs = [] }
        return ["presentation_original": base, "original_preserved": base == original,
            "mixed_script": mixed as String, "mixed_reading": reading as String,
            "spans": (result?.spans ?? []).map { span -> [String: Any] in
                let proof = refs.first { $0.range == span.range }
                return ["start_utf16": span.range.location, "end_utf16": NSMaxRange(span.range), "source": span.original,
                    "target": span.translated, "reading": span.romanization as Any? ?? NSNull(),
                    "output_id": proof?.outputID as Any? ?? NSNull(), "concept_id": proof?.conceptID as Any? ?? NSNull()]
            }]
    }
    private func automatic(_ owner: ConversationImmersion, _ detector: MessageLanguage, text: String, id: String) async throws -> [String: Any] {
        let detected = try await detector.identify(text)
        let begin = ProcessInfo.processInfo.systemUptime
        let result = await owner.result(for: text)
        let outcome = try XCTUnwrap(owner.lastOutcome, id)
        XCTAssertEqual(outcome.localTranslationCalls, 0, id)
        var row = render(result, original: text)
        row.merge(["id": id, "original": text, "detected_language": detected as Any? ?? NSNull(), "input_language_override": NSNull(),
            "status": outcome.status.rawValue, "origin": outcome.origin?.rawValue as Any? ?? NSNull(),
            "translation_calls": outcome.localTranslationCalls, "model_readiness_calls": outcome.modelReadinessCalls,
            "alignment_calls": outcome.alignmentCalls, "milliseconds": (ProcessInfo.processInfo.systemUptime - begin) * 1000]) { _, new in new }
        return row
    }
    private func write(_ value: Any, to url: URL) throws {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: url, options: .withoutOverwriting)
    }
    func testActualBundleAndDefaultRoutes() async throws {
        let docs=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let fixture=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:docs.appendingPathComponent("accepted-content-fixtures-r01.json"))) as? [String:Any])
        let root=try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        let assets=fixture["assets"] as! [String:[String:Any]]
        XCTAssertEqual(BundledSourceFrameCatalog.pinnedIndexSHA256,"c8ae8883785f6b01cce7e847550df2e99705fa89a494aacd37390191c56e5f2f")
        for (file,expected) in assets {
            let bytes=try Data(contentsOf:root.appendingPathComponent(file))
            XCTAssertEqual(bytes.count,expected["bytes"] as? Int,file)
            XCTAssertEqual(JapaneseStarterLookup.digest(bytes),expected["sha256"] as? String,file)
        }
        var validated=0
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            let metadata=try Data(contentsOf:root.appendingPathComponent("source-frames-"+source+"-"+target+"-catalog.json"))
            let m=try JSONDecoder().decode(SourceFrameLookup.Manifest.self,from:metadata)
            XCTAssertTrue(m.file.hasSuffix("-005.json"))
            let bytes=try Data(contentsOf:root.appendingPathComponent(m.file))
            _ = try SourceFrameLookup(bytes:bytes,manifestBytes:metadata,target:target,baselineIdentity:"asset-validation",source:source)
            let pack=try XCTUnwrap(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
            for row in pack["patterns"] as! [[String:Any]] {
                XCTAssertFalse(source == "en" && (row["id"] as? String)?.hasPrefix("bare-noun-r01:") == true && row["source"] as? String == "cheese")
            }
            validated += 1
        } }
        XCTAssertEqual(validated,110)
        var rows:[[String:Any]]=[]
        for old in fixture["samples"] as! [[String:Any]] {
            let source=old["source_language"] as! String,target=old["target_language"] as! String,text=old["original"] as! String
            let owner=ConversationImmersion() // Actual bundled default, no injection.
            await owner.configure(pair:.init(source:source,target:target),density:0.25)
            var row=try await automatic(owner,MessageLanguage(),text:text,id:old["id"] as! String)
            XCTAssertEqual(row["mixed_script"] as? String,old["mixed_script"] as? String)
            XCTAssertEqual(row["mixed_reading"] as? String,old["mixed_reading"] as? String)
            XCTAssertEqual(row["detected_language"] as? String,old["detected_language"] as? String)
            XCTAssertEqual((row["spans"] as! [[String:Any]]).count,(old["spans"] as! [[String:Any]]).count)
            row["source_language"]=source;row["target_language"]=target;rows.append(row);owner.close()
        }
        var controls:[[String:Any]]=[]
        let defaultLookup=try XCTUnwrap(BundledStarterLookup.provider())
        for input in fixture["controls"] as! [[String:Any]] {
            let text=input["original"] as! String,owner=ConversationImmersion()
            await owner.configure(pair:.init(source:"en",target:"es"),density:0.25)
            let auto=try await automatic(owner,MessageLanguage(),text:text,id:input["id"] as! String)
            let direct=try await defaultLookup.resolve(.init(original:text,pair:.init(source:"en",target:"es"),density:0.25,knownConceptIDs:[]))
            let displayed=render(direct.partial.map{.partial($0)},original:text)
            for value in [auto,displayed] { XCTAssertFalse((value["spans"] as! [[String:Any]]).contains{ $0["source"] as? String == "cheese" && ($0["output_id"] as? String)?.hasPrefix("bare-noun-r01:")==true }) }
            controls.append(["input":input,"automatic":auto,"direct":displayed]);owner.close()
        }
        try write(["default_provider":true,"injected_provider":false,"validated_pairs":validated,"assets":assets,"rows":rows,"controls":controls],to:docs.appendingPathComponent("accepted-content-default-r01.json"))
    }
}
