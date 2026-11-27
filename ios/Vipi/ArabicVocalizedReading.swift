import Foundation
import VipiCore

/// Dormant conventional renderer for explicitly vocalized Arabic. It never
/// fills missing short vowels or enables a prediction model.
enum ArabicVocalizedReading {
    static let policy = "vocalized-arabic-conventional-latin-candidate-1"
    struct Piece: Sendable {
        let startUTF16: Int, endUTF16: Int, source: String, reading: String?
        let protected: Bool
    }
    struct Result: Sendable {
        let reading: String?
        let pieces: [Piece]
        let unresolved: [NSRange]
    }
    private static let consonants: [Character: String] = [
        "ء": "'", "أ": "'", "إ": "'", "ؤ": "'", "ئ": "'", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "ḥ", "خ": "kh",
        "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "ṣ", "ض": "ḍ", "ط": "ṭ", "ظ": "ẓ", "ع": "'",
        "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y", "ة": "t"
    ]
    private static let sun = Set("تثدذرزسشصضطظلن")
    // Omitted orthographic long alif only; supplied short vowels remain authoritative.
    private static let longAlif: [String: Set<Int>] = [
        "هذا": [0], "هذه": [0], "ذلك": [0], "هؤلاء": [0], "أولئك": [2], "لكن": [0], "الله": [2], "الرحمن": [4],
        "رحمن": [2], "إله": [1], "الإله": [3]
    ]
    private static let vowels: [Character: String] = [
        "َ": "a", "ُ": "u", "ِ": "i", "ً": "an", "ٌ": "un", "ٍ": "in", "ْ": ""
    ]
    private static func mark(_ c: Unicode.Scalar) -> Bool { CharacterSet.nonBaseCharacters.contains(c) }
    private static func letter(_ c: Unicode.Scalar) -> Bool {
        CharacterSet.letters.contains(c)
            && ((0x600...0x6ff).contains(c.value) || (0x750...0x77f).contains(c.value)
                || (0x8a0...0x8ff).contains(c.value) || (0xfb50...0xfdff).contains(c.value)
                || (0xfe70...0xfeff).contains(c.value))
    }
    private struct Node { let base: Character, marks: Set<Character> }
    private static func nodes(_ word: String) -> [Node]? {
        let scalars = Array(word.precomposedStringWithCanonicalMapping.unicodeScalars)
        var result: [Node] = [], i = 0
        while i < scalars.count {
            let base = scalars[i]
            i += 1
            if base == "ـ" { continue }
            guard letter(base) else { return nil }
            var marks = Set<Character>()
            while i < scalars.count && mark(scalars[i]) {
                marks.insert(Character(String(scalars[i])))
                i += 1
            }
            guard marks.allSatisfy({ vowels[$0] != nil || $0 == "ّ" || $0 == "ٰ" }),
                marks.filter({ vowels[$0] != nil }).count <= 1
            else { return nil }
            result.append(.init(base: Character(String(base)), marks: marks))
        }
        return result.isEmpty ? nil : result
    }
    private static func short(_ node: Node) -> String? { node.marks.compactMap { vowels[$0] }.first }
    private static func word(_ text: String) -> String? {
        guard let n = nodes(text) else { return nil }
        let bare = String(n.map(\.base))
        var boost = longAlif[bare] ?? []
        if n.count > 1, "وفبك".contains(n[0].base), ["a", "i"].contains(short(n[0]) ?? ""),
            let extra = longAlif[String(bare.dropFirst())]
        {
            boost.formUnion(extra.map { $0 + 1 })
        }
        var start = 0, prefix = "", suppressDouble = -1
        var article = n.count > 2 && "اٱ".contains(n[0].base) && n[1].base == "ل" ? 0 : -1
        if article < 0, n.count > 3, "وفبك".contains(n[0].base), ["a", "i"].contains(short(n[0]) ?? ""),
            "اٱ".contains(n[1].base), n[2].base == "ل"
        {
            prefix = consonants[n[0].base]! + (short(n[0]) ?? "") + "-"
            article = 1
        }
        if article >= 0 {
            start = article + 2
            let next = n[start].base
            if sun.contains(next) {
                prefix += (article == 0 ? "a" : "") + consonants[next]! + "-"
                suppressDouble = start
            } else {
                prefix += (article == 0 ? "al-" : "l-")
            }
            if String(bare.dropFirst(article)) == "الله" {
                prefix = article == 0 ? "al" : String(prefix.dropLast(2)) + "l"
            }
        } else if n.count > 2, n[0].base == "ل", short(n[0]) == "i", n[1].base == "ل", n[1].marks.contains("ْ") {
            prefix = "li-l-"
            start = 2
        }
        var output = prefix, i = start
        while i < n.count {
            let node = n[i], c = node.base, next = i + 1 < n.count ? n[i + 1] : nil
            if c == "آ" {
                output += (i == 0 ? "ā" : "'ā")
                i += 1
                continue
            }
            if c == "ا", i == n.count - 1, i > 0, n[i - 1].base == "و", node.marks.isEmpty {
                i += 1
                continue
            }
            var consonant: String
            if "اٱ".contains(c) {
                consonant = ""
            } else if c == "ة", short(node) == nil {
                consonant = "h"
            } else if i == 0, "أإ".contains(c) {
                consonant = ""
            } else {
                guard let value = consonants[c] else { return nil }
                consonant = value
            }
            var vowel = short(node)
            if node.marks.contains("ٰ") {
                guard vowel == nil || vowel == "a" else { return nil }
                vowel = "ā"
            }
            if boost.contains(i), vowel == "a" { vowel = "ā" }
            if vowel == nil {
                if c == "ة", i == n.count - 1 {
                    output += "h"
                    i += 1
                    continue
                }
                if node.marks.contains("ّ"), i == n.count - 1 { vowel = "" } else { return nil }
            }
            if node.marks.contains("ّ"), i != suppressDouble { consonant += consonant }
            var consumed = 1
            if let next, next.marks.isEmpty {
                if (vowel == "a" && "اى".contains(next.base)) || (vowel == "u" && next.base == "و")
                    || (vowel == "i" && next.base == "ي")
                {
                    vowel = vowel == "a" ? "ā" : vowel == "u" ? "ū" : "ī"
                    consumed = 2
                } else if vowel == "an", next.base == "ا" {
                    consumed = 2
                }
            }
            output += consonant + (vowel ?? "")
            i += consumed
        }
        return output
    }
    static func resolve(_ text: String) -> Result {
        guard (1...16_384).contains(text.utf16.count) else { return .init(reading: nil, pieces: [], unresolved: []) }
        let native = text as NSString, scalars = Array(text.unicodeScalars)
        var offsets = [0], mask = [Bool](repeating: false, count: native.length)
        for scalar in scalars { offsets.append(offsets.last! + scalar.utf16.count) }
        var protectedRanges = TranslationIntegrity.protectedLiteralRanges(text)
        let latin = try! NSRegularExpression(pattern: #"[\p{Latin}][\p{Latin}\p{M}]*(?:[’'._-][\p{Latin}\p{M}]+)*"#)
        protectedRanges += latin.matches(in: text, range: NSRange(location: 0, length: native.length)).map(\.range)
        for range in protectedRanges { for i in range.location..<NSMaxRange(range) { mask[i] = true } }
        func protected(_ i: Int) -> Bool { (offsets[i]..<offsets[i + 1]).allSatisfy { mask[$0] } }
        func kind(_ i: Int) -> Int {
            if protected(i) { return 0 }
            return letter(scalars[i]) || mark(scalars[i]) || scalars[i] == "ـ" ? 1 : 2
        }
        var pieces: [Piece] = [], unresolved: [NSRange] = [], output = "", i = 0, any = false
        while i < scalars.count {
            let start = i, type = kind(i)
            i += 1
            while i < scalars.count && kind(i) == type { i += 1 }
            let range = NSRange(location: offsets[start], length: offsets[i] - offsets[start])
            let source = native.substring(with: range), value = type == 1 ? word(source) : source
            if type == 1 {
                any = true
                if value == nil { unresolved.append(range) }
            }
            if type == 2,
                source.unicodeScalars.contains(where: {
                    CharacterSet.letters.contains($0)
                        && String($0).range(of: #"\p{Latin}"#, options: .regularExpression) == nil
                })
            {
                unresolved.append(range)
            }
            pieces.append(
                .init(
                    startUTF16: range.location, endUTF16: NSMaxRange(range), source: source, reading: value,
                    protected: type == 0))
            output += value ?? source
        }
        precondition(pieces.map(\.source).joined().utf8.elementsEqual(text.utf8))
        return .init(
            reading: any && unresolved.isEmpty && output.utf16.count <= 65_536 ? output : nil, pieces: pieces,
            unresolved: unresolved)
    }
}
