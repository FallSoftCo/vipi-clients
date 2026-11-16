import Foundation
import VipiCore

struct SourceFrameStarterCandidate {
    let entryID, conceptID, category: String
    let rank, tokenCount: Int
    let range: NSRange
    let cost: Int
    let reason: String?
    let unit: SourceReferenceUnit
}
/// Finite reviewed source contexts, composed after existing full-reference priority.
@MainActor final class SourceFrameLookup {
    struct Variant: Decodable {
        let context: String
        let focus_utf16: [Int]
        let context_scope: String?
        let right_boundary: String?
        let carrier_utf16: [Int]?
        let carrier_rule: String?
    }
    struct Pattern: Decodable {
        let id, pair, source, target, reading, meaning, concept_id: String
        let source_only_permission: Bool
        let variants: [Variant]
    }
    struct Pack: Decodable {
        let schema, version, source, target, policy, approval_sha256: String
        let patterns: [Pattern]
    }
    struct Manifest: Decodable {
        let schema, file, sha256, version, source, target, policy: String
        let bytes, patterns: Int
    }
    enum Invalid: Error { case evidence }
    static let languages: Set<String> = ["en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw"]
    // Previously qualified en→ja/sw frames only; candidate packs are never auto-loaded.
    static let promotionEnabled = true
    let identity: String
    private let pack: Pack, packSHA: String, source: String, target: String, allowed: Set<String>
    private let baselineIdentity: String
    private(set) var trace: [[String:Any]] = []

    init(bytes: Data, manifestBytes: Data, target: String, baselineIdentity: String, source: String = "en") throws {
        guard bytes.count <= 1_048_576, manifestBytes.count <= 8_192,
              Self.languages.contains(source), Self.languages.contains(target), source != target else { throw Invalid.evidence }
        let manifest = try JSONDecoder().decode(Manifest.self, from: manifestBytes)
        pack = try JSONDecoder().decode(Pack.self, from: bytes)
        packSHA = JapaneseStarterLookup.digest(bytes)
        self.source = source
        self.target = target
        self.baselineIdentity = baselineIdentity
        allowed = Set(pack.patterns.map(\.id))
        identity = "source-frames-v1:" + JapaneseStarterLookup.digest(Data(
            (packSHA + JapaneseStarterLookup.digest(manifestBytes) + baselineIdentity).utf8))
        guard manifest.schema == "vipi-source-frame-manifest-1",
              manifest.file.range(of: "^source-frames-" + source + "-" + target + "-[0-9]{3}\\.json$", options: .regularExpression) != nil,
              manifest.sha256 == packSHA, manifest.bytes == bytes.count,
              manifest.version == pack.version, manifest.patterns == pack.patterns.count,
              manifest.source == source, manifest.target == target,
              manifest.policy == "reference-first-source-frames-1",
              pack.schema == "vipi-source-frame-pack-1", pack.source == source, pack.target == target,
              pack.policy == manifest.policy,
              pack.approval_sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
              (1...256).contains(pack.patterns.count), allowed.count == pack.patterns.count else { throw Invalid.evidence }
        for pattern in pack.patterns {
            guard pattern.source_only_permission, pattern.pair == source + "-" + target,
                  !pattern.id.isEmpty, !pattern.source.isEmpty, !pattern.target.isEmpty,
                  !pattern.meaning.isEmpty, !pattern.concept_id.isEmpty,
                  !["ar", "zh", "ja", "ko"].contains(target) || !pattern.reading.isEmpty,
                  (1...1024).contains(pattern.variants.count) else { throw Invalid.evidence }
            for variant in pattern.variants {
                let text = variant.context as NSString
                guard variant.context_scope == nil || variant.context_scope == "local_phrase" || variant.context_scope == "whole_sentence",
                      variant.right_boundary == nil || variant.right_boundary == "clause_or_end",
                      (1...256).contains(text.length), variant.focus_utf16.count == 2,
                      variant.focus_utf16[0] >= 0,
                      variant.focus_utf16[1] > variant.focus_utf16[0],
                      variant.focus_utf16[1] <= text.length else { throw Invalid.evidence }
                let range = NSRange(location: variant.focus_utf16[0], length: variant.focus_utf16[1]-variant.focus_utf16[0])
                guard Range(range, in: variant.context) != nil,
                      text.substring(with: range) == pattern.source else { throw Invalid.evidence }
                _ = try Self.reviewedCarrier(variant, head: pattern.source, source: source)
            }
        }
    }

