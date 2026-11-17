import Foundation

/// UIKit attachments occupy one UTF-16 unit while the original word can occupy
/// several. Translation always addresses the preserved original message.
struct OriginalTextSegment {
    let displayed: NSRange
    let original: NSRange
    var atomic = false
}

enum OriginalTextSelection {
    static func word(atUTF16 offset: Int, in original: String) -> NSRange? {
        guard offset >= 0, offset < original.utf16.count else { return nil }
        var found: NSRange?
        original.enumerateSubstrings(in: original.startIndex..<original.endIndex, options: .byWords) { _, range, _, stop in
            let candidate = NSRange(range, in: original)
            if NSLocationInRange(offset, candidate) { found = candidate; stop = true }
        }
        return found
    }
    static func range(for selection: NSRange, segments: [OriginalTextSegment], original: String) -> NSRange? {
        guard selection.location != NSNotFound, selection.location >= 0, selection.length > 0,
              selection.length <= Int.max - selection.location else { return nil }
        let originalLength = (original as NSString).length
        var mapped: [NSRange] = []
        var covered = 0
        var previousDisplayEnd = 0
        for segment in segments {
            guard segment.displayed.location >= 0, segment.displayed.length > 0,
                  segment.displayed.length <= Int.max - segment.displayed.location,
                  segment.original.location >= 0, segment.original.length > 0,
                  segment.original.location <= originalLength,
                  segment.original.length <= originalLength - segment.original.location,
                  segment.atomic || segment.displayed.length == segment.original.length,
                  segment.displayed.location >= previousDisplayEnd else { return nil }
            previousDisplayEnd = NSMaxRange(segment.displayed)
            let intersection = NSIntersectionRange(selection, segment.displayed)
            guard intersection.length > 0 else { continue }
            covered += intersection.length
            if let previous = mapped.last, NSMaxRange(previous) != segment.original.location + (segment.atomic ? 0 : intersection.location - segment.displayed.location) { return nil }
            if segment.atomic { mapped.append(segment.original) }
            else { mapped.append(NSRange(location: segment.original.location + intersection.location - segment.displayed.location,
                                         length: intersection.length)) }
        }
        guard covered == selection.length, let first = mapped.first, let last = mapped.last else { return nil }
        let range = NSRange(location: first.location, length: NSMaxRange(last) - first.location)
        guard range.length > 0 else { return nil }
        return (original as NSString).rangeOfComposedCharacterSequences(for: range)
    }
}
