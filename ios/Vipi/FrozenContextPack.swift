import Foundation
import SQLite3
import CryptoKit

/// Disabled research evidence reader. It never creates SourceLookupEvidence,
/// approvedOutputs, emissions, masks or fallback choices.
struct FrozenContextPack {
    enum Failure: Error { case identity, schema, bound, malformed, sqlite, invalidGeometry }
    struct Rule {
        let id: String, sourceKey: String, tokens: [String], target: String
        let focusOffset: Int, length: Int, components: Int
        let ratio: Double?, weight: Double
        let sourceRecordSHA256: String
        let headIDs: [String]
    }
    struct Head {
        let id: String, contextID: String, sourceKey: String, tokens: [String]
        let focus: [Int], target: String, readingsJSON: String, posJSON: String
        let fixed: Bool, trainRank: Int, sourceRecordSHA256: String
    }
    struct Winner {
        let rule: Rule
        let contextRange: NSRange
        let tokenStart: Int
        let contextGeometryCompatible: Bool
        // Empty headIDs is a real winner with no output, never permission to retry.
    }
    let contentSHA256: String
    let metadata: [String: String]
    let rules: [Rule]
    let evidence: Evidence
    let heads: [String: Head]
    private let byKey: [Data: [Rule]]
    private let tokenizer: FrozenContextTokenizer

