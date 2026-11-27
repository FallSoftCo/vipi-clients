import Foundation

/// Exact authored sentence values only; native segmentation remains the caller's.
public enum ReferenceComposition {
    public static func compose(
        original: String, sentences: [NSRange], target: String,
        lookup: (String) -> String?
    ) -> String? {
        guard !sentences.isEmpty else { return nil }
        let text = original as NSString
        var end = 0, output = ""
        for range in sentences {
            guard range.location >= end, range.location <= text.length, range.length > 0,
                range.length <= text.length - range.location, Range(range, in: original) != nil
            else { return nil }
            let gap = text.substring(with: NSRange(location: end, length: range.location - end))
            guard gap.allSatisfy(\.isWhitespace), let value = lookup(text.substring(with: range)) else { return nil }
            if gap.isEmpty, needsSeparator(left: output, right: value, target: target) { output += " " }
            output += gap + value
            end = NSMaxRange(range)
        }
        let tail = text.substring(from: end)
        return tail.allSatisfy(\.isWhitespace) ? output + tail : nil
    }
    /// Same whole-sentence rule for full-reference composition and typed partial
    /// copy/accessibility faces. A real imported reading explicitly opts into
    /// word-spaced presentation; target zh/ja script does not gain spaces.
    public static func needsSeparator(
        left: String, right: String, target: String,
        readingFace: Bool = false
    ) -> Bool {
        guard let last = left.last, let first = right.unicodeScalars.first,
            readingFace || !["zh", "ja"].contains(String(target.split(separator: "-").first ?? "")),
            ".!?。！？”’\"'".contains(last)
        else { return false }
        return CharacterSet.letters.contains(first) || first.properties.generalCategory == .decimalNumber
            || "¿¡“‘\"'".unicodeScalars.contains(first)
    }

}
