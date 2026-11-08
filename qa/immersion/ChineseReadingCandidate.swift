// QA candidate only. Not linked into the app or offered as a production fallback.
import Foundation
import CoreFoundation

struct ChineseReadingCandidate {
    static let policyVersion = "cf-pinyin-inspection-1"
    struct Result {
        let reading: String?
        let inspection: String
        let marked: String
        let tokens: [[String: Any]]
        let pieces: [[String: Any]]
        let issues: [[String: Any]]
        let protected: [[String: Any]]
    }
    private static let opaquePatterns = [
        #"`[^`\r\n]+`"#,
        #"(?i)(?:https?://|www\.)[^\s<>\"“”‘’，。！？；、]+"#,
        #"[\p{Latin}\p{M}\p{N}._%+\-]+@[\p{Latin}\p{M}\p{N}.\-]+\.[\p{Latin}\p{M}]{2,}"#,
        #"[\p{Latin}\p{M}\p{N}]+(?:[\-_'’./:][\p{Latin}\p{M}\p{N}]+)*"#
    ]
    private static func matches(_ text: String, _ expression: String) -> Bool {
        text.range(of: expression, options: .regularExpression) != nil
    }
    private static func nonLatinLetter(_ text: String) -> Bool {
        text.unicodeScalars.contains { scalar in
            CharacterSet.letters.contains(scalar) && !matches(String(scalar), #"\p{Latin}"#)
        }
    }
    private static func hanOnlyLetters(_ text: String) -> Bool {
        var found = false
        for scalar in text.unicodeScalars where CharacterSet.letters.contains(scalar) {
            guard matches(String(scalar), #"\p{Han}"#) else { return false }; found = true
        }
        return found
    }
    private static func validPinyin(_ text: String) -> Bool {
        !text.isEmpty && !matches(text, #"[^\p{Latin}\p{M}0-9 '\-’]"#) && matches(text, #"\p{Latin}"#)
    }
    private static func alphanumericEdge(_ text: String, last: Bool) -> Bool {
        guard let value = last ? text.unicodeScalars.last : text.unicodeScalars.first else { return false }
        return CharacterSet.alphanumerics.contains(value)
    }
    static func resolve(_ text: String) throws -> Result {
        let ns = text as NSString, whole = NSRange(location: 0, length: ns.length)
        guard (1...16_384).contains(ns.length) else {
            return .init(reading: nil, inspection: text, marked: text, tokens: [], pieces: [],
                         issues: [["reason": "input_length"]], protected: [])
        }
        var opaque: [NSRange] = []
        for pattern in opaquePatterns {
            for match in try NSRegularExpression(pattern: pattern).matches(in: text, range: whole) {
                // Earlier, more specific whole identifiers have precedence.
                if !opaque.contains(where: { NSIntersectionRange($0, match.range).length > 0 }) { opaque.append(match.range) }
            }
        }
        opaque.sort { $0.location < $1.location }
        let options = CFOptionFlags(kCFStringTokenizerUnitWord) | CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)
        let tokenizer = CFStringTokenizerCreate(nil, text as CFString, CFRange(location: 0, length: ns.length), options,
            CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: "zh" as CFString)))!
        var tokens: [(NSRange, String?)] = [], raw: [[String: Any]] = [], issues: [[String: Any]] = []
        var end = 0
        while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
            let value = CFStringTokenizerGetCurrentTokenRange(tokenizer), range = NSRange(location: value.location, length: value.length)
            guard range.location >= end, range.length > 0, NSMaxRange(range) <= ns.length else {
                issues.append(["reason": "invalid_native_range", "start": range.location, "length": range.length]); continue
            }
            let latin = CFStringTokenizerCopyCurrentTokenAttribute(tokenizer, CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)) as? String
            tokens.append((range, latin)); raw.append(["start": range.location, "length": range.length,
                "original": ns.substring(with: range), "raw_latin": latin as Any? ?? NSNull()]); end = NSMaxRange(range)
        }
        let boundaries = Set([0, ns.length] + tokens.flatMap { [$0.0.location, NSMaxRange($0.0)] } + opaque.flatMap { [$0.location, NSMaxRange($0)] }).sorted()
        var pieces: [[String: Any]] = [], inspection = "", marked = "", priorConverted = false
        for index in 0..<(boundaries.count - 1) {
            let range = NSRange(location: boundaries[index], length: boundaries[index + 1] - boundaries[index])
            let source = ns.substring(with: range)
            let protected = opaque.contains { NSIntersectionRange($0, range) == range }
            let native = tokens.first { NSIntersectionRange($0.0, range) == range }
            var rendered = source, converted = false, reason: String?
            if !protected && nonLatinLetter(source) {
                if !hanOnlyLetters(source) { reason = "unsupported_non_han_script" }
                else if native == nil { reason = "untokenized_han" }
                else if native!.0 != range { reason = "native_token_overlaps_opaque_identifier" }
                else if let reading = native!.1?.precomposedStringWithCanonicalMapping, validPinyin(reading) {
                    rendered = reading; converted = true
                } else { reason = "missing_or_non_latin_han_reading" }
            }
            let separator = (priorConverted || converted) && !inspection.isEmpty &&
                alphanumericEdge(inspection, last: true) && alphanumericEdge(rendered, last: false)
            if separator { inspection += " "; marked += " " }
            inspection += rendered; marked += reason == nil ? rendered : "⟦" + source + "⟧"
            if let reason { issues.append(["reason": reason, "start": range.location, "length": range.length, "original": source]) }
            pieces.append(["start": range.location, "length": range.length, "original": source, "rendered": rendered,
                           "protected_identifier": protected, "converted_han": converted, "inserted_separator": separator,
                           "issue": reason as Any? ?? NSNull()]); priorConverted = converted
        }
        // Verify protected spans survived exactly, including punctuation within URLs/code.
        for range in opaque where !inspection.contains(ns.substring(with: range)) {
            issues.append(["reason": "identifier_not_preserved", "start": range.location, "length": range.length])
        }
        return .init(reading: issues.isEmpty ? inspection : nil, inspection: inspection, marked: marked, tokens: raw,
            pieces: pieces, issues: issues, protected: opaque.map { ["start": $0.location, "length": $0.length, "original": ns.substring(with: $0)] })
    }
}
