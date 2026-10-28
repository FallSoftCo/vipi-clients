import Foundation
import SQLite3
import VipiCore

/// Indexed published dictionary evidence; native Swift lookup and selection.
enum LexicalConcordance {
    private static let policies:Set<String>=["native-linked-analysis-concordance-2","native-linked-lexical-units-3","native-linked-lexical-units-4","native-linked-noun-carriers-5","native-linked-modern-lexemes-6","native-linked-chinese-lexical-7","native-linked-noun-gloss-articles-8","native-linked-adjective-agreement-10","native-linked-swahili-reviewed-13","native-linked-swahili-object-carriers-15","native-linked-arabic-plural-readings-16","native-linked-attested-past-verbs-17","native-linked-attested-present-verbs-18"]
    private static let surfaceReadingRule="supplied-arabic-plural-reading-1"
    private static let pastReadingRule="supplied-past-verb-reading-1"
    private static let pastRule="attested-positive-past-verb-1"
    private static let presentRule="attested-positive-present-verb-1"
    private static let surfaceReadingRules:Set<String>=[surfaceReadingRule,pastReadingRule]
    private static let finitePastSubject=try! NSRegularExpression(pattern:#"(?i)(?<![\p{L}\p{M}\p{N}_])(?:i|you|he|she|it|we|they)[ \t]+$"#)
    static func hasFinitePastSubject(_ text:String,start:Int)->Bool {
        guard start>=0,start<=text.utf16.count else {return false}
        let prefix=(text as NSString).substring(to:start)
        return finitePastSubject.firstMatch(in:prefix,range:NSRange(location:0,length:prefix.utf16.count)) != nil
    }
    private struct ReadingKey:Hashable {let lexeme:String,word:String}
    private enum Limit:Error {case overflow}
    private struct Form:Hashable {
        let key:String,lexeme:String,written:String
        let start:Int,end:Int,number:Int,mode:Int
        let sourceSafe:Bool,targetSafe:Bool;let features:Set<String>;let pos:String;let proper:Bool,grammar:Bool;let head:String
    }
    private struct Term {let sense:String,reading:String;let eligible:Bool,explicit:Bool;let family:String}
    private struct Side {
        let windows:[String:[NSRange]],forms:[String:[Form]],terms:[String:[Term]]
        let surfaceReadings:[ReadingKey:[String:Set<String>]]
        let blocked:Set<String>,targetBlocked:Set<String>,names:Set<String>,guards:Set<String>,inventory:String,release:String
        let namedPlaces:[NSRange],phrases:[NSRange]
    }
    private static func key(_ value:String)->String {ImmersionEngine.lookupKey(value)}
    private static func marks(_ count:Int)->String {Array(repeating:"?",count:count).joined(separator:",")}
    private static let sentenceText=try! NSRegularExpression(pattern:#"[^.!?。！？؛;؟\r\n]+"#)
    private struct SentenceAlignment {
        let sources:[NSRange],targets:[NSRange]
        init(_ original:String,_ translation:String) {
            func scopes(_ text:String)->[NSRange] {
                sentenceText.matches(in:text,range:NSRange(location:0,length:text.utf16.count)).compactMap { match in
                    (text as NSString).substring(with:match.range).rangeOfCharacter(from:.alphanumerics) != nil ? match.range : nil
                }
            }
            sources=scopes(original);targets=scopes(translation)
        }
        func uniqueSource(_ source:NSRange,_ occurrences:[NSRange])->Bool {
            guard let sentence=sources.first(where:{$0.location<=source.location && NSMaxRange($0)>=NSMaxRange(source)}) else {return false}
            return Set(occurrences).filter{$0.location>=sentence.location && NSMaxRange($0)<=NSMaxRange(sentence)}.count==1
        }
        func permits(_ source:NSRange,_ target:NSRange)->Bool {
            // Only matching multiple-sentence structures provide this veto.
            guard sources.count>1,sources.count==targets.count else {return true}
            let a=sources.firstIndex{$0.location<=source.location && NSMaxRange($0)>=NSMaxRange(source)}
            let b=targets.firstIndex{$0.location<=target.location && NSMaxRange($0)>=NSMaxRange(target)}
            return a != nil && a==b
        }
    }
    private static let arabicPlace=try! NSRegularExpression(pattern:#"(?:^|[\s،؛:,.!?])[وفبلك]?(?:محطة(?:\s+(?:حافلات|قطارات|قطار|مترو))*|فندق|مطار|شارع|جامعة|مطعم)\s+"#)
    private static let arabicNameWord=try! NSRegularExpression(pattern:#"[\p{L}\p{M}]+"#)
    private static let nameStops:Set<String>=["من","إلى","الى","في","على","عند","عن","و","أو","هل","هو","هي","هذا","هذه"]
    // Keep literal fragments out of the idiom, including SMS article variants.
    // Whole-phrase mappings remain eligible for their own meaning checks.
    private static let englishAllTheWay=try! NSRegularExpression(pattern:#"(?<![\p{L}\p{M}\p{N}_])all\s+(?:the|e|d)\s+way(?![\p{L}\p{M}\p{N}_])"#,options:.caseInsensitive)
    private static let englishLectureShorthand=try! NSRegularExpression(pattern:#"(?<![\p{L}\p{M}\p{N}_])(?:finish\s+lect|lect\s+finishes)(?![\p{L}\p{M}\p{N}_])"#,options:.caseInsensitive)
    // Preserve the spaced homework unit rather than exposing generic "works".
    private static let englishSpacedHomework=try! NSRegularExpression(pattern:#"(?<![\p{L}\p{M}\p{N}_])home\s+works?(?![\p{L}\p{M}\p{N}_])"#,options:.caseInsensitive)
    private static func phrases(_ text:String,language:String)->[NSRange] {
        guard language=="en" else {return []}
        let range=NSRange(location:0,length:text.utf16.count)
        return (englishAllTheWay.matches(in:text,range:range)+englishLectureShorthand.matches(in:text,range:range)+englishSpacedHomework.matches(in:text,range:range)).map(\.range)
    }
    static func namedPlaces(_ text:String,language:String)->[NSRange] {
        guard language=="ar" else {return []}
        let value=text as NSString;var output:[NSRange]=[]
        for prefix in arabicPlace.matches(in:text,range:NSRange(location:0,length:value.length)) {
            var position=NSMaxRange(prefix.range)
            for _ in 0..<4 {
                guard position<value.length,let token=arabicNameWord.firstMatch(in:text,range:NSRange(location:position,length:value.length-position)),
                      token.range.location==position,!nameStops.contains(key(value.substring(with:token.range))) else {break}
                output.append(token.range);position=NSMaxRange(token.range)
                while position<value.length,let scalar=UnicodeScalar(value.character(at:position)),CharacterSet.whitespacesAndNewlines.contains(scalar) {position+=1}
            }
        }
        return output
    }
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
        for row in try query(db,"SELECT key,value FROM metadata WHERE key IN ('schema','policy','language','source_inventory_sha256','release_id','surface_reading_schema','surface_reading_rule','whole_verb_schema','whole_verb_rule','present_verb_schema','present_verb_rule')",[],limit:11) {
            metadata[row[0]]=try JSONDecoder().decode(String.self,from:Data(row[1].utf8))
        }
        guard let inventory=metadata.removeValue(forKey:"source_inventory_sha256"),inventory.range(of:"^[0-9a-f]{64}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        guard let release=metadata.removeValue(forKey:"release_id"),release.range(of:"^[0-9a-f]{64}$",options:.regularExpression) != nil else {throw VocabularyPackError.invalid}
        guard let policy=metadata.removeValue(forKey:"policy"),policies.contains(policy) else {throw VocabularyPackError.invalid}
        let hasPresent=policy=="native-linked-attested-present-verbs-18"
        if hasPresent {
            guard ["en","es","fr","de","pt"].contains(language),metadata.removeValue(forKey:"present_verb_schema")=="vipi-whole-present-verb-1",
                metadata.removeValue(forKey:"present_verb_rule")==presentRule else {throw VocabularyPackError.invalid}
        }
        let hasPast=policy=="native-linked-attested-past-verbs-17" || (hasPresent && language=="en")
        if hasPast {
            guard ["en","ja","ko"].contains(language),metadata.removeValue(forKey:"whole_verb_schema")=="vipi-whole-past-verb-1",
                metadata.removeValue(forKey:"whole_verb_rule")==pastRule else {throw VocabularyPackError.invalid}
        }
        let hasSurfaceReadings=policy=="native-linked-arabic-plural-readings-16" || (hasPast && language != "en")
        if hasSurfaceReadings {
            guard hasPast || language=="ar",metadata.removeValue(forKey:"surface_reading_schema")=="vipi-surface-reading-2",
                metadata.removeValue(forKey:"surface_reading_rule")==((hasPast) ? pastReadingRule : surfaceReadingRule) else {throw VocabularyPackError.invalid}
        }
        guard metadata==["schema":"vipi-lexical-shard-2","language":language] else {throw VocabularyPackError.invalid}
        guard let raw=ReviewedFrameLookup.windows(text,language:language) else {return nil}
        var windows:[String:[NSRange]]=[:]
        for (written,ranges) in raw {windows[key(written),default:[]]+=ranges}
        var forms:[String:[Form]]=[:],blocked=Set<String>(),guards=Set<String>(),targetBlocked=Set<String>(),names=Set<String>(),count=0
        let inputs=windows.keys.sorted()
        for start in stride(from:0,to:inputs.count,by:200) {
            let batch=Array(inputs[start..<min(inputs.count,start+200)])
            for r in try query(db,"SELECT s.normalized,s.lexeme,s.surface,s.start,s.end,s.number,s.mode,l.source_safe,l.target_safe,s.features,l.pos,COALESCE(g.reason,''),COALESCE(g.target_blocked,0),l.normalized FROM surfaces s JOIN lexemes l ON l.id=s.lexeme LEFT JOIN guards g ON g.normalized=l.normalized WHERE s.normalized IN (\(marks(batch.count))) ORDER BY s.normalized,s.lexeme",batch,limit:16384-count) {
                count+=1
                guard let a=Int(r[3]),let b=Int(r[4]),let n=Int(r[5]),let m=Int(r[6]) else {throw VocabularyPackError.invalid}
                let form=Form(key:r[0],lexeme:r[1],written:r[2],start:a,end:b,number:n,mode:m,sourceSafe:r[7]=="1",targetSafe:r[8]=="1",features:Set(try JSONDecoder().decode([String].self,from:Data(r[9].utf8))),pos:r[10],proper:["name","proper-noun","proper_noun"].contains(r[10]),grammar:["pron","det","prep","postp","conj","particle","article","aux"].contains(r[10]) || r[11]=="grammar" || r[12]=="1",head:r[13])
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
            for r in try query(db,"SELECT t.lexeme,t.sense,t.reading,t.eligible,s.explicit,s.source_url FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme IN (\(marks(batch.count))) ORDER BY t.lexeme,t.sense,t.reading",batch,limit:32768-count) {
                count+=1;terms[r[0],default:[]].append(Term(sense:r[1],reading:r[2],eligible:r[3]=="1",explicit:r[4]=="1",family:r[5]))
            }
        }
        var surfaceReadings:[ReadingKey:[String:Set<String>]]=[:]
        if hasSurfaceReadings {
            count=0
            for start in stride(from:0,to:inputs.count,by:200) {
                let batch=Array(inputs[start..<min(inputs.count,start+200)])
                for r in try query(db,"SELECT lexeme,normalized,reading,sense FROM surface_readings WHERE normalized IN (\(marks(batch.count))) ORDER BY normalized,lexeme,reading",batch,limit:16384-count) {
                    count+=1
                    guard !r[2].isEmpty,r[2].utf16.count<=96 else {throw VocabularyPackError.invalid}
                    surfaceReadings[ReadingKey(lexeme:r[0],word:r[1]),default:[:]][r[3],default:[]].insert(r[2])
                }
            }
        }
        return Side(windows:windows,forms:forms,terms:terms,surfaceReadings:surfaceReadings,blocked:blocked,targetBlocked:targetBlocked,names:names,guards:guards,inventory:inventory,release:release,namedPlaces:namedPlaces(text,language:language),phrases:phrases(text,language:language))
    }
    // Unmarked common nouns can have plural reference in these languages.
    // Explicit number, verb forms and grammatical analyses stay constrained.
    private static func numberCompatible(_ a:Form,_ b:Form,source:String,target:String)->Bool {
        if a.number==b.number {return true}
        guard a.pos=="noun",b.pos=="noun",!a.grammar,!b.grammar else {return false}
        func unmarked(_ f:Form,_ language:String)->Bool {
            ["zh","ja","ko"].contains(language) && f.number==0 && (1...2).contains(f.mode) &&
                f.features.isDisjoint(with:["singular","plural","dual"])
        }
        return (a.number==2 && unmarked(b,target)) || (b.number==2 && unmarked(a,source))
    }
    private static func linkedTerms(_ side:Side,_ form:Form)->[Term] {
        let terms=side.terms[form.lexeme,default:[]]
        guard !form.features.isDisjoint(with:surfaceReadingRules) else {return terms}
        guard (3...4).contains(form.mode) else {return []}
        let senses=Set(side.surfaceReadings[ReadingKey(lexeme:form.lexeme,word:form.key),default:[:]].keys)
        return terms.filter{senses.contains($0.sense)}
    }
    private static func readings(_ side:Side,_ form:Form,_ meanings:Set<String>)->Set<String> {
        let linked=linkedTerms(side,form).filter{$0.eligible && meanings.contains($0.sense)}
        guard !linked.isEmpty else {return []}
        // Never pronounce an inflected carrier using its singular headword.
        if !form.features.isDisjoint(with:surfaceReadingRules) {
            return (3...4).contains(form.mode) ? Set(side.surfaceReadings[ReadingKey(lexeme:form.lexeme,word:form.key),default:[:]].filter{meanings.contains($0.key)}.values.flatMap{$0}) : []
        }
        return Set(linked.map(\.reading).filter{!$0.isEmpty})
    }
    private static func shape(_ form:Form)->[Int] {
        [form.mode==3 ? form.start : 0,form.mode==3 ? form.end : 0,form.number,form.mode==3 ? 3 : 1]
    }
    private static func focus(_ form:Form,range:NSRange,text:String)->NSRange? {
        guard (1...5).contains(form.mode) else {return nil}
        if (1...2).contains(form.mode) {return range}
        let actual=(text as NSString).substring(with:range)
        if (4...5).contains(form.mode) && (form.start != 0 || form.end != actual.utf16.count) {return nil}
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
        side.namedPlaces.contains{NSIntersectionRange($0,range).length>0} || containedInPhrase(side,range:range) || side.guards.contains { word in side.windows[word,default:[]].contains { whole in
            whole.location<=range.location && NSMaxRange(whole)>=NSMaxRange(range) && whole != range
        }}
    }
    private static func containedInPhrase(_ side:Side,range:NSRange)->Bool {
        side.phrases.contains{$0.location<=range.location && NSMaxRange($0)>=NSMaxRange(range) && $0 != range}
    }
    private static let presentComplements:[String:Set<String>]=["live":["with"],"work":["at","from","in","on"],"wait":["for"],"listen":["to"],"talk":["to","with","about"],"speak":["to","with","about"],"write":["to","about"],"think":["about"],"learn":["about","from"],"help":["with"],"travel":["to","from"],"walk":["to","from"]]
    private static func protectedPresent(_ side:Side,range:NSRange,text:String,language:String)->Bool {
        let pronounUnits:[String:String]=language=="en" ? ["i miss you":"miss","i love you":"love","love you":"love"] : (language=="es" ? ["te amo":"amar"] : [:])
        let pronominal=PresentVerbGrammar.pronominalClause(text,focus:range,language:language)
        if language != "en" && !pronominal {return protected(side,range:range)}
        if side.namedPlaces.contains(where:{NSIntersectionRange($0,range).length>0}) || containedInPhrase(side,range:range) {return true}
        let forms=side.forms[key((text as NSString).substring(with:range)),default:[]].filter(completePresent)
        return side.guards.contains { word in side.windows[word,default:[]].contains { whole in
            guard whole.location<=range.location,NSMaxRange(whole)>=NSMaxRange(range),whole != range else {return false}
            let parts=word.components(separatedBy:" ")
            let assessedPronounUnit=pronominal && !forms.isEmpty && forms.allSatisfy{pronounUnits[word]==$0.head}
            return !assessedPronounUnit && !(language=="en" && whole.location==range.location && parts.count==2 && !forms.isEmpty &&
                forms.allSatisfy{parts[0]==$0.key && presentComplements[$0.head,default:[]].contains(parts[1])})
        }}
    }
    private static func protectedTarget(_ side:Side,range:NSRange,text:String,language:String,features:Set<String>)->Bool {
        if side.namedPlaces.contains(where:{NSIntersectionRange($0,range).length>0}) || containedInPhrase(side,range:range) {return true}
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
    private static func completePast(_ form:Form)->Bool {
        form.mode==4 && form.pos=="verb" && form.targetSafe && !form.grammar && form.features.contains(pastRule)
    }
    private static func pastGrammar(_ form:Form,analyses:[Form],text:String,range:NSRange,language:String)->Bool {
        guard completePast(form) else {return false}
        if language=="en" {
            if analyses.contains(where:{$0.pos=="verb" && (1...2).contains($0.mode) && $0.head==$0.key && $0.head != form.head}) {return false}
            if analyses.contains(where:{$0.pos != "verb" && $0.targetSafe}) && !hasFinitePastSubject(text,start:range.location) {return false}
        }
        return form.features.contains("past-source-unambiguous") ||
            (language=="en" && form.features.contains("past-source-requires-finite-clause") && hasFinitePastSubject(text,start:range.location))
    }
    private static func completeNoun(_ form:Form)->Bool {
        form.pos=="noun" && (1...2).contains(form.mode) && form.targetSafe &&
        !form.grammar && !form.proper && form.start==0 && form.end==form.written.utf16.count
    }
    private static func completePresent(_ form:Form)->Bool {
        form.mode==5 && form.pos=="verb" && form.targetSafe && (!form.grammar || form.head=="need") && form.features.contains(presentRule)
    }
    private static func completeVerb(_ form:Form,mode:Int)->Bool {
        mode==4 ? completePast(form) : completePresent(form)
    }
    private static func verbKey(_ form:Form,mode:Int)->String {
        (mode==4 ? "@past:" : "@present:")+form.head
    }
    private static func verbGrammar(_ form:Form,analyses:[Form],text:String,range:NSRange,language:String,mode:Int)->Bool {
        if mode==4 {return pastGrammar(form,analyses:analyses,text:text,range:range,language:language)}
        return completePresent(form) &&
            (!form.grammar || (language=="en" && form.head=="need" && PresentVerbGrammar.pronominalClause(text,focus:range,language:language))) &&
            !(language=="en" && analyses.contains{$0.mode==4 && $0.lexeme != form.lexeme}) &&
            !PresentVerbGrammar.people(form.features,text:text,start:range.location,language:language).isEmpty
    }
    private static func contextualEntries(left:Side,right:Side,db:OpaquePointer,original:String,translation:String,source:String,target:String,
        strict:[VocabularyEntry],alignment:SentenceAlignment,diagnostic:(String)->Void,wholeMode:Int=0) throws -> [VocabularyEntry] {
        var targetKeys=Set<String>()
        for (word,forms) in right.forms {for form in forms {for carrier in right.windows[word,default:[]] {
            if wholeMode != 0 && !completeVerb(form,mode:wholeMode) {continue}
            if let range=focus(form,range:carrier,text:translation) {targetKeys.insert(wholeMode != 0 ? verbKey(form,mode:wholeMode) : key((translation as NSString).substring(with:range)))}
        }}}
        var sourceKeys=Set<String>()
        for (word,forms) in left.forms {for form in forms {for carrier in left.windows[word,default:[]] {
            if wholeMode != 0 && !completeVerb(form,mode:wholeMode) {continue}
            if let range=focus(form,range:carrier,text:original) {sourceKeys.insert(wholeMode != 0 ? verbKey(form,mode:wholeMode) : key((original as NSString).substring(with:range)))}
        }}}
        guard let evidence=try ContextWitnessLookup.load(db,original:original,source:source,target:target,release:left.release,sources:sourceKeys,targets:targetKeys,contextKeys:Set(left.windows.keys)) else {return []}
        // Reciprocal evidence is anchored to independently accepted nearby
        // vocabulary in both messages, with the original sentence boundaries.
        let reverseEvidence=wholeMode==5 ? try ContextWitnessLookup.load(db,original:translation,source:target,target:source,release:right.release,sources:targetKeys,targets:sourceKeys,contextKeys:Set(right.windows.keys)) : nil
        let lexicalWindows=left.windows.filter { word,_ in
            let forms=left.forms[word,default:[]],names=left.forms[word,default:[]].filter(\.proper)
            return (!left.blocked.contains(word) || (left.names.contains(word) && !names.isEmpty && names.allSatisfy{$0.written.first?.isUppercase==true})) &&
                forms.contains{$0.targetSafe} && !forms.contains{$0.grammar}
        }.mapValues { ranges in ranges.filter { range in
            let word=key((original as NSString).substring(with:range))
            return !left.names.contains(word) || (original as NSString).substring(with:range).first?.isLowercase==true
        }}
        func reverseWindows(_ focus:NSRange)->[String:[NSRange]] {
            guard reverseEvidence != nil else {return [:]}
            let anchors=Set(strict.compactMap { e -> NSRange? in
                guard let a=e.sourceScope,let b=e.targetScope,a.original==original,b.translation==translation else {return nil}
                let sourceRange=NSRange(location:a.start,length:a.end-a.start)
                guard lexicalWindows.values.contains(where:{$0.contains(sourceRange)}),
                    evidence.hasNearbyContext(focus:focus,text:original,windows:["anchor":[sourceRange]]) else {return nil}
                return NSRange(location:b.start,length:b.end-b.start)
            })
            return right.windows.mapValues{$0.filter{anchors.contains($0)}}.filter{!$0.value.isEmpty}
        }
        let needsReading=["ar","zh","ja","ko"].contains(target)
        struct Claim:Hashable {let sourceRange:NSRange,range:NSRange,reading:String}
        struct SourceShape:Hashable {let range:NSRange,number:Int}
        var output:[VocabularyEntry]=[]
        for word in left.forms.keys.sorted() {
            let forms=left.forms[word,default:[]]
            let contextualNeed=wholeMode==5 && source=="en" && forms.contains{completePresent($0) && $0.head=="need"}
            guard !left.targetBlocked.contains(word),(!forms.contains(where:{$0.grammar}) || contextualNeed) else {continue}
            for carrier in Set(left.windows[word,default:[]]) {
                guard alignment.uniqueSource(carrier,left.windows[word,default:[]].filter{wholeMode==5 ? !protectedPresent(left,range:$0,text:original,language:source) : !protected(left,range:$0)}) else {continue}
                let transparentSource=wholeMode==5 && protected(left,range:carrier) && !protectedPresent(left,range:carrier,text:original,language:source)
                guard !(wholeMode==5 ? protectedPresent(left,range:carrier,text:original,language:source) : protected(left,range:carrier)),!strict.contains(where:{ e in
                    guard let scope=e.sourceScope else {return false}
                    return scope.start<NSMaxRange(carrier) && carrier.location<scope.end
                }) else {continue}
                let actual=(original as NSString).substring(with:carrier)
                let lexicalNeed=contextualNeed && PresentVerbGrammar.pronominalClause(original,focus:carrier,language:source)
                if left.blocked.contains(word) && !lexicalNeed {
                    let proper=forms.filter(\.proper)
                    guard left.names.contains(word),actual.first?.isLowercase==true,!proper.isEmpty,
                        proper.allSatisfy({$0.written.first?.isUppercase==true}) else {continue}
                }
                let usable=forms.filter { form in
                    form.targetSafe && key(actual)==key(form.written) &&
                    (wholeMode != 0 ? verbGrammar(form,analyses:forms,text:original,range:carrier,language:source,mode:wholeMode) && targetCaseMatches(form,range:carrier,text:original)
                        : (1...3).contains(form.mode) && actual.first?.isUppercase==form.written.first?.isUppercase)
                }
                let focuses=Set(usable.compactMap { form in
                    focus(form,range:carrier,text:original).map{SourceShape(range:$0,number:form.number)}
                })
                // A conflicting carrier may be resolved only as a whole noun with
                // a noun counterpart and a nearby lexical witness.
                let conflictingGeometry=usable.contains(where:{$0.mode==3}) && focuses.count != 1
                let allForms=wholeMode != 0 ? forms.filter{$0.targetSafe && key(actual)==key($0.written)} : usable
                let allMeanings=Set(allForms.flatMap{linkedTerms(left,$0)}.filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                var claims=Set<Claim>(),reverseClaims=Set<Claim>(),pronounClaims=Set<Claim>()
                for form in usable {
                    if conflictingGeometry && (form.pos != "noun" || !(1...2).contains(form.mode)) {continue}
                    guard let sourceFocus=focus(form,range:carrier,text:original) else {continue}
                    let meanings=Set(linkedTerms(left,form).filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                    if meanings.isEmpty {continue}
                    let anchoredReverse=reverseWindows(sourceFocus)
                    let sourcePronounClause=wholeMode==5 && PresentVerbGrammar.pronominalClause(original,focus:sourceFocus,language:source)
                    let features=forms.filter{$0.lexeme==form.lexeme && $0.mode==form.mode}.map(\.features).reduce(form.features){$0.intersection($1)}
                    for other in right.forms.keys.sorted() {
                        guard !right.targetBlocked.contains(other) else {continue}
                        let targets=right.forms[other,default:[]]
                        for candidate in Set(targets) {
                            let readings=readings(right,candidate,meanings)
                            if needsReading && readings.count != 1 {continue}
                            if conflictingGeometry && (candidate.pos != "noun" || candidate.grammar) {continue}
                            guard candidate.targetSafe,!(candidate.features.contains("abbreviation") && targets.contains{$0.grammar}),(wholeMode != 0 ? completeVerb(candidate,mode:wholeMode) : (1...3).contains(candidate.mode)),numberCompatible(form,candidate,source:source,target:target),
                                  linkedTerms(right,candidate).contains(where:{$0.eligible && meanings.contains($0.sense)}) else {continue}
                            let targetMeanings=Set(linkedTerms(right,candidate).filter(\.eligible).map(\.sense))
                            // Narrower meanings must explain nearby lexical context;
                            // a common grammatical cue alone is insufficient there.
                            let narrow = !targetMeanings.isSuperset(of:allMeanings) || targets.contains{$0.grammar}
                            let nearbyLexical=evidence.hasNearbyContext(focus:sourceFocus,text:original,windows:lexicalWindows)
                            if (conflictingGeometry || (transparentSource && !sourcePronounClause)) && !nearbyLexical {continue}
                            let cueWindows = conflictingGeometry || transparentSource || (narrow && nearbyLexical) ? lexicalWindows : left.windows
                            for targetCarrier in Set(right.windows[other,default:[]]) {
                                if wholeMode != 0 && !verbGrammar(candidate,analyses:targets,text:translation,range:targetCarrier,language:target,mode:wholeMode) {continue}
                                if wholeMode==5 && PresentVerbGrammar.people(form.features,text:original,start:carrier.location,language:source)
                                    .intersection(PresentVerbGrammar.people(candidate.features,text:translation,start:targetCarrier.location,language:target)).isEmpty {continue}
                                let isProtected=protectedTarget(right,range:targetCarrier,text:translation,language:target,features:features)
                                let transparentTarget=wholeMode==5 && isProtected && !protectedPresent(right,range:targetCarrier,text:translation,language:target)
                                guard (!isProtected || transparentTarget),(!transparentTarget || nearbyLexical || sourcePronounClause),
                                    targetCaseMatches(candidate,range:targetCarrier,text:translation),let targetFocus=focus(candidate,range:targetCarrier,text:translation) else {continue}
                                guard alignment.permits(sourceFocus,targetFocus) else {continue}
                                if strict.contains(where:{ e in
                                    guard let scope=e.targetScope else {return false}
                                    return scope.start<NSMaxRange(targetFocus) && targetFocus.location<scope.end
                                }) {continue}
                                let sourceKey=wholeMode != 0 ? verbKey(form,mode:wholeMode) : key((original as NSString).substring(with:sourceFocus))
                                let targetKey=wholeMode != 0 ? verbKey(candidate,mode:wholeMode) : key((translation as NSString).substring(with:targetFocus))
                                let sharedMeanings=meanings.intersection(targetMeanings)
                                let pronounClause=wholeMode==5 && PresentVerbGrammar.pronominalClause(original,focus:sourceFocus,language:source) &&
                                    PresentVerbGrammar.pronominalClause(translation,focus:targetFocus,language:target)
                                if (transparentSource || transparentTarget) && !nearbyLexical && !pronounClause {continue}
                                let selectedWindows=pronounClause ? left.windows : (wholeMode==5 || transparentTarget ? lexicalWindows : cueWindows)
                                let nounMeanings=wholeMode==0 && completeNoun(form) && completeNoun(candidate) ? sharedMeanings : []
                                let forward=evidence.supports(word:sourceKey,counterpart:targetKey,focus:sourceFocus,text:original,windows:selectedWindows,allowedMeanings:sharedMeanings,allowedNounMeanings:nounMeanings)
                                let reverse=wholeMode==5 && reverseEvidence?.supports(word:targetKey,counterpart:sourceKey,focus:targetFocus,text:translation,windows:anchoredReverse,allowedMeanings:sharedMeanings)==true
                                if forward || reverse {
                                    let claim=Claim(sourceRange:sourceFocus,range:targetFocus,reading:needsReading ? readings.first! : "")
                                    claims.insert(claim)
                                    if !forward && reverse {reverseClaims.insert(claim)}
                                    if forward && pronounClause {pronounClaims.insert(claim)}
                                }
                            }
                        }
                    }
                }
                guard claims.count==1,let claim=claims.first else {continue}
                let targetText=(translation as NSString).substring(with:claim.range)
                if reverseClaims.contains(claim) {diagnostic("present_reverse_candidate")}
                if pronounClaims.contains(claim) {diagnostic("present_pronominal_candidate")}
                diagnostic(wholeMode==4 ? "past_context_candidate" : (wholeMode==5 ? "present_context_candidate" : "context_witness_candidate"))
                output.append(VocabularyEntry(source:(original as NSString).substring(with:claim.sourceRange),targets:[targetText],romanizations:needsReading ? [targetText:[claim.reading]] : [:],
                    sourceScope:VocabularySourceScope(original:original,start:claim.sourceRange.location,end:NSMaxRange(claim.sourceRange)),
                    targetScope:VocabularyTargetScope(translation:translation,start:claim.range.location,end:NSMaxRange(claim.range))))
            }
        }
        return output
    }
    static func entries(leftDB:OpaquePointer,rightDB:OpaquePointer,original:String,translation:String,source:String,target:String,witnessDB:OpaquePointer?=nil,diagnostic:(String)->Void={_ in}) throws -> [VocabularyEntry] {
        try autoreleasepool {
            try lookup(leftDB:leftDB,rightDB:rightDB,original:original,translation:translation,source:source,target:target,witnessDB:witnessDB,diagnostic:diagnostic)
        }
    }
    private static func lookup(leftDB:OpaquePointer,rightDB:OpaquePointer,original:String,translation:String,source:String,target:String,witnessDB:OpaquePointer?,diagnostic:(String)->Void) throws -> [VocabularyEntry] {
        guard original.utf16.count<=16384,translation.utf16.count<=32768,source != target else {return []}
        do {
            guard let left=try load(leftDB,text:original,language:source),let right=try load(rightDB,text:translation,language:target) else {return []}
            guard left.inventory==right.inventory && left.release==right.release else {throw VocabularyPackError.invalid}
            let alignment=SentenceAlignment(original,translation)
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
                // One coarse native gloss cannot resolve several linked senses.
                let families=Dictionary(grouping:linkedTerms(left,form).filter{$0.eligible && $0.explicit},by:{$0.family})
                let ambiguousFamilies=families.values.map{Set($0.map(\.sense))}.filter{$0.count>1}
                if !ambiguousFamilies.isEmpty && target != "en" {diagnostic("linked_sense_ambiguity");continue}
                let features=forms.filter{$0.lexeme==form.lexeme && $0.mode==form.mode}.map(\.features).reduce(form.features){$0.intersection($1)}
                let meanings=Set(linkedTerms(left,form).filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                if meanings.isEmpty {diagnostic("no_eligible_link");continue}
                for carrier in Set(left.windows[word,default:[]]) {
                    guard alignment.uniqueSource(carrier,left.windows[word,default:[]].filter{!protected(left,range:$0)}) else {continue}
                    guard !protected(left,range:carrier) else {diagnostic("source_compound");continue}
                    guard targetCaseMatches(form,range:carrier,text:original) else {diagnostic("source_case");continue}
                    guard let sourceFocus=focus(form,range:carrier,text:original) else {continue}
                    var claims=Set<Claim>()
                    for other in right.forms.keys.sorted() {
                        guard !right.targetBlocked.contains(other) else {continue}
                        let targets=right.forms[other,default:[]]
                        for candidate in Set(targets) {
                            let readings=readings(right,candidate,meanings)
                            if needsReading && readings.count != 1 {continue}
                            guard candidate.targetSafe,!(candidate.features.contains("abbreviation") && targets.contains{$0.grammar}),(1...3).contains(candidate.mode),numberCompatible(form,candidate,source:source,target:target),
                                  linkedTerms(right,candidate).contains(where:{$0.eligible && meanings.contains($0.sense)}) else {continue}
                            let targetMeanings=Set(linkedTerms(right,candidate).filter{$0.eligible}.map(\.sense))
                            guard ambiguousFamilies.allSatisfy({$0.isSubset(of:targetMeanings)}) else {continue}
                            for targetCarrier in Set(right.windows[other,default:[]]) {
                                guard !protectedTarget(right,range:targetCarrier,text:translation,language:target,features:features),targetCaseMatches(candidate,range:targetCarrier,text:translation),let targetFocus=focus(candidate,range:targetCarrier,text:translation) else {continue}
                                guard alignment.permits(sourceFocus,targetFocus) else {continue}
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
            if let witnessDB {
                output += try contextualEntries(left:left,right:right,db:witnessDB,original:original,translation:translation,source:source,target:target,strict:output,alignment:alignment,diagnostic:diagnostic)
                output += try contextualEntries(left:left,right:right,db:witnessDB,original:original,translation:translation,source:source,target:target,strict:output,alignment:alignment,diagnostic:diagnostic,wholeMode:4)
                output += try contextualEntries(left:left,right:right,db:witnessDB,original:original,translation:translation,source:source,target:target,strict:output,alignment:alignment,diagnostic:diagnostic,wholeMode:5)
            }
            return output
        } catch Limit.overflow {diagnostic("query_overflow");return []}
    }
}

/// Person evidence for supplied complete present verbs; native UTF-16 offsets.
private enum PresentVerbGrammar {
    // Grammatical-only cues are limited to an exact short pronoun clause.
    // All words are inspected, including unknown words outside the dictionary.
    static func pronominalClause(_ text:String,focus:NSRange,language:String)->Bool {
        let pronouns:Set<String>
        switch language {
        case "en":pronouns=["i","you","he","she","it","we","they","me","him","her","us","them"]
        case "es":pronouns=["yo","tú","vos","él","ella","usted","nosotros","nosotras","vosotros","vosotras","ellos","ellas","ustedes","me","te","lo","la","le","nos","os","los","las","les","se"]
        default:return false
        }
        let ns=text as NSString,stops=CharacterSet(charactersIn:".!?。！？;；\r\n…")
        let left=ns.rangeOfCharacter(from:stops,options:.backwards,range:NSRange(location:0,length:focus.location))
        let right=ns.rangeOfCharacter(from:stops,options:[],range:NSRange(location:NSMaxRange(focus),length:ns.length-NSMaxRange(focus)))
        let start=left.location==NSNotFound ? 0 : NSMaxRange(left),end=right.location==NSNotFound ? ns.length : right.location
        let words=LocalImmersion.words(text,language:language).filter{$0.location>=start && NSMaxRange($0)<=end}
        return (2...4).contains(words.count) && words.contains(focus) && words.filter{$0 != focus}.allSatisfy{pronouns.contains(ns.substring(with:$0).lowercased())}
    }
    private static let subjects:[String:[String:Set<String>]]=[
        "en": ["i":["1s"],"you":["2p","2s"],"he":["3s"],"she":["3s"],"it":["3s"],"we":["1p"],"they":["3p"]],
        "de": ["ich":["1s"],"du":["2s"],"er":["3s"],"sie":["3p","3s"],"es":["3s"],"wir":["1p"],"ihr":["2p"]],
        "fr": ["je":["1s"],"j'":["1s"],"j’":["1s"],"tu":["2s"],"il":["3s"],"elle":["3s"],"on":["3s"],"nous":["1p"],"vous":["2p"],"ils":["3p"],"elles":["3p"]],
        "es": ["yo":["1s"],"tú":["2s"],"vos":["2s"],"él":["3s"],"ella":["3s"],"usted":["3s"],"nosotros":["1p"],"nosotras":["1p"],"vosotros":["2p"],"vosotras":["2p"],"ellos":["3p"],"ellas":["3p"],"ustedes":["3p"]],
        "pt": ["eu":["1s"],"tu":["2s"],"ele":["3s"],"ela":["3s"],"você":["3s"],"nós":["1p"],"vós":["2p"],"eles":["3p"],"elas":["3p"],"vocês":["3p"]]
    ]
    private static let nonPresentAuxiliary=try! NSRegularExpression(pattern:#"(?i)(?<![\p{L}\p{M}\p{N}_])(?:did|didn['’]t|will|won['’]t|would|wouldn['’]t|can|can['’]t|could|couldn['’]t|shall|shan['’]t|should|shouldn['’]t|may|might|must|have|has|had|am|is|are|was|were)[ \t]+$"#)
    private static let previous=try! NSRegularExpression(pattern:#"(?<![\p{L}\p{M}\p{N}_])([\p{L}\p{M}]+['’]?)([ \t]*)$"#)
    static func people(_ features:Set<String>,text:String,start:Int,language:String)->Set<String> {
        guard start>=0,start<=text.utf16.count else {return []}
        let people=Set(features.filter{$0.hasPrefix("present-person-")}.map{String($0.dropFirst("present-person-".count))})
        let prefix=(text as NSString).substring(to:start)
        if let match=previous.firstMatch(in:prefix,range:NSRange(location:0,length:prefix.utf16.count)) {
            let word=(prefix as NSString).substring(with:match.range(at:1)).lowercased()
            if language=="en" {
                let before=(prefix as NSString).substring(to:match.range.location)
                if nonPresentAuxiliary.firstMatch(in:before,range:NSRange(location:0,length:before.utf16.count)) != nil {return []}
            }
            let nominal:[String:Set<String>]=[
                "es":["el","la","los","las","un","una","unos","unas","mi","mis","tu","tus","su","sus","nuestro","nuestra","vuestro","vuestra","este","esta","ese","esa"],
                "pt":["o","a","os","as","um","uma","uns","umas","meu","minha","teu","tua","seu","sua","nosso","nossa","vosso","vossa","este","esta","esse","essa"]]
            if match.range(at:2).length>0,nominal[language,default:[]].contains(word) {return []}
            if match.range(at:2).length>0 || ["j'","j’"].contains(word) {
                if let subject=subjects[language]?[word] {return people.intersection(subject)}
            }
        }
        return ["en","de","fr"].contains(language) ? [] : people
    }
}
