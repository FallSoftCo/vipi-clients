import CryptoKit
import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class ReviewedContextPackTests:XCTestCase {
    func testSignedReviewedContextsUseNativeIndexedLookup() async throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let root=documents.appendingPathComponent("reviewed-contexts-001")
        let output=documents.appendingPathComponent("reviewed-context-native-001.json")
        guard !FileManager.default.fileExists(atPath:output.path) else {XCTFail("Preserve receipt");return}
        let buildBytes=try Data(contentsOf:root.appendingPathComponent("receipt.json"))
        let build=try XCTUnwrap(JSONSerialization.jsonObject(with:buildBytes) as? [String:Any])
        let pairs=try XCTUnwrap(build["pairs"] as? [[String:Any]]);XCTAssertEqual(pairs.count,90)
        let key=try Data(contentsOf:root.appendingPathComponent("signing-public-key.der"))
        let keyID=try XCTUnwrap(pairs.first?["key_id"] as? String)
        let installRoot=documents.appendingPathComponent("context-qualification-installed-001")
        let store=try VocabularyPackStore(root:installRoot,trustedKeys:[keyID:key],receiptPrefix:"context-qa-001-",kind:.reviewedContext)
        for (index,pair) in pairs.enumerated() {
            let id=try XCTUnwrap(pair["pack_id"] as? String);let folder=root.appendingPathComponent(id)
            let manifest=try Data(contentsOf:folder.appendingPathComponent("manifest.json"))
            let signature=try Data(contentsOf:folder.appendingPathComponent("manifest.sig"))
            let database=try Data(contentsOf:folder.appendingPathComponent("contexts.sqlite"))
            let installed=try await store.install(manifestBytes:manifest,signature:signature,database:database)
            XCTAssertEqual(installed,id)
            let unknown=try await store.entries(id:id,text:"unmatched context 729348");XCTAssertTrue(unknown.isEmpty)
            if index==0 {
                let generic=try VocabularyPackStore(root:installRoot,trustedKeys:[keyID:key],receiptPrefix:"generic-context-qa-001-")
                do {_ = try await generic.install(manifestBytes:manifest,signature:signature,database:database);XCTFail("Wrong pack kind accepted")} catch {}
                var badSignature=signature;badSignature[badSignature.count-1] ^= 1
                do {_ = try await store.install(manifestBytes:manifest,signature:badSignature,database:database);XCTFail("Wrong signature accepted")} catch {}
                var badDatabase=database;badDatabase[badDatabase.count-1] ^= 1
                do {_ = try await store.install(manifestBytes:manifest,signature:signature,database:badDatabase);XCTFail("Corrupt database accepted")} catch {}
            }
        }
        var results:[[String:Any]]=[];var withMappings=0,withImmersion=0
        for name in ["phrase-observations-apple-002.json","phrase-observations-apple-004.json"] {
            let capture=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:documents.appendingPathComponent(name))) as? [String:Any])
            XCTAssertEqual(capture["complete"] as? Bool,true)
            for row in try XCTUnwrap(capture["results"] as? [[String:Any]]) {
                let source=try XCTUnwrap(row["source"] as? String),target=try XCTUnwrap(row["target"] as? String)
                let original=try XCTUnwrap(row["original"] as? String),translation=try XCTUnwrap(row["translation"] as? String)
                let begin=ContinuousClock.now
                let entries=try await store.entries(id:source+"-"+target,text:original)
                let result=LocalImmersion.align(original:original,translation:translation,entries:entries,density:1,source:source,target:target)
                let duration=begin.duration(to:.now).components
                if !entries.isEmpty {withMappings+=1};if !result.spans.isEmpty {withImmersion+=1}
                for span in result.spans {
                    XCTAssertEqual(span.range.location,row["start"] as? Int);XCTAssertEqual(NSMaxRange(span.range),row["end"] as? Int)
                    if ["ar","zh","ja","ko"].contains(target) {XCTAssertFalse((span.romanization ?? "").isEmpty)}
                }
                results.append(["case":try XCTUnwrap(row["case"] as? String),"source":source,"target":target,
                    "mapping_count":entries.count,"spans":result.spans.map{["start":$0.range.location,"end":NSMaxRange($0.range),"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull()]},
                    "lookup_alignment_ms":Double(duration.seconds)*1000+Double(duration.attoseconds)/1e15])
            }
        }
        XCTAssertEqual(results.count,3582);XCTAssertEqual(withMappings,3564)
        let variant="Can we bring our books?"
        let entries=try await store.entries(id:"en-es",text:variant);XCTAssertEqual(entries.first?.source,"books");XCTAssertEqual(entries.count,1)
        let reservation=try await store.entries(id:"en-es",text:"Can we book our flights?");XCTAssertTrue(reservation.isEmpty)
        try await store.remove(id:"en-es")
        let removed=try await store.entries(id:"en-es",text:variant);XCTAssertTrue(removed.isEmpty)
        let receipt:[String:Any]=["schema":"vipi-reviewed-context-native-1","platform":"iOS",
            "build_sha256":SHA256.hash(data:buildBytes).map{String(format:"%02x",$0)}.joined(),
            "cases":results.count,"cases_with_mappings":withMappings,"cases_with_immersion":withImmersion,
            "signed_pairs_installed":90,"linguistic_acceptance":false,"general_chat_integration":false,"results":results]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
    }
}
