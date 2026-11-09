import Foundation
import SQLite3
import VipiCore

/// Actual native source observations for the disabled research producer. Own one
/// immutable dictionary handle per data identity; no customer call site installed.
final class FrozenNativeCandidateProvider {
    let dictionarySHA256:String
    private let db:OpaquePointer
    private let release:String,inventory:String
    private let roleProvider=EnglishSourceRoleProvider()
    init(dictionaryURL:URL,expectedSHA256:String,expectedRelease:String,expectedInventory:String)throws {
        guard try FrozenCandidateCatalog.digest(dictionaryURL,maximum:512<<20)==expectedSHA256 else{throw FrozenContextPack.Failure.identity}
        var pointer:OpaquePointer?;guard sqlite3_open_v2(dictionaryURL.path,&pointer,SQLITE_OPEN_READONLY|SQLITE_OPEN_NOMUTEX,nil)==SQLITE_OK,let pointer else{if let pointer{sqlite3_close(pointer)};throw FrozenContextPack.Failure.sqlite}
        guard sqlite3_exec(pointer,"PRAGMA query_only=ON;PRAGMA trusted_schema=OFF;BEGIN",nil,nil,nil)==SQLITE_OK else{sqlite3_close(pointer);throw FrozenContextPack.Failure.sqlite}
        do {guard try FrozenCandidateCatalog.digest(dictionaryURL,maximum:512<<20)==expectedSHA256 else{throw FrozenContextPack.Failure.identity}}catch{sqlite3_close(pointer);throw error}
        db=pointer;dictionarySHA256=expectedSHA256;release=expectedRelease;inventory=expectedInventory
    }
    deinit{sqlite3_close(db)}
    struct Snapshot {
        let input:FrozenCandidateProducer.Input
        let recognition:LexicalSourceRecognition.Snapshot
        let role:EnglishSourceRoleProvider.Snapshot
    }
    func inspect(original:String,protectedRanges:[NSRange])throws->Snapshot {
        let words=LocalImmersion.words(original,language:"en")
        let role=roleProvider.inspect(original:original,language:"en",wordRanges:words,protectedRanges:protectedRanges)
        guard let recognition=try LexicalConcordance.sourceRecognition(db:db,original:original,language:"en",protectedRanges:protectedRanges),
              recognition.matches(original:original,language:"en",dictionaryRelease:release,dictionaryInventory:inventory,protectedRanges:protectedRanges),
              role.matches(original:original,language:"en",wordRanges:words,protectedRanges:protectedRanges),
              let windows=ReviewedFrameLookup.windows(original,language:"en") else{throw FrozenContextPack.Failure.invalidGeometry}
        let roles=Dictionary(uniqueKeysWithValues:role.observations.map{o in (o.range,FrozenCandidateProducer.Observation(raw:o.rawLexicalTag.map{[$0]},mapped:role.status == .ready ? FrozenCandidateProducer.Observation.apple(o.rawLexicalTag):nil))})
        let masks=recognition.phraseRanges.enumerated().map{["unit_id":"native-phrase-\($0.offset)","utf16":FrozenCandidateProducer.pair($0.element)] as [String:Any]}+recognition.units.enumerated().filter{$0.element.protectsInner}.map{["unit_id":"native-unit-\($0.offset)","utf16":FrozenCandidateProducer.pair($0.element.range)] as [String:Any]}
        var guards:Set<NSRange>=[]
        for unit in recognition.units where words.contains(unit.range) {
            guard unit.hasNameGuard,unit.sourceBlocked,!unit.targetBlocked,
                  unit.forms.contains(where:{$0.mode>0 && $0.mode<=2 && $0.partOfSpeech=="noun" && $0.intrinsicRange==NSRange(location:0,length:$0.written.utf16.count)}) else{continue}
            var s:OpaquePointer?;guard sqlite3_prepare_v2(db,"SELECT blocked,target_blocked,reason FROM guards WHERE normalized=?",-1,&s,nil)==SQLITE_OK,let s else{throw FrozenContextPack.Failure.sqlite};defer{sqlite3_finalize(s)}
            sqlite3_bind_text(s,1,ImmersionEngine.lookupKey(unit.original),-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self));let status=sqlite3_step(s)
            guard status==SQLITE_ROW || status==SQLITE_DONE else{throw FrozenContextPack.Failure.sqlite}
            if status==SQLITE_ROW,sqlite3_column_int(s,0) != 0,sqlite3_column_int(s,1)==0,let p=sqlite3_column_text(s,2),String(cString:p)=="name"{guards.insert(unit.range)}
        }
        let input=FrozenCandidateProducer.Input(original:original,words:words,windows:windows.values.flatMap{$0}.sorted{($0.location,$0.length)<($1.location,$1.length)},protected:protectedRanges+recognition.namedPlaces+role.detectedNames,sourceMasks:masks,roles:roles,sourceNameOnlyGuards:guards,basis:"Actual native dictionary/role/window snapshot; supplied protection retained; no display approval")
        return .init(input:input,recognition:recognition,role:role)
    }
}


