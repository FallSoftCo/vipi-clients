import CryptoKit
import Foundation
import SQLite3
import XCTest

final class ContextIndexTests: XCTestCase {
    struct Row: Codable, Equatable { let id: Int; let target: String }
    struct Query: Decodable { let source: String; let target: String; let source_key: String; let query: String; let expected: [Row] }
    struct Fixture: Decodable { let database_sha256: String; let database_bytes: Int; let pairs: Int; let queries: [Query] }
    func testAttestedContextIndexOnNativeSQLite() throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let fixture = documents.appendingPathComponent("context-index-001")
        let expected = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: fixture.appendingPathComponent("native-queries.json")))
        let database = fixture.appendingPathComponent("contexts.sqlite")
        let bytes = try Data(contentsOf: database, options: .mappedIfSafe)
        XCTAssertEqual(bytes.count, expected.database_bytes)
        XCTAssertEqual(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(), expected.database_sha256)
        var handle: OpaquePointer?
        XCTAssertEqual(sqlite3_open_v2(database.path, &handle, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nil), SQLITE_OK)
        let db = try XCTUnwrap(handle); defer { sqlite3_close(db) }
        let sql = "SELECT e.id,e.target FROM context_search JOIN examples e ON e.id=context_search.docid WHERE context_search MATCH ? AND e.source_language=? AND e.target_language=? AND e.source_key=? ORDER BY e.id LIMIT 8"
        var elapsed: [Double] = []; var pairs = Set<String>()
        for query in expected.queries {
            let begin = ProcessInfo.processInfo.systemUptime
            var statement: OpaquePointer?
            XCTAssertEqual(sqlite3_prepare_v2(db, sql, -1, &statement, nil), SQLITE_OK)
            let cursor = try XCTUnwrap(statement); defer { sqlite3_finalize(cursor) }
            for (index, value) in [query.query, query.source, query.target, query.source_key].enumerated() {
                XCTAssertEqual(sqlite3_bind_text(cursor, Int32(index+1), value, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self)), SQLITE_OK)
            }
            var rows: [Row] = []; var status = sqlite3_step(cursor)
            while status == SQLITE_ROW {
                let target = try XCTUnwrap(sqlite3_column_text(cursor, 1))
                rows.append(Row(id: Int(sqlite3_column_int64(cursor, 0)), target: String(cString: target)))
                status = sqlite3_step(cursor)
            }
            XCTAssertEqual(status, SQLITE_DONE)
            elapsed.append((ProcessInfo.processInfo.systemUptime - begin) * 1000)
            XCTAssertEqual(rows, query.expected, query.source + "-" + query.target)
            pairs.insert(query.source + "-" + query.target)
        }
        XCTAssertEqual(pairs.count, expected.pairs)
        XCTAssertFalse(elapsed.isEmpty)
        let sorted = elapsed.sorted()
        let report: [String: Any] = ["queries": elapsed.count, "pairs": pairs.count, "query_ms": elapsed,
            "median_ms": sorted[sorted.count/2], "p95_ms": sorted[min(sorted.count-1, Int(Double(sorted.count)*0.95))],
            "sqlite_version": String(cString: sqlite3_libversion()), "database_sha256": expected.database_sha256,
            "linguistic_acceptance": false, "evidence": "attested-example self-retrieval, not independent meaning selection"]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: documents.appendingPathComponent("context-index-native.json"), options: .atomic)
    }
}
