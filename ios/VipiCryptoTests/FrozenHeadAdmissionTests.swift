import Foundation
import SQLite3
import CryptoKit
import XCTest
@testable import Vipi

final class FrozenHeadAdmissionTests: XCTestCase {
    func testConditionalEvidenceAndVetoesOnFrozenFullMessages() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["VIPI_HEAD_ADMISSION_QA_DIRECTORY"] != nil,
                          "Explicit private frozen-source qualification only")
        let root=URL(fileURLWithPath:try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_HEAD_ADMISSION_QA_DIRECTORY"]))
        let config=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("bindings.json"))) as? [String:Any])
        let packRoot=URL(fileURLWithPath:try XCTUnwrap(config["pack_input_directory"] as? String))
        let expected=try XCTUnwrap(config["expected_metadata"] as? [String:String])
        let en=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
        let pack=try FrozenContextPack(url:packRoot.appendingPathComponent("context.sqlite"),expectedSHA256:"cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",expectedMetadata:expected,dictionaryURLs:["en":en,"es":packRoot.appendingPathComponent("d-es.sqlite")])
        XCTAssertEqual(pack.evidence.forms.count,326);XCTAssertEqual(pack.evidence.terms.count,651);XCTAssertEqual(pack.evidence.links.count,5328)
        XCTAssertEqual(pack.evidence.families.count,3011);XCTAssertEqual(pack.evidence.roles.count,6384);XCTAssertEqual(pack.evidence.functionWords.count,87)
        var pointer:OpaquePointer?;XCTAssertEqual(sqlite3_open_v2(en.path,&pointer,SQLITE_OPEN_READONLY,nil),SQLITE_OK)
        let db=try XCTUnwrap(pointer);defer{sqlite3_close(db)}
        let comparisonData=try Data(contentsOf:root.appendingPathComponent("frozen-comparison.json"))
        XCTAssertEqual(SHA256.hash(data:comparisonData).map{String(format:"%02x",$0)}.joined(),try XCTUnwrap(config["comparison_sha256"] as? String))
        let fixture=try XCTUnwrap(JSONSerialization.jsonObject(with:comparisonData) as? [String:Any])
        let cases=try XCTUnwrap(fixture["cases"] as? [[String:Any]]);XCTAssertEqual(cases.count,8)
        let adapter=try FrozenHeadAdmission(),provider=EnglishSourceRoleProvider();var output:[[String:Any]]=[]
        for row in cases {
            let text=try XCTUnwrap(row["source"] as? String),id=try XCTUnwrap(row["case_id"] as? String)
            let masks=try XCTUnwrap(row["protected_ranges_utf16"] as? [[Int]]).map{NSRange(location:$0[0],length:$0[1]-$0[0])}
            let native=LocalImmersion.words(text,language:"en")
            let recognition=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:text,language:"en",protectedRanges:masks))
            let role=provider.inspect(original:text,language:"en",wordRanges:native,protectedRanges:masks)
            let scopes=try XCTUnwrap(row["scopes"] as? [[String:Any]]);XCTAssertLessThanOrEqual(scopes.count,16)
            var results:[[String:Any]]=[]
            for (index,scope) in scopes.enumerated() {
                let r=try XCTUnwrap(scope["focus_utf16"] as? [Int]);let focus=NSRange(location:r[0],length:r[1]-r[0])
                let keyScope=FrozenHeadAdmission.KeyScope(original:text,focus:focus,keys:try XCTUnwrap(scope["source_keys"] as? [String]),identity:try XCTUnwrap(scope["key_scope_identity"] as? String),basis:try XCTUnwrap(scope["basis"] as? String))
                let tick=DispatchTime.now().uptimeNanoseconds
                let assessment=try adapter.assess(pack:pack,original:text,focus:focus,keyScope:keyScope,recognition:recognition,role:role,knownFamilyIDs:[])
                let elapsed=DispatchTime.now().uptimeNanoseconds-tick
                let known=try adapter.assess(pack:pack,original:text,focus:focus,keyScope:keyScope,recognition:recognition,role:role,knownFamilyIDs:assessment.knowledgeIDs)
                XCTAssertEqual(known.chosenRuleID,assessment.chosenRuleID)
                if !assessment.knowledgeIDs.isEmpty {XCTAssertTrue(known.rejectionReasons.contains("known_families"));XCTAssertTrue(known.heads.allSatisfy{!$0.conditionallyEligible})}
                for head in assessment.heads where head.conditionallyEligible {
                    XCTAssertNotNil(head.originalContext)
                    for tuple in head.supportedTuples {
                        let source=try XCTUnwrap(pack.evidence.forms[tuple.sourceFormID]);let target=try XCTUnwrap(pack.evidence.forms[tuple.targetFormID])
                        XCTAssertTrue((1...2).contains(source.mode));XCTAssertTrue((1...2).contains(target.mode));XCTAssertEqual(source.number,target.number)
                        XCTAssertEqual(pack.evidence.terms[tuple.sourceTermID]?.senseID,pack.evidence.terms[tuple.targetTermID]?.senseID)
                    }
                }
                if index==0 && native.contains(focus) {
                    let protection=masks+[focus]
                    let protectedRecognition=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:text,language:"en",protectedRanges:protection))
                    let protectedRole=provider.inspect(original:text,language:"en",wordRanges:native,protectedRanges:protection)
                    let blocked=try adapter.assess(pack:pack,original:text,focus:focus,keyScope:keyScope,recognition:protectedRecognition,role:protectedRole,knownFamilyIDs:[])
                    XCTAssertEqual(blocked.chosenRuleID,assessment.chosenRuleID);XCTAssertTrue(blocked.heads.allSatisfy{!$0.conditionallyEligible})
                }
                let stale=FrozenHeadAdmission.KeyScope(original:text+" ",focus:focus,keys:keyScope.keys,identity:keyScope.identity,basis:keyScope.basis)
                XCTAssertTrue(try adapter.assess(pack:pack,original:text,focus:focus,keyScope:stale,recognition:recognition,role:role,knownFamilyIDs:[]).rejectionReasons.contains("invalid_or_stale_key_scope"))
                results.append(["focus":[focus.location,focus.length],"chosen_rule":assessment.chosenRuleID as Any? ?? NSNull(),
                    "learned_context":assessment.learnedContext.map{[$0.location,$0.length]} as Any? ?? NSNull(),"classification":assessment.classification,
                    "knowledge_ids":assessment.knowledgeIDs,"reasons":assessment.rejectionReasons,"elapsed_ns":elapsed,
                    "heads":assessment.heads.map{ h -> [String:Any] in ["id":h.headID,"original_context":h.originalContext.map{[$0.location,$0.length]} as Any? ?? NSNull(),"target":h.target,"readings":h.originalReadingsJSON,"eligible":h.conditionallyEligible,"reasons":h.rejectionReasons,"tuples":h.supportedTuples.map{[$0.ruleID,$0.headID,$0.sourceFormID,$0.targetFormID,$0.sourceTermID,$0.targetTermID]}]},
                    "original_gate":scope["original_gate"]!,"original_admitted_head_ids":scope["original_admitted_head_ids"]!])
            }
            output.append(["case_id":id,"role_status":role.status.rawValue,"current_native_ranges":native.map{[$0.location,$0.length]},"results":results,
                "scope":"Conditional prebudget native evidence, not complete producer/selector parity or permission. Empty original gate scopes remain empty."])
        }
        let caseData=try Data(contentsOf:root.appendingPathComponent("case-table-receipt.json"))
        let controls=try XCTUnwrap(JSONSerialization.jsonObject(with:caseData) as? [String:Any]);let predicate=try FrozenSourceCase()
        for c in try XCTUnwrap(controls["controls"] as? [[String:Any]]) {
            let text=try XCTUnwrap(c["source"] as? String);XCTAssertEqual(predicate.isLower(text),c["islower"] as? Bool);XCTAssertEqual(predicate.firstIsUpper(text),c["first_isupper"] as? Bool)
        }
        let data=try JSONSerialization.data(withJSONObject:["schema":"vipi.native-head-admission.r01","cases":output,"case_table_sha256":FrozenSourceCaseTables.sha256,"no_display_permission":true],options:[.sortedKeys])
        XCTAssertLessThanOrEqual(data.count,4*1024*1024)
        let attachment=XCTAttachment(data:data,uniformTypeIdentifier:"public.json");attachment.name="conditional-head-admission-r01";attachment.lifetime = .keepAlways;add(attachment)
    }
}
