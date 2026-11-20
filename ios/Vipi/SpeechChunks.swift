import Foundation
import NaturalLanguage

enum SpeechChunks {
    /// Two adjacent immersion units may have no separator in the original
    /// script. Keep their utterances distinct instead of synthesizing a new
    /// joined word (for example, English “togetherlunch” from Japanese slots).
    /// Whitespace and punctuation already supply a natural joining boundary.
    static func coalesced(_ spans: [(text: String, language: String)]) -> [(text: String, language: String)] {
        var result: [(text: String, language: String)] = []
        for span in spans {
            guard !span.text.isEmpty else { continue }
            let punctuationOnly = span.text.allSatisfy { $0.isWhitespace || ".,!?;:。！？、؛،".contains($0) }
            if let last = result.last {
                let touchingLetters = last.text.last?.isLetter == true && span.text.first?.isLetter == true
                if punctuationOnly || (last.language == span.language && !touchingLetters) {
                    result[result.count - 1].text += span.text
                    continue
                }
            }
            if !span.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { result.append(span) }
        }
        return result
    }
    /// Linear bounded lookahead; String.count on each remaining suffix makes
    /// large messages quadratic. Never cut a grapheme or discard source tails.
    static func plan(_ spans:[(text:String,language:String)]) -> [[(text:String,language:String)]] {
        plan(spans,checkCancellation:{})
    }
    static func plan(_ spans: [(text: String, language: String)],
                     checkCancellation: () throws -> Void) rethrows -> [[(text: String, language: String)]] {
        var chunks: [[(text:String,language:String)]] = []
        var current: [(text:String,language:String)] = [], count = 0
        for span in spans {
            var start = span.text.startIndex
            while start < span.text.endIndex {
                try checkCancellation()
                var end = start, length = 0, boundary: (String.Index,Int)?
                while end < span.text.endIndex && length < 160 {
                    let character = span.text[end]
                    end = span.text.index(after:end); length += 1
                    if length >= 60 && (character.isWhitespace || ".!?。！？،,;；".contains(character)) { boundary = (end,length) }
                }
                if end != span.text.endIndex,let preferred = boundary { end = preferred.0; length = preferred.1 }
                if count > 0 && count + length > 160 { chunks.append(current); current = []; count = 0 }
                current.append((String(span.text[start..<end]),span.language)); count += length
                start = end
            }
        }
        if !current.isEmpty { chunks.append(current) }
        return chunks
    }
    static func wordRanges(_ text:String,language:String) -> [NSRange] {
        let tokenizer = NLTokenizer(unit:.word)
        tokenizer.string = text; tokenizer.setLanguage(NLLanguage(rawValue:language))
        var ranges:[NSRange] = []
        tokenizer.enumerateTokens(in:text.startIndex..<text.endIndex) { range,_ in
            if hasSpokenContent(String(text[range])) { ranges.append(NSRange(range,in:text)) }
            return true
        }
        return ranges
    }
    static func marksCoverWords(_ marks:[SpeechMark],text:String,language:String) -> Bool {
        let words = wordRanges(text,language:language)
        guard !words.isEmpty,!marks.isEmpty else { return false }
        let offsets = marks.sorted{$0.start < $1.start}.map(\.byteSampleOffset)
        guard zip(offsets,offsets.dropFirst()).allSatisfy({$0.0 < $0.1}) else { return false }
        let ranges = marks.filter{$0.start >= 0 && $0.start <= text.utf16.count && $0.length > 0 && $0.length <= text.utf16.count-$0.start}.map{NSRange(location:$0.start,length:$0.length)}.sorted{$0.location < $1.location}
        return words.allSatisfy { word in
            var cursor = word.location
            for range in ranges where NSIntersectionRange(range,word).length > 0 {
                guard range.location <= cursor else { return false }
                cursor = max(cursor,NSMaxRange(range))
                if cursor >= NSMaxRange(word) { return true }
            }
            return false
        }
    }
    /// Keep each native sentence intact for continuous prosody. The bounded
    /// source-message budget and synthesis timeout still apply to long sentences.
    static func sentencePlan(_ spans:[(text:String,language:String)]) -> [[(text:String,language:String)]] {
        var result:[[(text:String,language:String)]] = []
        for span in spans {
            var cursor = span.text.startIndex
            span.text.enumerateSubstrings(in:span.text.startIndex..<span.text.endIndex,options:.bySentences) { _,_,enclosing,_ in
                guard enclosing.upperBound > cursor else { return }
                result.append([(String(span.text[cursor..<enclosing.upperBound]),span.language)])
                cursor = enclosing.upperBound
            }
            if cursor < span.text.endIndex { result.append([(String(span.text[cursor...]),span.language)]) }
        }
        return result
    }
    static func hasSpokenContent(_ text:String) -> Bool {
        text.unicodeScalars.contains { CharacterSet.alphanumerics.contains($0) }
    }
}
