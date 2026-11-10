import Foundation
import VipiCore

struct FrameStarterCandidate {
    let entryID, conceptID, category: String
    let rank, tokenCount: Int
    let range: NSRange
    let cost: Int
    let reason: String?
    let unit: SourceReferenceUnit
}
/// Private qualification overlay only; no bundled/default factory uses this type.
@MainActor final class FrameContextAdapter {
    struct Variant: Decodable { let context: String; let focus_utf16: [Int] }
    struct Pattern: Decodable {
        let id, pair, source, target, reading, meaning, concept_id: String
        let source_only_permission: Bool
        let variants: [Variant]
    }
    struct Pack: Decodable { let schema, source, target: String; let runtime_enabled: Bool; let patterns: [Pattern] }
    struct Permission: Decodable { let purpose: String; let runtime_enabled: Bool; let pack_sha256: [String:String]; let pattern_ids: [String] }
    enum Invalid: Error { case evidence }
    let identity: String
    private let pack: Pack, packSHA: String, target: String, allowed: Set<String>
    private let baselineIdentity: String
    private(set) var trace: [[String:Any]] = []
    init(bytes: Data, permissionBytes: Data, target: String, baselineIdentity: String) throws {
        pack = try JSONDecoder().decode(Pack.self, from: bytes)
        let permission = try JSONDecoder().decode(Permission.self, from: permissionBytes)
        packSHA = JapaneseStarterLookup.digest(bytes); self.target = target; self.baselineIdentity = baselineIdentity; allowed = Set(permission.pattern_ids)
        identity = "frame-test-v1:" + JapaneseStarterLookup.digest(Data((packSHA + JapaneseStarterLookup.digest(permissionBytes) + baselineIdentity).utf8))
        guard pack.schema == "vipi-source-context-candidate-1", pack.source == "en", pack.target == target, !pack.runtime_enabled,
              permission.purpose == "test_only_source_permission_proposal", !permission.runtime_enabled,
              permission.pack_sha256["en-"+target] == packSHA, (1...256).contains(pack.patterns.count),
              Set(pack.patterns.map(\.id)).count == pack.patterns.count,
              pack.patterns.allSatisfy({ !$0.source_only_permission && allowed.contains($0.id) }) else { throw Invalid.evidence }
    }
    private final class Hit {
        let pattern: Pattern, context: NSRange, focus: NSRange, contextCost: Int, cost: Int, id: String
        var reason: String?
        init(_ p:Pattern,_ c:NSRange,_ f:NSRange,_ cc:Int,_ cost:Int,_ id:String,_ reason:String?) { pattern=p;context=c;focus=f;contextCost=cc;self.cost=cost;self.id=id;self.reason=reason }
    }
    private func overlap(_ a:NSRange,_ b:NSRange)->Bool { NSIntersectionRange(a,b).length > 0 }
    private func union(_ ranges:[NSRange])->NSRange { let lo=ranges.map(\.location).min()!;return NSRange(location:lo,length:ranges.map(NSMaxRange).max()!-lo) }
    private func contains(_ outer:NSRange,_ inner:NSRange)->Bool { inner.location >= outer.location && NSMaxRange(inner) <= NSMaxRange(outer) }
    private func matches(_ original:String) throws -> [Hit] {
        let text=original as NSString;let native=LocalImmersion.words(original,language:"en")
        guard let basis=NativeSourceTokenBasis(original:original,wordRanges:native) else { throw Invalid.evidence }
        var hits:[Hit]=[];var seen=Set<String>()
        func cost(_ range:NSRange)->Int? {
            let touched=native.filter{overlap($0,range)}
            guard touched.first?.location == range.location,touched.last.map(NSMaxRange) == NSMaxRange(range) else {return nil}
            return basis.cost(for:range)
        }
        for p in pack.patterns {
            guard (1...1024).contains(p.variants.count) else {throw Invalid.evidence}
            for v in p.variants {
                guard !v.context.isEmpty,v.context.utf16.count<=256,v.focus_utf16.count==2 else {throw Invalid.evidence}
                var from=0
                while from<=text.length-v.context.utf16.count {
                    let context=text.range(of:v.context,options:[],range:NSRange(location:from,length:text.length-from))
                    if context.location==NSNotFound {break};from=context.location+1
                    let focus=NSRange(location:context.location+v.focus_utf16[0],length:v.focus_utf16[1]-v.focus_utf16[0])
                    guard contains(context,focus),Range(focus,in:original) != nil,text.substring(with:focus)==p.source else {throw Invalid.evidence}
                    let id=p.id+"@\(context.location):\(NSMaxRange(context)):\(focus.location):\(NSMaxRange(focus))"
                    if !seen.insert(id).inserted {continue}
                    let cc=cost(context),fc=cost(focus)
                    let reason:String? = cc == nil || fc == nil ? "partial_native_word" : (v.context.contains(where:{".!?。！？;；\r\n".contains($0)}) ? "context_barrier" : nil)
                    hits.append(Hit(p,context,focus,cc ?? 0,fc ?? 0,id,reason));guard hits.count<=4096 else {throw Invalid.evidence}
                }
            }
        }
        return hits
    }
    func geometry(_ original:String) throws -> [[String:Any]] {
        try matches(original).map{["pattern_id":$0.pattern.id,"context":[$0.context.location,NSMaxRange($0.context)],"focus":[$0.focus.location,NSMaxRange($0.focus)],"reason":$0.reason as Any? ?? NSNull()]}
    }
    func resolve(original:String,density:Double,known:Set<String>,baseline:SourceLookupEvidence,raw:[FrameStarterCandidate]) throws -> SourceLookupEvidence {
        guard !original.isEmpty,original.utf16.count<=16384,density.isFinite,(0...0.75).contains(density),
              baseline.catalogIdentity == baselineIdentity, baseline.validated(text:original,sourceLanguage:"en",targetLanguage:target,identity:baseline.catalogIdentity) != nil else {throw Invalid.evidence}
        trace=[];let text=original as NSString;let native=LocalImmersion.words(original,language:"en")
        let budget=density>0 ? max(1,Int(Double(native.count)*density)) : 0
        let literalRanges=TranslationIntegrity.qaLiteralRanges(original)
        let hits=try matches(original);let presentationReasons:Set<String>=["caller_known_concept","native_density_budget","unchanged_normalized_face"]
        for h in hits where h.reason == nil {
            if literalRanges.contains(where:{overlap($0,h.context)}) || baseline.recognitions.contains(where:{($0.mode == .ambiguous || $0.mode == .atomic) && $0.mask.map{overlap($0,h.context)} == true}) {h.reason="existing_source_mask"}
            else if raw.contains(where:{overlap($0.range,h.focus) && $0.reason != nil && !presentationReasons.contains($0.reason!)}) {h.reason="existing_starter_source_guard"}
            else if !TranslationIntegrity.preservesIdentifiers(original:original,translation:text.replacingCharacters(in:h.focus,with:h.pattern.target)) {h.reason="full_message_literal_integrity"}
            else if !allowed.contains(h.pattern.id) {h.reason="source_permission_absent"}
            else if h.pattern.source == h.pattern.target {h.reason="unchanged_face"}
            else if known.contains(h.pattern.concept_id) {h.reason="caller_known_concept"}
            else if h.cost>budget {h.reason="native_density_budget"}
        }
        func stronger(_ a:Hit,_ b:Hit)->Bool {
            if a.contextCost != b.contextCost {return a.contextCost>b.contextCost}
            if a.context.length != b.context.length {return a.context.length>b.context.length}
            if a.cost != b.cost {return a.cost>b.cost}
            if a.focus.location != b.focus.location {return a.focus.location<b.focus.location}
            return a.id<b.id
        }
        var groups:[[Hit]]=[]
        for h in hits.filter({ !["partial_native_word","context_barrier"].contains($0.reason ?? "") }).sorted(by:{($0.focus.location,NSMaxRange($0.focus))<($1.focus.location,NSMaxRange($1.focus))}) {
            if let last=groups.last,h.focus.location<last.map({NSMaxRange($0.focus)}).max()! {groups[groups.count-1].append(h)}else{groups.append([h])}
        }
        var frameUnits:[(Hit,SourceReferenceUnit)]=[];var frameRecognitions:[SourceRecognition]=[]
        for (n,g) in groups.enumerated() {
            let ordered=g.sorted(by:stronger),best=ordered[0]
            let top=ordered.filter{$0.contextCost==best.contextCost && $0.context.length==best.context.length && $0.cost==best.cost}
            let choices=Set(top.map{[String($0.focus.location),String(NSMaxRange($0.focus)),$0.pattern.meaning,$0.pattern.target,$0.pattern.reading]})
            let ambiguous=choices.count != 1
            for h in g where !top.contains(where:{$0 === h}) && h.reason == nil {h.reason="stronger_context_recognized"}
            if ambiguous {for h in top {h.reason="competing_strongest_contexts"}}
            let approved:[SourceApprovedOutput] = !ambiguous && best.reason == nil ? [.init(outputID:best.id,range:best.focus)] : []
            if !approved.isEmpty {frameUnits.append((best,.init(range:best.focus,original:text.substring(with:best.focus),translated:best.pattern.target,reading:best.pattern.reading.isEmpty ? nil : best.pattern.reading,referenceID:"frame:"+packSHA+":"+best.pattern.id,catalogSHA256:packSHA,nativeSourceTokens:best.cost,conceptID:best.pattern.concept_id,outputID:best.id)))}
            frameRecognitions.append(.init(ruleID:"frame-group-\(n)",recordSHA256:JapaneseStarterLookup.digest(Data(g.map(\.id).sorted().joined(separator:"\0").utf8)),context:union(g.map(\.context)),mask:union(g.map(\.focus)),mode:ambiguous ? .ambiguous : .headBackoff,approvedOutputs:approved))
        }
        trace=hits.map{["pattern_id":$0.pattern.id,"output_id":$0.id,"context":[$0.context.location,NSMaxRange($0.context)],"focus":[$0.focus.location,NSMaxRange($0.focus)],"reason":$0.reason as Any? ?? NSNull()]}
        let masks=frameRecognitions.compactMap(\.mask)
        let ordinary=raw.filter{c in c.reason==nil && !masks.contains(where:{overlap($0,c.range)})}.sorted {
            if ($0.category=="content") != ($1.category=="content") {return $0.category=="content"}
            if $0.rank != $1.rank {return $0.rank<$1.rank}
            if $0.tokenCount != $1.tokenCount {return $0.tokenCount>$1.tokenCount}
            return $0.range.location<$1.range.location
        }
        let fixed=baseline.recognitions.filter{$0.mode != .headBackoff}+frameRecognitions.filter{$0.mode != .headBackoff}+literalRanges.enumerated().map{n,r in SourceRecognition(ruleID:"native-literal-\(n)",recordSHA256:packSHA,context:r,mask:r,mode:.ambiguous,approvedOutputs:[])}
        let candidates=(frameUnits.sorted{stronger($0.0,$1.0)}.map{$0.1}+ordinary.map(\.unit)).filter{u in fixed.allSatisfy{n in n.mask.map{overlap($0,u.range)} != true || (n.mode != .ambiguous && n.approvedOutputs.contains{$0.outputID==u.outputID && $0.range==u.range})}}

        var chosen:[SourceReferenceUnit]=[];var used=0
        for u in candidates {if chosen.count>=128 {break};if used+u.nativeSourceTokens>budget || chosen.contains(where:{overlap($0.range,u.range)}) {continue};chosen.append(u);used+=u.nativeSourceTokens}
        let nodes=(baseline.recognitions+frameRecognitions).filter{$0.mode == .headBackoff}.sorted{(($0.mask ?? $0.context).location,NSMaxRange($0.mask ?? $0.context)) < (($1.mask ?? $1.context).location,NSMaxRange($1.mask ?? $1.context))}
        var merged:[[SourceRecognition]]=[]
        for n in nodes {let range=n.mask ?? n.context;if let last=merged.last,range.location<last.map({NSMaxRange($0.mask ?? $0.context)}).max()! {merged[merged.count-1].append(n)}else{merged.append([n])}}
        let recognitions=merged.enumerated().map{n,g -> SourceRecognition in
            let mask=union(g.compactMap(\.mask)),ambiguous=g.contains{$0.mode == .ambiguous},context=union(g.map(\.context))
            let permitted:[SourceApprovedOutput] = ambiguous ? [] : candidates.filter{contains(mask,$0.range)}.map{.init(outputID:$0.outputID!,range:$0.range)}
            return .init(ruleID:"merged-\(n)",recordSHA256:JapaneseStarterLookup.digest(Data(g.map(\.recordSHA256).sorted().joined().utf8)),context:context,mask:mask,mode:ambiguous ? .ambiguous : .headBackoff,approvedOutputs:permitted)
        }
        let partial=SourceReferencePresentation.create(original:original,target:target,units:chosen.sorted{$0.range.location<$1.range.location},density:density,nativeSourceTokenCount:native.count)
        let result=SourceLookupEvidence(original:original,source:"en",target:target,catalogIdentity:identity,partial:partial,recognitions:recognitions+fixed)
        guard let constraints=result.validated(text:original,sourceLanguage:"en",targetLanguage:target,identity:identity) else {throw Invalid.evidence}
        if let partial {guard constraints.filterPartial(partial)==partial else {throw Invalid.evidence}}
        return result
    }
}
