import Foundation

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
