import Foundation

/// Read-only source dictionary observations. These records never authorize a
/// translation or remove a caller's protection. The adapter shares the existing
/// native dictionary loader; it does not claim Python research-tokenizer parity.
enum LexicalSourceRecognition {
    struct Form: Sendable {
        let lexemeID: String
        let written: String
        // Mode0 with raw0/0 has no lexical focus; keep the recognized form.
        let intrinsicRange: NSRange?
        let number: Int
        let mode: Int
        let sourceSafe: Bool
        let targetSafe: Bool
        let features: Set<String>
        let partOfSpeech: String
        let isProperName: Bool
        let isGrammar: Bool
        let headword: String
    }
    struct Unit: Sendable {
        let key: String
        let range: NSRange
        let original: String
        let sourceBlocked: Bool
        let targetBlocked: Bool
        let hasNameGuard: Bool
        let protectsInner: Bool
        let forms: [Form]
    }
    struct Snapshot: Sendable {
        let original: String
        let language: String
        let dictionaryRelease: String
        let dictionaryInventory: String
        let suppliedProtection: [NSRange]
        let namedPlaces: [NSRange]
        let phraseRanges: [NSRange]
        let units: [Unit]

        func matches(original text: String, language: String,
                     dictionaryRelease: String, dictionaryInventory: String,
                     protectedRanges: [NSRange]) -> Bool {
            original.utf8.elementsEqual(text.utf8) && self.language == language &&
                self.dictionaryRelease == dictionaryRelease &&
                self.dictionaryInventory == dictionaryInventory &&
                suppliedProtection == protectedRanges
        }

        /// Invalid geometry is protected. A false result says nothing about
        /// meaning, form eligibility, a source-blocked unit or display approval.
        func hasStructuralProtection(at range: NSRange) -> Bool {
            guard LexicalSourceRecognition.valid(range, in: original) else { return true }
            if (suppliedProtection + namedPlaces).contains(where: {
                NSIntersectionRange($0, range).length > 0
            }) { return true }
            func strictlyContains(_ outer: NSRange) -> Bool {
                outer != range && outer.location <= range.location && NSMaxRange(outer) >= NSMaxRange(range)
            }
            return phraseRanges.contains(where: strictlyContains) ||
                units.contains { $0.protectsInner && strictlyContains($0.range) }
        }
    }

    static func valid(_ range: NSRange, in text: String) -> Bool {
        let count = text.utf16.count
        guard range.location >= 0, range.location <= count, range.length > 0,
              range.length <= count - range.location else { return false }
        let edges = Set(text.indices.map { $0.utf16Offset(in: text) } + [count])
        return edges.contains(range.location) && edges.contains(NSMaxRange(range))
    }
}
