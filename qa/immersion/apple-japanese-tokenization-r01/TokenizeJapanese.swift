import Foundation
import NaturalLanguage
import CryptoKit
import Darwin

struct Input: Decodable {
    struct Row: Decodable { let id: String, text: String, original_sha256: String }
    let schema: String, cases: [Row]
}
struct Piece: Codable, Equatable {
    let text: String, utf16: [Int], codepoints: [Int], kind: String, origin: String
    let rules: [String], grapheme_aligned: Bool
}
struct NativeWord: Codable, Equatable {
    let text: String, utf16: [Int], codepoints: [Int], attributes: UInt
}
struct Geometry: Codable, Equatable {
    let status: String, raw_native_words: [NativeWord], tokens: [Piece], separators: [Piece]
    let protected_ranges: [Piece], diagnostics: [String], exact_reconstruction: Bool
    let native_calls: Int
}
struct Capture: Encodable {
    let id: String, text: String, original_sha256: String, first: Geometry
    let first_milliseconds: Double, warm_milliseconds: Double, warm_equal: Bool, warm_sha256: String
    let peak_rss_bytes: Int
}
struct Literal { var range: NSRange; var rules: Set<String> }
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
let encoder: JSONEncoder = { let e = JSONEncoder(); e.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]; return e }()
func native(_ text: String, offset: Int = 0) -> [(NSRange, UInt)] {
    let tokenizer = NLTokenizer(unit: .word)
    tokenizer.string = text; tokenizer.setLanguage(.japanese)
    var rows: [(NSRange, UInt)] = []
    tokenizer.enumerateTokens(in: text.startIndex..<text.endIndex) { range, attrs in
        let local = NSRange(range, in: text)
        rows.append((.init(location: offset + local.location, length: local.length), attrs.rawValue)); return true
    }
    return rows
}
func literals(_ text: String) throws -> ([Literal], [String]) {
    let ns = text as NSString, all = NSRange(location: 0, length: (text as NSString).length)
    var result: [Literal] = [], issues: [String] = []
    // Supported ASCII URI syntax is explicit. Unicode IRI/IDN ambiguity is
    // reported below; it is not silently parsed as an ordinary Japanese word.
    let patterns = [
        ("ascii_uri", #"(?i)(?:https?://|www\.)[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]++"#),
        ("email", #"[\p{Latin}\p{M}\p{N}._%+\-]++@[A-Za-z0-9\-]++(?:\.[A-Za-z0-9\-]++)+"#),
        ("handle", #"[@#][\p{L}\p{M}\p{N}_]++"#),
        ("number", #"[+\-]?\p{N}++(?:[.,:]\p{N}++)*(?:[%％])?"#),
        ("identifier", #"[\p{Latin}\p{M}\p{N}]++(?:[._'’\-][\p{Latin}\p{M}\p{N}]++)++"#)
    ]
    for (kind, pattern) in patterns {
        if kind == "email" && !text.contains("@") { continue }
        for match in try NSRegularExpression(pattern: pattern).matches(in: text, range: all) {
            result.append(.init(range: match.range, rules: [kind]))
        }
    }
    // Linear scan of maximal Latin/digit runs avoids repeated-prefix lookahead
    // on long identifiers. Ordinary Latin names remain native words.
    for match in try NSRegularExpression(pattern: #"[\p{Latin}\p{M}\p{N}]++"#).matches(in: text, range: all) {
        let value = ns.substring(with: match.range)
        if value.unicodeScalars.contains(where: CharacterSet.letters.contains) &&
            value.unicodeScalars.contains(where: CharacterSet.decimalDigits.contains) {
            result.append(.init(range: match.range, rules: ["alphanumeric_identifier"]))
        }
    }
    var cursor = 0
    while cursor < ns.length {
        let marker = ["```", "`"].first { value in
            cursor + value.utf16.count <= ns.length && ns.substring(with: .init(location: cursor, length: value.utf16.count)) == value
        }
        guard let marker, cursor == 0 || ns.substring(with: .init(location: cursor-1, length: 1)) != "\\" else { cursor += 1; continue }
        var search = cursor + marker.utf16.count, end = ns.length, closed = false
        while search < ns.length {
            let found = ns.range(of: marker, range: .init(location: search, length: ns.length-search))
            if found.location == NSNotFound { break }
            if found.location > 0 && ns.substring(with: .init(location: found.location-1, length: 1)) == "\\" { search = NSMaxRange(found); continue }
            end = NSMaxRange(found); closed = true; break
        }
        result.append(.init(range: .init(location: cursor, length: end-cursor), rules: ["code"]))
        if !closed { issues.append("unclosed_code_to_end") }
        cursor = end
    }
    // A broad URI with non-ASCII body is retained conservatively as one opaque
    // interval and flagged, rather than pretending its identifier end is known.
    for match in try NSRegularExpression(pattern: #"(?i)(?:https?://|www\.)[^\s<>\"。！？、]++"#).matches(in: text, range: all) {
        let value = ns.substring(with: match.range)
        if value.unicodeScalars.contains(where: { $0.value > 127 }) {
            result.append(.init(range: match.range, rules: ["uri_non_ascii_boundary_ambiguous"]))
            issues.append("uri_non_ascii_boundary_ambiguous")
        }
    }
    var union: [Literal] = []
    for item in result.sorted(by: { $0.range.location == $1.range.location ? $0.range.length > $1.range.length : $0.range.location < $1.range.location }) {
        if let last = union.last, item.range.location < NSMaxRange(last.range) {
            union[union.count-1] = .init(range: NSUnionRange(last.range, item.range), rules: last.rules.union(item.rules))
        } else { union.append(item) }
    }
    return (union, issues)
}
func analyze(_ text: String) throws -> Geometry {
    guard (1...16_384).contains(text.utf16.count) else {
        return .init(status: "input_length_rejected", raw_native_words: [], tokens: [], separators: [], protected_ranges: [], diagnostics: ["input_length"], exact_reconstruction: false, native_calls: 0)
    }
    let ns = text as NSString
    var cp: [Int: Int] = [0: 0], offset = 0
    for (i, scalar) in text.unicodeScalars.enumerated() { offset += scalar.utf16.count; cp[offset] = i+1 }
    let edges = Set(text.indices.map { $0.utf16Offset(in: text) } + [text.utf16.count])
    func piece(_ range: NSRange, kind: String, origin: String, rules: [String] = []) throws -> Piece {
        guard let start = cp[range.location], let end = cp[NSMaxRange(range)] else { throw ProbeError.invalid("non_scalar_range") }
        return .init(text: ns.substring(with: range), utf16: [range.location, NSMaxRange(range)], codepoints: [start,end],
                     kind: kind, origin: origin, rules: rules, grapheme_aligned: edges.contains(range.location) && edges.contains(NSMaxRange(range)))
    }
    let raw = native(text)
    let rawWords = try raw.map { range, attrs in
        let p = try piece(range, kind: "word", origin: "whole_text_native")
        return NativeWord(text: p.text, utf16: p.utf16, codepoints: p.codepoints, attributes: attrs)
    }
    let (opaque, initialIssues) = try literals(text)
    var issues = initialIssues, tokens: [Piece] = [], separators: [Piece] = [], calls = 1
    func gap(_ range: NSRange) throws {
        var at = range.location
        for character in ns.substring(with: range) {
            let value = String(character), count = value.utf16.count
            let kind: String
            if value.unicodeScalars.allSatisfy(CharacterSet.whitespacesAndNewlines.contains) { kind = "separator" }
            else if value.unicodeScalars.allSatisfy(CharacterSet.punctuationCharacters.contains) { kind = "punctuation" }
            else if value.unicodeScalars.contains(where: CharacterSet.symbols.contains) { kind = "symbol" }
            else { kind = "other"; issues.append("non_whitespace_native_gap") }
            let p = try piece(.init(location: at, length: count), kind: kind, origin: "exact_native_gap")
            if kind == "separator" { separators.append(p) } else { tokens.append(p) }
            at += count
        }
    }
    func region(_ start: Int, _ end: Int) throws {
        guard end > start else { return }
        let source = ns.substring(with: .init(location: start, length: end-start))
        let words = native(source, offset: start); calls += 1
        var position = start
        for (range, _) in words {
            guard range.location >= position, NSMaxRange(range) <= end, range.length > 0 else { throw ProbeError.invalid("invalid_native_geometry") }
            if range.location > position { try gap(.init(location: position, length: range.location-position)) }
            let p = try piece(range, kind: "word", origin: "native_nonliteral_region")
            if !p.grapheme_aligned { issues.append("native_non_grapheme_boundary") }
            tokens.append(p); position = NSMaxRange(range)
        }
        if position < end { try gap(.init(location: position, length: end-position)) }
    }
    var position = 0, protected: [Piece] = []
    for item in opaque {
        try region(position, item.range.location)
        let p = try piece(item.range, kind: "literal", origin: "protected_interval", rules: item.rules.sorted())
        if !p.grapheme_aligned { issues.append("literal_non_grapheme_boundary") }
        tokens.append(p); protected.append(p); position = NSMaxRange(item.range)
    }
    try region(position, ns.length)
    let partitions = (tokens + separators).sorted { $0.utf16[0] < $1.utf16[0] }
    var end = 0, rebuilt = ""
    for p in partitions { guard p.utf16[0] == end else { throw ProbeError.invalid("gap_or_overlap") }; end = p.utf16[1]; rebuilt += p.text }
    guard end == ns.length, rebuilt.utf8.elementsEqual(text.utf8) else { throw ProbeError.invalid("reconstruction") }
    for p in tokens where p.kind != "literal" {
        guard !opaque.contains(where: { NSIntersectionRange($0.range, .init(location: p.utf16[0], length: p.utf16[1]-p.utf16[0])).length > 0 }) else { throw ProbeError.invalid("partial_literal_overlap") }
    }
    return .init(status: "tokenized", raw_native_words: rawWords, tokens: tokens, separators: separators, protected_ranges: protected,
                 diagnostics: Array(Set(issues)).sorted(), exact_reconstruction: true, native_calls: calls)
}
enum ProbeError: Error { case invalid(String) }
@main struct Main {
    static func main() throws {
        let args = CommandLine.arguments; guard args.count == 4 else { throw ProbeError.invalid("input output expected_sha256") }
        let bytes = try Data(contentsOf: URL(fileURLWithPath: args[1])); guard digest(bytes) == args[3] else { throw ProbeError.invalid("input_hash") }
        let input = try JSONDecoder().decode(Input.self, from: bytes)
        guard input.schema == "vipi.japanese-tokenization-inputs.1", input.cases.count <= 512 else { throw ProbeError.invalid("input_schema_or_count") }
        let directory = URL(fileURLWithPath: args[2]); try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        let path = directory.appendingPathComponent("rows.jsonl"); guard !FileManager.default.fileExists(atPath: path.path) else { throw ProbeError.invalid("existing_output") }
        FileManager.default.createFile(atPath: path.path, contents: nil)
        let handle = try FileHandle(forWritingTo: path); defer { try? handle.close() }
        var size = 0, times: [Double] = [], complete = 0
        let start = ProcessInfo.processInfo.systemUptime
        for row in input.cases {
            guard digest(Data(row.text.utf8)) == row.original_sha256 else { throw ProbeError.invalid("row_hash") }
            try autoreleasepool {
                let before = ProcessInfo.processInfo.systemUptime, first = try analyze(row.text)
                let split = ProcessInfo.processInfo.systemUptime, warm = try analyze(row.text)
                let after = ProcessInfo.processInfo.systemUptime
                var usage = rusage(); getrusage(RUSAGE_SELF, &usage)
                let value = Capture(id: row.id, text: row.text, original_sha256: row.original_sha256, first: first,
                    first_milliseconds: (split-before)*1000, warm_milliseconds: (after-split)*1000,
                    warm_equal: first == warm, warm_sha256: digest(try encoder.encode(warm)), peak_rss_bytes: Int(usage.ru_maxrss))
                var data = try encoder.encode(value); data.append(10)
                guard size + data.count <= 8*1024*1024 else { throw ProbeError.invalid("output_cap") }
                try handle.write(contentsOf: data); try handle.synchronize(); size += data.count; complete += 1; times.append(value.first_milliseconds)
            }
        }
        let summary: [String: Any] = ["schema":"vipi.japanese-tokenization-capture.1", "rows":complete, "input_sha256":args[3], "output_bytes":size,
            "seconds":ProcessInfo.processInfo.systemUptime-start, "provider_calls":0, "asset_requests":0,
            "os":ProcessInfo.processInfo.operatingSystemVersionString, "policy":"native-ja-regions-and-literals-1"]
        try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted,.sortedKeys]).write(to: directory.appendingPathComponent("summary.json"))
    }
}
