import Foundation
import SQLite3
import CryptoKit
import XCTest
@testable import Vipi

final class LexicalSourceRecognitionTests: XCTestCase {
    private func guards(_ db: OpaquePointer, key: String) throws -> [String]? {
        var statement: OpaquePointer?
        XCTAssertEqual(sqlite3_prepare_v2(db,"SELECT blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized=?",-1,&statement,nil),SQLITE_OK)
        let s=try XCTUnwrap(statement);defer { sqlite3_finalize(s) }
        let transient=unsafeBitCast(-1,to:sqlite3_destructor_type.self)
        XCTAssertEqual(sqlite3_bind_text(s,1,key,-1,transient),SQLITE_OK)
        let status=sqlite3_step(s)
        if status==SQLITE_DONE { return nil }
        XCTAssertEqual(status,SQLITE_ROW)
        return (0..<4).map { i in sqlite3_column_text(s,Int32(i)).map { String(cString:$0) } ?? "" }
    }
    func testRealDictionarySnapshotRangesGuardsAndProtection() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["VIPI_FROZEN_CONTEXT_QA_DIRECTORY"] != nil,
                          "Explicit qualification requires the hash-bound private dictionary inputs")
        let en=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
        let file=try FileHandle(forReadingFrom:en);defer { try? file.close() };var hash=SHA256()
        while let data=try file.read(upToCount:1<<20),!data.isEmpty { hash.update(data:data) }
        XCTAssertEqual(hash.finalize().map { String(format:"%02x",$0) }.joined(),"5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68")
        var pointer:OpaquePointer?;XCTAssertEqual(sqlite3_open_v2(en.path,&pointer,SQLITE_OPEN_READONLY,nil),SQLITE_OK)
        let db=try XCTUnwrap(pointer);defer { sqlite3_close(db) }
        let fixture=try XCTUnwrap(Data(base64Encoded:EnglishSourceRoleFixture.base64))
        let input=try XCTUnwrap(JSONSerialization.jsonObject(with:fixture) as? [String:Any])
        let rows=try XCTUnwrap(input["cases"] as? [[String:Any]]);XCTAssertEqual(rows.count,52)
        var observations:[[String:Any]]=[]
        for row in rows {
            let source=try XCTUnwrap(row["source"] as? String)
            let masks=try XCTUnwrap(row["protected_ranges_utf16"] as? [[Int]]).map { NSRange(location:$0[0],length:$0[1]-$0[0]) }
            let snapshot=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:source,language:"en",protectedRanges:masks), "Missing recognition for \(row["case_id"] ?? "unknown")")
            XCTAssertTrue(snapshot.matches(original:source,language:"en",dictionaryRelease:snapshot.dictionaryRelease,dictionaryInventory:snapshot.dictionaryInventory,protectedRanges:masks))
            XCTAssertFalse(snapshot.matches(original:source+" ",language:"en",dictionaryRelease:snapshot.dictionaryRelease,dictionaryInventory:snapshot.dictionaryInventory,protectedRanges:masks))
            XCTAssertEqual(snapshot.suppliedProtection,masks)
            for mask in masks { XCTAssertTrue(snapshot.hasStructuralProtection(at:mask)) }
            for unit in snapshot.units {
                XCTAssertTrue(LexicalSourceRecognition.valid(unit.range,in:source))
                XCTAssertEqual(Array(unit.original.utf8),Array((source as NSString).substring(with:unit.range).utf8))
                let flags=try guards(db,key:unit.key)
                XCTAssertEqual(unit.hasNameGuard,flags?[3]=="name")
                XCTAssertEqual(unit.protectsInner,flags?[2]=="1")
                // Native overflow guards may add blocking; a raw true guard must survive.
                if flags?[0]=="1" { XCTAssertTrue(unit.sourceBlocked) }
                if flags?[1]=="1" { XCTAssertTrue(unit.targetBlocked) }
                for form in unit.forms {
                    if let focus = form.intrinsicRange {
                        XCTAssertGreaterThan(focus.length,0)
                        XCTAssertGreaterThanOrEqual(focus.location,0)
                        XCTAssertLessThanOrEqual(NSMaxRange(focus),form.written.utf16.count)
                    } else {
                        XCTAssertEqual(form.mode,0)
                    }
                }
            }
            observations.append(["case_id":row["case_id"]!,"units":snapshot.units.map { u -> [String:Any] in ["key":u.key,"range":[u.range.location,u.range.length],"original":u.original,"source_blocked":u.sourceBlocked,"target_blocked":u.targetBlocked,"name_guard":u.hasNameGuard,"protects_inner":u.protectsInner,"forms":u.forms.map { f -> [String:Any] in ["lexeme":f.lexemeID,"written":f.written,"range":f.intrinsicRange.map { [$0.location,$0.length] } as Any? ?? NSNull(),"number":f.number,"mode":f.mode,"source_safe":f.sourceSafe,"target_safe":f.targetSafe,"features":f.features.sorted(),"pos":f.partOfSpeech,"proper":f.isProperName,"grammar":f.isGrammar,"head":f.headword] }] },"forms":snapshot.units.reduce(0){$0+$1.forms.count},"phrase_ranges":snapshot.phraseRanges.map { [$0.location,$0.length] },"named_places":snapshot.namedPlaces.map { [$0.location,$0.length] },"release":snapshot.dictionaryRelease,"inventory":snapshot.dictionaryInventory])
        }
        let supplied=NSRange(location:4,length:3)
        let maskSnapshot=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:"the dog",language:"en",protectedRanges:[supplied]))
        XCTAssertTrue(maskSnapshot.hasStructuralProtection(at:supplied))
        let phrase=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:"all the way",language:"en",protectedRanges:[]))
        XCTAssertTrue(phrase.hasStructuralProtection(at:NSRange(location:8,length:3)))
        XCTAssertFalse(phrase.hasStructuralProtection(at:NSRange(location:0,length:11)))
        XCTAssertNil(try LexicalConcordance.sourceRecognition(db:db,original:"😀 cat",language:"en",protectedRanges:[NSRange(location:1,length:1)]))
        XCTAssertNil(try LexicalConcordance.sourceRecognition(db:db,original:"cafe\u{301}",language:"en",protectedRanges:[NSRange(location:3,length:1)]))
        XCTAssertNil(try LexicalConcordance.sourceRecognition(db:db,original:String(repeating:"x",count:16_385),language:"en",protectedRanges:[]))
        let composed=try XCTUnwrap(LexicalConcordance.sourceRecognition(db:db,original:"café",language:"en",protectedRanges:[]))
        XCTAssertFalse(composed.matches(original:"cafe\u{301}",language:"en",dictionaryRelease:composed.dictionaryRelease,dictionaryInventory:composed.dictionaryInventory,protectedRanges:[]))
        let attachment=XCTAttachment(data:try JSONSerialization.data(withJSONObject:["schema":"vipi.lexical-source-recognition.r01","cases":observations,"scope":"Native dictionary snapshot only; no translation/output permission, known-state or density filtering"],options:[.sortedKeys]),uniformTypeIdentifier:"public.json")
        attachment.name="lexical-source-recognition-r01";attachment.lifetime = .keepAlways;add(attachment)
    }
}
