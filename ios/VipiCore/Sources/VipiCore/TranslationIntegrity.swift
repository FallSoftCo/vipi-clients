import Foundation

/// Literal preservation only. Passing this check says nothing about meaning.
public enum TranslationIntegrity {
    private static let literals = try! NSRegularExpression(pattern: #"```[\s\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\.)[^\s<>"「」『』]+|[\p{L}\p{N}_.+-]+@[\p{L}\p{N}_.-]+\.[\p{L}]{2,}|[@#][\p{L}\p{N}_]+"#)
    private static let punctuation = Set(".,!?;:。！？、，；：…")

    static func identifiers(_ text: String) -> [String: Int] {
        let ns = text as NSString
        var result: [String: Int] = [:]
        for match in literals.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            var value = ns.substring(with: match.range)
            let lower = value.lowercased()
            if lower.hasPrefix("http://") || lower.hasPrefix("https://") || lower.hasPrefix("www.") {
                // Strip sentence punctuation, retaining balanced URL delimiters.
                while let last = value.last {
                    let opening: Character? = [")": "(", "]": "[", "}": "{"][last]
                    let unmatched = opening.map { open in value.filter { $0 == last }.count > value.filter { $0 == open }.count } ?? false
                    guard punctuation.contains(last) || unmatched else { break }
                    value.removeLast()
                }
            }
            result[value, default: 0] += 1
        }
        return result
    }

    public static func preservesIdentifiers(original: String, translation: String) -> Bool {
        identifiers(original) == identifiers(translation)
    }
}
