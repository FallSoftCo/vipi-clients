import Foundation
import SQLite3
import XCTest
@testable import Vipi

/// Synthetic scope fixtures; these are not conversational acceptance data.
final class SideUnitFrameTests:XCTestCase {
    func testNativeWindowsKeepKoreanParticlesAndSwahiliLocativesOutsideTheFlip() throws {
        for (language,text,translated,noun,suffix,targetNoun) in [
            ("ko","책을 가져왔어요.","I brought the book.","책","을","book"),
            ("sw","Tutakutana shuleni.","We will meet at school.","shule","ni","school")
        ] {
            for reverse in [false,true] {
                var handle:OpaquePointer?
                XCTAssertEqual(sqlite3_open(":memory:",&handle),SQLITE_OK)
                let db=try XCTUnwrap(handle);defer {sqlite3_close(db)}
                func execute(_ sql:String,_ arguments:[String]=[]) throws {
                    var statement:OpaquePointer?
                    XCTAssertEqual(sqlite3_prepare_v2(db,sql,-1,&statement,nil),SQLITE_OK)
                    let query=try XCTUnwrap(statement);defer {sqlite3_finalize(query)}
                    for (index,value) in arguments.enumerated() {
                        XCTAssertEqual(sqlite3_bind_text(query,Int32(index+1),value,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self)),SQLITE_OK)
                    }
                    XCTAssertEqual(sqlite3_step(query),SQLITE_DONE)
                }
                let source=reverse ? "en" : language,target=reverse ? language : "en"
                let original=reverse ? translated : text,translation=reverse ? text : translated
                let attached:[[String:String]]=[["focus":noun],["literal":suffix]],unit=[["focus":targetNoun]]
                let payload:[String:Any]=["id":"fixture","meaning":"specific noun","source_language":source,"target_language":target,
                    "source":reverse ? targetNoun : noun,"target":reverse ? noun : targetNoun,
                    "source_parts":reverse ? unit : attached,"target_parts":reverse ? attached : unit,
                    "reading":target=="ko" ? "chaek" : "","lexical_unit":false,
                    "source_lexical_unit":reverse,"target_lexical_unit":!reverse]
                try execute("PRAGMA user_version=8")
                try execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                try execute("INSERT INTO metadata VALUES ('schema','vipi-reviewed-frame-3'),('context_policy','reviewed-bidirectional-side-unit-3')")
                try execute("CREATE TABLE mappings(id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
                try execute("CREATE TABLE source_inputs(input TEXT,mapping_id TEXT)")
                try execute("CREATE TABLE target_inputs(input TEXT,mapping_id TEXT)")
                let encoded=try JSONSerialization.data(withJSONObject:payload)
                try execute("INSERT INTO mappings VALUES (?,?)",["fixture",String(decoding:encoded,as:UTF8.self)])
                try execute("INSERT INTO source_inputs VALUES (?,?)",[reverse ? targetNoun : noun+suffix,"fixture"])
                try execute("INSERT INTO target_inputs VALUES (?,?)",[reverse ? noun+suffix : targetNoun,"fixture"])
                let entries=try ReviewedFrameLookup.entries(db:db,original:original,translation:translation,source:source,target:target)
                let result=LocalImmersion.align(original:original,translation:translation,entries:entries,density:1,source:source,target:target)
                XCTAssertEqual(result.spans.count,1)
                XCTAssertEqual(result.speech(source:source,target:target).map(\.text).joined(),
                    original.replacingOccurrences(of:reverse ? targetNoun : noun,with:reverse ? noun : targetNoun))
                if target=="ko" {XCTAssertEqual(result.spans.first?.romanization,"chaek")}
                let repeated=try ReviewedFrameLookup.entries(db:db,original:original+" "+original,translation:translation,source:source,target:target)
                XCTAssertTrue(repeated.isEmpty)
                let repeatedTarget=try ReviewedFrameLookup.entries(db:db,original:original,translation:translation+" "+translation,source:source,target:target)
                XCTAssertTrue(repeatedTarget.isEmpty)
                if !reverse {
                    let longer=original.replacingOccurrences(of:noun+suffix,with:(language=="ko" ? "공" : "ki")+noun+suffix)
                    XCTAssertTrue(try ReviewedFrameLookup.entries(db:db,original:longer,translation:translation,source:source,target:target).isEmpty)
                }
                try execute("PRAGMA user_version=7")
                try execute("UPDATE metadata SET value='vipi-reviewed-frame-2' WHERE key='schema'")
                try execute("UPDATE metadata SET value='reviewed-bidirectional-phrase-and-unit-2' WHERE key='context_policy'")
                XCTAssertThrowsError(try ReviewedFrameLookup.entries(db:db,original:original,translation:translation,source:source,target:target))
            }
        }
    }
}