    /// Only catalog-attested noun attachments may expose a head inside one word.
    /// This validates exact stored geometry; it never stems an arbitrary message.
    static func reviewedCarrier(_ variant: Variant, head: String, source: String) throws -> NSRange? {
        guard variant.carrier_utf16 != nil || variant.carrier_rule != nil else { return nil }
        guard let offsets = variant.carrier_utf16, let rule = variant.carrier_rule,
              offsets.count == 2, offsets[0] >= 0, offsets[1] > offsets[0],
              offsets[1] <= variant.context.utf16.count,
              variant.focus_utf16.count == 2 else { throw Invalid.evidence }
        let range = NSRange(location: offsets[0], length: offsets[1] - offsets[0])
        guard let nativeRange = Range(range, in: variant.context),
              variant.context.indices.contains(nativeRange.lowerBound),
              nativeRange.upperBound == variant.context.endIndex || variant.context.indices.contains(nativeRange.upperBound)
        else { throw Invalid.evidence }
        let carrier = String(variant.context[nativeRange])
        switch rule {
        case "supplied-singular-definite-article-1":
            guard source == "ar", head.count >= 2, !head.hasPrefix("ال"),
                  head.unicodeScalars.allSatisfy({ (0x0620...0x064A).contains($0.value) }),
                  carrier == "ال" + head,
                  variant.focus_utf16 == [offsets[0] + 2, offsets[1]] else { throw Invalid.evidence }
        case "hangul-noun-particles-1":
            guard source == "ko", (1...64).contains(head.count),
                  head.unicodeScalars.allSatisfy({ (0xAC00...0xD7A3).contains($0.value) }),
                  let last = head.unicodeScalars.last,
                  variant.focus_utf16 == [offsets[0], offsets[0] + head.utf16.count] else { throw Invalid.evidence }
            let consonant = (last.value - 0xAC00) % 28 != 0
            let suffixes = [consonant ? "은" : "는", consonant ? "이" : "가",
                            consonant ? "을" : "를", consonant ? "과" : "와", "도", "만", "에", "에서", "의"]
            guard suffixes.contains(where: { carrier == head + $0 }) else { throw Invalid.evidence }
        default: throw Invalid.evidence
        }
        return range
    }

    static func bundled(target: String, baseline: SourceUnitLookup,
                        raw: @escaping () -> [SourceFrameStarterCandidate]) -> SourceUnitLookup {
        guard promotionEnabled,
              let root = Bundle.main.resourceURL?.appendingPathComponent("immersion"),
              let manifestBytes = try? Data(contentsOf: root.appendingPathComponent("source-frames-en-" + target + "-catalog.json")),
              let manifest = try? JSONDecoder().decode(Manifest.self, from: manifestBytes),
              manifest.file.range(of: "^source-frames-en-" + target + "-[0-9]{3}\\.json$", options: .regularExpression) != nil,
              let bytes = try? Data(contentsOf: root.appendingPathComponent(manifest.file)),
              let owner = try? SourceFrameLookup(bytes: bytes, manifestBytes: manifestBytes,
                  target: target, baselineIdentity: baseline.identity) else { return baseline }
        return owner.provider(baseline: baseline, raw: raw)
    }

