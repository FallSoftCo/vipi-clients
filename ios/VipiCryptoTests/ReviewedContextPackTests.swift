import CryptoKit
import Foundation
import VipiCore
import XCTest
@testable import Vipi

final class ReviewedContextPackTests:XCTestCase {
    func testSignedReviewedContextsUseNativeIndexedLookup() async throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let config=documents.appendingPathComponent("reviewed-context-run-id.txt")
        let run=FileManager.default.fileExists(atPath:config.path) ? try String(contentsOf:config,encoding:.utf8).trimmingCharacters(in:.whitespacesAndNewlines) : "001"
        guard run.range(of:"^[0-9]{3}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        struct Fixture:Decodable {let root:String,captures:[String],cases:Int,mapped:Int}
        let fixtureURL=documents.appendingPathComponent("reviewed-context-fixture.json")
        let fixture=FileManager.default.fileExists(atPath:fixtureURL.path)
            ? try JSONDecoder().decode(Fixture.self,from:Data(contentsOf:fixtureURL))
            : Fixture(root:"reviewed-contexts-001",captures:["phrase-observations-apple-002.json","phrase-observations-apple-004.json"],cases:3582,mapped:3564)
        guard fixture.root.range(of:"^reviewed-contexts-[0-9]{3}$",options:.regularExpression) != nil,
              (1...20).contains(fixture.captures.count),Set(fixture.captures).count==fixture.captures.count,
              fixture.captures.allSatisfy({$0.range(of:"^phrase-observations-apple-[0-9]{3}\\.json$",options:.regularExpression) != nil}),
              (1...20000).contains(fixture.cases),(1...fixture.cases).contains(fixture.mapped) else {throw VocabularyPackError.invalid}
        let root=documents.appendingPathComponent(fixture.root)
        let output=documents.appendingPathComponent("reviewed-context-native-\(run).json")
        guard !FileManager.default.fileExists(atPath:output.path) else {XCTFail("Preserve receipt");return}
        let buildBytes=try Data(contentsOf:root.appendingPathComponent("receipt.json"))
        let build=try XCTUnwrap(JSONSerialization.jsonObject(with:buildBytes) as? [String:Any])
        let pairs=try XCTUnwrap(build["pairs"] as? [[String:Any]]);XCTAssertEqual(pairs.count,90)
        let key=try Data(contentsOf:root.appendingPathComponent("signing-public-key.der"))
        let keyID=try XCTUnwrap(pairs.first?["key_id"] as? String)
        let installRoot=documents.appendingPathComponent("installed-"+fixture.root)
        let store=try VocabularyPackStore(root:installRoot,trustedKeys:[keyID:key],receiptPrefix:fixture.root+"-",kind:.reviewedContext)
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
        let greetings=["en":"Hello","es":"Hola","fr":"Bonjour","de":"Hallo","it":"Ciao","pt":"Olá",
            "ar":"مرحبًا","zh":"你好","ja":"こんにちは","ko":"안녕하세요"]
        for text in ["안녕하세요 🙂. 시간이 더 필요해요.","안녕하세요 . 시간이 더 필요해요.","안녕하세요 👩🏽‍💻! 시간이 더 필요해요."] {
            let words=LocalImmersion.words(text,language:"ko").map{(text as NSString).substring(with:$0)}
            XCTAssertEqual(words,["안녕하세요","시간이","더","필요해요"])
        }
        func prefix(_ language:String)->String {greetings[language]! + " 🙂" + (["zh","ja"].contains(language) ? "。 " : ". ")}
        var results:[[String:Any]]=[];var withMappings=0,withImmersion=0,paragraphMappings=0,paragraphImmersion=0
        for name in fixture.captures {
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
                let before=prefix(source),paragraph=prefix(source)+original
                let paragraphEntries=try await store.entries(id:source+"-"+target,text:paragraph)
                let paragraphResult=LocalImmersion.align(original:paragraph,translation:prefix(target)+translation,entries:paragraphEntries,density:1,source:source,target:target)
                if !paragraphEntries.isEmpty {paragraphMappings+=1};if !paragraphResult.spans.isEmpty {paragraphImmersion+=1}
                XCTAssertEqual(entries.count,paragraphEntries.count,row["case"] as? String ?? "")
                XCTAssertEqual(result.spans.count,paragraphResult.spans.count,row["case"] as? String ?? "")
                for span in paragraphResult.spans {
                    XCTAssertEqual(span.range.location,before.utf16.count+(try XCTUnwrap(row["start"] as? Int)))
                    XCTAssertEqual(NSMaxRange(span.range),before.utf16.count+(try XCTUnwrap(row["end"] as? Int)))
                    let expected=(paragraph as NSString).replacingCharacters(in:span.range,with:span.translated)
                    XCTAssertEqual(paragraphResult.speech(source:source,target:target).map(\.text).joined(),expected)
                }
                for span in result.spans {
                    XCTAssertEqual(span.range.location,row["start"] as? Int);XCTAssertEqual(NSMaxRange(span.range),row["end"] as? Int)
                    if ["ar","zh","ja","ko"].contains(target) {XCTAssertFalse((span.romanization ?? "").isEmpty)}
                }
                results.append(["case":try XCTUnwrap(row["case"] as? String),"source":source,"target":target,
                    "mapping_count":entries.count,"spans":result.spans.map{["start":$0.range.location,"end":NSMaxRange($0.range),"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull()]},
                    "paragraph_mapping_count":paragraphEntries.count,"paragraph_span_count":paragraphResult.spans.count,
                    "lookup_alignment_ms":Double(duration.seconds)*1000+Double(duration.attoseconds)/1e15])
            }
        }
        XCTAssertEqual(results.count,fixture.cases);XCTAssertEqual(withMappings,fixture.mapped)
        let variant="Can we bring our books?"
        let entries=try await store.entries(id:"en-es",text:variant);XCTAssertEqual(entries.first?.source,"books");XCTAssertEqual(entries.count,1)
        let reservation=try await store.entries(id:"en-es",text:"Can we book our flights?");XCTAssertTrue(reservation.isEmpty)
        let fragment=try await store.entries(id:"en-es",text:"We know that I need more time.");XCTAssertTrue(fragment.isEmpty)
        let repeated="Can we bring our books? Can we bring our books?"
        let repeatedEntries=try await store.entries(id:"en-es",text:repeated);XCTAssertEqual(repeatedEntries.count,2)
        XCTAssertTrue(LocalImmersion.align(original:repeated,translation:"¿Podemos traer nuestros libros? ¿Podemos traer nuestros libros?",entries:repeatedEntries,density:1,source:"en",target:"es").spans.isEmpty)
        let code="Hello.\n```\nI need more time.\n```"
        let codeEntries=try await store.entries(id:"en-es",text:code)
        XCTAssertTrue(LocalImmersion.align(original:code,translation:"Hola. Necesito más tiempo.",entries:codeEntries,density:1,source:"en",target:"es").spans.isEmpty)
        let oversized=try await store.entries(id:"en-es",text:String(repeating:"Hello. ",count:129)+"I need more time.")
        XCTAssertTrue(oversized.isEmpty)
        try await store.remove(id:"en-es")
        let removed=try await store.entries(id:"en-es",text:variant);XCTAssertTrue(removed.isEmpty)
        let receipt:[String:Any]=["schema":"vipi-reviewed-context-native-1","platform":"iOS",
            "build_sha256":SHA256.hash(data:buildBytes).map{String(format:"%02x",$0)}.joined(),
            "cases":results.count,"cases_with_mappings":withMappings,"cases_with_immersion":withImmersion,
            "assembled_paragraph_cases_with_mappings":paragraphMappings,"assembled_paragraph_cases_with_immersion":paragraphImmersion,
            "paragraph_evidence":"Mechanical sentence-scope test using assembled greeting plus retained sentence translation; not a model-generated paragraph translation",
            "signed_pairs_installed":90,"linguistic_acceptance":false,"general_chat_integration":false,"results":results]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
    }
}
