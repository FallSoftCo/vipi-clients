import Foundation
import XCTest
import SwiftUI
import VipiCore
@testable import Vipi

@MainActor final class DictionaryDefaultTests: XCTestCase {
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
    func testExactDictionaryBundleFocusedSample() async throws {
        let docs=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let fixture=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:docs.appendingPathComponent("dictionary-default-fixtures-r01.json"))) as? [String:Any])
        let root=try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        XCTAssertEqual(BundledSourceFrameCatalog.pinnedIndexSHA256,"a0f6f73172cd747a758d677a8c49383fc25591763045a1b0bb77575ba60114a3")
        for (file,expected) in fixture["assets"] as! [String:[String:Any]] {
            let bytes=try Data(contentsOf:root.appendingPathComponent(file))
            XCTAssertEqual(bytes.count,expected["bytes"] as? Int,file)
            XCTAssertEqual(JapaneseStarterLookup.digest(bytes),expected["sha256"] as? String,file)
        }
        var changed=0,retained=0
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            let metadata=try Data(contentsOf:root.appendingPathComponent("source-frames-"+source+"-"+target+"-catalog.json"))
            let m=try JSONDecoder().decode(SourceFrameLookup.Manifest.self,from:metadata)
            let bytes=try Data(contentsOf:root.appendingPathComponent(m.file))
            _ = try SourceFrameLookup(bytes:bytes,manifestBytes:metadata,target:target,baselineIdentity:"asset-validation",source:source)
            if m.file.hasSuffix("-007.json") {changed += 1} else {XCTAssertTrue(m.file.hasSuffix("-005.json"));retained += 1}
        } }
        XCTAssertEqual(changed,22);XCTAssertEqual(retained,88)
        let lookup=try XCTUnwrap(BundledStarterLookup.provider())
        var rows:[[String:Any]]=[],failures:[[String:Any]]=[]
        for input in (fixture["cases"] as! [[String:Any]]) + (fixture["controls"] as! [[String:Any]]) {
            let source=input["source_language"] as! String,target=input["target_language"] as! String,text=input["original"] as! String
            let owner=ConversationImmersion()
            await owner.configure(pair:.init(source:source,target:target),density:0.25)
            let auto=try await automatic(owner,MessageLanguage(),text:text,id:input["id"] as! String)
            let direct=try await lookup.resolve(.init(original:text,pair:.init(source:source,target:target),density:0.5,knownConceptIDs:[]))
            let displayed=render(direct.partial.map{.partial($0)},original:text)
            var row:[String:Any]=["fixture":input,"automatic":auto,"direct":displayed,"automatic_density":0.25,"direct_density":0.5]
            if let prefix=input["forbidden_pattern_prefix"] as? String,let focus=input["forbidden_focus"] as? String {
                let forbidden=[auto,displayed].flatMap{$0["spans"] as! [[String:Any]]}.filter{$0["source"] as? String==focus && ($0["output_id"] as? String)?.hasPrefix(prefix)==true}
                row["forbidden_outputs"]=forbidden
                if !forbidden.isEmpty {failures.append(["fixture":input,"outputs":forbidden])}
            }
            rows.append(row);owner.close()
        }
        var baseline:[[String:Any]]=[]
        for old in fixture["baseline_samples"] as! [[String:Any]] {
            let target=old["target_language"] as! String,text=old["original"] as! String,owner=ConversationImmersion()
            await owner.configure(pair:.init(source:"en",target:target),density:0.25)
            var row=try await automatic(owner,MessageLanguage(),text:text,id:old["id"] as! String)
            XCTAssertEqual(row["mixed_script"] as? String,old["mixed_script"] as? String)
            XCTAssertEqual(row["mixed_reading"] as? String,old["mixed_reading"] as? String)
            row["pair"]="en-"+target;baseline.append(row);owner.close()
        }
        try write(["changed_pair_packs":changed,"retained_pair_packs":retained,"rows":rows,"baseline":baseline,"forbidden_failures":failures,"injected_provider":false,"scope":"Actual bundled default; positive opportunities may abstain"],to:docs.appendingPathComponent("dictionary-default-results-r01.json"))
        XCTAssertEqual(rows.count,32);XCTAssertTrue(failures.isEmpty)
    }
}
