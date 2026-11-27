// Native OS reading adapter. No model preparation or sound-change rules.
import Foundation
import VipiCore
import CoreFoundation

/// Retains Core Foundation's spelling-based Hangul transcription, including its
/// hyphens. This is not a claim of pronunciation-oriented Revised Romanization.
enum KoreanFullReading {
    static let policy = "cf-hangul-orthographic-guard-1"
    struct Piece: Sendable, Codable {
        let startUTF16: Int, endUTF16: Int, source: String, rendered: String
        let kind: String, insertedSeparator: Bool, issue: String?
    }
    struct Token: Sendable, Codable {
        let startUTF16: Int, endUTF16: Int, source: String, rawLatin: String?
    }
    struct Result: Sendable, Codable {
        let reading: String?, inspection: String
        let pieces: [Piece], tokens: [Token], issues: [String]
    }
    private static let opaquePatterns = [
        #"```[\s\S]*?```"#, #"`[^`\r\n]+`"#,
        #"(?i)(?:https?://|www\.)[^\s<>\"“”‘’，。！？；、]+"#,
        #"[\p{Latin}\p{M}\p{N}._%+\-]+@[\p{Latin}\p{M}\p{N}.\-]+\.[\p{Latin}\p{M}]{2,}"#,
        #"[\p{Latin}\p{M}\p{N}]+(?:[\-_'’./:][\p{Latin}\p{M}\p{N}]+)*"#
    ]
    private static let opaqueExpressions = opaquePatterns.map { try! NSRegularExpression(pattern: $0) }
    private static func hangul(_ scalar: Unicode.Scalar) -> Bool {
        (0xAC00...0xD7A3).contains(scalar.value)
    }
    private static func unknownLetter(_ scalar: Unicode.Scalar) -> Bool {
        CharacterSet.letters.contains(scalar)
            && String(scalar).range(of: #"\p{Latin}"#, options: .regularExpression) == nil
    }
    private static func usable(_ latin: String) -> Bool {
        // Do not modify native hyphenation or infer unobserved pronunciation.
        latin.range(of: #"\A[A-Za-z]+(?:[ -][A-Za-z]+)*\z"#, options: .regularExpression) != nil
    }
    static func resolve(_ text: String) -> Result {
        let native = text as NSString
        guard (1...FullMessageBudget.recordBytes).contains(text.utf8.count) else {
            return .init(reading: nil, inspection: text, pieces: [], tokens: [], issues: ["input_length"])
        }
        var mask = [Bool](repeating: false, count: native.length)
        for regex in opaqueExpressions {
            for match in regex.matches(in: text, range: NSRange(location: 0, length: native.length)) {
                let span = match.range.location..<NSMaxRange(match.range)
                guard !span.contains(where: { mask[$0] }) else { continue }
                for position in span { mask[position] = true }
            }
        }
        let scalars = Array(text.unicodeScalars)
        var offsets = [0]
        for scalar in scalars { offsets.append(offsets.last! + scalar.utf16.count) }
        func classification(_ i: Int) -> String {
            if (offsets[i]..<offsets[i + 1]).allSatisfy({ mask[$0] }) { return "opaque" }
            if hangul(scalars[i]) { return "hangul" }
            return unknownLetter(scalars[i]) ? "unresolved" : "literal"
        }
        var pieces: [Piece] = [], tokens: [Token] = [], issues: [String] = [], inspection = ""
        var previousConverted = false, convertedAny = false
        func append(_ range: NSRange, rendered: String, kind: String, issue: String? = nil) {
            let converted = kind == "converted"
            let separator =
                (previousConverted || converted)
                && inspection.unicodeScalars.last.map(CharacterSet.alphanumerics.contains) == true
                && rendered.unicodeScalars.first.map(CharacterSet.alphanumerics.contains) == true
            if separator { inspection += " " }
            inspection += rendered
            pieces.append(
                .init(
                    startUTF16: range.location, endUTF16: NSMaxRange(range),
                    source: native.substring(with: range), rendered: rendered, kind: kind,
                    insertedSeparator: separator, issue: issue))
            if let issue { issues.append(issue) }
            previousConverted = converted
            convertedAny = convertedAny || converted
        }
        var index = 0
        while index < scalars.count {
            let kind = classification(index), first = index
            index += 1
            while index < scalars.count && classification(index) == kind { index += 1 }
            let span = NSRange(location: offsets[first], length: offsets[index] - offsets[first])
            let source = native.substring(with: span)
            guard kind == "hangul" else {
                append(
                    span, rendered: source, kind: kind,
                    issue: kind == "unresolved" ? "untranscribed_script" : nil)
                continue
            }
            let run = source as NSString
            let options =
                CFOptionFlags(kCFStringTokenizerUnitWord) | CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)
            guard
                let tokenizer = CFStringTokenizerCreate(
                    nil, source as CFString,
                    CFRange(location: 0, length: run.length), options,
                    CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: "ko" as CFString)))
            else {
                append(span, rendered: source, kind: "unresolved", issue: "tokenizer_unavailable")
                continue
            }
            var end = 0
            while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
                let raw = CFStringTokenizerGetCurrentTokenRange(tokenizer)
                guard raw.location >= end, raw.length > 0, raw.location <= run.length,
                    raw.length <= run.length - raw.location
                else {
                    issues.append("invalid_native_range")
                    continue
                }
                if raw.location > end {
                    let gap = NSRange(location: span.location + end, length: raw.location - end)
                    append(gap, rendered: native.substring(with: gap), kind: "unresolved", issue: "untokenized_hangul")
                }
                let range = NSRange(location: span.location + raw.location, length: raw.length)
                let latin =
                    CFStringTokenizerCopyCurrentTokenAttribute(
                        tokenizer,
                        CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)) as? String
                tokens.append(
                    .init(
                        startUTF16: range.location, endUTF16: NSMaxRange(range),
                        source: native.substring(with: range), rawLatin: latin))
                if let latin, usable(latin) {
                    append(range, rendered: latin, kind: "converted")
                } else {
                    append(
                        range, rendered: native.substring(with: range), kind: "unresolved",
                        issue: "missing_or_non_latin_reading")
                }
                end = raw.location + raw.length
            }
            if end < run.length {
                let gap = NSRange(location: span.location + end, length: run.length - end)
                append(gap, rendered: native.substring(with: gap), kind: "unresolved", issue: "untokenized_hangul")
            }
        }
        return .init(
            reading: issues.isEmpty && convertedAny ? inspection : nil,
            inspection: inspection, pieces: pieces, tokens: tokens, issues: issues)
    }
}
