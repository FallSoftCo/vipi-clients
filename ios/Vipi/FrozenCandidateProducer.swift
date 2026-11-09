import Foundation

/// Research candidate and selector parity, uncalled by customer presentation.
struct FrozenCandidateProducer {
    struct Observation {
        let raw: [Any]?, mapped: String?
        static func apple(_ tag:String?)->String? {
            switch tag {case "Noun":return "noun";case "Adjective":return "adj";case "Adverb":return "adv";default:return nil}
        }
    }
    struct Input {
        let original:String
        let words:[NSRange], windows:[NSRange], protected:[NSRange]
        let sourceMasks:[[String:Any]]
        let roles:[NSRange:Observation]
        let sourceNameOnlyGuards:Set<NSRange>
        // These must describe independent full source observations, not candidates.
        let basis:String
    }
    struct Output {let inputIdentity:String, bundleIdentity:String; let candidates:[[String:Any]], ordinaryCount:Int, geometryRejections:[[String:Any]], conditionalGeometryRejections:[[String:Any]], gates:[String:[String:Any]], qualifiedIndices:[Int]}
    private let tokenizer:FrozenContextTokenizer,sourceCase:FrozenSourceCase
    init()throws{tokenizer=try FrozenContextTokenizer();sourceCase=try FrozenSourceCase()}
    static func identity(_ input:Input)throws->String {
        let roles=input.roles.keys.sorted{($0.location,$0.length)<($1.location,$1.length)}.map{r -> [String:Any] in
            ["range":pair(r),"raw":input.roles[r]!.raw as Any? ?? NSNull(),"mapped":input.roles[r]!.mapped as Any? ?? NSNull()]
        }
        let guards=input.sourceNameOnlyGuards.sorted{($0.location,$0.length)<($1.location,$1.length)}.map(pair)
        let value:[String:Any]=["original_utf8":Data(input.original.utf8).base64EncodedString(),"words":input.words.map(pair),"windows":input.windows.map(pair),"protected":input.protected.map(pair),"masks":input.sourceMasks,"roles":roles,"guards":guards,"basis":input.basis]
        let bytes=try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]);guard bytes.count<=16<<20 else{throw FrozenContextPack.Failure.bound}
        return FrozenCandidateCatalog.hash(bytes.base64EncodedString())
    }
    static func qualifiedOrder(ordinary:[Int],admittedGroups:[[Int]])->[Int] { (ordinary+admittedGroups.flatMap{$0}).sorted() }
    static func pair(_ r:NSRange)->[Int]{[r.location,NSMaxRange(r)]}
    static func range(_ v:[Int])->NSRange{NSRange(location:v[0],length:v[1]-v[0])}
    static func overlap(_ a:NSRange,_ b:NSRange)->Bool{NSIntersectionRange(a,b).length>0}
    static func cost(_ range:NSRange,_ words:[NSRange])->(Int?,String?) {
        let inside=words.filter{overlap(range,$0)}
        guard !inside.isEmpty else{return(nil,"no_native_words")}
        guard inside.allSatisfy({$0.location>=range.location && NSMaxRange($0)<=NSMaxRange(range)}) else{return(nil,"partial_native_word")}
        guard inside.first?.location==range.location,inside.last.map({NSMaxRange($0)})==NSMaxRange(range) else{return(nil,"not_exact_native_boundaries")}
        return(inside.count,nil)
    }
    func produce(_ input:Input,catalog:FrozenCandidateCatalog,pack:FrozenContextPack)throws->Output {
        guard catalog.contextPackSHA256 == pack.contentSHA256 else{throw FrozenContextPack.Failure.identity}
        let text=input.original,ns=text as NSString
        guard text.utf16.count<=16384,input.words.count<=16384,input.windows.count<=65536,input.protected.count<=4096,input.sourceMasks.count<=16384,!input.basis.isEmpty else{throw FrozenContextPack.Failure.bound}
        var offsets:[Int:Int]=[0:0],offset=0
        for (i,s) in text.unicodeScalars.enumerated(){offset+=s.utf16.count;offsets[offset]=i+1}
        var last=0
        for r in input.words{guard r.location>=last,r.length>0,offsets[r.location] != nil,offsets[NSMaxRange(r)] != nil else{throw FrozenContextPack.Failure.invalidGeometry};last=NSMaxRange(r)}
        for r in input.windows+input.protected{guard r.location>=0,r.length>0,offsets[r.location] != nil,offsets[NSMaxRange(r)] != nil else{throw FrozenContextPack.Failure.invalidGeometry}}
        let sorted=input.windows.sorted{($0.location,$0.length)<($1.location,$1.length)}
        guard sorted==input.windows,Set(input.windows).count==input.windows.count else{throw FrozenContextPack.Failure.invalidGeometry}
        let tokens=try tokenizer.tokenize(text),starts=Dictionary(uniqueKeysWithValues:tokens.enumerated().map{($0.element.range.location,$0.offset)}),ends=Dictionary(uniqueKeysWithValues:tokens.enumerated().map{(NSMaxRange($0.element.range),$0.offset+1)})
        var candidates:[[String:Any]]=[],rejections:[[String:Any]]=[],experimental:[[String:Any]]=[],ordinaryCount=0
        for ordinary in [true,false] {
            for window in input.windows {
                let key=try tokenizer.normalize(ns.substring(with:window))
                for head in try catalog.heads(sourceKey:key,ordinary:ordinary) {
                    let record=head.record
                    func reject(_ reason:String){let r:[String:Any]=["head":head.id,"window":Self.pair(window),"reason":reason];if ordinary{rejections.append(r)}else{experimental.append(r)}}
                    guard let first=starts[window.location],let end=ends[NSMaxRange(window)] else{reject("training_token_boundary");continue}
                    let actual=Array(tokens[first..<end]);guard let expected=record["source_context_token_text"] as? [String],actual.map(\.normalized).map({Data($0.utf8)})==expected.map({Data($0.utf8)}) else{reject("context_token_sequence");continue}
                    guard let relative=record["source_focus_relative_tokens"] as? [Int],relative.count==2,relative[0]>=0,relative[1]>relative[0],relative[1]<=actual.count else{throw FrozenContextPack.Failure.malformed}
                    let focus=NSRange(location:actual[relative[0]].range.location,length:NSMaxRange(actual[relative[1]-1].range)-actual[relative[0]].range.location)
                    let (cost,error)=Self.cost(focus,input.words);if let error{reject(error);continue}
                    let original=ns.substring(with:focus),norm=try tokenizer.normalize(original),words=try tokenizer.tokenize(original).filter{tokenizer.originalHasAlphabeticScalar($0.original)}.map(\.normalized)
                    let nonfunction=words.filter{!pack.evidence.isFunction($0)},anchors=nonfunction.filter{!pack.evidence.roles(for:$0).isDisjoint(with:["noun","adj","adv","verb"])}
                    let category = !anchors.isEmpty ? "content" : !nonfunction.isEmpty ? "unresolved":"function"
                    let knowledge=Set(nonfunction.map{pack.evidence.family(for:$0) ?? "unmapped:"+$0}).sorted()
                    let role=input.roles[focus];var reasons:[String]=[]
                    if relative[1]-relative[0] != 1 || cost != 1{reasons.append("not_single_token_head")}
                    if role?.mapped == nil{reasons.append("role_unassessed")}else if !(record["source_pos"] as? [String] ?? []).contains(role!.mapped!){reasons.append("role_conflict")}
                    if category != "content"{reasons.append("not_content_classified")}
                    guard let target=record["target_face"] as? String,let readings=record["head_readings"] as? [[String:Any]],let fixed=record["fixed"] as? Bool else{throw FrozenContextPack.Failure.malformed}
                    if !ordinary {
                        if role?.mapped != "noun"{reasons.append("rescue_requires_actual_NOUN")}
                        if category != "content"{reasons.append("rescue_requires_content")}
                        if cost != 1 || reasons.contains("not_single_token_head"){reasons.append("rescue_requires_exact_single_token")}
                        if !sourceCase.isLower(original){reasons.append("rescue_requires_lowercase_source")}
                        if !input.sourceNameOnlyGuards.contains(focus){reasons.append("rescue_requires_exact_current_source_name_guard")}
                    }
                    let c:[String:Any]=["id":head.id+"@\(window.location):\(NSMaxRange(window))","head_id":head.id,"context_id":head.contextID,"fixed":fixed,"focus_utf16":Self.pair(focus),"context_utf16":Self.pair(window),"source":original,"target":target,"reading":Set(readings.compactMap{$0["text"] as? String}).sorted(),"identical_face":try tokenizer.normalize(target)==norm,"category":category,"content_anchor_words":anchors,"knowledge_ids":knowledge,"concept_id":pack.evidence.family(for:norm) ?? "lexical:"+norm,"train_rank":head.rank,"cost":cost!,"source_key":key,"context_native_cost":input.words.filter{$0.location>=window.location && NSMaxRange($0)<=NSMaxRange(window)}.count,"role":["raw":role?.raw as Any? ?? NSNull(),"mapped":role?.mapped as Any? ?? NSNull()],"filter_reasons":reasons,"output_codepoints":[offsets[focus.location]!,offsets[NSMaxRange(focus)]!]]
                    candidates.append(c);guard candidates.count<=65536 else{throw FrozenContextPack.Failure.bound}
                }
            }
            if ordinary{ordinaryCount=candidates.count}
        }
        var groups:[NSRange:[Int]]=[:],keep:[Int]=[],gates:[String:[String:Any]]=[:]
        for (i,c) in candidates.enumerated(){guard (c["filter_reasons"] as! [String]).isEmpty else{continue};if i<ordinaryCount{keep.append(i)}else{groups[Self.range(c["focus_utf16"] as! [Int]),default:[]].append(i)}}
        for focus in groups.keys.sorted(by:{($0.location,$0.length)<($1.location,$1.length)}) {
            let indices=groups[focus]!,keys=try Set(indices.flatMap{try catalog.keys(headID:candidates[$0]["head_id"] as! String)}).sorted()
            let match=try pack.assess(original:text,nativeWordRanges:input.words,focus:focus,sourceKeys:keys)
            let admitted=indices.filter{i in guard let w=match.winner else{return false};return w.rule.headIDs.contains(candidates[i]["head_id"] as! String) && w.rule.target==candidates[i]["target"] as! String}
            keep+=admitted
            let key="[\(focus.location),\(NSMaxRange(focus))]"
            gates[key]=["candidate_indices":indices,"admitted_indices":admitted,"source_keys":keys,"chosen_rule_id":match.winner?.rule.id as Any? ?? NSNull(),"chosen_context_utf16":match.winner.map{Self.pair($0.contextRange)} as Any? ?? NSNull(),"reason": !admitted.isEmpty ? "qualified_context":match.winner == nil ? "no_qualified_multiword_context":"winner_without_original_supported_head"]
        }
        return .init(inputIdentity:try Self.identity(input),bundleIdentity:catalog.bundleIdentity,candidates:candidates,ordinaryCount:ordinaryCount,geometryRejections:rejections,conditionalGeometryRejections:experimental,gates:gates,qualifiedIndices:Self.qualifiedOrder(ordinary:keep,admittedGroups:[]))
    }
}
