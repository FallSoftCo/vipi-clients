import XCTest
import Foundation
import VipiCore
@testable import Vipi

@MainActor final class SourceContextFrameRoutingTests: XCTestCase {
    private struct Owner { let provider: SourceUnitLookup; let trace: () -> [[String:Any]]; let raw: () -> [FrameStarterCandidate] }
    private func encoded(_ x:Any) throws -> Data { try JSONSerialization.data(withJSONObject:x,options:[.sortedKeys]) }
    private enum Failed: Error {case prerequisite}
    private func same(_ a:Data,_ b:Data) throws {XCTAssertEqual(a,b);guard a==b else {throw Failed.prerequisite}}
    private func mode(_ x:SourceAtomicMode)->String {switch x {case .none:return "NONE";case .atomic:return "ATOMIC";case .headBackoff:return "HEAD_BACKOFF";case .ambiguous:return "AMBIGUOUS"}}
    private func range(_ r:NSRange)->[Int] {[r.location,NSMaxRange(r)]}
    private func spans(_ p:ImmersionPresentation?)->[[String:Any]] {(p?.spans ?? []).map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":range($0.range)]}}
    private func evidence(_ e:SourceLookupEvidence)->[String:Any] {
        let p=e.partial.map{ImmersionPresentation.partial($0)}
        let refs:[[String:Any]]=(e.partial?.references ?? []).map{["scope":range($0.range),"original":$0.original,"target":$0.translated,"reading":$0.reading as Any? ?? NSNull(),"reference":$0.referenceID,"pack_sha":$0.catalogSHA256,"cost":$0.nativeSourceTokens,"concept_id":$0.conceptID as Any? ?? NSNull(),"output_id":$0.outputID as Any? ?? NSNull()]}
        let masks:[[String:Any]]=e.recognitions.map{r in ["rule":r.ruleID,"record_sha":r.recordSHA256,"context":range(r.context),"mask":r.mask.map(range) as Any? ?? NSNull(),"mode":mode(r.mode),"approved":r.approvedOutputs.map{["id":$0.outputID,"scope":range($0.range)]}]}
        return ["original":e.original,"source":e.source,"target":e.target,"identity":e.catalogIdentity,"spans":spans(p),"references":refs,"recognitions":masks]
    }
    private func mixed(_ p:ImmersionPresentation?,_ original:String)->String {
        var result=original;for s in (p?.spans ?? []).reversed(){result=(result as NSString).replacingCharacters(in:s.range,with:s.romanization ?? s.translated)};return result
    }
    func testFrozenFrameComparison() async throws {
        guard let path=ProcessInfo.processInfo.environment["VIPI_SOURCE_FRAMES_QA"] else {throw XCTSkip("Private opt-in source-frame qualification")}
        let root=URL(fileURLWithPath:path)
        func read(_ name:String)throws->Data {try Data(contentsOf:root.appendingPathComponent(name))}
        func json(_ name:String)throws->[String:Any] {try XCTUnwrap(JSONSerialization.jsonObject(with:read(name)) as? [String:Any])}
        let manifest=try json("manifest.json"),files=try XCTUnwrap(manifest["files"] as? [String:String])
        for(n,h) in files {let actual=try JapaneseStarterLookup.digest(read(n));XCTAssertEqual(actual,h);guard actual==h else {throw Failed.prerequisite}}
        let previous=try String(decoding:read("prior-apple-output.jsonl"),as:UTF8.self).split(separator:"\n").map{try XCTUnwrap(JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any])};guard previous.count==656 else {throw Failed.prerequisite}
        let cases=try json("cases.json"),baseline=try json("baseline-cases.json"),packs=try XCTUnwrap(manifest["packs"] as? [String:[String:String]])
        let baselinePairs=try XCTUnwrap(baseline["pairs"] as? [String:[[String:Any]]]),baselineStates=try XCTUnwrap(baseline["states"] as? [String:[[String:Any]]])
        func owner(_ target:String,_ reference:Bool=false)throws->Owner {
            let spec=try XCTUnwrap(packs[target]);let bytes=try read(XCTUnwrap(spec["pack"])),meta=try read(XCTUnwrap(spec["manifest"]))
            if reference {
                if target=="ja" {let x=try ReferenceJapaneseStarterLookup(data:bytes,manifest:meta,packMultiple:true);return Owner(provider:x.provider(),trace:{x.trace},raw:{[]})}
                let x=try ReferenceSwahiliStarterLookup(data:bytes,manifest:meta,packMultiple:true);return Owner(provider:x.provider(),trace:{x.trace},raw:{[]})
            }
            if target=="ja" {let x=try JapaneseStarterLookup(data:bytes,manifest:meta,packMultiple:true);return Owner(provider:x.provider(),trace:{x.trace},raw:{x.rawCandidates})}
            let x=try SwahiliStarterLookup(data:bytes,manifest:meta,packMultiple:true);return Owner(provider:x.provider(),trace:{x.trace},raw:{x.rawCandidates})
        }
        let started=ProcessInfo.processInfo.systemUptime;var parity=0,geometry=0,rows=0;var mechanisms:[[String:Any]]=[]
        let output=root.appendingPathComponent("frame-output.jsonl");XCTAssertFalse(FileManager.default.fileExists(atPath:output.path));FileManager.default.createFile(atPath:output.path,contents:nil)
        let handle=try FileHandle(forWritingTo:output);defer{try? handle.close()}
        func write(_ value:Any)throws {
            let bytes=try encoded(value)+Data([10]);try handle.write(contentsOf:bytes)
            guard try handle.offset()<=32*1024*1024,ProcessInfo.processInfo.systemUptime-started<300 else {throw Failed.prerequisite}
        }
        for target in ["ja","sw"] {for state in try XCTUnwrap(baselineStates["en-"+target]) {
            let known=Set(try XCTUnwrap(state["known_ids"] as? [String])),x=try owner(target),ref=try owner(target,true)
            for c in try XCTUnwrap(baselinePairs["en-"+target]) {for d in [0.25,0.75] {
                let text=try XCTUnwrap(c["source"] as? String),request=SourceUnitLookup.Context(original:text,pair:.init(source:"en",target:target),density:d,knownConceptIDs:known)
                let a=try await ref.provider.resolve(request),b=try await x.provider.resolve(request)
                try same(encoded(evidence(a)),encoded(evidence(b)));try same(encoded(ref.trace()),encoded(x.trace()));parity+=1
            }}
        }}
        XCTAssertEqual(parity,1536);guard parity==1536 else {throw Failed.prerequisite}
        try encoded(["comparisons":parity,"all_fields_equal":true]).write(to:root.appendingPathComponent("frame-baseline-parity.json"))
        for target in ["ja","sw"] {
            let spec=try XCTUnwrap(packs[target]),pack=try json(XCTUnwrap(spec["pack"])),frameBytes=try read(XCTUnwrap(spec["patterns"])),proposal=try read("permission-proposal.json")
            let framePack=try JSONDecoder().decode(FrameContextAdapter.Pack.self,from:frameBytes)
            let empty=try owner(target),g=try FrameContextAdapter(bytes:frameBytes,permissionBytes:proposal,target:target,baselineIdentity:empty.provider.identity)
            for p in framePack.patterns {for v in p.variants {
                let hits=try g.geometry(v.context)
                let qualified=hits.contains{($0["pattern_id"] as? String)==p.id && $0["reason"] is NSNull && ($0["focus"] as? [Int])==v.focus_utf16};XCTAssertTrue(qualified);guard qualified else {throw Failed.prerequisite};geometry+=1
            }}
            let mechanismSource="Need a phone charger.",focus=NSRange(location:7,length:13)
            let mechanismBase=try await empty.provider.resolve(.init(original:mechanismSource,pair:.init(source:"en",target:target),density:0.75,knownConceptIDs:[]))
            let everyFrame=Set(framePack.patterns.map(\.concept_id))
            let withheld=try g.resolve(original:mechanismSource,density:0.75,known:everyFrame,baseline:mechanismBase,raw:empty.raw())
            let knownPass = !(withheld.partial?.spans.contains{NSIntersectionRange($0.range,focus).length>0} ?? false) && withheld.recognitions.contains{$0.mask.map{NSIntersectionRange($0,focus)==focus} == true}
            XCTAssertTrue(knownPass);guard knownPass else {throw Failed.prerequisite}
            let all=NSRange(location:0,length:mechanismSource.utf16.count)
            let protected=SourceLookupEvidence(original:mechanismSource,source:"en",target:target,catalogIdentity:empty.provider.identity,partial:nil,recognitions:[.init(ruleID:"caller-protection",recordSHA256:JapaneseStarterLookup.digest(frameBytes),context:all,mask:all,mode:.ambiguous,approvedOutputs:[])])
            let blocked=try g.resolve(original:mechanismSource,density:0.75,known:[],baseline:protected,raw:[])
            XCTAssertNil(blocked.partial);guard blocked.partial==nil else {throw Failed.prerequisite}
            let atomic=SourceLookupEvidence(original:mechanismSource,source:"en",target:target,catalogIdentity:empty.provider.identity,partial:nil,recognitions:[.init(ruleID:"caller-atomic",recordSHA256:JapaneseStarterLookup.digest(frameBytes),context:all,mask:all,mode:.atomic,approvedOutputs:[])])
            let atomicResult=try g.resolve(original:mechanismSource,density:0.75,known:[],baseline:atomic,raw:[])
            let atomicPass=atomicResult.partial==nil && atomicResult.recognitions.contains{$0.ruleID=="caller-atomic" && $0.mode == .atomic && $0.mask==all}
            XCTAssertTrue(atomicPass);guard atomicPass else {throw Failed.prerequisite}
            let repeated=String(repeating:"I need help. ",count:140)
            let repeatBase=try await empty.provider.resolve(.init(original:repeated,pair:.init(source:"en",target:target),density:0.75,knownConceptIDs:[]))
            let repeatResult=try g.resolve(original:repeated,density:0.75,known:[],baseline:repeatBase,raw:empty.raw())
            XCTAssertEqual(repeatResult.partial?.spans.count,128);guard repeatResult.partial?.spans.count==128 else {throw Failed.prerequisite}
            mechanisms.append(["pair":"en-"+target,"known_withheld":evidence(withheld),"protected":evidence(blocked),"atomic":evidence(atomicResult),"cap":evidence(repeatResult)])
            for state in ["none","current_starter_concepts_excluded"] {
                let entries=try XCTUnwrap(pack["entries"] as? [[String:Any]])
                let known=state=="none" ? Set<String>() : Set(try entries.map{try XCTUnwrap($0["concept_id"] as? String)})
                let x=try owner(target),ref=try owner(target,true),adapter=try FrameContextAdapter(bytes:frameBytes,permissionBytes:proposal,target:target,baselineIdentity:x.provider.identity)
                let routingIdentity=adapter.identity+":reference-first-v1"
                let catalogStart=ProcessInfo.processInfo.systemUptime,referenceCatalog=BundledImmersionCatalog()
                let catalogSetupMs=(ProcessInfo.processInfo.systemUptime-catalogStart)*1000
                var referenceCalls=0,branch="not_invoked";var referenceMs:Double?;var referenceFirst=false
                let provider=SourceUnitLookup(identity:routingIdentity){request in
                    let b=try await x.provider.resolve(request)
                    let start=ProcessInfo.processInfo.systemUptime
                    let reference=try await referenceCatalog.reference(original:request.original,pair:request.pair)
                    referenceMs=(ProcessInfo.processInfo.systemUptime-start)*1000;referenceFirst=referenceCalls==0;referenceCalls+=1
                    branch=reference != nil ? "existing_forward_reference_baseline_evidence" : "reference_miss_frame_evidence"
                    let value:SourceLookupEvidence
                    if reference != nil {value=b} else {value=try adapter.resolve(original:request.original,density:request.density,known:request.knownConceptIDs,baseline:b,raw:x.raw())}
                    return SourceLookupEvidence(original:value.original,source:value.source,target:value.target,catalogIdentity:routingIdentity,partial:value.partial,recognitions:value.recognitions)
                }
                for c in try XCTUnwrap(cases["cases"] as? [[String:Any]]) where c["pair"] as? String=="en-"+target {
                    let id=try XCTUnwrap(c["id"] as? String),text=try XCTUnwrap(c["source"] as? String)
                    let densities=([0.25,0.75]+(["control-32","control-33"].contains(id) ? [0,0.05] : [])).sorted()
                    for d in densities {
                        let request=SourceUnitLookup.Context(original:text,pair:.init(source:"en",target:target),density:d,knownConceptIDs:known)
                        let a=try await ref.provider.resolve(request),b=try await x.provider.resolve(request)
                        try same(encoded(evidence(a)),encoded(evidence(b)));try same(encoded(ref.trace()),encoded(x.trace()))
                        let raw=x.trace(),directStart=ProcessInfo.processInfo.systemUptime
                        let candidate=try adapter.resolve(original:text,density:d,known:known,baseline:b,raw:x.raw()),directMs=(ProcessInfo.processInfo.systemUptime-directStart)*1000,frameTrace=adapter.trace
                        let prior=try XCTUnwrap(previous.first{($0["pair"] as? String)=="en-"+target && ($0["id"] as? String)==id && ($0["state"] as? String)==state && ($0["density"] as? Double)==d})
                        try same(encoded(XCTUnwrap(prior["baseline"])),encoded(evidence(b)));try same(encoded(XCTUnwrap(prior["candidate"])),encoded(evidence(candidate)));try same(encoded(XCTUnwrap(prior["starter_trace"])),encoded(raw));try same(encoded(XCTUnwrap(prior["frame_trace"])),encoded(frameTrace))
                        if id=="control-32" && [0,0.05,0.25].contains(d) {
                            let f=NSRange(location:7,length:13)
                            let pass = !(candidate.partial?.spans.contains{NSIntersectionRange($0.range,f).length>0} ?? false) && candidate.recognitions.contains{$0.mask.map{NSIntersectionRange($0,f)==f} == true}
                            XCTAssertTrue(pass);guard pass else {throw Failed.prerequisite}
                        }
                        if id.hasPrefix("context-literal-") {let pass = !(candidate.partial?.references.contains{$0.referenceID.hasPrefix("frame:")} ?? false);XCTAssertTrue(pass);guard pass else {throw Failed.prerequisite}}
                        branch="not_invoked";referenceMs=nil;referenceFirst=false
                        var route:[String:Any]=[:];var timing:[String:Any]=["direct_resolve_ms":directMs,"reference_catalog_constructor_ms":catalogSetupMs,"fresh_engine_per_route":true]
                        for (arm,p) in [("baseline",x.provider),("candidate",provider)] {
                            let setupStart=ProcessInfo.processInfo.systemUptime
                            let engine=ConversationImmersion(modelStatus:{_ in .unsupported},sourceUnits:p)
                            await engine.configure(pair:.init(source:"en",target:target),density:d,knownConceptIDs:known)
                            let message=state+"/"+id+"/"+String(d)+"/"+arm;engine.selectInputLanguage("en",for:message)
                            let setupMs=(ProcessInfo.processInfo.systemUptime-setupStart)*1000,callStart=ProcessInfo.processInfo.systemUptime
                            let value=await engine.result(for:text,inputLanguage:"en",messageID:message);timing[arm+"_setup_ms"]=setupMs;timing[arm+"_result_ms"]=(ProcessInfo.processInfo.systemUptime-callStart)*1000;XCTAssertEqual(engine.lastOutcome?.localTranslationCalls,0)
                            route[arm]=["spans":spans(value),"mixed":mixed(value,text),"origin":engine.lastOutcome?.origin?.rawValue as Any? ?? NSNull()];engine.close()
                        }
                        let priorRoute=try XCTUnwrap(prior["route"] as? [String:Any])
                        try same(encoded(XCTUnwrap(priorRoute["baseline"])),encoded(XCTUnwrap(route["baseline"])))
                        if branch=="existing_forward_reference_baseline_evidence" {try same(encoded(XCTUnwrap(route["baseline"])),encoded(XCTUnwrap(route["candidate"])))}
                        else {try same(encoded(XCTUnwrap(priorRoute["candidate"])),encoded(XCTUnwrap(route["candidate"])))}
                        timing["reference_lookup_ms"]=referenceMs as Any? ?? NSNull();timing["first_reference_lookup_for_pair_state"]=referenceFirst
                        try write(["routing_branch":branch,"timing":timing,"pair":"en-"+target,"id":id,"source":text,"state":state,"known_ids":known.sorted(),"density":d,"native_words":LocalImmersion.words(text,language:"en").map(range),"baseline":evidence(b),"candidate":evidence(candidate),"starter_trace":raw,"frame_trace":frameTrace,"route":route]);rows+=1
                    }
                }
            }
        }
        XCTAssertEqual(geometry,780);XCTAssertEqual(rows,656);guard geometry==780,rows==656 else {throw Failed.prerequisite}
        try encoded(mechanisms).write(to:root.appendingPathComponent("frame-mechanisms.json"))
        let status=try encoded(["complete":true,"rows":rows,"baseline_comparisons":parity,"geometry_variants":geometry,"seconds":ProcessInfo.processInfo.systemUptime-started])
        try status.write(to:root.appendingPathComponent("frame-status.json"));try handle.synchronize()
        for name in ["frame-output.jsonl","frame-baseline-parity.json","frame-status.json","frame-mechanisms.json"] {let a=XCTAttachment(data:try read(name),uniformTypeIdentifier:"public.json");a.name=name;a.lifetime = .keepAlways;add(a)}
    }
}
