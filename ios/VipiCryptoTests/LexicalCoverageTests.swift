import Foundation
import CryptoKit
import SQLite3
import VipiCore
import XCTest
@testable import Vipi

final class LexicalCoverageTests:XCTestCase {
    private struct Manifest:Decodable {
        struct Shard:Decodable {let language:String,sha256:String;let bytes:Int}
        let schema:String,cases_sha256:String,shards:[Shard]
    }
    private struct Case:Decodable {
        let id:String,dataset:String,source:String,target:String,original:String,translation:String
        let forbidden_source:String?,forbidden_target:String?,expected_source:String?,expected_target:String?
    }
    private func sha(_ url:URL) throws -> String {
        let file=try FileHandle(forReadingFrom:url);defer {try? file.close()}
        var digest=SHA256()
        while let bytes=try file.read(upToCount:65536),!bytes.isEmpty {digest.update(data:bytes)}
        return digest.finalize().map{String(format:"%02x",$0)}.joined()
    }
    func testPublishedDictionaryConcordanceAndConversationReplay() async throws {
        let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let config=try String(contentsOf:documents.appendingPathComponent("lexical-qa-run.txt"),encoding:.utf8).trimmingCharacters(in:.whitespacesAndNewlines)
        let parts=config.split(whereSeparator:{$0.isWhitespace}).map(String.init)
        guard (1...2).contains(parts.count) else {throw VocabularyPackError.invalid}
        let run=parts[0],fixture=parts.last!
        guard fixture.range(of:"^[0-9]{3}$",options:.regularExpression) != nil,run.range(of:"^[0-9]{3}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        let root=documents.appendingPathComponent("lexical-qualification-"+fixture)
        let manifest=try JSONDecoder().decode(Manifest.self,from:Data(contentsOf:root.appendingPathComponent("manifest.json")))
        XCTAssertEqual(manifest.schema,"vipi-lexical-qualification-1")
        var databases:[String:OpaquePointer]=[:]
        defer {databases.values.forEach{sqlite3_close($0)}}
        for value in manifest.shards {
            guard value.language.range(of:"^[a-z]{2}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
            let file=root.appendingPathComponent(value.language+".sqlite")
            XCTAssertEqual(try file.resourceValues(forKeys:[.fileSizeKey]).fileSize,value.bytes)
            XCTAssertEqual(try sha(file),value.sha256)
            var handle:OpaquePointer?
            guard sqlite3_open_v2(file.path,&handle,SQLITE_OPEN_READONLY|SQLITE_OPEN_NOMUTEX,nil)==SQLITE_OK,let db=handle else {
                if let handle {sqlite3_close(handle)};throw VocabularyPackError.storage
            }
            databases[value.language]=db
        }
        let input=root.appendingPathComponent("cases.json")
        XCTAssertEqual(try sha(input),manifest.cases_sha256)
        let cases=try JSONDecoder().decode([Case].self,from:Data(contentsOf:input))
        let output=documents.appendingPathComponent("lexical-coverage-"+run+".json")
        guard !FileManager.default.fileExists(atPath:output.path) else {throw VocabularyPackError.invalid}
        let catalog=BundledImmersionCatalog()
        var outcomes:[[String:Any]]=[];var failures:[String]=[]
        #if targetEnvironment(simulator)
        let platform="iOS Simulator"
        #else
        let platform="Physical iOS device"
        #endif
        var report:[String:Any] = ["schema":"vipi-lexical-coverage-1","run":run,"fixture":fixture,"manifest_sha256":try sha(root.appendingPathComponent("manifest.json")),
            "platform":platform,"translation_reused":true,"classification_exercised":false,"independent_semantic_acceptance":false]
        func save() throws {
            report["outcomes"]=outcomes
            try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]).write(to:output,options:.atomic)
        }
        for (i,row) in cases.enumerated() {
            let intact=TranslationIntegrity.preservesIdentifiers(original:row.original,translation:row.translation)
            var diagnostic:[String:Int]=[:]
            let start=ContinuousClock.now
            let entries:[VocabularyEntry]
            if intact {
                entries=try LexicalConcordance.entries(leftDB:try XCTUnwrap(databases[row.source]),rightDB:try XCTUnwrap(databases[row.target]),
                    original:row.original,translation:row.translation,source:row.source,target:row.target,diagnostic:{diagnostic[$0,default:0]+=1})
            } else {entries=[]}
            let result=LocalImmersion.align(original:row.original,translation:row.translation,entries:entries,density:1,source:row.source,target:row.target)
            let elapsed=start.duration(to:.now).components
            let previous:ImmersionResult?
            if intact {previous=try await catalog.result(original:row.original,translation:row.translation,pair:.init(source:row.source,target:row.target),density:1)}
            else {previous=nil}
            XCTAssertEqual(result.original,row.original);XCTAssertEqual(result.translation,row.translation)
            XCTAssertEqual(result.speech(source:row.source,target:row.target,revealed:Set(result.spans.map(\.id))).map(\.text).joined(),row.original)
            if ["ar","zh","ja","ko"].contains(row.target) {XCTAssertTrue(result.spans.allSatisfy{$0.romanization != nil})}
            let spans=result.spans.map { span -> [String:Any] in
                ["source":span.original,"target":span.translated,"start":span.range.location,"end":NSMaxRange(span.range),
                 "target_start":span.targetRange.location,"target_end":NSMaxRange(span.targetRange),"reading":span.romanization as Any? ?? NSNull()]
            }
            outcomes.append(["id":row.id,"dataset":row.dataset,"source":row.source,"target":row.target,"spans":spans,
                "baseline_spans":previous?.spans.count ?? 0,"elapsed_ms":Double(elapsed.seconds)*1000+Double(elapsed.attoseconds)/1e15,"identifier_guard":intact,"diagnostics":diagnostic])
            if i%100==0 || row.forbidden_source != nil || row.expected_source != nil {try save()}
            if let source=row.forbidden_source,let target=row.forbidden_target {
                if result.spans.contains(where:{$0.original==source && $0.translated==target}) {failures.append(row.id+": known meaning/scope error")}
            }
            if let source=row.expected_source,let target=row.expected_target {
                if !result.spans.contains(where:{$0.original==source && $0.translated==target}) {failures.append(row.id+": missing required lexical behavior")}
            }
        }
        report["complete"]=true;report["cases"]=cases.count;report["failures"]=failures;report["passed"]=failures.isEmpty;try save()
        XCTAssertTrue(failures.isEmpty,failures.joined(separator:"; "))
    }
}
