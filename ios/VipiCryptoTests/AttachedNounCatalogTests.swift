import Foundation
import SQLite3
import VipiCore
import XCTest
@testable import Vipi

final class AttachedNounCatalogTests:XCTestCase {
    func testEveryListedAttachmentPreservesTheSurroundingNativeGrammar() async throws {
        let root=try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        let index=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("catalog.json"))) as? [String:Any])
        let packs=try XCTUnwrap(index["packs"] as? [[String:Any]])
        let catalog=BundledImmersionCatalog(root:root)
        var records=0,cases=0,unchanged=0,directions=Set<String>()
        for pack in packs {
            let identity=try XCTUnwrap(pack["id"] as? String),codes=identity.split(separator:"-").map(String.init)
            let pair=TranslationPair(source:codes[0],target:codes[1])
            var handle:OpaquePointer?
            XCTAssertEqual(sqlite3_open_v2(root.appendingPathComponent(identity+".sqlite").path,&handle,SQLITE_OPEN_READONLY,nil),SQLITE_OK)
            let db=try XCTUnwrap(handle);defer {sqlite3_close(db)}
            func forms(_ side:String,_ id:String) throws -> [String] {
                var statement:OpaquePointer?
                XCTAssertEqual(sqlite3_prepare_v2(db,"SELECT input FROM \(side)_inputs WHERE mapping_id=? ORDER BY input",-1,&statement,nil),SQLITE_OK)
                let query=try XCTUnwrap(statement);defer {sqlite3_finalize(query)}
                XCTAssertEqual(sqlite3_bind_text(query,1,id,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self)),SQLITE_OK)
                var values=[String](),status=sqlite3_step(query)
                while status==SQLITE_ROW {values.append(String(cString:try XCTUnwrap(sqlite3_column_text(query,0))));status=sqlite3_step(query)}
                XCTAssertEqual(status,SQLITE_DONE);return values
            }
            var statement:OpaquePointer?
            XCTAssertEqual(sqlite3_prepare_v2(db,"SELECT id,payload FROM mappings WHERE id LIKE 'vipi-authored-r1:attached_noun_%' ORDER BY id",-1,&statement,nil),SQLITE_OK)
            let query=try XCTUnwrap(statement);defer {sqlite3_finalize(query)}
            var status=sqlite3_step(query)
            while status==SQLITE_ROW {
                let id=String(cString:try XCTUnwrap(sqlite3_column_text(query,0)))
                let raw=String(cString:try XCTUnwrap(sqlite3_column_text(query,1)))
                let row=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(raw.utf8)) as? [String:Any])
                let noun=try XCTUnwrap(row["source"] as? String),replacement=try XCTUnwrap(row["target"] as? String)
                let left=try forms("source",id),right=try forms("target",id)
                XCTAssertFalse(left.isEmpty);XCTAssertFalse(right.isEmpty)
                for a in left {for b in right {
                    let original=a+".",translation=b+"."
                    let result=try await catalog.result(original:original,translation:translation,pair:pair,density:1)
                    XCTAssertEqual(result.original,original);XCTAssertEqual(result.translation,translation)
                    XCTAssertEqual(result.speech(source:pair.source,target:pair.target,revealed:Set(result.spans.map(\.id))).map(\.text).joined(),original)
                    if noun.caseInsensitiveCompare(replacement) == .orderedSame && !["ar","zh","ja","ko"].contains(pair.target) {
                        XCTAssertTrue(result.spans.isEmpty);unchanged+=1
                    } else {
                        XCTAssertEqual(result.spans.count,1,"\(identity):\(id):\(a) -> \(b)")
                        XCTAssertEqual(result.spans.first?.original,noun)
                        XCTAssertEqual(result.speech(source:pair.source,target:pair.target).map(\.text).joined(),original.replacingOccurrences(of:noun,with:replacement))
                        if ["ar","zh","ja","ko"].contains(pair.target) {XCTAssertEqual(result.spans.first?.romanization,row["reading"] as? String)}
                    }
                    cases+=1
                }}
                records+=1;directions.insert(identity);status=sqlite3_step(query)
            }
            XCTAssertEqual(status,SQLITE_DONE)
        }
        XCTAssertEqual(records,2551);XCTAssertEqual(directions.count,38);XCTAssertGreaterThan(cases,records)
        let output=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("attached-noun-catalog-004.json")
        let receipt:[String:Any]=["records":records,"cases":cases,"directions":directions.count,"unchanged_forms":unchanged,
            "runtime_path":"app-bundled-native-catalog","independent_linguistic_acceptance":false]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.withoutOverwriting)
    }
}
