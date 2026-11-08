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
/// authored readings always take precedence. The new local adapter is opt-in
/// Debug QA only; its data is not a shipping resource or model download.
struct FullSentenceReadings: Sendable {
    let chinese: ChineseFullReading?
    func reading(_ text: String, language: String) -> FullReading? {
        if let authored = SentenceReadings.reading(text, language: language) {
            return .init(text: authored, provenance: .authored)
        }
        guard language == "zh", let chinese,
              let result = try? chinese.resolve(text), let reading = result.reading else { return nil }
        return .init(text: reading, provenance: .localTransliteration)
    }
    #if DEBUG
    private static let candidateEnabled = ProcessInfo.processInfo.arguments.contains("-vipi-chinese-reading-qa")
    #endif
    static let policy: String = {
        #if DEBUG
        if candidateEnabled { return "authored-first:" + ChineseFullReading.policy + ":" + ChineseFullReading.dataSHA256 }
        #endif
        return "authored-sentence-readings-1"
    }()
    private static let current: Self = {
        #if DEBUG
        if candidateEnabled {
            let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("chinese-reading-qa/ordinary-data.json")
            // The parser verifies the exact pinned size, hash and schema.
            if (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) == 773_812,
               let bytes = try? Data(contentsOf: file), let reader = try? ChineseFullReading(data: bytes) {
                return .init(chinese: reader)
            }
        }
        #endif
        return .init(chinese: nil)
    }()
    static func resolve(_ text: String, language: String) -> FullReading? {
        if let authored = SentenceReadings.reading(text, language: language) {
            return .init(text: authored, provenance: .authored)
        }
        return current.reading(text, language: language)
    }
}
