import Foundation

extension FrozenCandidateProducer {
    /// Caller-known vocabulary is explicit. Frozen frequency controls belong to QA callers only.
    func select(_ output:Output,input:Input,expectedBundleIdentity:String,indices:[Int],knownFamilyIDs:Set<String>,withholdFunction:Bool,density:Double)throws->[String:Any] {
        guard output.bundleIdentity == expectedBundleIdentity, output.inputIdentity == (try Self.identity(input)) else{throw FrozenContextPack.Failure.identity}
        guard density.isFinite,density>0,density<=1,knownFamilyIDs.count<=65536,indices.count<=65536,Set(indices).count==indices.count,indices.allSatisfy({output.candidates.indices.contains($0)}) else{throw FrozenContextPack.Failure.bound}
        let cs=output.candidates,budget=max(1,Int(floor(Double(input.words.count)*density)))
        var masks:[NSRange]=[]
        for item in input.sourceMasks{guard let id=item["unit_id"] as? String,!id.isEmpty,let r=item["utf16"] as? [Int],r.count==2,r[0]>=0,r[1]>r[0],r[1]<=input.original.utf16.count else{throw FrozenContextPack.Failure.invalidGeometry};masks.append(Self.range(r))}
        var admitted:[Int]=[],rejected:[Int:[String]]=[:],costs:[Int:Int]=[:],depths:[Int:Int]=[:],ranges:[Int:NSRange]=[:]
        let categories=["content":0,"unresolved":1,"function":2]
        for i in indices {
            let c=cs[i],focus=Self.range(c["focus_utf16"] as! [Int]),context=Self.range(c["context_utf16"] as! [Int]);var reasons:[String]=[]
            if !(context.location<=focus.location && NSMaxRange(focus)<=NSMaxRange(context)){reasons.append("focus_outside_context")}
            let (cost,error)=Self.cost(focus,input.words),(depth,contextError)=Self.cost(context,input.words)
            if let error{reasons.append("focus_"+error)};if let contextError{reasons.append("context_"+contextError)}
            if c["identical_face"] as! Bool{reasons.append("identical_face")}
            if withholdFunction && c["category"] as! String=="function"{reasons.append("known_function")}
            let knowledge=c["knowledge_ids"] as! [String]
            if !knowledge.isEmpty && knowledge.allSatisfy({knownFamilyIDs.contains($0)}){reasons.append("known_vocabulary")}
            if input.protected.contains(where:{Self.overlap($0,focus)}){reasons.append("protected_focus")}
            if masks.contains(where:{$0 != focus && $0.location<=focus.location && NSMaxRange(focus)<=NSMaxRange($0)}){reasons.append("inside_recognized_source_unit")}
            if reasons.isEmpty{admitted.append(i);costs[i]=cost!;depths[i]=depth!;ranges[i]=focus}else{rejected[i]=Set(reasons).sorted()}
        }
        admitted.sort{a,b in
            if depths[a] != depths[b]{return depths[a]!>depths[b]!}
            let ca=categories[cs[a]["category"] as! String]!,cb=categories[cs[b]["category"] as! String]!
            if ca != cb{return ca<cb};let ra=cs[a]["train_rank"] as! Int,rb=cs[b]["train_rank"] as! Int
            if ra != rb{return ra<rb};if costs[a] != costs[b]{return costs[a]!>costs[b]!}
            if ranges[a]!.location != ranges[b]!.location{return ranges[a]!.location<ranges[b]!.location}
            return (cs[a]["id"] as! String)<(cs[b]["id"] as! String)
        }
        let over=admitted.filter{costs[$0]!>budget};var selected:[Int]=[],occupied:[NSRange]=[],concepts:Set<String>=[],remaining=budget
        for i in admitted {
            let concept=cs[i]["concept_id"] as! String;var reasons:[String]=[]
            if concepts.contains(concept){reasons.append("repeated_concept")}
            if occupied.contains(where:{Self.overlap($0,ranges[i]!)}){reasons.append("overlapping_selected_focus")}
            if costs[i]!>budget{reasons.append("over_total_budget")}else if costs[i]!>remaining{reasons.append("exceeds_remaining_budget")}
            if reasons.isEmpty{selected.append(i);occupied.append(ranges[i]!);concepts.insert(concept);remaining-=costs[i]!}else{rejected[i]=reasons}
        }
        let mixed=NSMutableString(string:input.original)
        for i in selected.sorted(by:{ranges[$0]!.location>ranges[$1]!.location}){mixed.replaceCharacters(in:ranges[i]!,with:cs[i]["target"] as! String)}
        return ["selected_indices":selected,"pre_budget_indices":admitted,"budget_only_indices":over,"budget":budget,"rejected":rejected.keys.sorted().map{["index":$0,"reasons":rejected[$0]!] as [String:Any]},"mixed_output":mixed as String]
    }
}
