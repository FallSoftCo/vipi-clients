import Foundation

/// Literal preservation only. Passing this check says nothing about meaning.
public enum TranslationIntegrity {
    // Obvious underscore identifiers and common filename suffixes. This is a
    // bounded lexical rule, not detection of arbitrary paths or proper names.
    // Do not treat every dotted word as a file: ordinary chat omits spaces.
    private static let technicalTokens = #"(?<![\p{L}\p{N}\p{M}_.-])(?=[\p{L}\p{N}\p{M}_.-]*_)[\p{L}\p{N}\p{M}_.-]*[\p{L}\p{N}\p{M}_-](?![\p{L}\p{N}\p{M}_-]|\.[\p{L}\p{N}\p{M}_.-]*[\p{L}\p{N}\p{M}_-])|(?<![\p{L}\p{N}\p{M}_.])[\p{L}\p{N}\p{M}_-]+(?:\.[\p{L}\p{N}\p{M}_-]+)*\.(?i:txt|md|pdf|csv|tsv|json|jsonl|xml|yaml|yml|toml|ini|log|zip|gz|tar|jpg|jpeg|png|svg|webp|gif|heic|mp3|wav|m4a|mp4|mov|html|css|js|ts|py|swift|kt|kts|sql|apk|ipa|vipihistory)(?:\.[\p{L}\p{N}\p{M}_-]+)*(?![\p{L}\p{N}\p{M}_])"#
    private static let literals = try! NSRegularExpression(pattern: #"```[\s\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\.)[^\s<>"「」『』]+|[\p{L}\p{N}\p{M}_.+-]+@[\p{L}\p{N}\p{M}_.-]+\.[\p{L}\p{M}]{2,}|[@#][\p{L}\p{N}\p{M}_]+|"# + technicalTokens)
    private static let punctuation = Set(".,!?;:。！？、，；：…")

    /// Exact native literal ranges, using the same URL trimming as preservation.
    public static func protectedLiteralRanges(_ text: String) -> [NSRange] {
        let ns = text as NSString
        var result: [NSRange] = []
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
            result.append(NSRange(location: match.range.location, length: value.utf16.count))
        }
        return result
    }

    private static func literalOccurrences(_ text: String) -> [String] {
        let ns = text as NSString
        return protectedLiteralRanges(text).map { ns.substring(with: $0) }
    }

    // Retained for existing diagnostics/tests only. Swift String dictionary
    // equality folds canonically equivalent encodings; NEVER use it to grant
    // protected-literal integrity.
    static func identifiers(_ text: String) -> [String: Int] {
        literalOccurrences(text).reduce(into: [:]) { $0[$1, default: 0] += 1 }
    }
    private static func literalByteMultiset(_ text: String) -> [Data: Int] {
        // Convert EACH raw occurrence before any String-key aggregation.
        // No normalization, reindexing or change to the user's source bytes.
        literalOccurrences(text).reduce(into: [:]) { counts, value in
            counts[Data(value.utf8), default: 0] += 1
        }
    }
    public static func preservesIdentifiers(original: String, translation: String) -> Bool {
        literalByteMultiset(original) == literalByteMultiset(translation)
    }
}
