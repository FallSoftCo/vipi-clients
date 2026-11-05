import Foundation

/// One selected visible run. A slot identity denotes an inline word face;
/// literal source gaps have no slot. Original faces remain explicitly marked.
public struct ImmersionCopyRun: Sendable, Equatable {
    public let text: String
    public let slotID: Int?
    public let showsOriginal: Bool

    public init(text: String, slotID: Int? = nil, showsOriginal: Bool = true) {
        self.text = text
        self.slotID = slotID
        self.showsOriginal = showsOriginal
    }
}

/// Logical clipboard/accessibility text only. This does not alter visual slots,
/// UTF-16 source anchors, matching, original messages or speech segments.
public enum ImmersionCopyText {
    public static func compose(_ selectedRuns: [ImmersionCopyRun]) -> String {
        var result = ""
        var previous: ImmersionCopyRun?
        for run in selectedRuns {
            if let previous,
               let leftID = previous.slotID,
               let rightID = run.slotID,
               leftID != rightID,
               !(previous.showsOriginal && run.showsOriginal),
               latinLetterAtEdge(previous.text, fromEnd: true),
               latinLetterAtEdge(run.text, fromEnd: false) {
                result += " "
            }
            result += run.text
            previous = run
        }
        return result
    }

    private static func latinLetterAtEdge(_ text: String, fromEnd: Bool) -> Bool {
        // Swift Character supplies the platform's standard grapheme boundary.
        // Do not skip leading marks or split joiner/emoji clusters.
        guard let edge = fromEnd ? text.last : text.first,
              let first = edge.unicodeScalars.first,
              latinLetter(first) else { return false }
        return edge.unicodeScalars.allSatisfy { scalar in
            if latinLetter(scalar) { return true }
            switch scalar.properties.generalCategory {
            case .nonspacingMark, .spacingMark, .enclosingMark:
                return true
            default:
                return false
            }
        }
    }

    private static func latinLetter(_ scalar: Unicode.Scalar) -> Bool {
        switch scalar.properties.generalCategory {
        case .uppercaseLetter, .lowercaseLetter, .titlecaseLetter, .modifierLetter, .otherLetter:
            return String(scalar).range(of: #"\p{Latin}"#, options: .regularExpression) != nil
        default:
            return false
        }
    }
}
