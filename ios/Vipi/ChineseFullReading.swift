import Foundation
import VipiCore
import CryptoKit

/// Native ordinary-pinyin implementation of pinned pinyin-pro 3.29.5 data and
/// max-probability phrase selection (MIT, copyright 2022-present zh-lx).
/// See qa/immersion/chinese-reading-upstream-r01 for complete source and notice.
/// Marked dictionary tones are a visual guide; original-script audio stays authoritative.
struct ChineseFullReading: Sendable {
    static let dataSHA256 = "ec2f31077ea4aa2f531e0711366bb3d07af495c8ab53f144f32a5b231ed3f35c"
    static let policy = "pinyin-pro-3.29.5-marked-native-2"
    enum Invalid: Error { case data, input }
    struct Piece: Sendable, Codable {
        let startUTF16: Int, endUTF16: Int, source: String, reading: String
        let converted: Bool, protected: Bool
    }
    struct Result: Sendable {
        let reading: String?
        let pieces: [Piece]
        let unresolved: [NSRange]
    }
    private struct CharacterEntry: Decodable {
        let source: String, readings: [String]
        init(from decoder: Decoder) throws {
            var row = try decoder.unkeyedContainer()
            source = try row.decode(String.self); readings = try row.decode([String].self)
            guard row.isAtEnd else { throw Invalid.data }
        }
    }
    private struct Pattern: Decodable, Sendable {
        let source: String, readings: [String], probability: Double, priority: Int, order: Int
    }
    private struct Word: Decodable, Sendable { let source: String, readings: [String]; let capitalized: Bool }
    private let words: [Word]
    private struct Tables: Decodable {
        let schema: String, characters: [CharacterEntry], patterns: [Pattern], words: [Word]
    }
    private struct Node: Sendable { var children: [UInt32: Int] = [:]; var pattern: Int? }
    private struct State {
        var probability: Double, decimal: Int, next: Int
        var pattern: Int?
        mutating func scale() {
            if probability < 1e-300 { probability *= 1e300; decimal += 1 }
        }
    }
    private let characters: [UInt32: [String]]
    private let patterns: [Pattern]
    private let nodes: [Node]
    init(data: Data) throws {
        guard data.count == 813_708,
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == Self.dataSHA256 else { throw Invalid.data }
        let table = try JSONDecoder().decode(Tables.self, from: data)
        guard table.schema == "vipi-pinyin-pro-marked-2", table.characters.count == 21_132,
              table.patterns.count == 4_198 else { throw Invalid.data }
        var chars: [UInt32: [String]] = [:], trie = [Node()]
        for item in table.characters {
            let source = Array(item.source.unicodeScalars)
            guard source.count == 1, !item.readings.isEmpty, item.readings.allSatisfy({ !$0.isEmpty }),
                  chars[source[0].value] == nil else { throw Invalid.data }
            chars[source[0].value] = item.readings
        }
        for (index, pattern) in table.patterns.enumerated() {
            let scalars = Array(pattern.source.unicodeScalars)
            guard (2...5).contains(scalars.count), scalars.count == pattern.readings.count,
                  pattern.priority == 1, pattern.order == index,
                  pattern.probability.isFinite, pattern.probability > 0 else { throw Invalid.data }
            var node = 0
            for scalar in scalars {
                if let next = trie[node].children[scalar.value] { node = next }
                else {
                    let next = trie.count; trie.append(Node()); trie[node].children[scalar.value] = next; node = next
                }
            }
            // Upstream inserts later equal-probability entries before earlier
            // ones; only the highest priority/probability terminal is emitted.
            if let old = trie[node].pattern, table.patterns[old].probability > pattern.probability { continue }
            trie[node].pattern = index
        }
        guard table.words.count == 35, table.words.allSatisfy({ (2...5).contains($0.source.unicodeScalars.count) && $0.source.unicodeScalars.count == $0.readings.count }) else { throw Invalid.data }
        words = table.words.sorted { $0.source.unicodeScalars.count > $1.source.unicodeScalars.count }
        characters = chars; patterns = table.patterns; nodes = trie
    }
    private static func best(_ a: State?, _ b: State) -> State {
        guard let a else { return b }
        if a.decimal != b.decimal { return a.decimal < b.decimal ? a : b }
        return a.probability > b.probability ? a : b // exact ties prefer incoming
    }
    private func selected(_ scalars: [Unicode.Scalar], protected: [Bool]) -> [Int: Int] {
        guard !scalars.isEmpty else { return [:] }
        let n = scalars.count
        var ending = [[(Int, Int)]](repeating: [], count: n)
        // Bounded length-five trie produces the same end-index/longest-first
        // match order as upstream AC, without building a second fail automaton.
        for start in 0..<n where !protected[start] {
            var node = 0
            for end in start..<min(n, start + 5) {
                guard !protected[end], let next = nodes[node].children[scalars[end].value] else { break }
                node = next
                if let pattern = nodes[node].pattern { ending[end].append((start, pattern)) }
            }
        }
        var dp = [State?](repeating: nil, count: n)
        let terminal = State(probability: 1, decimal: 0, next: n, pattern: nil)
        for end in stride(from: n - 1, through: 0, by: -1) {
            let suffix = end + 1 == n ? terminal : dp[end + 1]!
            let next = suffix.pattern == nil ? suffix.next : end + 1
            // Ascending starts above mean longest-first; upstream traverses its
            // end-sorted match list backwards, so process shortest-first here.
            for (start, pattern) in ending[end].reversed() {
                var state = State(probability: patterns[pattern].probability * suffix.probability,
                                  decimal: suffix.decimal, next: next, pattern: pattern)
                state.scale(); dp[start] = Self.best(dp[start], state)
            }
            // Reproduce upstream's explicit decimal=0 fallback exactly. Do not
            // silently change numeric/tie behavior while asserting parity.
            var unknown = State(probability: 1e-13 * suffix.probability, decimal: 0, next: next, pattern: nil)
            unknown.scale(); dp[end] = Self.best(dp[end], unknown)
        }
        var chosen: [Int: Int] = [:], index = 0
        while index < n {
            let state = dp[index]!
            if let pattern = state.pattern { chosen[index] = pattern }
            index = state.next
        }
        return chosen
    }
    private static let opaquePatterns = [
        #"```[\s\S]*?```"#, #"`[^`\r\n]+`"#,
        #"(?i)(?:https?://|www\.)[^\s<>\"“”‘’，。！？；、]+"#,
        #"[\p{Latin}\p{M}\p{N}._%+\-]+@[\p{Latin}\p{M}\p{N}.\-]+\.[\p{Latin}\p{M}]{2,}"#,
        #"[\p{Latin}\p{M}\p{N}]+(?:[\-_'’./:][\p{Latin}\p{M}\p{N}]+)*"#
    ]
    func resolve(_ text: String, preserveOpaque: Bool = true) throws -> Result {
        guard (1...FullMessageBudget.recordBytes).contains(text.utf8.count) else { throw Invalid.input }
        let scalars = Array(text.unicodeScalars), native = text as NSString
        var offsets = [0]
        // Each regex emits non-overlapping matches. A bounded UTF16 occupancy
        // mask preserves ordered-pattern precedence without scanning every
        // earlier range for each identifier and each source scalar.
        var opaque = [Bool](repeating: false, count: native.length)
        for scalar in scalars { offsets.append(offsets.last! + scalar.utf16.count) }
        if preserveOpaque {
            for pattern in Self.opaquePatterns {
                for match in try NSRegularExpression(pattern: pattern).matches(in: text, range: NSRange(location: 0, length: native.length)) {
                    let range = match.range.location..<NSMaxRange(match.range)
                    if !range.contains(where: { opaque[$0] }) {
                        for position in range { opaque[position] = true }
                    }
                }
            }
        }
        let protected = scalars.indices.map { i in (offsets[i]..<offsets[i+1]).allSatisfy { opaque[$0] } }
        let selected = selected(scalars, protected: protected)
        var values = scalars.indices.map { i -> String in
            let scalar = scalars[i], previous = i == 0 ? nil : characters[scalars[i-1].value]
            if protected[i] { return String(scalar) }
            if scalar == "了", previous == nil { return "liǎo" }
            if scalar == "々" { return previous?.first ?? "tóng" }
            return characters[scalar.value]?.first ?? String(scalar)
        }
        for (start, pattern) in selected {
            for (offset, reading) in patterns[pattern].readings.enumerated() { values[start + offset] = reading }
        }
        // Word joins require exact selected syllables; no pronunciation is guessed.
        var joined = [String?](repeating: nil, count: scalars.count), wordStart = 0
        while wordStart < scalars.count {
            let start = wordStart
            let word = words.first { word in
                let source = Array(word.source.unicodeScalars)
                return start + source.count <= scalars.count && source.indices.allSatisfy { j in
                    !protected[start+j] && scalars[start+j] == source[j] && values[start+j] == word.readings[j]
                }
            }
            guard let word else { wordStart += 1; continue }
            for j in 1..<word.readings.count {
                joined[start+j] = values[start+j].first.map { "aāáǎàeēéěèoōóǒò".contains($0) } == true ? "'" : ""
            }
            if word.capitalized { values[start] = values[start].prefix(1).uppercased() + values[start].dropFirst() }
            wordStart += word.readings.count
        }
        var pieces: [Piece] = [], unresolved: [NSRange] = [], output = "", previousConverted = false
        for i in scalars.indices {
            let source = String(scalars[i]), reading = values[i], converted = source != reading && !protected[i]
            let range = NSRange(location: offsets[i], length: offsets[i+1] - offsets[i])
            if !protected[i] && !converted && CharacterSet.letters.contains(scalars[i]) &&
                source.range(of: #"\p{Latin}"#, options: .regularExpression) == nil { unresolved.append(range) }
            if let join = joined[i] { output += join }
            else if (previousConverted || converted), let left = output.unicodeScalars.last,
               let right = reading.unicodeScalars.first, (CharacterSet.alphanumerics.contains(left) || CharacterSet.nonBaseCharacters.contains(left)),
               CharacterSet.alphanumerics.contains(right) { output += " " }
            output += reading; previousConverted = converted
            pieces.append(.init(startUTF16: offsets[i], endUTF16: offsets[i+1], source: source,
                                reading: reading, converted: converted, protected: protected[i]))
        }
        return .init(reading: unresolved.isEmpty ? output : nil, pieces: pieces, unresolved: unresolved)
    }
}
