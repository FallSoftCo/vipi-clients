import Foundation

/// Exact authored sentence values only; native segmentation remains the caller's.
public enum ReferenceComposition {
    public static func compose(original: String, sentences: [NSRange], target: String,
                               lookup: (String) -> String?) -> String? {
        guard !sentences.isEmpty else { return nil }
        let text = original as NSString
        var end = 0, output = ""
        for range in sentences {
            guard range.location >= end, range.location <= text.length, range.length > 0,
                  range.length <= text.length-range.location, Range(range, in: original) != nil else { return nil }
            let gap = text.substring(with: NSRange(location: end, length: range.location-end))
            guard gap.allSatisfy(\.isWhitespace), let value = lookup(text.substring(with: range)) else { return nil }
            if gap.isEmpty, let last = output.last, let first = value.unicodeScalars.first,
               !["zh", "ja"].contains(String(target.split(separator: "-").first ?? "")),
               ".!?。！？”’\"'".contains(last),
               (CharacterSet.letters.contains(first) || first.properties.generalCategory == .decimalNumber) || "¿¡“‘\"'".unicodeScalars.contains(first) {
                output += " "
            }
            output += gap + value; end = NSMaxRange(range)
        }
        let tail = text.substring(from: end)
        return tail.allSatisfy(\.isWhitespace) ? output + tail : nil
    }
}
