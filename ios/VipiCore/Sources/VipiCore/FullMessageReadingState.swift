import Foundation

/// Reading-guide metadata is independent of the translated message and speech.
/// Absence on an older record means it needs a reading-only refresh.
public struct FullMessageReadingState: Codable, Sendable, Equatable {
    public enum Status: String, Codable, Sendable { case notNeeded, available, unavailable }
    public enum Failure: String, Codable, Sendable { case inputLimit, unsupportedLanguage, producerUnavailable
        case outputLimit = "OUTPUT_LIMIT", unresolved = "UNRESOLVED" }
    public let status: Status
    public let failure: Failure?
    public let policy: String
    public var canRetry: Bool { status == .unavailable && failure == .producerUnavailable }
    public init(status: Status, failure: Failure? = nil, policy: String) {
        self.status = status; self.failure = failure; self.policy = policy
    }
}

/// Inspect the actual text, including Latin-only output from a non-Latin target.
/// Code, URLs and actual email addresses are literal content, never pronunciation input.
public enum FullReadingRequirement {
    private static let protected = [
        #"```[\s\S]*?```"#, #"`[^`\r\n]+`"#,
        #"(?i)(?:https?://|www\.)[^\s<>\"“”‘’，。！？；、]+"#
    ].map { try! NSRegularExpression(pattern: $0) }
    private static let nonLatinLetter = try! NSRegularExpression(pattern: #"[\p{L}&&[^\p{Latin}\p{Common}\p{Inherited}]]"#)
    // Start only at actual @ scalars. Each local/domain run is scanned at most
    // twice because @ is neither a local nor domain character. No global greedy
    // email search retries from every position of a long non-email identifier.
    private static func emailRanges(_ text:String) -> [NSRange] {
        let scalars = Array(text.unicodeScalars)
        var offsets = [0], spans:[NSRange] = []
        for scalar in scalars { offsets.append(offsets.last! + scalar.utf16.count) }
        func letterOrMark(_ scalar:Unicode.Scalar) -> Bool {
            CharacterSet.letters.contains(scalar) || CharacterSet.nonBaseCharacters.contains(scalar)
        }
        func identifier(_ scalar:Unicode.Scalar) -> Bool {
            letterOrMark(scalar) || CharacterSet.alphanumerics.contains(scalar)
        }
        for at in scalars.indices where scalars[at] == "@" {
            var start = at, end = at + 1
            while start > 0 && (identifier(scalars[start-1]) || "_.+%-".unicodeScalars.contains(scalars[start-1])) { start -= 1 }
            while end < scalars.count && (identifier(scalars[end]) || "_.-".unicodeScalars.contains(scalars[end])) {
                end += 1
            }
            while end > at+1 && scalars[end-1] == "." { end -= 1 }
            guard start < at,let dot = scalars[(at+1)..<end].lastIndex(of:"."),dot > at+1,end-dot-1 >= 2,
                  scalars[(dot+1)..<end].allSatisfy(letterOrMark) else { continue }
            spans.append(NSRange(location:offsets[start],length:offsets[end]-offsets[start]))
        }
        return spans
    }
    public static func needsReading(_ text: String) -> Bool {
        let length = (text as NSString).length
        let range = NSRange(location: 0, length: length)
        let letters = nonLatinLetter.matches(in: text, range: range)
        guard !letters.isEmpty else { return false }
        let spans = (protected.flatMap { $0.matches(in: text, range: range).map(\.range) } + emailRanges(text))
            .sorted { $0.location < $1.location }
        var index = 0, coveredThrough = 0
        for letter in letters {
            while index < spans.count && spans[index].location <= letter.range.location {
                coveredThrough = max(coveredThrough, NSMaxRange(spans[index])); index += 1
            }
            if NSMaxRange(letter.range) > coveredThrough { return true }
        }
        return false
    }
}
