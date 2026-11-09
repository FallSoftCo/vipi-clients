import Foundation
import SQLite3
#if os(iOS)
@testable import Vipi
#endif

enum FrozenCandidateQualification {
    static func guardRanges(_ text:String,words:[NSRange],db:OpaquePointer)throws->Set<NSRange> {
        let tokenizer=try FrozenContextTokenizer();var result:Set<NSRange>=[]
        for r in words {
            let key=try tokenizer.normalize((text as NSString).substring(with:r));var s:OpaquePointer?
            guard sqlite3_prepare_v2(db,"SELECT blocked,target_blocked,reason FROM guards WHERE normalized=?",-1,&s,nil)==SQLITE_OK,let s else{throw FrozenContextPack.Failure.sqlite};defer{sqlite3_finalize(s)}
            sqlite3_bind_text(s,1,key,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self));let code=sqlite3_step(s)
            if code==SQLITE_ROW,sqlite3_column_int(s,0) != 0,sqlite3_column_int(s,1)==0,let p=sqlite3_column_text(s,2),String(cString:p)=="name"{result.insert(r)}
            else if code != SQLITE_ROW && code != SQLITE_DONE{throw FrozenContextPack.Failure.sqlite}
        };return result
    }
    static func run(root:URL,en:URL,nativeEvidence:((String,[NSRange],FrozenCandidateCatalog,FrozenContextPack,[String])throws->[String:Any])? = nil,actual:((String,[NSRange])throws->(FrozenCandidateProducer.Input,[String:Any]))? = nil)throws->[String:Any] {
        let start=DispatchTime.now().uptimeNanoseconds
        let config=try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("bindings.json"))) as! [String:Any]
        let packRoot=URL(fileURLWithPath:config["pack_input_directory"] as! String),expected=config["expected_metadata"] as! [String:String]
        let pack=try FrozenContextPack(url:packRoot.appendingPathComponent("context.sqlite"),expectedSHA256:"cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",expectedMetadata:expected,dictionaryURLs:["en":en,"es":packRoot.appendingPathComponent("d-es.sqlite")])
        let catalog=try FrozenCandidateCatalog(url:root.appendingPathComponent("catalog.sqlite"),manifestURL:root.appendingPathComponent("manifest.json"),manifestSHA256:"9c0d7af245a599bfaadc07dc6fb84c41a3bf72b5e657adcee0b7b68efa96a281",contextPack:pack)
        let prepared=DispatchTime.now().uptimeNanoseconds-start,producer=try FrozenCandidateProducer()
        guard try FrozenCandidateCatalog.digest(root.appendingPathComponent("reference.json"),maximum:16<<20)=="34048ad4a8754c4097d0bf7c7a7eeddc4245df24817b4206a8f78381f9782be3" else{throw FrozenContextPack.Failure.identity}
        let reference=try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("reference.json"))) as! [String:Any]
        let familyOrder=reference["frozen_test_family_order"] as! [String]
        var db:OpaquePointer?;guard sqlite3_open_v2(en.path,&db,SQLITE_OPEN_READONLY,nil)==SQLITE_OK,let db else{throw FrozenContextPack.Failure.sqlite};defer{sqlite3_close(db)}
        var records:[[String:Any]]=[]
        for row in reference["cases"] as! [[String:Any]] {
            let text=row["original"] as! String,words=(row["native_words_utf16"] as! [[Int]]).map(FrozenCandidateProducer.range),protection=(row["protected_ranges_utf16"] as! [[Int]]).map(FrozenCandidateProducer.range)
            var roles:[NSRange:FrozenCandidateProducer.Observation]=[:]
            for c in row["candidates"] as! [[String:Any]] {let role=c["role"] as! [String:Any],r=FrozenCandidateProducer.range(c["focus_utf16"] as! [Int]);roles[r] = .init(raw:role["raw"] as? [Any],mapped:role["mapped"] as? String)}
            let input=FrozenCandidateProducer.Input(original:text,words:words,windows:(row["native_windows_utf16"] as! [[Int]]).map(FrozenCandidateProducer.range),protected:protection,sourceMasks:row["source_masks"] as! [[String:Any]],roles:roles,sourceNameOnlyGuards:try guardRanges(text,words:words,db:db),basis:"Frozen geometry/masks/OpenNLP observations; actual immutable dictionary guard read; diagnostic only")
            func result(_ input:FrozenCandidateProducer.Input)throws->[String:Any]{
                let tick=DispatchTime.now().uptimeNanoseconds,out=try producer.produce(input,catalog:catalog,pack:pack);let duration=DispatchTime.now().uptimeNanoseconds-tick
                // Same geometry and character count cannot authorize stale original text.
                let changedText = input.original.isEmpty ? "x" : "#"+String(input.original.dropFirst())
                let stale=FrozenCandidateProducer.Input(original:changedText,words:input.words,windows:input.windows,protected:input.protected,sourceMasks:input.sourceMasks,roles:input.roles,sourceNameOnlyGuards:input.sourceNameOnlyGuards,basis:input.basis)
                do {_ = try producer.select(out,input:stale,expectedBundleIdentity:catalog.bundleIdentity,indices:out.qualifiedIndices,knownFamilyIDs:[],withholdFunction:false,density:0.25);throw FrozenContextPack.Failure.malformed} catch FrozenContextPack.Failure.identity {}
                let changedMasks=FrozenCandidateProducer.Input(original:input.original,words:input.words,windows:input.windows,protected:input.protected+[NSRange(location:0,length:1)],sourceMasks:input.sourceMasks,roles:input.roles,sourceNameOnlyGuards:input.sourceNameOnlyGuards,basis:input.basis)
                do {_ = try producer.select(out,input:changedMasks,expectedBundleIdentity:catalog.bundleIdentity,indices:out.qualifiedIndices,knownFamilyIDs:[],withholdFunction:false,density:0.25);throw FrozenContextPack.Failure.malformed} catch FrozenContextPack.Failure.identity {}
                do {_ = try producer.select(out,input:input,expectedBundleIdentity:"different-pack",indices:out.qualifiedIndices,knownFamilyIDs:[],withholdFunction:false,density:0.25);throw FrozenContextPack.Failure.malformed} catch FrozenContextPack.Failure.identity {}
                var selected:[String:Any]=[:]
                for (name,known) in [("all_function",Set<String>()),("all_function_global300",Set(familyOrder.prefix(300)))] {
                    let base=out.candidates.indices.filter{$0<out.ordinaryCount && (out.candidates[$0]["filter_reasons"] as! [String]).isEmpty},all=out.candidates.indices.filter{(out.candidates[$0]["filter_reasons"] as! [String]).isEmpty}
                    selected[name]=["baseline":try producer.select(out,input:input,expectedBundleIdentity:catalog.bundleIdentity,indices:base,knownFamilyIDs:known,withholdFunction:true,density:0.25),"experimental":try producer.select(out,input:input,expectedBundleIdentity:catalog.bundleIdentity,indices:all,knownFamilyIDs:known,withholdFunction:true,density:0.25),"qualified":try producer.select(out,input:input,expectedBundleIdentity:catalog.bundleIdentity,indices:out.qualifiedIndices,knownFamilyIDs:known,withholdFunction:true,density:0.25)]
                }
                // Explicit empty actual-user-known set; frequency controls above are diagnostics only.
                let emptyUser=try producer.select(out,input:input,expectedBundleIdentity:catalog.bundleIdentity,indices:out.qualifiedIndices,knownFamilyIDs:[],withholdFunction:false,density:0.25)
                return ["candidates":out.candidates,"baseline_candidate_count":out.ordinaryCount,"geometry_rejections":out.geometryRejections,"experimental_geometry_rejections":out.conditionalGeometryRejections,"gates":out.gates,"selections":selected,"empty_actual_known_selection":emptyUser,"elapsed_ns":duration,"input_identity":out.inputIdentity,"bundle_identity":out.bundleIdentity,"stale_bundle_rejected":true,"stale_text_rejected":true,"changed_protection_rejected":true,"native_words_utf16":input.words.map(FrozenCandidateProducer.pair),"protected_ranges_utf16":input.protected.map(FrozenCandidateProducer.pair),"source_masks":input.sourceMasks,"basis":input.basis]
            }
            var record:[String:Any]=["case_id":row["case_id"]!,"diagnostic":try result(input)]
            if let actual{let(value,metadata)=try actual(text,protection);record["actual"]=try result(value);record["actual_metadata"]=metadata}
            if let nativeEvidence {record["current_evidence"]=try nativeEvidence(text,protection,catalog,pack,familyOrder)}
            records.append(record)
        }
        return ["cases":records,"identity_preparation_ns":prepared,"manifest_sha256":"9c0d7af245a599bfaadc07dc6fb84c41a3bf72b5e657adcee0b7b68efa96a281","catalog_sha256":catalog.sha256,"actual_role_mapping":["Noun":"noun","Adjective":"adj","Adverb":"adv"],"limits":"Diagnostic frozen observations are implementation parity, not fresh gold. Actual provider/mask differences retained. No SourceLookupEvidence or app activation. Loaded immutable catalog and pack retained across all52 cases."]
    }
}
