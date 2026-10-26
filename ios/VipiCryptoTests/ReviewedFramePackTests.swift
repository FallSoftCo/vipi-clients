import CryptoKit
import Foundation
import VipiCore
import XCTest
@testable import Vipi

struct FrameQAConfiguration:Decodable {
    let pack_root:String,run_id:String,capture_file:String
    static func read(_ documents:URL) throws -> Self {
        let value=try JSONDecoder().decode(Self.self,from:Data(contentsOf:documents.appendingPathComponent("frame-qa.json")))
        guard value.pack_root.range(of:"^reviewed-frames-[0-9]{3}$",options:.regularExpression) != nil,
              value.run_id.range(of:"^[0-9]{3}$",options:.regularExpression) != nil,
              value.capture_file.range(of:"^phrase-observations-apple-[0-9]{3}\\.json$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        return value
    }
}

final class ReviewedFramePackTests:XCTestCase {
    func testSignedFramesBindBothSidesAcrossNativeLanguages() async throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let config=try FrameQAConfiguration.read(documents)
        let root=documents.appendingPathComponent(config.pack_root)
        let output=documents.appendingPathComponent("reviewed-frame-native-\(config.run_id).json")
        guard !FileManager.default.fileExists(atPath:output.path) else {XCTFail("Preserve receipt");return}
        let buildBytes=try Data(contentsOf:root.appendingPathComponent("receipt.json"))
        let build=try XCTUnwrap(JSONSerialization.jsonObject(with:buildBytes) as? [String:Any])
        let pairs=try XCTUnwrap(build["pairs"] as? [[String:Any]])
        let key=try Data(contentsOf:root.appendingPathComponent("signing-public-key.der"))
        let keyID=try XCTUnwrap(pairs.first?["key_id"] as? String)
        let store=try VocabularyPackStore(root:documents.appendingPathComponent("installed-frames-001"),trustedKeys:[keyID:key],receiptPrefix:"frame-qa-001-",kind:.reviewedFrame)
        for (index,pair) in pairs.enumerated() {
            let id=try XCTUnwrap(pair["pack_id"] as? String),folder=root.appendingPathComponent(try XCTUnwrap(pair["pack_id"] as? String))
            let manifest=try Data(contentsOf:folder.appendingPathComponent("manifest.json")),signature=try Data(contentsOf:folder.appendingPathComponent("manifest.sig")),database=try Data(contentsOf:folder.appendingPathComponent("frames.sqlite"))
            let installed=try await store.install(manifestBytes:manifest,signature:signature,database:database);XCTAssertEqual(installed,id)
            if index==0 {
                for kind in [VocabularyPackKind.vocabulary,.reviewedContext] {
                    let other=try VocabularyPackStore(root:root.appendingPathComponent("wrong-kind"),trustedKeys:[keyID:key],receiptPrefix:"frame-wrong-001-",kind:kind)
                    do {_ = try await other.install(manifestBytes:manifest,signature:signature,database:database);XCTFail("Wrong kind accepted")} catch {}
                }
                var bad=signature;bad[bad.count-1] ^= 1
                do {_ = try await store.install(manifestBytes:manifest,signature:bad,database:database);XCTFail("Bad signature accepted")} catch {}
                var corrupt=database;corrupt[corrupt.count-1] ^= 1
                do {_ = try await store.install(manifestBytes:manifest,signature:signature,database:corrupt);XCTFail("Corrupt pack accepted")} catch {}
            }
        }
        let fixtureBytes=try Data(contentsOf:root.appendingPathComponent("native-fixture.json"))
        let fixture=try XCTUnwrap(JSONSerialization.jsonObject(with:fixtureBytes) as? [String:Any])
        let rows=try XCTUnwrap(fixture["rows"] as? [[String:Any]])
        var results:[[String:Any]]=[]
        func expectedRange(_ row:[String:Any],_ side:String) throws -> NSRange {
            let text=try XCTUnwrap(row[side+"_context"] as? String),span=try XCTUnwrap(row[side+"_span"] as? [Int])
            let units=text.unicodeScalars.map{$0.value>0xFFFF ? 2 : 1}
            let start=units.prefix(span[0]).reduce(0,+),end=units.prefix(span[1]).reduce(0,+)
            return NSRange(location:3+start,length:end-start) // leading emoji plus space
        }
        for row in rows {
            let source=try XCTUnwrap(row["source_language"] as? String),target=try XCTUnwrap(row["target_language"] as? String)
            let original="🙂 "+(try XCTUnwrap(row["source_context"] as? String))+" 🙂"
            let translation="🙂 "+(try XCTUnwrap(row["target_context"] as? String))+" 🙂"
            let word=try XCTUnwrap(row["source"] as? String),targetWord=try XCTUnwrap(row["target"] as? String)
            let id=source+"-"+target,caseID=try XCTUnwrap(row["logical_id"] as? String)
            let begin=ContinuousClock.now
            let entries=try await store.entries(id:id,text:original,translation:translation)
            let result=LocalImmersion.align(original:original,translation:translation,entries:entries,density:1,source:source,target:target)
            let duration=begin.duration(to:.now).components
            let expected=word.caseInsensitiveCompare(targetWord) == .orderedSame && !["ar","zh","ja","ko"].contains(target) ? 0 : 1
            XCTAssertEqual(entries.count,1,caseID);XCTAssertEqual(result.spans.count,expected,caseID)
            if let span=result.spans.first {
                XCTAssertEqual(span.range,try expectedRange(row,"source"),caseID)
                XCTAssertEqual(span.targetRange,try expectedRange(row,"target"),caseID)
                XCTAssertEqual(span.translated,targetWord,caseID)
                XCTAssertEqual(result.speech(source:source,target:target).map(\.text).joined(),(original as NSString).replacingCharacters(in:span.range,with:targetWord),caseID)
                if ["ar","zh","ja","ko"].contains(target) {XCTAssertFalse((span.romanization ?? "").isEmpty,caseID)}
            }
            let missing=try await store.entries(id:id,text:original);XCTAssertTrue(missing.isEmpty)
            let absent=try await store.entries(id:id,text:original,translation:"unmatched 348273");XCTAssertTrue(absent.isEmpty)
            let repeated=try await store.entries(id:id,text:original+" "+original,translation:translation);XCTAssertTrue(repeated.isEmpty,caseID)
            let repeatedTarget=try await store.entries(id:id,text:original,translation:translation+" "+translation);XCTAssertTrue(repeatedTarget.isEmpty,caseID)
            results.append(["case":caseID,"source":source,"target":target,"mapping_count":entries.count,"span_count":result.spans.count,
                "lookup_alignment_ms":Double(duration.seconds)*1000+Double(duration.attoseconds)/1e15])
        }
        let original="I am reading a book now.",translation="Estoy leyendo un libro ahora. Otro libro."
        let selected=try await store.entries(id:"en-es",text:original,translation:translation)
        XCTAssertEqual(LocalImmersion.align(original:original,translation:translation,entries:selected,density:1,source:"en",target:"es").spans.count,1)
        let code="```\n"+original+"\n```",codeEntries=try await store.entries(id:"en-es",text:code,translation:translation)
        XCTAssertTrue(LocalImmersion.align(original:code,translation:translation,entries:codeEntries,density:1,source:"en",target:"es").spans.isEmpty)
        XCTAssertNil(ReviewedFrameLookup.windows(String(repeating:"word ",count:1000),language:"en"))
        XCTAssertFalse(ReviewedFrameLookup.windows("reading. a book",language:"en")?.keys.contains("reading. a book") ?? true)
        try await store.remove(id:"en-es")
        let removed=try await store.entries(id:"en-es",text:original,translation:translation);XCTAssertTrue(removed.isEmpty)
        XCTAssertEqual(pairs.count,90);XCTAssertEqual(results.count,build["records"] as? Int)
        let receipt:[String:Any]=["schema":"vipi-reviewed-frame-native-1","platform":"iOS","cases":results.count,
            "build_sha256":SHA256.hash(data:buildBytes).map{String(format:"%02x",$0)}.joined(),
            "fixture_sha256":SHA256.hash(data:fixtureBytes).map{String(format:"%02x",$0)}.joined(),
            "reference_translations":true,"linguistic_acceptance":false,"general_chat_integration":false,"results":results]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
    }
}