extension FrozenNativeCandidateProvider {
    /// A current native evidence assessment, still without display permission.
    /// Only indices supported by both the frozen context and current dictionary
    /// may enter this wrapper's selector. No shorter context is retried.
    struct Prepared {
        let snapshot: Snapshot
        let output: FrozenCandidateProducer.Output
        let dictionarySHA256: String
        let qualifiedIndices: [Int]
        let currentEvidence: [String:FrozenHeadAdmission.Assessment]
    }
    func prepare(original:String, protectedRanges:[NSRange], catalog:FrozenCandidateCatalog,
                 pack:FrozenContextPack)throws->Prepared {
        guard dictionarySHA256 == catalog.metadata["dictionary_en_sha256"],
              catalog.contextPackSHA256 == pack.contentSHA256 else{throw FrozenContextPack.Failure.identity}
        let snapshot=try inspect(original:original,protectedRanges:protectedRanges)
        let producer=try FrozenCandidateProducer(),admission=try FrozenHeadAdmission()
        let output=try producer.produce(snapshot.input,catalog:catalog,pack:pack)
        var eligible=Set(output.qualifiedIndices.filter{$0<output.ordinaryCount})
        var assessments:[String:FrozenHeadAdmission.Assessment]=[:]
        for key in output.gates.keys.sorted() {
            let gate=output.gates[key]!
            guard let indices=gate["candidate_indices"] as? [Int],let first=indices.first,
                  let keys=gate["source_keys"] as? [String],
                  let focusPair=output.candidates[first]["focus_utf16"] as? [Int] else{throw FrozenContextPack.Failure.malformed}
            let focus=FrozenCandidateProducer.range(focusPair)
            let scope=FrozenHeadAdmission.KeyScope(original:original,focus:focus,keys:keys,
                identity:FrozenCandidateCatalog.hash(output.bundleIdentity+"\n"+output.inputIdentity+"\n"+key),
                basis:"Eligible current candidate head keys, exact source context and immutable bundle")
            let assessed=try admission.assess(pack:pack,original:original,focus:focus,keyScope:scope,
                recognition:snapshot.recognition,role:snapshot.role,knownFamilyIDs:[])
            // Both assessments must have fixed the same context before any head
            // checks. A disagreement is an integrity failure, not a fallback.
            guard assessed.chosenRuleID == gate["chosen_rule_id"] as? String else{throw FrozenContextPack.Failure.identity}
            let supported=Set(assessed.heads.filter{assessed.rejectionReasons.isEmpty && $0.conditionallyEligible}.map(\.headID))
            for index in output.qualifiedIndices where indices.contains(index) {
                if let head=output.candidates[index]["head_id"] as? String,supported.contains(head){eligible.insert(index)}
            }
            assessments[key]=assessed
        }
        return .init(snapshot:snapshot,output:output,dictionarySHA256:dictionarySHA256,
            qualifiedIndices:eligible.sorted(),currentEvidence:assessments)
    }
    func select(_ prepared:Prepared,catalog:FrozenCandidateCatalog,knownFamilyIDs:Set<String>,
                withholdFunction:Bool,density:Double)throws->[String:Any] {
        guard prepared.dictionarySHA256 == dictionarySHA256,
              dictionarySHA256 == catalog.metadata["dictionary_en_sha256"] else{throw FrozenContextPack.Failure.identity}
        return try FrozenCandidateProducer().select(prepared.output,input:prepared.snapshot.input,
            expectedBundleIdentity:catalog.bundleIdentity,indices:prepared.qualifiedIndices,
            knownFamilyIDs:knownFamilyIDs,withholdFunction:withholdFunction,density:density)
    }
}
