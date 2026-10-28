import Foundation
import SQLite3

/// Experimental reference evidence, supplied explicitly by native QA.
struct ContextWitnessLookup {
    private struct Pair:Hashable {let word:String,counterpart:String}
    private struct Alternative {let cue:String,senses:Set<String>}
    private let cues:[Pair:[String]],alternatives:[Pair:[Alternative]],words:[NSRange]
    private func nearby(_ range:NSRange,focus:NSRange,text:String)->Bool {
        let left=NSMaxRange(range)<=focus.location,right=range.location>=NSMaxRange(focus)
        guard left || right else {return false}
        let start=left ? NSMaxRange(range) : NSMaxRange(focus),end=left ? focus.location : range.location
        let between=(text as NSString).substring(with:NSRange(location:start,length:end-start))
        return !between.contains(where:{".!?。！？;；\r\n".contains($0)}) && words.filter{$0.location>=start && NSMaxRange($0)<=end}.count<6
    }
    func hasNearbyContext(focus:NSRange,text:String,windows:[String:[NSRange]])->Bool {
        windows.values.contains{ranges in ranges.contains{nearby($0,focus:focus,text:text)}}
    }
    func supports(word:String,counterpart:String,focus:NSRange,text:String,windows:[String:[NSRange]],allowedMeanings:Set<String>=[])->Bool {
        guard !words.isEmpty else {return false}
        let pair=Pair(word:word,counterpart:counterpart)
        let accepted=cues[pair,default:[]]+alternatives[pair,default:[]].filter{!$0.senses.isDisjoint(with:allowedMeanings)}.map(\.cue)
        return accepted.contains { cue in
            if cue=="@whole" {return words.allSatisfy{$0.location>=focus.location && NSMaxRange($0)<=NSMaxRange(focus)}}
            return windows[String(cue.dropFirst(2)),default:[]].contains { range in
                let left=cue.hasPrefix("L:") && NSMaxRange(range)<=focus.location
                let right=cue.hasPrefix("R:") && range.location>=NSMaxRange(focus)
                return (left || right) && nearby(range,focus:focus,text:text)
            }
        }
    }
    static func load(_ db:OpaquePointer,original:String,source:String,target:String,release:String,
        sources:Set<String>,targets:Set<String>) throws -> ContextWitnessLookup? {
        guard sources.count<=256,targets.count<=256,!sources.isEmpty,!targets.isEmpty else {return nil}
        func query(_ sql:String,_ arguments:[String],_ limit:Int) throws -> [[String]] {
            var statement:OpaquePointer?
            guard sqlite3_prepare_v2(db,sql,-1,&statement,nil)==SQLITE_OK else {throw VocabularyPackError.storage}
            defer {sqlite3_finalize(statement)}
            for (i,value) in arguments.enumerated() {
                guard sqlite3_bind_text(statement,Int32(i+1),value,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self))==SQLITE_OK else {throw VocabularyPackError.storage}
            }
            var result:[[String]]=[];var status=sqlite3_step(statement)
            while status==SQLITE_ROW {
                var row:[String]=[]
                for i in 0..<sqlite3_column_count(statement) {
                    guard let value=sqlite3_column_text(statement,i) else {throw VocabularyPackError.invalid}
                    row.append(String(cString:value))
                }
                result.append(row);if result.count>limit {return result}
                status=sqlite3_step(statement)
            }
            guard status==SQLITE_DONE else {throw VocabularyPackError.storage};return result
        }
        var meta:[String:String]=[:]
        for row in try query("SELECT key,value FROM metadata WHERE key IN ('schema','policy','source_release_id','minimum_support','minimum_agreement','pairs','whole_verb_context_policy','whole_present_context_policy','semantic_alternative_policy')",[],9) {meta[row[0]]=row[1]}
        func string(_ name:String) throws -> String {
            guard let raw=meta[name] else {throw VocabularyPackError.invalid}
            return try JSONDecoder().decode(String.self,from:Data(raw.utf8))
        }
        guard try string("schema")=="vipi-context-witnesses-1",try string("policy")=="experimental-direct-reference-agreement-1",
              try string("source_release_id")==release,let supportText=meta["minimum_support"],let minimum=Int(supportText),minimum>=3,
              let agreementText=meta["minimum_agreement"],let agreement=Double(agreementText),agreement.isFinite,agreement>=0.98,agreement<=1,
              let pairText=meta["pairs"] else {throw VocabularyPackError.invalid}
        if sources.contains(where:{$0.hasPrefix("@past:")}) || targets.contains(where:{$0.hasPrefix("@past:")}) {
            guard try string("whole_verb_context_policy")=="attested-positive-past-lemma-1" else {throw VocabularyPackError.invalid}
        }
        if sources.contains(where:{$0.hasPrefix("@present:")}) || targets.contains(where:{$0.hasPrefix("@present:")}) {
            guard try string("whole_present_context_policy")=="attested-positive-present-lemma-1" else {throw VocabularyPackError.invalid}
        }
        let pairs=try JSONDecoder().decode([String:Int].self,from:Data(pairText.utf8))
        guard pairs[source+"-"+target] != nil else {return nil}
        var rows:[Pair:[String]]=[:],alternatives:[Pair:[Alternative]]=[:];var count=0
        let semantic=meta["semantic_alternative_policy"] != nil
        if semantic {guard try string("semantic_alternative_policy")=="shared-explicit-verb-alternatives-1" else {throw VocabularyPackError.invalid}}
        let left=sources.sorted(),right=targets.sorted()
        func marks(_ n:Int)->String {Array(repeating:"?",count:n).joined(separator:",")}
        for i in stride(from:0,to:left.count,by:100) {for j in stride(from:0,to:right.count,by:100) {
            let a=Array(left[i..<min(i+100,left.count)]),b=Array(right[j..<min(j+100,right.count)])
            let found=try query("SELECT word,counterpart,cue,support,total FROM witnesses WHERE source=? AND target=? AND word IN (\(marks(a.count))) AND counterpart IN (\(marks(b.count)))",[source,target]+a+b,8192-count)
            count+=found.count;if count>8192 {return nil}
            for r in found {
                let cue=r[2]
                guard let n=Int(r[3]),let total=Int(r[4]),n>=minimum,total>=n,Double(n)/Double(total)>=agreement,
                      cue=="@whole" || ((cue.hasPrefix("L:") || cue.hasPrefix("R:")) && cue.count>2) else {throw VocabularyPackError.invalid}
                if cue.utf16.count<=130 {rows[Pair(word:r[0],counterpart:r[1]),default:[]].append(cue)}
            }
        }}
        if semantic {
            let presentLeft=left.filter{$0.hasPrefix("@present:")},presentRight=right.filter{$0.hasPrefix("@present:")}
            for i in stride(from:0,to:presentLeft.count,by:100) {for j in stride(from:0,to:presentRight.count,by:100) {
                let a=Array(presentLeft[i..<min(i+100,presentLeft.count)]),b=Array(presentRight[j..<min(j+100,presentRight.count)])
                let found=try query("SELECT word,counterpart,cue,support,total,counterpart_support,candidate_senses FROM semantic_alternatives WHERE source=? AND target=? AND word IN (\(marks(a.count))) AND counterpart IN (\(marks(b.count)))",[source,target]+a+b,8192-count)
                count+=found.count;if count>8192 {return nil}
                for r in found {
                    let cue=r[2]
                    guard let n=Int(r[3]),let total=Int(r[4]),let specific=Int(r[5]),n>=minimum,total>=n,specific>=minimum,specific<=n,Double(n)/Double(total)>=agreement,
                        cue=="@whole" || ((cue.hasPrefix("L:") || cue.hasPrefix("R:")) && cue.count>2) else {throw VocabularyPackError.invalid}
                    let raw=try JSONDecoder().decode([String].self,from:Data(r[6].utf8)),senses=Set(raw)
                    guard (1...128).contains(raw.count),senses.allSatisfy({$0.count==64 && $0.allSatisfy{"0123456789abcdef".contains($0)}}) else {throw VocabularyPackError.invalid}
                    if cue.utf16.count<=130 {alternatives[Pair(word:r[0],counterpart:r[1]),default:[]].append(Alternative(cue:cue,senses:senses))}
                }
            }}
        }
        return ContextWitnessLookup(cues:rows,alternatives:alternatives,words:LocalImmersion.words(original,language:source))
    }
}
