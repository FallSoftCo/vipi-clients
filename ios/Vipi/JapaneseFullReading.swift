// Native OS reading adapter. No model preparation or phrase overrides.
import Foundation
import VipiCore
import CoreFoundation

/// Core Foundation's lexical Latin readings, with exact source reconstruction.
/// Particles retain native orthographic conventions; original audio determines
/// pronunciation. Small-tsu composition is structural, never a phrase override.
enum JapaneseFullReading {
    static let policy = "cf-japanese-guard-sokuon-1"
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
    private struct Unit {
        var range: NSRange
        var latin: String?
        var issue: String?
    }
    private static let opaquePatterns = [
        #"```[\s\S]*?```"#, #"`[^`\r\n]+`"#,
        #"(?i)(?:https?://|www\.)[^\s<>\"“”‘’，。！？；、]+"#,
        // Email punctuation can remain between exact protected Latin chunks.
        // No global greedy email validator is needed to preserve those bytes.
        #"[\p{Latin}\p{M}\p{N}]+(?:[\-_'’./:][\p{Latin}\p{M}\p{N}]+)*"#
    ]
    private static let opaqueExpressions = opaquePatterns.map { try! NSRegularExpression(pattern: $0) }
    private static func japanese(_ s: Unicode.Scalar) -> Bool {
        switch s.value {
        case 0x3041...0x309F, 0x30A0...0x30FF, 0x31F0...0x31FF,
            0xFF66...0xFF9F, 0x3400...0x4DBF, 0x4E00...0x9FFF,
            0xF900...0xFAFF, 0x20000...0x323AF, 0x3005:
            return true
        default: return false
        }
    }
    private static func unknownLetter(_ scalar: Unicode.Scalar) -> Bool {
        CharacterSet.letters.contains(scalar)
            && String(scalar).range(of: #"\p{Latin}"#, options: .regularExpression) == nil
    }
    private static func usable(_ latin: String) -> Bool {
        latin.range(of: #"\A[\p{Latin}\p{M}]+(?:[ '\-][\p{Latin}\p{M}]+)*\z"#, options: .regularExpression) != nil
            && latin.range(of: #"\p{Latin}"#, options: .regularExpression) != nil
    }
    private static func geminate(_ latin: String) -> String? {
        if latin.hasPrefix("ch") { return "t" }
        guard let first = latin.first, "bdfghjkpstvwz".contains(first) else { return nil }
        return String(first)
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
                for p in span { mask[p] = true }
            }
        }
        let scalars = Array(text.unicodeScalars)
        var offsets = [0]
        for scalar in scalars { offsets.append(offsets.last! + scalar.utf16.count) }
        func classification(_ i: Int) -> String {
            if (offsets[i]..<offsets[i + 1]).allSatisfy({ mask[$0] }) { return "opaque" }
            if japanese(scalars[i]) { return "japanese" }
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
                    startUTF16: range.location, endUTF16: NSMaxRange(range), source: native.substring(with: range),
                    rendered: rendered, kind: kind, insertedSeparator: separator, issue: issue))
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
            guard kind == "japanese" else {
                append(span, rendered: source, kind: kind, issue: kind == "unresolved" ? "untranscribed_script" : nil)
                continue
            }
            let run = source as NSString
            let options =
                CFOptionFlags(kCFStringTokenizerUnitWord) | CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)
            guard
                let tokenizer = CFStringTokenizerCreate(
                    nil, source as CFString, CFRange(location: 0, length: run.length),
                    options, CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: "ja" as CFString)))
            else {
                append(span, rendered: source, kind: "unresolved", issue: "tokenizer_unavailable")
                continue
            }
            var end = 0, units: [Unit] = []
            while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
                let raw = CFStringTokenizerGetCurrentTokenRange(tokenizer)
                guard raw.location >= end, raw.length > 0, raw.location <= run.length,
                    raw.length <= run.length - raw.location
                else {
                    issues.append("invalid_native_range")
                    continue
                }
                if raw.location > end {
                    units.append(
                        .init(
                            range: NSRange(location: span.location + end, length: raw.location - end),
                            latin: nil, issue: "untokenized_japanese"))
                }
                let range = NSRange(location: span.location + raw.location, length: raw.length)
                let latin =
                    CFStringTokenizerCopyCurrentTokenAttribute(
                        tokenizer,
                        CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)) as? String
                tokens.append(
                    .init(
                        startUTF16: range.location, endUTF16: NSMaxRange(range), source: native.substring(with: range),
                        rawLatin: latin))
                units.append(.init(range: range, latin: latin, issue: nil))
                end = raw.location + raw.length
            }
            if end < run.length {
                units.append(
                    .init(
                        range: NSRange(location: span.location + end, length: run.length - end), latin: nil,
                        issue: "untokenized_japanese"))
            }
            var resolved: [Unit] = [], i = 0
            while i < units.count {
                let unit = units[i]
                if let raw = unit.latin, raw.hasSuffix("~tsu"),
                    let last = native.substring(with: unit.range).unicodeScalars.last,
                    [0x3063, 0x30C3, 0xFF6F].contains(last.value), i + 1 < units.count
                {
                    let next = units[i + 1], prefix = String(raw.dropLast(4))
                    if NSMaxRange(unit.range) == next.range.location,
                        let latin = next.latin, usable(latin), let initial = geminate(latin),
                        prefix.isEmpty || usable(prefix)
                    {
                        var range = NSRange(
                            location: unit.range.location, length: NSMaxRange(next.range) - unit.range.location)
                        var value = prefix + initial + latin
                        if prefix.isEmpty {
                            guard let previous = resolved.last, let text = previous.latin, usable(text),
                                NSMaxRange(previous.range) == range.location
                            else {
                                resolved.append(.init(range: unit.range, latin: nil, issue: "unresolved_geminate"))
                                i += 1
                                continue
                            }
                            resolved.removeLast()
                            range = NSRange(
                                location: previous.range.location, length: NSMaxRange(range) - previous.range.location)
                            value = text + value
                        }
                        resolved.append(.init(range: range, latin: value, issue: nil))
                        i += 2
                        continue
                    }
                }
                if let latin = unit.latin, usable(latin) {
                    resolved.append(unit)
                } else {
                    resolved.append(
                        .init(range: unit.range, latin: nil, issue: unit.issue ?? "missing_or_non_latin_reading"))
                }
                i += 1
            }
            for unit in resolved {
                if let latin = unit.latin {
                    append(unit.range, rendered: latin, kind: "converted")
                } else {
                    append(
                        unit.range, rendered: native.substring(with: unit.range), kind: "unresolved", issue: unit.issue)
                }
            }
        }
        return .init(
            reading: issues.isEmpty && convertedAny ? inspection : nil, inspection: inspection, pieces: pieces,
            tokens: tokens, issues: issues)
    }
}