    /// Caller must preserve file immutability during each read. Base-file hashes
    /// never authenticate SQLite sidecars; reject them, including empty sidecars.
    private static func noSidecars(_ url: URL) throws {
        guard ["-wal", "-shm", "-journal"].allSatisfy({ !FileManager.default.fileExists(atPath: url.path+$0) }) else { throw Failure.identity }
    }
    private static func digest(_ url: URL, maximum: Int) throws -> String {
        try noSidecars(url)
        let h = try FileHandle(forReadingFrom: url); defer { try? h.close() }
        var hash = SHA256(), total = 0
        while let data = try h.read(upToCount: 1 << 20), !data.isEmpty {
            total += data.count; guard total <= maximum else { throw Failure.bound }; hash.update(data: data)
        }
        try noSidecars(url)
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }
    private static func open(_ url: URL) throws -> OpaquePointer {
        try noSidecars(url)
        var db: OpaquePointer?
        guard sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nil) == SQLITE_OK, let db else {
            if let db { sqlite3_close(db) }; throw Failure.sqlite
        }
        sqlite3_limit(db, SQLITE_LIMIT_LENGTH, 1_048_576)
        sqlite3_limit(db, SQLITE_LIMIT_SQL_LENGTH, 16_384)
        sqlite3_limit(db, SQLITE_LIMIT_ATTACHED, 0)
        sqlite3_busy_timeout(db, 100)
        guard sqlite3_exec(db, "PRAGMA query_only=ON; PRAGMA trusted_schema=OFF; BEGIN", nil, nil, nil) == SQLITE_OK else {
            sqlite3_close(db); throw Failure.sqlite
        }
        return db
    }
    static func rows(_ db: OpaquePointer, _ sql: String, maximum: Int,
                             body: (OpaquePointer) throws -> Void) throws {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, let statement else { throw Failure.sqlite }
        defer { sqlite3_finalize(statement) }
        var count = 0
        while true {
            let status = sqlite3_step(statement)
            if status == SQLITE_DONE { return }
            guard status == SQLITE_ROW else { throw Failure.sqlite }
            count += 1; guard count <= maximum else { throw Failure.bound }; try body(statement)
        }
    }
    static func text(_ s: OpaquePointer, _ column: Int32) throws -> String {
        guard sqlite3_column_type(s, column) == SQLITE_TEXT, let pointer = sqlite3_column_text(s, column) else { throw Failure.malformed }
        let data = Data(bytes: pointer, count: Int(sqlite3_column_bytes(s, column)))
        guard let value = String(data: data, encoding: .utf8), !value.contains("\0") else { throw Failure.malformed }; return value
    }
    static func integer(_ s: OpaquePointer, _ column: Int32) throws -> Int {
        guard sqlite3_column_type(s, column) == SQLITE_INTEGER else { throw Failure.malformed }
        let n = sqlite3_column_int64(s, column); guard let value = Int(exactly: n) else { throw Failure.bound }; return value
    }
    static func strings(_ text: String) throws -> [String] { try JSONDecoder().decode([String].self, from: Data(text.utf8)) }
    private static func metadata(_ db: OpaquePointer) throws -> [String: String] {
        var result: [String: String] = [:]
        try rows(db, "SELECT key,value FROM metadata ORDER BY key", maximum: 512) { s in
            let key = try text(s, 0); guard result[key] == nil else { throw Failure.malformed }; result[key] = try text(s, 1)
        }; return result
    }
    /// Caller provides exact independently frozen identities and original dictionary files.
    /// Dictionary metadata is compared in full, not release_id alone.
    init(url: URL, expectedSHA256: String, expectedMetadata: [String: String], dictionaryURLs: [String: URL]) throws {
        guard expectedSHA256.count == 64, try Self.digest(url, maximum: 16 << 20) == expectedSHA256,
              dictionaryURLs.keys.sorted() == ["en", "es"] else { throw Failure.identity }
        let db = try Self.open(url); defer { sqlite3_close(db) }
        var appID = 0, version = 0
        try Self.rows(db, "PRAGMA application_id", maximum: 1) { appID = try Self.integer($0, 0) }
        try Self.rows(db, "PRAGMA user_version", maximum: 1) { version = try Self.integer($0, 0) }
        guard appID == 1447645257, version == 1 else { throw Failure.schema }
        let meta = try Self.metadata(db)
        let required = ["kind":"vipi.frozen-context-research", "schema":"1", "source":"en", "target":"es", "permission":"disabled_research_only",
                        "normalization":"NFC+Unicode-casefold+whitespace-collapse; offsets never normalized",
                        "tokenizer_sha256":"d1f41157ec44e95e25420a7d65b37bcfe40b174592dfce812248e49955aeeb5f"]
        guard required.allSatisfy({ meta[$0.key] == $0.value }),
              ["policy_sha256", "input_manifest_sha256"].allSatisfy({ expectedMetadata[$0]?.count == 64 }),
              expectedMetadata.allSatisfy({ meta[$0.key] == $0.value }) else { throw Failure.identity }
        for language in ["en", "es"] {
            let dictionary = dictionaryURLs[language]!
            guard try Self.digest(dictionary, maximum: 512 << 20) == meta["dictionary_\(language)_sha256"] else { throw Failure.identity }
            let dd = try Self.open(dictionary); defer { sqlite3_close(dd) }
            let actual = try Self.metadata(dd)
            let encoded = try JSONDecoder().decode([String: String].self, from: Data((meta["dictionary_\(language)_metadata_json"] ?? "").utf8))
            guard actual == encoded, actual["release_id"] != nil, actual["source_inventory_sha256"] != nil,
                  try Self.digest(dictionary, maximum: 512 << 20) == meta["dictionary_\(language)_sha256"] else { throw Failure.identity }
        }
        var integrity: [String] = []
        try Self.rows(db, "PRAGMA integrity_check(1)", maximum: 1) { integrity.append(try Self.text($0, 0)) }
        guard integrity == ["ok"] else { throw Failure.schema }
        try Self.rows(db, "PRAGMA foreign_key_check", maximum: 1) { _ in throw Failure.schema }
        var headMap: [String: Head] = [:]
        try Self.rows(db, "SELECT id,context_id,source_key,tokens_json,focus_json,target,readings_json,pos_json,fixed,train_rank,source_record_sha256,permission FROM heads ORDER BY id", maximum: 4096) { s in
            let id = try Self.text(s, 0), tokens = try Self.strings(Self.text(s, 3))
            let focus = try JSONDecoder().decode([Int].self, from: Data(Self.text(s, 4).utf8))
            let fixed = try Self.integer(s, 8), rank = try Self.integer(s, 9)
            guard !tokens.isEmpty, tokens.count <= 128, focus.count == 2, focus[0] >= 0, focus[1] > focus[0], focus[1] <= tokens.count,
                  [0,1].contains(fixed), rank >= 0, try Self.text(s, 11) == "conditional_source_name_only" else { throw Failure.malformed }
            headMap[id] = try .init(id: id, contextID: Self.text(s, 1), sourceKey: Self.text(s, 2), tokens: tokens, focus: focus,
                target: Self.text(s, 5), readingsJSON: Self.text(s, 6), posJSON: Self.text(s, 7), fixed: fixed == 1, trainRank: rank, sourceRecordSHA256: Self.text(s, 10))
        }
        var edges: [String: [String]] = [:]
        try Self.rows(db, "SELECT rule_id,head_id,support_components FROM rule_heads ORDER BY rule_id,head_id", maximum: 32768) { s in
            let rule = try Self.text(s, 0), head = try Self.text(s, 1)
            guard headMap[head] != nil, try Self.integer(s, 2) >= 2 else { throw Failure.malformed }; edges[rule, default: []].append(head)
        }
        var loaded: [Rule] = []
        try Self.rows(db, "SELECT id,source_key,tokens_json,focus_offset,length,target,ratio,winner_components,winner_weight,source_record_sha256,permission FROM rules ORDER BY id", maximum: 4096) { s in
            let id = try Self.text(s, 0), key = try Self.text(s, 1), tokens = try Self.strings(Self.text(s, 2))
            let focus = try Self.integer(s, 3), length = try Self.integer(s, 4), support = try Self.integer(s, 7)
            let ratio: Double? = sqlite3_column_type(s, 6) == SQLITE_NULL ? nil : sqlite3_column_double(s, 6)
            let weight = sqlite3_column_double(s, 8), target = try Self.text(s, 5)
            guard (2...8).contains(length), tokens.count == length, (0..<length).contains(focus), support >= 2,
                  ratio == nil || (ratio!.isFinite && ratio! > 1.5), weight.isFinite, weight > 0,
                  try Self.text(s, 10) == "conditional_research_only",
                  (edges[id] ?? []).allSatisfy({ headMap[$0]?.target == target }) else { throw Failure.malformed }
            loaded.append(.init(id: id, sourceKey: key, tokens: tokens, target: target, focusOffset: focus, length: length,
                                components: support, ratio: ratio, weight: weight, sourceRecordSHA256: try Self.text(s, 9), headIDs: edges[id] ?? []))
        }
        guard loaded.count == 1157, loaded.filter({ $0.headIDs.isEmpty }).count == 23,
              try Self.digest(url, maximum: 16 << 20) == expectedSHA256 else { throw Failure.identity }
        let parsedEvidence = try Self.readEvidence(db, rules: loaded, heads: headMap)
        guard try Self.digest(url, maximum: 16 << 20) == expectedSHA256 else { throw Failure.identity }
        evidence = parsedEvidence
        contentSHA256 = expectedSHA256; metadata = meta; heads = headMap; rules = loaded
        byKey = Dictionary(grouping: loaded, by: { Data($0.sourceKey.utf8) }); tokenizer = try FrozenContextTokenizer()
    }
    struct Assessment {
        let winner: Winner?
        let rawMatches: [Winner]
    }
    /// Frozen Python gate: reject context/native geometry mismatch BEFORE ranking.
    /// Keep raw windows diagnostically; no target/head/known/budget fallback exists.
    func winner(original: String, nativeWordRanges: [NSRange], focus: NSRange, sourceKeys: [String]) throws -> Winner? {
        try assess(original: original, nativeWordRanges: nativeWordRanges, focus: focus, sourceKeys: sourceKeys).winner
    }
    func assess(original: String, nativeWordRanges: [NSRange], focus: NSRange, sourceKeys: [String]) throws -> Assessment {
        guard original.utf16.count <= 16_384, sourceKeys.count <= 256, sourceKeys.allSatisfy({ $0.utf8.count <= 4096 }), nativeWordRanges.count <= 16_384 else { throw Failure.bound }
        let length = original.utf16.count
        let boundaries = Set(original.indices.map { $0.utf16Offset(in: original) } + [length])
        var end = 0
        for range in nativeWordRanges {
            guard range.location >= end, range.location <= length, range.length > 0, range.length <= length-range.location,
                  boundaries.contains(range.location), boundaries.contains(NSMaxRange(range)) else { throw Failure.invalidGeometry }
            end = NSMaxRange(range)
        }
        guard nativeWordRanges.contains(focus) else { throw Failure.invalidGeometry }
        let tokens = try tokenizer.tokenize(original), native = Set(nativeWordRanges)
        guard let position = tokens.firstIndex(where: { $0.range == focus }) else { return .init(winner: nil, rawMatches: []) }
        var matches: [Winner] = []; var seen = Set<Data>()
        for key in sourceKeys.sorted() {
            guard seen.insert(Data(key.utf8)).inserted else { continue }
            // Frozen source keys are serialized arrays, not normalized spellings alone.
            guard let parts = try JSONSerialization.jsonObject(with: Data(key.utf8)) as? [Any],
                  let spelling = parts.first as? String, spelling.utf8.elementsEqual(tokens[position].normalized.utf8) else { throw Failure.malformed }
            for rule in byKey[Data(key.utf8)] ?? [] {
                let start = position-rule.focusOffset, after = start+rule.length
                guard start >= 0, after <= tokens.count else { continue }
                let window = tokens[start..<after]
                guard window.allSatisfy({ $0.hasAlphabeticScalar }),
                      zip(window.map(\.normalized), rule.tokens).allSatisfy({ $0.utf8.elementsEqual($1.utf8) }) else { continue }
                matches.append(.init(rule: rule, contextRange: .init(location: tokens[start].range.location,
                    length: NSMaxRange(tokens[after-1].range)-tokens[start].range.location), tokenStart: start, contextGeometryCompatible: window.allSatisfy({ native.contains($0.range) })))
            }
        }
        let ranked = matches.sorted {
            let a = $0.rule, b = $1.rule
            if a.length != b.length { return a.length > b.length }
            if a.ratio != b.ratio { return (a.ratio ?? .infinity) > (b.ratio ?? .infinity) }
            if a.components != b.components { return a.components > b.components }
            if a.weight != b.weight { return a.weight > b.weight }
            if $0.tokenStart != $1.tokenStart { return $0.tokenStart < $1.tokenStart }
            return a.id < b.id
        }
        return .init(winner: ranked.first(where: { $0.contextGeometryCompatible }), rawMatches: ranked)
    }
}
