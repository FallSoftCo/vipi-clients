// Bounded macOS investigation only. No application fallback or model preparation.
import Foundation
import CoreFoundation
import NaturalLanguage
import CryptoKit
import Darwin

struct ProtocolInput: Decodable {
    struct Case: Decodable { let id: String; let language: String; let text: String; let group: String }
    let schema: String
    let cases: [Case]
}
func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
func peakRSS() -> Int64 { var usage = rusage(); guard getrusage(RUSAGE_SELF, &usage) == 0 else { return -1 }; return Int64(usage.ru_maxrss) }
func nonRoman(_ text: String) -> Bool {
    text.range(of: #"[\p{Arabic}\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}]"#, options: .regularExpression) != nil
}
func edgeIsAlphanumeric(_ text: String, last: Bool) -> Bool {
    guard let value = last ? text.unicodeScalars.last : text.unicodeScalars.first else { return false }
    return CharacterSet.alphanumerics.contains(value)
}
func capture(_ item: ProtocolInput.Case, schemes: [NLTagScheme]) -> [String: Any] {
    let start = ProcessInfo.processInfo.systemUptime, rssBefore = peakRSS()
    let text = item.text, native = text as NSString
    let options = CFOptionFlags(kCFStringTokenizerUnitWord) | CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription) | CFOptionFlags(kCFStringTokenizerAttributeLanguage)
    let tokenizer = CFStringTokenizerCreate(nil, text as CFString, CFRange(location: 0, length: native.length), options,
        CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: item.language as CFString)))!
    var tokens: [[String: Any]] = [], segments: [[String: Any]] = [], errors: [String] = []
    var end = 0, reconstructed = "", marked = "", priorNonRoman = false
    func appendGap(_ range: NSRange) {
        guard range.length > 0 else { return }
        let gap = native.substring(with: range), unknown = nonRoman(gap)
        segments.append(["kind": "gap", "start": range.location, "length": range.length, "original": gap,
                         "contains_untranscribed_script": unknown])
        reconstructed += gap; marked += unknown ? "⟦" + gap + "⟧" : gap
    }
    while true {
        let type = CFStringTokenizerAdvanceToNextToken(tokenizer)
        if type.rawValue == 0 { break }
        let raw = CFStringTokenizerGetCurrentTokenRange(tokenizer)
        let range = NSRange(location: raw.location, length: raw.length)
        guard range.location >= end, range.length > 0, NSMaxRange(range) <= native.length else {
            errors.append("invalid_or_overlapping_native_range"); continue
        }
        let gap = NSRange(location: end, length: range.location - end)
        appendGap(gap)
        let source = native.substring(with: range)
        let reading = CFStringTokenizerCopyCurrentTokenAttribute(tokenizer, CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)) as? String
        let detected = CFStringTokenizerCopyCurrentTokenAttribute(tokenizer, CFOptionFlags(kCFStringTokenizerAttributeLanguage)) as? String
        let script = nonRoman(source)
        let usable = reading.map { !$0.isEmpty && !nonRoman($0) } ?? false
        // This is a mechanical inspection string, not an accepted pronunciation.
        // Preserve Latin/number identifiers exactly; expose missing native readings.
        let replacement = script && usable ? reading! : source
        let missing = script && !usable
        let separator = gap.length == 0 && !reconstructed.isEmpty && (priorNonRoman || script) &&
            edgeIsAlphanumeric(reconstructed, last: true) && edgeIsAlphanumeric(replacement, last: false)
        if separator { reconstructed += " "; marked += " " }
        reconstructed += replacement; marked += missing ? "⟦" + source + "⟧" : replacement
        let row: [String: Any] = ["start": range.location, "length": range.length, "original": source,
            "raw_latin": reading as Any? ?? NSNull(), "detected_language": detected as Any? ?? NSNull(),
            "native_token_flags": type.rawValue, "non_roman_source": script,
            "missing_or_non_latin_reading": missing, "display_inspection": replacement, "inserted_separator": separator]
        tokens.append(row); segments.append(row.merging(["kind": "token"]) { _, new in new })
        end = NSMaxRange(range); priorNonRoman = script
    }
    appendGap(NSRange(location: end, length: native.length - end))
    var tags: [[String: Any]] = []
    if schemes.contains(.lexicalClass) {
        let tagger = NLTagger(tagSchemes: [.lexicalClass]); tagger.string = text
        tagger.setLanguage(NLLanguage(rawValue: item.language), range: text.startIndex..<text.endIndex)
        tagger.enumerateTags(in: text.startIndex..<text.endIndex, unit: .word, scheme: .lexicalClass, options: []) { tag, range in
            let utf16 = NSRange(range, in: text)
            tags.append(["start": utf16.location, "length": utf16.length, "original": String(text[range]), "tag": tag?.rawValue as Any? ?? NSNull()]); return true
        }
    }
    let nativeElapsed = (ProcessInfo.processInfo.systemUptime - start) * 1000
    return ["tokens": tokens, "segments": segments, "range_errors": errors, "lexical_tags": tags,
            "reconstruction": reconstructed, "marked_reconstruction": marked,
            "generic_to_latin_negative_control": text.applyingTransform(.toLatin, reverse: false) as Any? ?? NSNull(),
            "native_token_tag_reconstruction_ms": nativeElapsed, "peak_rss_before_bytes": rssBefore,
            "peak_rss_after_bytes": peakRSS(), "all_work_ms": (ProcessInfo.processInfo.systemUptime - start) * 1000]
}
let arguments = CommandLine.arguments
precondition(arguments.count == 4, "INPUT OUTPUT EXPECTED_INPUT_SHA256")
let input = URL(fileURLWithPath: arguments[1]), output = URL(fileURLWithPath: arguments[2])
precondition(!FileManager.default.fileExists(atPath: output.path), "Fresh output required")
let data = try Data(contentsOf: input)
precondition(sha(data) == arguments[3], "Frozen input hash mismatch")
let protocolInput = try JSONDecoder().decode(ProtocolInput.self, from: data)
precondition(protocolInput.schema == "vipi-full-reading-probe-1" && protocolInput.cases.count == 48)
precondition(Set(protocolInput.cases.map(\.id)).count == 48)
precondition(protocolInput.cases.allSatisfy { ["ja", "zh", "ko", "ar"].contains($0.language) && !$0.text.isEmpty && $0.text.utf16.count <= 512 })
let watchdog = DispatchSource.makeTimerSource(queue: .global(qos: .utility)); watchdog.schedule(deadline: .now() + 90)
watchdog.setEventHandler { exit(124) }; watchdog.resume(); defer { watchdog.cancel() }
let started = Date(), rssStart = peakRSS()
var schemes: [String: [NLTagScheme]] = [:]
for language in ["ja", "zh", "ko", "ar"] { schemes[language] = NLTagger.availableTagSchemes(for: .word, language: NLLanguage(rawValue: language)) }
var results: [[String: Any]] = []
for item in protocolInput.cases {
    let first = autoreleasepool { capture(item, schemes: schemes[item.language]!) }
    let warm = autoreleasepool { capture(item, schemes: schemes[item.language]!) }
    results.append(["id": item.id, "language": item.language, "group": item.group, "text": item.text, "first": first, "warm": warm])
    let report: [String: Any] = ["platform": "macOS VM native APIs; not physical iOS or translation-provider acceptance",
        "schema": "vipi-full-reading-probe-output-1", "input_sha256": sha(data), "complete": results.count == 48,
        "started": ISO8601DateFormatter().string(from: started), "elapsed_seconds": Date().timeIntervalSince(started),
        "os": ProcessInfo.processInfo.operatingSystemVersionString, "locale": Locale.current.identifier,
        "preferred_languages": Locale.preferredLanguages, "network_disabled": false,
        "model_download_or_requestAssets_called": false, "audio_generated": false,
        "timing_scope": "First observed invocation in this process and immediate repeat, not OS cold-cache timing; RSS is process high-water, not per-case allocation.",
        "available_word_tag_schemes": schemes.mapValues { $0.map(\.rawValue).sorted() },
        "peak_rss_start_bytes": rssStart, "peak_rss_bytes": peakRSS(), "cases": results]
    try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
}
