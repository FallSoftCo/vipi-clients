import XCTest
import Foundation
import VipiCore
@testable import Vipi

@MainActor final class StarterPackingProductionTests: XCTestCase {
    private func spans(_ value: PartialImmersionResult?) -> [[String:Any]] {
        (value?.spans ?? []).map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":[$0.range.location,NSMaxRange($0.range)]] }
    }
    private func canonical(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]) }
    func testFrozenDensityRange() throws {
        guard let path=ProcessInfo.processInfo.environment["VIPI_STARTER_PACKING_QA"] else { throw XCTSkip("Private packing qualification is opt-in") }
        let root=URL(fileURLWithPath:path)
        func read(_ name:String) throws -> Data { try Data(contentsOf:root.appendingPathComponent(name)) }
        let manifest=try XCTUnwrap(JSONSerialization.jsonObject(with:read("manifest.json")) as? [String:Any])
        let files=try XCTUnwrap(manifest["files"] as? [String:String])
        for (name,hash) in files { XCTAssertEqual(JapaneseStarterLookup.digest(try read(name)),hash) }
        XCTAssertFalse(JapaneseStarterLookup.packingEnabled);XCTAssertFalse(SwahiliStarterLookup.packingEnabled)
        let ja=try JapaneseStarterLookup(data:read("starter-en-ja-002.json"),manifest:read("starter-catalog.json"),packMultiple:true)
        let sw=try SwahiliStarterLookup(data:read("starter-en-sw-001.json"),manifest:read("starter-sw-catalog.json"),packMultiple:true)
        let jaOld=try JapaneseStarterLookup(data:read("starter-en-ja-002.json"),manifest:read("starter-catalog.json"))
        let swOld=try SwahiliStarterLookup(data:read("starter-en-sw-001.json"),manifest:read("starter-sw-catalog.json"))
        XCTAssertNotEqual(ja.identity,jaOld.identity);XCTAssertNotEqual(sw.identity,swOld.identity)
        let prior=try XCTUnwrap(JSONSerialization.jsonObject(with:read("packing-reference.json")) as? [String:Any])
        let oldRows=try XCTUnwrap(prior["cases"] as? [[String:Any]])
        let oldByKey=Dictionary(uniqueKeysWithValues:oldRows.map { ("\($0["pair"]!)/\($0["id"]!)/\($0["known_state"]!)",$0) })
        let raw=try XCTUnwrap(String(data:read("density-reference.jsonl"),encoding:.utf8))
        var records:[[String:Any]]=[];var evaluated=0;var baseline=0
        let started=ProcessInfo.processInfo.systemUptime
        for line in raw.split(separator:"\n") {
            let row=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any])
            let pair=try XCTUnwrap(row["pair"] as? String),id=try XCTUnwrap(row["id"] as? String),state=try XCTUnwrap(row["known_state"] as? Int),text=try XCTUnwrap(row["source"] as? String)
            let target=pair=="en-ja" ? "ja" : "sw",known=Set(try XCTUnwrap(row["known_ids"] as? [String]))
            let words=LocalImmersion.words(text,language:"en")
            let basis=try XCTUnwrap(NativeSourceTokenBasis(original:text,wordRanges:words))
            let steps=try XCTUnwrap(row["steps"] as? [[String:Any]]),expected=try XCTUnwrap(row["outputs"] as? [String:[String:Any]])
            var outputs:[String:Any]=[:];var actualSteps:[[String:Any]]=[]
            for step in steps {
                let bits=try XCTUnwrap(step["density_bits"] as? String),density=Double(bitPattern:try XCTUnwrap(UInt64(bits,radix:16)))
                let context=SourceUnitLookup.Context(original:text,pair:.init(source:"en",target:target),density:density,knownConceptIDs:known)
                let evidence=try target=="ja" ? ja.resolve(context) : sw.resolve(context)
                let identity=target=="ja" ? ja.identity : sw.identity
                let validated=try XCTUnwrap(evidence.validated(text:text,sourceLanguage:"en",targetLanguage:target,identity:identity))
                let actual=evidence.partial.flatMap { validated.filterPartial($0) }
                let key=try XCTUnwrap(step["output"] as? String),wanted=try XCTUnwrap(expected[key])
                XCTAssertEqual(try canonical(spans(actual)),try canonical(wanted["spans"]!),"\(pair)/\(id)/\(state)/\(bits)")
                let budget=density>0 ? max(1,Int(Double(words.count)*density)) : 0
                for reference in actual?.references ?? [] { XCTAssertEqual(basis.exactWordCost(for:reference.range),reference.nativeSourceTokens) }
                XCTAssertLessThanOrEqual(actual?.references.reduce(0){$0+$1.nativeSourceTokens} ?? 0,budget)
                if density==0 || state==2 { XCTAssertNil(actual) }
                let refs=(actual?.references ?? []).map { ["scope":[$0.range.location,NSMaxRange($0.range)],"output_id":$0.outputID as Any? ?? NSNull(),"reference_id":$0.referenceID,"pack_sha":$0.catalogSHA256,"native_cost":$0.nativeSourceTokens] as [String:Any] }
                XCTAssertEqual(try canonical(refs),try canonical(wanted["references"]!))
                if density==0.25 {
                    let old=try target=="ja" ? jaOld.resolve(context) : swOld.resolve(context)
                    let oldRow=try XCTUnwrap(oldByKey["\(pair)/\(id)/\(state)"])
                    XCTAssertEqual(try canonical(spans(old.partial)),try canonical(oldRow["a_direct"]!));baseline+=1
                }
                var mixed=text
                for span in (actual?.spans ?? []).reversed() { mixed=(mixed as NSString).replacingCharacters(in:span.range,with:span.romanization ?? span.translated) }
                XCTAssertEqual(mixed,wanted["mixed"] as? String)
                outputs[key]=["spans":spans(actual),"mixed":mixed,"references":refs]
                actualSteps.append(["density_bits":bits,"output":key,"budget":budget,"android_budget":step["budget"]!]);evaluated+=1
            }
            records.append(["pair":pair,"id":id,"known_state":state,"native_words":words.map{[$0.location,NSMaxRange($0)]},"android_native_words":row["native_words"]!,"steps":actualSteps,"outputs":outputs])
        }
        XCTAssertEqual(records.count,768);XCTAssertEqual(evaluated,21504);XCTAssertEqual(baseline,768)
        // Existing presentation capacity: retain an admitted prefix, never pass 129+ units.
        let long=Array(repeating:"music",count:200).joined(separator:" ")
        var controls:[[String:Any]]=[]
        for target in ["ja","sw"] {
            let context=SourceUnitLookup.Context(original:long,pair:.init(source:"en",target:target),density:0.75,knownConceptIDs:[])
            let plain=try target=="ja" ? ja.resolve(context) : sw.resolve(context)
            XCTAssertEqual(plain.partial?.spans.count,128)
            let mask=NSRange(location:0,length:5)
            let protected=try target=="ja" ? ja.resolve(context,protectedRanges:[mask]) : sw.resolve(context,protectedRanges:[mask])
            XCTAssertEqual(protected.partial?.spans.count,128);XCTAssertFalse(protected.partial?.spans.contains{$0.range.location==0} ?? true)
            let masked=try target=="ja" ? ja.resolve(context,sourceMasks:[NSRange(location:0,length:long.utf16.count)]) : sw.resolve(context,sourceMasks:[NSRange(location:0,length:long.utf16.count)])
            XCTAssertNil(masked.partial);XCTAssertFalse(masked.recognitions.isEmpty)
            controls.append(["target":target,"plain":spans(plain.partial),"protected":spans(protected.partial),"fully_masked_count":masked.partial?.spans.count ?? 0])
        }
        let result:[String:Any]=["complete":true,"activated":false,"platform":"apple","manifest_sha256":JapaneseStarterLookup.digest(try read("manifest.json")),"cases":records,"controls":controls,"evaluations":evaluated,"baseline_parity":baseline,"seconds":ProcessInfo.processInfo.systemUptime-started]
        let data=try canonical(result);XCTAssertLessThan(data.count,16*1024*1024)
        let attachment=XCTAttachment(data:data,uniformTypeIdentifier:"public.json");attachment.name="starter-packing-production-apple-r01.json";attachment.lifetime = .keepAlways;add(attachment)
    }
}
