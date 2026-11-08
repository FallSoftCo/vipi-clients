import Foundation
import VipiCore

/// Explicit readings of complete authored sentences. Unknown clauses, names or
/// changed grammar never inherit a neighbouring sentence's reading.
enum SentenceReadings {
    private struct Index: Decodable {
        struct Entry: Decodable { let language: String; let text: String; let latin: String }
        let schema: String; let entries: [Entry]
    }
    private static let index: [String: [String: String]] = {
        guard let url = Bundle.main.url(forResource: "sentence-readings", withExtension: "json"),
              let bytes = try? Data(contentsOf: url), let value = try? JSONDecoder().decode(Index.self, from: bytes),
              value.schema == "vipi-sentence-readings-1" else { return [:] }
        var result: [String: [String: String]] = [:]
        for entry in value.entries {
            guard ["ar", "zh", "ja", "ko"].contains(entry.language), !entry.text.isEmpty, !entry.latin.isEmpty,
                  result[entry.language]?[entry.text] == nil else { return [:] }
            result[entry.language, default: [:]][entry.text] = entry.latin
        }
        return result
    }()
    static func reading(_ text: String, language: String) -> String? {
        guard text.utf16.count <= 16_384, let values = index[language] else { return nil }
        if let value = values[text] { return value }
        let ranges = LocalImmersion.sentences(text, language: language)
        guard !ranges.isEmpty else { return nil }
        let native = text as NSString
        var end = 0, result = ""
        for range in ranges {
            let gap = native.substring(with: NSRange(location: end, length: range.location-end))
            guard gap.allSatisfy(\.isWhitespace), let reading = values[native.substring(with: range)] else { return nil }
            // Written Japanese/Chinese need no inter-sentence space; Latin
            // readings do. Preserve explicit whitespace when it is present.
            result += gap.isEmpty && !result.isEmpty ? " " : gap
            result += reading; end = NSMaxRange(range)
        }
        let tail = native.substring(from: end)
        return tail.allSatisfy(\.isWhitespace) ? result + tail : nil
    }
}

/// Full-text display metadata, resolved outside SwiftUI rendering. Reviewed
/// authored readings always take precedence. The ordinary Chinese guide uses
/// pinned bundled data; original-script audio remains pronunciation authority.
struct FullSentenceReadings: Sendable {
    let chinese: ChineseFullReading?
    func reading(_ text: String, language: String) -> FullReading? {
        if let authored = SentenceReadings.reading(text, language: language) {
            return .init(text: authored, provenance: .authored)
        }
        if language == "ko" { return Self.korean(text) }
        guard language == "zh", let chinese,
              let result = try? chinese.resolve(text), let reading = result.reading else { return nil }
        return .init(text: reading, provenance: .localTransliteration)
    }
    static let policy = "authored-first:" + ChineseFullReading.policy + ":" + ChineseFullReading.dataSHA256 + ":" + KoreanFullReading.policy
    private static func korean(_ text: String) -> FullReading? {
        guard let reading = KoreanFullReading.resolve(text).reading else { return nil }
        return .init(text: reading, provenance: .localTransliteration)
    }
    private static let current: Self = {
        // Static initialization runs once inside the off-render cache producer.
        // Missing or changed data leaves authored readings usable.
        if let file = Bundle.main.url(forResource: "chinese-ordinary", withExtension: "json"),
           (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) == 773_812,
           let bytes = try? Data(contentsOf: file), let reader = try? ChineseFullReading(data: bytes) {
            return .init(chinese: reader)
        }
        return .init(chinese: nil)
    }()
    static func resolve(_ text: String, language: String) -> FullReading? {
        if let authored = SentenceReadings.reading(text, language: language) {
            return .init(text: authored, provenance: .authored)
        }
        if language == "ko" { return korean(text) }
        guard language == "zh" else { return nil }
        return current.reading(text, language: language)
    }
}
