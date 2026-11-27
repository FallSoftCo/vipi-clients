import Foundation

/// One selected visible run. A slot identity denotes an inline word face;
/// literal source gaps have no slot. Original faces remain explicitly marked.
public struct ImmersionCopyRun: Sendable, Equatable {
    public let text: String
    public let slotID: Int?
    public let showsOriginal: Bool
    // Only the typed partial proof factory below grants sentence metadata.
    let sentenceRange: NSRange?
    let sentenceTarget: String?
    let wholeFace: Bool
    let readingFace: Bool

    public init(text: String, slotID: Int? = nil, showsOriginal: Bool = true) {
        self.text = text
        self.slotID = slotID
        self.showsOriginal = showsOriginal
        sentenceRange = nil
        sentenceTarget = nil
        wholeFace = true
        readingFace = false
    }
    init(
        text: String, slotID: Int, showsOriginal: Bool, sentenceRange: NSRange?, sentenceTarget: String?,
        wholeFace: Bool, readingFace: Bool
    ) {
        self.text = text
        self.slotID = slotID
        self.showsOriginal = showsOriginal
        self.sentenceRange = sentenceRange
        self.sentenceTarget = sentenceTarget
        self.wholeFace = wholeFace
        self.readingFace = readingFace
    }
}

/// Logical clipboard/accessibility text only. This does not alter visual slots,
/// UTF-16 source anchors, matching, original messages or speech segments.
public enum ImmersionCopyText {
    /// Chooses the same face as the native attachment renderer. Imported faces
    /// stay atomic; revealed originals use only their selected source slice.
    /// Sentence authority requires a matching WHOLE typed partial reference.
    public static func run(
        for span: ImmersionSpan, in value: ImmersionPresentation,
        showingOriginal: Bool, script: Bool = false,
        selectedOriginalRange: NSRange? = nil
    ) -> ImmersionCopyRun {
        let length = value.original.utf16.count
        guard span.range.location >= 0, span.range.location <= length,
            span.range.length > 0, span.range.length <= length - span.range.location
        else { return .init(text: "") }
        if let selectedOriginalRange {
            guard selectedOriginalRange.location >= 0, selectedOriginalRange.location <= length,
                selectedOriginalRange.length >= 0,
                selectedOriginalRange.length <= length - selectedOriginalRange.location
            else { return .init(text: "") }
        }
        let selected = selectedOriginalRange.map { NSIntersectionRange($0, span.range) } ?? span.range
        guard selected.length > 0 else { return .init(text: "") }
        let face =
            showingOriginal
            ? (value.original as NSString).substring(with: selected)
            : (script ? span.translated : span.displayedTarget)
        var range: NSRange? = nil
        var target: String? = nil
        if case .partial(let partial) = value,
            let proof = partial.references.first(where: { $0.range == span.range }),
            proof.original.utf8.elementsEqual(span.original.utf8),
            proof.translated.utf8.elementsEqual(span.translated.utf8),
            span.targetRange == NSRange(location: 0, length: proof.translated.utf16.count)
        {
            range = proof.range
            target = partial.targetLanguage
        }
        return .init(
            text: face, slotID: span.id, showsOriginal: showingOriginal,
            sentenceRange: range, sentenceTarget: target, wholeFace: !showingOriginal || selected == span.range,
            readingFace: !showingOriginal && !script && span.romanization != nil)
    }

    public static func compose(_ selectedRuns: [ImmersionCopyRun]) -> String {
        var result = ""
        var previous: ImmersionCopyRun?
        for run in selectedRuns {
            if let previous,
                let leftID = previous.slotID,
                let rightID = run.slotID,
                leftID != rightID,
                !(previous.showsOriginal && run.showsOriginal)
            {
                let sentenceBoundary: Bool
                if let left = previous.sentenceRange, let right = run.sentenceRange,
                    NSMaxRange(left) == right.location, previous.wholeFace && run.wholeFace,
                    let target = run.sentenceTarget, previous.sentenceTarget == target
                {
                    sentenceBoundary = ReferenceComposition.needsSeparator(
                        left: previous.text, right: run.text,
                        target: target, readingFace: previous.readingFace || run.readingFace)
                } else {
                    sentenceBoundary = false
                }
                if sentenceBoundary
                    || (latinLetterAtEdge(previous.text, fromEnd: true) && latinLetterAtEdge(run.text, fromEnd: false))
                {
                    result += " "
                }
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
            latinLetter(first)
        else { return false }
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