    func provider(baseline: SourceUnitLookup,
                  raw: @escaping () -> [SourceFrameStarterCandidate],
                  catalog: BundledImmersionCatalog = BundledImmersionCatalog()) -> SourceUnitLookup {
        let identity = self.identity + ":reference-first-v1"
        return SourceUnitLookup(identity: identity) { context in
            let original = try await baseline.resolve(context)
            // Snapshot before awaiting the actor: another message may use the same matcher.
            let candidates = raw()
            let reference = try await catalog.reference(original: context.original, pair: context.pair)
            let resolved = reference != nil ? original : try self.resolve(
                original: context.original, density: context.density,
                known: context.knownConceptIDs, baseline: original, raw: candidates)
            return SourceLookupEvidence(original: resolved.original, source: resolved.source,
                target: resolved.target, catalogIdentity: identity, partial: resolved.partial,
                recognitions: resolved.recognitions, eligiblePool: resolved.eligiblePool,
                nativeSourceTokenCount: resolved.nativeSourceTokenCount)
        }
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
        let text=original as NSString;let native=LocalImmersion.words(original,language:source)
        guard let basis=NativeSourceTokenBasis(original:original,wordRanges:native) else { throw Invalid.evidence }
        let sentenceRanges: Set<NSRange> = pack.patterns.contains(where: {
            $0.variants.contains(where: { $0.context_scope == "whole_sentence" })
        }) ? Set(LocalImmersion.sentences(original, language: source)) : []
        var hits:[Hit]=[];var seen=Set<String>()
        func rightBoundary(_ range: NSRange) -> Bool {
            let suffix = text.substring(from: NSMaxRange(range))
            for scalar in suffix.unicodeScalars {
                if scalar.value == 9 || scalar.properties.generalCategory == .spaceSeparator { continue }
                return ".!?。！？,，;；\r\n".unicodeScalars.contains(scalar)
            }
            return true
        }
        func contextBarrier(_ variant: Variant) -> Bool {
            var content = variant.context
            if variant.context_scope == "whole_sentence" {
                while let last = content.last, ".!?。！？".contains(last) { content.removeLast() }
            }
            return content.contains(where: { ".!?。！？;；\r\n".contains($0) })
        }
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
                    let cc = v.context_scope == "whole_sentence" ? basis.cost(for: context) : cost(context)
                    let fc: Int?
                    if let relativeCarrier = try Self.reviewedCarrier(v, head: p.source, source: source) {
                        let carrier = NSRange(location: context.location + relativeCarrier.location, length: relativeCarrier.length)
                        fc = cost(carrier) == 1 ? 1 : nil
                    } else { fc = cost(focus) }
                    let reason: String?
                    if cc == nil || fc == nil { reason = "partial_native_word" }
                    else if v.context_scope == "whole_sentence" && !sentenceRanges.contains(context) { reason = "not_whole_sentence" }
                    else if v.right_boundary == "clause_or_end" && !rightBoundary(context) { reason = "right_context_boundary" }
                    else if contextBarrier(v) { reason = "context_barrier" }
                    else { reason = nil }
                    hits.append(Hit(p,context,focus,cc ?? 0,fc ?? 0,id,reason));guard hits.count<=4096 else {throw Invalid.evidence}
                }
            }
        }
        return hits
    }
    func geometry(_ original:String) throws -> [[String:Any]] {
        try matches(original).map{["pattern_id":$0.pattern.id,"context":[$0.context.location,NSMaxRange($0.context)],"focus":[$0.focus.location,NSMaxRange($0.focus)],"reason":$0.reason as Any? ?? NSNull()]}
    }
    func resolve(original:String,density:Double,known:Set<String>,baseline:SourceLookupEvidence,raw:[SourceFrameStarterCandidate]) throws -> SourceLookupEvidence {
        guard !original.isEmpty,original.utf16.count<=16384,density.isFinite,(0...0.75).contains(density),
              baseline.catalogIdentity == baselineIdentity, baseline.validated(text:original,sourceLanguage:source,targetLanguage:target,identity:baseline.catalogIdentity) != nil else {throw Invalid.evidence}
        trace=[];let text=original as NSString;let native=LocalImmersion.words(original,language:source)
        let budget=density>0 ? max(1,Int(Double(native.count)*density)) : 0
        let literalRanges=TranslationIntegrity.protectedLiteralRanges(original)
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
        for h in hits.filter({ !["partial_native_word","context_barrier","not_whole_sentence","right_context_boundary"].contains($0.reason ?? "") }).sorted(by:{($0.focus.location,NSMaxRange($0.focus))<($1.focus.location,NSMaxRange($1.focus))}) {
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
            if !approved.isEmpty {frameUnits.append((best,.init(range:best.focus,original:text.substring(with:best.focus),translated:best.pattern.target,reading:best.pattern.reading.isEmpty ? nil : best.pattern.reading,referenceID:"frame:"+packSHA+":"+best.pattern.id,catalogSHA256:packSHA,nativeSourceTokens:best.cost,conceptID:best.pattern.concept_id,outputID:best.id,reviewedFrameIdentity:ReviewedFrameIdentity(
                verifiedReviewedPattern:true,sourceLanguage:source,targetLanguage:target,patternID:best.pattern.id,
                sourceFace:text.substring(with:best.focus),targetFace:best.pattern.target,meaning:best.pattern.meaning,reading:best.pattern.reading))))}
            frameRecognitions.append(.init(ruleID:"frame-group-\(n)",recordSHA256:JapaneseStarterLookup.digest(Data(g.map(\.id).sorted().joined(separator:"\0").utf8)),context:union(g.map(\.context)),mask:union(g.map(\.focus)),mode:ambiguous ? .ambiguous : .headBackoff,approvedOutputs:approved))
        }
        trace=hits.map{["pattern_id":$0.pattern.id,"output_id":$0.id,"context":[$0.context.location,NSMaxRange($0.context)],"focus":[$0.focus.location,NSMaxRange($0.focus)],"reason":$0.reason as Any? ?? NSNull()]}
        let masks=frameRecognitions.compactMap(\.mask)
        let ordinary=raw.filter{c in c.reason==nil && !masks.contains(where:{overlap($0,c.range)})}.sorted {
            if ($0.category=="content") != ($1.category=="content") {return $0.category=="content"}
            if $0.tokenCount != $1.tokenCount {return $0.tokenCount>$1.tokenCount}
            if $0.rank != $1.rank {return $0.rank<$1.rank}
            return $0.range.location<$1.range.location
        }
        let fixed=baseline.recognitions.filter{$0.mode != .headBackoff}+frameRecognitions.filter{$0.mode != .headBackoff}+literalRanges.enumerated().map{n,r in SourceRecognition(ruleID:"native-literal-\(n)",recordSHA256:packSHA,context:r,mask:r,mode:.ambiguous,approvedOutputs:[])}
        let candidates=(frameUnits.sorted{stronger($0.0,$1.0)}.map{$0.1}+ordinary.map(\.unit)).filter{u in fixed.allSatisfy{n in n.mask.map{overlap($0,u.range)} != true || (n.mode != .ambiguous && n.approvedOutputs.contains{$0.outputID==u.outputID && $0.range==u.range})}}

        // Preserve the established strongest/content/rank precedence before
        // exporting a pool; remove overlapping weaker alternatives without a
        // density cap, so later valid words remain available to the packer.
        var poolCandidates:[SourceReferenceUnit]=[]
        for unit in candidates where !poolCandidates.contains(where:{overlap($0.range,unit.range)}) {
            poolCandidates.append(unit)
        }
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
        let base=SourceLookupEvidence(original:original,source:source,target:target,catalogIdentity:identity,partial:partial,recognitions:recognitions+fixed)
        guard let constraints=base.validated(text:original,sourceLanguage:source,targetLanguage:target,identity:identity) else {throw Invalid.evidence}
        let qualifiedPool=poolCandidates.filter { unit in
            constraints.permits(range:unit.range,outputID:unit.outputID) &&
                SourceReferencePresentation.create(original:original,target:target,units:[unit],density:1,nativeSourceTokenCount:native.count) != nil
        }
        let result=SourceLookupEvidence(original:original,source:source,target:target,catalogIdentity:identity,partial:partial,recognitions:recognitions+fixed,
            eligiblePool:density > 0 && !native.isEmpty ? qualifiedPool : nil,nativeSourceTokenCount:density > 0 && !native.isEmpty ? native.count : nil)
        guard result.validated(text:original,sourceLanguage:source,targetLanguage:target,identity:identity) != nil else {throw Invalid.evidence}
        if let partial {guard constraints.filterPartial(partial)==partial else {throw Invalid.evidence}}
        return result
    }
}
