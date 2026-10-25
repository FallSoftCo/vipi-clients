import CryptoKit
import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class ConversationMappingTests: XCTestCase {
    @MainActor func testExpandedContextMappings() throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let configURL=documents.appendingPathComponent("conversation-mapping-config.json")
        let config: [String:String]
        if FileManager.default.fileExists(atPath:configURL.path) {
            config=try JSONDecoder().decode([String:String].self,from:Data(contentsOf:configURL))
        } else {config=[:]}
        func filename(_ key:String,_ fallback:String,_ suffix:String) throws -> String {
            let name=config[key] ?? fallback
            guard name.range(of:"^[a-z0-9-]+\\."+suffix+"$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
            return name
        }
        let captureName=try filename("capture","phrase-observations-apple-002.json","json")
        let referenceName=try filename("references","conversation-records.jsonl","jsonl")
        let outputName=try filename("output","conversation-mappings-apple-005.json","json")
        let input=try Data(contentsOf:documents.appendingPathComponent(captureName))
        let capture=try XCTUnwrap(JSONSerialization.jsonObject(with:input) as? [String:Any])
        XCTAssertEqual(capture["complete"] as? Bool,true)
        let referenceBytes=try Data(contentsOf:documents.appendingPathComponent(referenceName))
        let referenceText=try XCTUnwrap(String(data:referenceBytes,encoding:.utf8))
        var references:[String:[String:Any]]=[:]
        for line in referenceText.split(separator:"\n") {
            let value=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any])
            references[try XCTUnwrap(value["logical_id"] as? String)]=value
        }
        let rows=try XCTUnwrap(capture["results"] as? [[String:Any]])
        var output:[[String:Any]]=[];var accepted=0
        for row in rows {
            let original=try XCTUnwrap(row["original"] as? String), translation=try XCTUnwrap(row["translation"] as? String)
            let source=try XCTUnwrap(row["source"] as? String),target=try XCTUnwrap(row["target"] as? String)
            let start=try XCTUnwrap(row["start"] as? Int),end=try XCTUnwrap(row["end"] as? Int)
            let word=try XCTUnwrap(row["source_word"] as? String),translated=try XCTUnwrap(row["expected_target"] as? String)
            let reading=try XCTUnwrap(row["expected_reading"] as? String),identifier=try XCTUnwrap(row["case"] as? String)
            let text=original as NSString;let focus=NSRange(location:start,length:end-start)
            XCTAssertEqual(text.substring(with:focus),word)
            let reference=try XCTUnwrap(references[identifier])
            XCTAssertEqual(reference["source_context"] as? String,original)
            XCTAssertEqual(reference["target"] as? String,translated);XCTAssertEqual(reference["reading"] as? String,reading)
            let targetContext=try XCTUnwrap(reference["target_context"] as? String)
            let offsets=try XCTUnwrap(reference["target_span"] as? [Int])
            let ts=String(targetContext.unicodeScalars.prefix(offsets[0])).utf16.count
            let te=String(targetContext.unicodeScalars.prefix(offsets[1])).utf16.count
            let targetFocus=NSRange(location:ts,length:te-ts)
            XCTAssertEqual((targetContext as NSString).substring(with:targetFocus),translated)
            let touching=LocalImmersion.words(targetContext,language:target).filter {NSIntersectionRange($0,targetFocus).length>0}
            var forms:[VocabularyTargetForm]=[]
            if let first=touching.first,let last=touching.last {
                let a=min(ts,first.location),b=max(te,NSMaxRange(last))
                forms=[.init(surface:(targetContext as NSString).substring(with:NSRange(location:a,length:b-a)),target:translated,start:ts-a,end:te-a)]
            }
            var parts:[ContextPart]=[]
            if start>0 {parts.append(.literal(text.substring(to:start)))}
            parts.append(.focus(word))
            if end<text.length {parts.append(.literal(text.substring(from:end)))}
            let mapping=ContextMapping(id:identifier,meaning:try XCTUnwrap(row["concept"] as? String),sourceLanguage:source,
                targetLanguage:target,parts:parts,targets:[translated],readings:reading.isEmpty ? [:] : [translated:[reading]],targetForms:forms)
            let entries=ContextMappingMatcher.entries(original:original,source:source,target:target,mappings:[mapping])
            XCTAssertEqual(entries.count,1)
            let result=LocalImmersion.align(original:original,translation:translation,entries:entries,density:1,source:source,target:target)
            var spans:[[String:Any]]=[]
            for span in result.spans {
                XCTAssertEqual(span.range,focus);XCTAssertEqual(span.original,word)
                if ["ar","zh","ja","ko"].contains(target) {XCTAssertFalse((span.romanization ?? "").isEmpty)}
                spans.append(["start":span.range.location,"end":NSMaxRange(span.range),"target":span.translated,"reading":span.romanization as Any? ?? NSNull()])
            }
            if !spans.isEmpty {accepted+=1}
            output.append(["case":identifier,"source":source,"target":target,"original":original,"translation":translation,
                "spans":spans,"visible_script":result.speech(source:source,target:target).map(\.text).joined()])
        }
        let receipt=documents.appendingPathComponent(outputName)
        guard !FileManager.default.fileExists(atPath:receipt.path) else {XCTFail("Preserve existing receipt");return}
        let report:[String:Any] = ["schema":"vipi-native-conversation-mappings-1",
            "capture_sha256":SHA256.hash(data:input).map{String(format:"%02x",$0)}.joined(),"cases":rows.count,
            "reference_sha256":SHA256.hash(data:referenceBytes).map{String(format:"%02x",$0)}.joined(),
            "cases_with_immersion":accepted,"platform":"iOS","scope":"authored development contexts against retained actual Apple output",
            "independent_linguistic_acceptance":false,"general_chat_integration":false,"results":output]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:receipt,options:.atomic)
    }
}
