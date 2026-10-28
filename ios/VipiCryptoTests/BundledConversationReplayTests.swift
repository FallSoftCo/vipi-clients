import Foundation
import CryptoKit
import VipiCore
import XCTest
@testable import Vipi

/// Small development cohort through the app's selected-pair data path.
/// Reused translations are not a translator-accuracy or population-coverage claim.
final class BundledConversationReplayTests:XCTestCase {
    private struct Row:Decodable {
        let id,dataset,source,target,original,translation:String
        let forbidden_source,forbidden_target,expected_source,expected_target:String?
        let forbidden_source_start:Int?
    }
    func testSelectedPairConversationReplay() async throws {
        let fm=FileManager.default
        let documents=fm.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let config=try String(contentsOf:documents.appendingPathComponent("bundled-conversation-run.txt"),encoding:.utf8)
            .split(whereSeparator:{$0.isWhitespace}).map(String.init)
        guard config.count==2,config[0].range(of:"^[0-9]{3}$",options:.regularExpression) != nil,
              config[1].range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        let run=config[0]
        let data=try Data(contentsOf:documents.appendingPathComponent("bundled-conversation-cases.json"))
        XCTAssertEqual(SHA256.hash(data: data).map{String(format:"%02x",$0)}.joined(),config[1])
        let rows=try JSONDecoder().decode([Row].self,from:data).sorted{
            [$0.source,$0.target].sorted().joined(separator:"-") < [$1.source,$1.target].sorted().joined(separator:"-")
        }
        let output=documents.appendingPathComponent("bundled-conversations-"+run+".json")
        let root=fm.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("bundled-conversation-replay-"+run)
        guard !fm.fileExists(atPath:output.path),!fm.fileExists(atPath:root.path) else {throw VocabularyPackError.invalid}
        defer {try? fm.removeItem(at:root)}
        let lexical=BundledLexicalCatalog(root:root)
        let starter=BundledImmersionCatalog()
        var outcomes:[[String:Any]]=[],failures:[String]=[],preparation:[[String:Any]]=[]
        var lastPair=""
        func spans(_ result:ImmersionResult)->[[String:Any]] {
            result.spans.map{["source":$0.original,"target":$0.translated,
                "start":$0.range.location,"end":NSMaxRange($0.range),
                "target_start":$0.targetRange.location,"target_end":NSMaxRange($0.targetRange),
                "reading":$0.romanization as Any? ?? NSNull()]}
        }
        #if targetEnvironment(simulator)
        let platform = "iOS simulator"
        #else
        let platform = "physical iOS device"
        #endif
        func save(_ complete:Bool) throws {
            let report:[String:Any]=["schema":"vipi-bundled-conversation-replay-1","run":run,
                "complete":complete,"cases_sha256":config[1],"platform":platform,
                "translation_reused":true,"population_coverage_claim":false,
                "independent_semantic_acceptance":false,"failures":failures,
                "pair_preparation":preparation,"outcomes":outcomes]
            try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]).write(to:output,options:.atomic)
        }
        for row in rows {
            let pair=TranslationPair(source:row.source,target:row.target)
            let key=[row.source,row.target].sorted().joined(separator:"-")
            if key != lastPair {
                if fm.fileExists(atPath:root.path) {try fm.removeItem(at:root)}
                let start=Date()
                let ready=try await lexical.prepare(pair)
                XCTAssertTrue(ready)
                let files=try fm.contentsOfDirectory(at:root,includingPropertiesForKeys:[.fileSizeKey])
                let bytes=try files.reduce(0){try $0 + ($1.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0)}
                preparation.append(["pair":key,"elapsed_ms":-start.timeIntervalSinceNow*1000,"expanded_bytes":bytes])
                lastPair=key
            }
            let start=Date()
            let entries=try await lexical.entries(original:row.original,translation:row.translation,pair:pair)
            let result=try await starter.result(original:row.original,translation:row.translation,pair:pair,density:1,supplementalEntries:entries)
            let elapsed = -start.timeIntervalSinceNow*1000
            let previous=try await starter.result(original:row.original,translation:row.translation,pair:pair,density:1)
            let retained=previous.spans.allSatisfy{result.spans.contains($0)}
            if !retained {failures.append(row.id+": lost starter span")}
            if let source=row.forbidden_source,let target=row.forbidden_target,
                result.spans.contains(where:{$0.original==source && $0.translated==target &&
                    (row.forbidden_source_start==nil || row.forbidden_source_start==$0.range.location)}) {
                failures.append(row.id+": known meaning/scope error")
            }
            if let source=row.expected_source,let target=row.expected_target,
                !result.spans.contains(where:{$0.original==source && $0.translated==target}) {
                failures.append(row.id+": missing retained mapping")
            }
            XCTAssertEqual(result.original,row.original)
            XCTAssertEqual(result.speech(source:row.source,target:row.target,revealed:Set(result.spans.map(\.id))).map(\.text).joined(),row.original)
            if ["ar","zh","ja","ko"].contains(row.target) {XCTAssertTrue(result.spans.allSatisfy{!($0.romanization ?? "").isEmpty})}
            outcomes.append(["id":row.id,"dataset":row.dataset,"source":row.source,"target":row.target,
                "original":row.original,"translation":row.translation,"baseline_spans":spans(previous),
                "combined_spans":spans(result),"elapsed_ms":elapsed,"baseline_retained":retained])
            if outcomes.count%10==0 {try save(false)}
        }
        try save(true)
        XCTAssertTrue(failures.isEmpty,failures.joined(separator:"; "))
    }
}
