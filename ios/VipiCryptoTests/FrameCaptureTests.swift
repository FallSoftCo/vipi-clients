import CryptoKit
import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class FrameCaptureTests:XCTestCase {
    func testCapturedTranslationsWithSignedFrames() async throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let config=try FrameQAConfiguration.read(documents)
        let conversationProbe=config.conversation_probe == true
        let root=documents.appendingPathComponent(config.pack_root),output=documents.appendingPathComponent("frame-capture-native-\(config.run_id).json")
        guard !FileManager.default.fileExists(atPath:output.path) else {XCTFail("Preserve receipt");return}
        func object(_ data:Data) throws -> [String:Any] {try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])}
        let captureBytes=try Data(contentsOf:documents.appendingPathComponent(config.capture_file)),capture=try object(captureBytes)
        XCTAssertEqual(capture["complete"] as? Bool,true)
        let rows=try XCTUnwrap(capture["results"] as? [[String:Any]])
        let fixture=try object(Data(contentsOf:root.appendingPathComponent("native-fixture.json")))
        let references=try XCTUnwrap(fixture["rows"] as? [[String:Any]])
        let expected=try Dictionary(uniqueKeysWithValues:references.map{(try XCTUnwrap($0["logical_id"] as? String),$0)})
        if !conversationProbe {XCTAssertEqual(rows.count,expected.count)}
        XCTAssertEqual(rows.count,capture["cases_expected"] as? Int)
        XCTAssertEqual(rows.count,capture["cases_completed"] as? Int)
        let identities=try rows.map{[try XCTUnwrap($0["case"] as? String),try XCTUnwrap($0["source"] as? String),try XCTUnwrap($0["target"] as? String)]}
        XCTAssertEqual(Set(identities).count,rows.count)
        let buildBytes=try Data(contentsOf:root.appendingPathComponent("receipt.json")),build=try object(buildBytes)
        let pairs=try XCTUnwrap(build["pairs"] as? [[String:Any]]),keyID=try XCTUnwrap((build["pairs"] as? [[String:Any]])?.first?["key_id"] as? String)
        let key=try Data(contentsOf:root.appendingPathComponent("signing-public-key.der"))
        let store=try VocabularyPackStore(root:documents.appendingPathComponent("installed-frames-001"),trustedKeys:[keyID:key],receiptPrefix:"frame-qa-001-",kind:.reviewedFrame)
        for pair in pairs {
            let folder=root.appendingPathComponent(try XCTUnwrap(pair["pack_id"] as? String))
            _ = try await store.install(manifestBytes:Data(contentsOf:folder.appendingPathComponent("manifest.json")),signature:Data(contentsOf:folder.appendingPathComponent("manifest.sig")),database:Data(contentsOf:folder.appendingPathComponent("frames.sqlite")))
        }
        var results:[[String:Any]]=[]
        for row in rows {
            let caseID=try XCTUnwrap(row["case"] as? String)
            let original=try XCTUnwrap(row["original"] as? String),translation=try XCTUnwrap(row["translation"] as? String)
            let source=try XCTUnwrap(row["source"] as? String),target=try XCTUnwrap(row["target"] as? String)
            XCTAssertEqual(row["status"] as? String,"executed")
            if !conversationProbe {
                let reference=try XCTUnwrap(expected[caseID])
                XCTAssertEqual(reference["source_context"] as? String,original)
                XCTAssertEqual(reference["source_language"] as? String,source);XCTAssertEqual(reference["target_language"] as? String,target)
            }
            let begin=ContinuousClock.now,entries=try await store.entries(id:source+"-"+target,text:original,translation:translation)
            let result=LocalImmersion.align(original:original,translation:translation,entries:entries,density:1,source:source,target:target)
            let duration=begin.duration(to:.now).components
            if !conversationProbe {
                for span in result.spans {XCTAssertEqual(span.range.location,row["start"] as? Int);XCTAssertEqual(NSMaxRange(span.range),row["end"] as? Int)}
            }
            results.append(["case":caseID,"source":source,"target":target,"original":original,"translation":translation,
                "mapping_count":entries.count,"lookup_alignment_ms":Double(duration.seconds)*1000+Double(duration.attoseconds)/1e15,
                "spans":result.spans.map{["start":$0.range.location,"end":NSMaxRange($0.range),"targetStart":$0.targetRange.location,"targetEnd":NSMaxRange($0.targetRange),"original":$0.original,"translated":$0.translated,"reading":$0.romanization as Any? ?? NSNull()]}])
        }
        let receipt:[String:Any]=["schema":conversationProbe ? "vipi-frame-conversation-1" : "vipi-frame-capture-1","platform":"iOS","cases":results.count,
            "translation_capture_sha256":SHA256.hash(data:captureBytes).map{String(format:"%02x",$0)}.joined(),
            "build_sha256":SHA256.hash(data:buildBytes).map{String(format:"%02x",$0)}.joined(),
            "evidence":"native frame lookup on retained actual Apple translations; not new model execution",
            "linguistic_acceptance":false,"general_chat_integration":false,"results":results]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
    }
}
