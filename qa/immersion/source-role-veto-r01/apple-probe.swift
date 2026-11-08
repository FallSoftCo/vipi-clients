import Foundation
import NaturalLanguage
import CryptoKit
import Darwin
func rss() -> UInt64 {
    var info = mach_task_basic_info(); var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
    let result = withUnsafeMutablePointer(to: &info) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count) } }
    return result == KERN_SUCCESS ? UInt64(info.resident_size) : 0
}
let start = DispatchTime.now().uptimeNanoseconds
let input = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
let cases = input["cases"] as! [[String: String]]
let available = NLTagger.availableTagSchemes(for: .word, language: .english).contains(.lexicalClass)
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
FileManager.default.createFile(atPath: outputURL.path, contents: nil)
let handle = try FileHandle(forWritingTo: outputURL)
var written = 0
func write(_ row: [String: Any]) throws {
    var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]); data.append(10)
    guard written + data.count <= 16 * 1024 * 1024 else { throw NSError(domain: "output_limit", code: 1) }
    try handle.write(contentsOf: data); written += data.count
}
func annotate(_ item: [String: String]) -> [String: Any] {
    let tick = DispatchTime.now().uptimeNanoseconds; let text = item["text"]!
    let tagger = NLTagger(tagSchemes: [.lexicalClass]); tagger.string = text
    tagger.setLanguage(.english, range: text.startIndex..<text.endIndex)
    var tokens: [[Any]] = []
    if available {
        tagger.enumerateTags(in: text.startIndex..<text.endIndex, unit: .word, scheme: .lexicalClass, options: [.omitWhitespace]) { tag, range in
            let ns = NSRange(range, in: text)
            let (hypotheses, hypothesisRange) = tagger.tagHypotheses(at: range.lowerBound, unit: .word, scheme: .lexicalClass, maximumCount: 1)
            let score: Any = hypothesisRange == range ? (tag.flatMap { hypotheses[$0.rawValue] }.map { $0 as Any } ?? NSNull()) : NSNull()
            tokens.append([ns.location, ns.length, tag.map { $0.rawValue as Any } ?? NSNull(), score])
            return true
        }
    }
    return ["id": item["id"]!, "source_sha256": SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined(), "utf16_length": text.utf16.count, "tokens": tokens, "elapsed_us": Double(DispatchTime.now().uptimeNanoseconds - tick) / 1000, "rss_bytes": rss(), "missing_scheme": !available]
}
var cold: [[String: Any]] = []
for (index, item) in cases.enumerated() {
    guard DispatchTime.now().uptimeNanoseconds - start < 170_000_000_000 else { throw NSError(domain: "time_limit", code: 1) }
    let row = annotate(item); if index < 20 { cold.append(row) }; try write(row)
}
try handle.close()
let warm = cases.prefix(20).map { annotate($0) }
var usage = rusage(); getrusage(RUSAGE_SELF, &usage)
let metadata: [String: Any] = ["schema": "vipi.apple-source-role-compact.1", "os": ProcessInfo.processInfo.operatingSystemVersionString, "input_cases": cases.count, "output_bytes": written, "available_lexical_class": available, "token_columns": ["utf16_start", "utf16_length", "raw_tag_or_null", "raw_score_or_null"], "score_basis": "tagHypotheses maximumCount1; null when no matching selected tag or token range. Not semantic certainty.", "cold_first20": cold, "warm_same20": warm, "process_lifetime_peak_rss_bytes": usage.ru_maxrss, "total_elapsed_ms": Double(DispatchTime.now().uptimeNanoseconds-start)/1e6, "limits": "Source-only current messages. No NameType, targets, previous dialogue, assets request, downloads or runtime changes. Cold means initial in-process cases, not OS cache flush. RSS process-wide." ]
try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: URL(fileURLWithPath: CommandLine.arguments[3]), options: .atomic)
