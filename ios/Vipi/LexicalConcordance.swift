import Foundation
import SQLite3
import VipiCore

/// Indexed published dictionary evidence; native Swift lookup and selection.
enum LexicalConcordance {
    private static let policies:Set<String>=["native-linked-analysis-concordance-2","native-linked-lexical-units-3","native-linked-lexical-units-4"]
    private enum Limit:Error {case overflow}
    private struct Form:Hashable {
        let key:String,lexeme:String,written:String
        let start:Int,end:Int,number:Int,mode:Int
        let sourceSafe:Bool,targetSafe:Bool;let features:Set<String>;let proper:Bool,grammar:Bool
    }
    private struct Term {let sense:String,reading:String;let eligible:Bool,explicit:Bool}
    private struct Side {
        let windows:[String:[NSRange]],forms:[String:[Form]],terms:[String:[Term]]
        let blocked:Set<String>,targetBlocked:Set<String>,names:Set<String>,guards:Set<String>,inventory:String,release:String
    }
    private static func key(_ value:String)->String {ImmersionEngine.lookupKey(value)}
    private static func marks(_ count:Int)->String {Array(repeating:"?",count:count).joined(separator:",")}
    private static func query(_ db:OpaquePointer,_ sql:String,_ arguments:[String],limit:Int) throws -> [[String]] {
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
            result.append(row);if result.count>limit {throw Limit.overflow}
            status=sqlite3_step(statement)
        }
        guard status==SQLITE_DONE else {throw VocabularyPackError.storage};return result
    }
    private static func load(_ db:OpaquePointer,text:String,language:String) throws -> Side? {
        var metadata:[String:String]=[:]
        for row in try query(db,"SELECT key,value FROM metadata WHERE key IN ('schema','policy','language','source_inventory_sha256','release_id')",[],limit:5) {
            metadata[row[0]]=try JSONDecoder().decode(String.self,from:Data(row[1].utf8))
        }
        guard let inventory=metadata.removeValue(forKey:"source_inventory_sha256"),inventory.range(of:"^[0-9a-f]{64}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        guard let release=metadata.removeValue(forKey:"release_id"),release.range(of:"^[0-9a-f]{64}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        guard let policy=metadata.removeValue(forKey:"policy"),policies.contains(policy),
              metadata==["schema":"vipi-lexical-shard-2","language":language] else {throw VocabularyPackError.invalid}
        guard let raw=ReviewedFrameLookup.windows(text,language:language) else {return nil}
        var windows:[String:[NSRange]]=[:]
        for (written,ranges) in raw {windows[key(written),default:[]]+=ranges}
        var forms:[String:[Form]]=[:],blocked=Set<String>(),guards=Set<String>(),targetBlocked=Set<String>(),names=Set<String>(),count=0
        let inputs=windows.keys.sorted()
        for start in stride(from:0,to:inputs.count,by:200) {
            let batch=Array(inputs[start..<min(inputs.count,start+200)])
            for r in try query(db,"SELECT s.normalized,s.lexeme,s.surface,s.start,s.end,s.number,s.mode,l.source_safe,l.target_safe,s.features,l.pos,COALESCE(g.reason,''),COALESCE(g.target_blocked,0) FROM surfaces s JOIN lexemes l ON l.id=s.lexeme LEFT JOIN guards g ON g.normalized=l.normalized WHERE s.normalized IN (\(marks(batch.count))) ORDER BY s.normalized,s.lexeme",batch,limit:16384-count) {
                count+=1
                guard let a=Int(r[3]),let b=Int(r[4]),let n=Int(r[5]),let m=Int(r[6]) else {throw VocabularyPackError.invalid}
                let form=Form(key:r[0],lexeme:r[1],written:r[2],start:a,end:b,number:n,mode:m,sourceSafe:r[7]=="1",targetSafe:r[8]=="1",features:Set(try JSONDecoder().decode([String].self,from:Data(r[9].utf8))),proper:["name","proper-noun","proper_noun"].contains(r[10]),grammar:["pron","det","prep","postp","conj","particle","article","aux"].contains(r[10]) || r[11]=="grammar" || r[12]=="1")
                if forms[r[0],default:[]].count<256 {forms[r[0],default:[]].append(form)} else {blocked.insert(r[0]);targetBlocked.insert(r[0])}
            }
            for r in try query(db,"SELECT normalized,blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized IN (\(marks(batch.count)))",batch,limit:200) {
                if r[1]=="1" {blocked.insert(r[0])};if r[2]=="1" {targetBlocked.insert(r[0])};if r[3]=="1" {guards.insert(r[0])}
                if r[4]=="name" {names.insert(r[0])}
            }
        }
        let ids=Set(forms.values.flatMap{$0}.map(\.lexeme)).sorted()
        var terms:[String:[Term]]=[:];count=0
        for start in stride(from:0,to:ids.count,by:200) {
            let batch=Array(ids[start..<min(ids.count,start+200)])
            for r in try query(db,"SELECT t.lexeme,t.sense,t.reading,t.eligible,s.explicit FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme IN (\(marks(batch.count))) ORDER BY t.lexeme,t.sense,t.reading",batch,limit:32768-count) {
                count+=1;terms[r[0],default:[]].append(Term(sense:r[1],reading:r[2],eligible:r[3]=="1",explicit:r[4]=="1"))
            }
        }
        return Side(windows:windows,forms:forms,terms:terms,blocked:blocked,targetBlocked:targetBlocked,names:names,guards:guards,inventory:inventory,release:release)
    }
    private static func shape(_ form:Form)->[Int] {
        [form.mode==3 ? form.start : 0,form.mode==3 ? form.end : 0,form.number,form.mode==3 ? 3 : 1]
    }
    private static func focus(_ form:Form,range:NSRange,text:String)->NSRange? {
        guard (1...3).contains(form.mode) else {return nil}
        if form.mode != 3 {return range}
        let actual=(text as NSString).substring(with:range)
        guard actual.utf16.count==form.written.utf16.count,actual.lowercased()==form.written.lowercased(),
              form.start>=0,form.end>form.start,form.end<=actual.utf16.count else {return nil}
        let value=NSRange(location:range.location+form.start,length:form.end-form.start)
        guard Range(value,in:text) != nil else {return nil};return value
    }
    private static func targetCaseMatches(_ form:Form,range:NSRange,text:String)->Bool {
        let actual=(text as NSString).substring(with:range)
        if actual==form.written {return true}
        guard key(actual)==key(form.written) else {return false}
        if actual.first?.isUppercase==true && form.written.first?.isLowercase==true {
            let before=(text as NSString).substring(to:range.location).trimmingCharacters(in:.whitespacesAndNewlines)
            return before.isEmpty || ".!?。！？\n".contains(before.last!)
        }
        return actual.first?.isUppercase==form.written.first?.isUppercase
    }
    private static func protected(_ side:Side,range:NSRange)->Bool {
        side.guards.contains { word in side.windows[word,default:[]].contains { whole in
            whole.location<=range.location && NSMaxRange(whole)>=NSMaxRange(range) && whole != range
        }}
    }
    private static func protectedTarget(_ side:Side,range:NSRange,text:String,language:String,features:Set<String>)->Bool {
        let people=features.intersection(["first-person","second-person","third-person"])
        let numbers=features.intersection(["singular","plural"])
        var subjects:Set<String>=[]
        if language=="en" && features.contains("present") && people.count==1 && numbers.count==1 {
            switch people.first!+":"+numbers.first! {
            case "first-person:singular":subjects=["i"]
            case "first-person:plural":subjects=["we"]
            case "second-person:singular","second-person:plural":subjects=["you"]
            case "third-person:singular":subjects=["he","she","it"]
            case "third-person:plural":subjects=["they"]
            default:break
            }
        }
        let carrier=(text as NSString).substring(with:range).lowercased()
        return side.guards.contains { word in side.windows[word,default:[]].contains { whole in
            whole.location<=range.location && NSMaxRange(whole)>=NSMaxRange(range) && whole != range &&
                !subjects.contains(where:{(text as NSString).substring(with:whole).lowercased()==$0+" "+carrier})
        }}
    }
    private static func contextualEntries(left:Side,right:Side,db:OpaquePointer,original:String,translation:String,source:String,target:String,
        strict:[VocabularyEntry],diagnostic:(String)->Void) throws -> [VocabularyEntry] {
        var targetKeys=Set<String>()
        for (word,forms) in right.forms {for form in forms {for carrier in right.windows[word,default:[]] {
            if let range=focus(form,range:carrier,text:translation) {targetKeys.insert(key((translation as NSString).substring(with:range)))}
        }}}
        guard let evidence=try ContextWitnessLookup.load(db,original:original,source:source,target:target,release:left.release,sources:Set(left.forms.keys),targets:targetKeys) else {return []}
        let needsReading=["ar","zh","ja","ko"].contains(target)
        struct Claim:Hashable {let range:NSRange,reading:String}
        var output:[VocabularyEntry]=[]
        for word in left.forms.keys.sorted() {
            let forms=left.forms[word,default:[]]
            guard !left.targetBlocked.contains(word),!forms.contains(where:{$0.grammar}) else {continue}
            for carrier in Set(left.windows[word,default:[]]) {
                guard !protected(left,range:carrier),!strict.contains(where:{ e in
                    guard let scope=e.sourceScope else {return false}
                    return scope.start<NSMaxRange(carrier) && carrier.location<scope.end
                }) else {continue}
                let actual=(original as NSString).substring(with:carrier)
                if left.blocked.contains(word) {
                    let proper=forms.filter(\.proper)
                    guard left.names.contains(word),actual.first?.isLowercase==true,!proper.isEmpty,
                        proper.allSatisfy({$0.written.first?.isUppercase==true}) else {continue}
                }
                let usable=forms.filter{$0.targetSafe && (1...2).contains($0.mode) && key(actual)==key($0.written) &&
                    actual.first?.isUppercase==$0.written.first?.isUppercase}
                var claims=Set<Claim>()
                for form in usable {
                    let meanings=Set(left.terms[form.lexeme,default:[]].filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                    if meanings.isEmpty {continue}
                    let features=forms.filter{$0.lexeme==form.lexeme && $0.mode==form.mode}.map(\.features).reduce(form.features){$0.intersection($1)}
                    for other in right.forms.keys.sorted() {
                        guard !right.targetBlocked.contains(other) else {continue}
                        let targets=right.forms[other,default:[]]
                        let readings=Set(targets.flatMap{right.terms[$0.lexeme,default:[]]}.map(\.reading).filter{!$0.isEmpty})
                        if needsReading && readings.count != 1 {continue}
                        for candidate in Set(targets) {
                            guard candidate.targetSafe,(1...3).contains(candidate.mode),candidate.number==form.number,
                                  right.terms[candidate.lexeme,default:[]].contains(where:{$0.eligible && meanings.contains($0.sense)}) else {continue}
                            for targetCarrier in Set(right.windows[other,default:[]]) {
                                guard !protectedTarget(right,range:targetCarrier,text:translation,language:target,features:features),
                                    targetCaseMatches(candidate,range:targetCarrier,text:translation),let targetFocus=focus(candidate,range:targetCarrier,text:translation) else {continue}
                                if strict.contains(where:{ e in
                                    guard let scope=e.targetScope else {return false}
                                    return scope.start<NSMaxRange(targetFocus) && targetFocus.location<scope.end
                                }) {continue}
                                if evidence.supports(word:key(actual),counterpart:key((translation as NSString).substring(with:targetFocus)),focus:carrier,text:original,windows:left.windows) {
                                    claims.insert(Claim(range:targetFocus,reading:needsReading ? readings.first! : ""))
                                }
                            }
                        }
                    }
                }
                guard claims.count==1,let claim=claims.first else {continue}
                let targetText=(translation as NSString).substring(with:claim.range)
                diagnostic("context_witness_candidate")
                output.append(VocabularyEntry(source:actual,targets:[targetText],romanizations:needsReading ? [targetText:[claim.reading]] : [:],
                    sourceScope:VocabularySourceScope(original:original,start:carrier.location,end:NSMaxRange(carrier)),
                    targetScope:VocabularyTargetScope(translation:translation,start:claim.range.location,end:NSMaxRange(claim.range))))
            }
        }
        return output
    }
    static func entries(leftDB:OpaquePointer,rightDB:OpaquePointer,original:String,translation:String,source:String,target:String,witnessDB:OpaquePointer?=nil,diagnostic:(String)->Void={_ in}) throws -> [VocabularyEntry] {
        guard original.utf16.count<=16384,translation.utf16.count<=32768,source != target else {return []}
        do {
            guard let left=try load(leftDB,text:original,language:source),let right=try load(rightDB,text:translation,language:target) else {return []}
            guard left.inventory==right.inventory && left.release==right.release else {throw VocabularyPackError.invalid}
            let needsReading=["ar","zh","ja","ko"].contains(target)
            struct Claim:Hashable {let range:NSRange,reading:String}
            var output:[VocabularyEntry]=[]
            for word in left.forms.keys.sorted() {
                let forms=left.forms[word,default:[]]
                guard !left.blocked.contains(word) else {diagnostic("source_guard");continue}
                guard Set(forms.map(\.lexeme)).count==1 else {diagnostic("multiple_source_entries");continue}
                // Different analyses must not disappear because only one of
                // them has a convenient counterpart in the translated text.
                let usable=forms.filter{$0.sourceSafe && (1...3).contains($0.mode)}
                let shapes=Set(usable.map(shape))
                guard shapes.count==1,let form=usable.first else {diagnostic(usable.isEmpty ? "source_sense_or_form" : "source_form_conflict");continue}
                let features=forms.filter{$0.lexeme==form.lexeme && $0.mode==form.mode}.map(\.features).reduce(form.features){$0.intersection($1)}
                let meanings=Set(left.terms[form.lexeme,default:[]].filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                if meanings.isEmpty {diagnostic("no_eligible_link");continue}
                for carrier in Set(left.windows[word,default:[]]) {
                    guard !protected(left,range:carrier) else {diagnostic("source_compound");continue}
                    guard let sourceFocus=focus(form,range:carrier,text:original) else {continue}
                    var claims=Set<Claim>()
                    for other in right.forms.keys.sorted() {
                        guard !right.targetBlocked.contains(other) else {continue}
                        let targets=right.forms[other,default:[]]
                        let readings=Set(targets.flatMap{right.terms[$0.lexeme,default:[]]}.map(\.reading).filter{!$0.isEmpty})
                        if needsReading && readings.count != 1 {continue}
                        for candidate in Set(targets) {
                            guard candidate.targetSafe,(1...3).contains(candidate.mode),candidate.number==form.number,
                                  right.terms[candidate.lexeme,default:[]].contains(where:{$0.eligible && meanings.contains($0.sense)}) else {continue}
                            for targetCarrier in Set(right.windows[other,default:[]]) {
                                guard !protectedTarget(right,range:targetCarrier,text:translation,language:target,features:features),targetCaseMatches(candidate,range:targetCarrier,text:translation),let targetFocus=focus(candidate,range:targetCarrier,text:translation) else {continue}
                                claims.insert(Claim(range:targetFocus,reading:needsReading ? readings.first! : ""))
                            }
                        }
                    }
                    guard claims.count==1,let claim=claims.first else {diagnostic(claims.isEmpty ? "no_target_claim" : "multiple_target_claims");continue}
                    diagnostic("dictionary_candidate")
                    let sourceText=(original as NSString).substring(with:sourceFocus)
                    let targetText=(translation as NSString).substring(with:claim.range)
                    output.append(VocabularyEntry(source:sourceText,targets:[targetText],
                        romanizations:needsReading ? [targetText:[claim.reading]] : [:],
                        sourceScope:VocabularySourceScope(original:original,start:sourceFocus.location,end:NSMaxRange(sourceFocus)),
                        targetScope:VocabularyTargetScope(translation:translation,start:claim.range.location,end:NSMaxRange(claim.range))))
                }
            }
            if let witnessDB {output += try contextualEntries(left:left,right:right,db:witnessDB,original:original,translation:translation,source:source,target:target,strict:output,diagnostic:diagnostic)}
            return output
        } catch Limit.overflow {diagnostic("query_overflow");return []}
    }
}
