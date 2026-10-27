import Foundation
import CoreFoundation
import NaturalLanguage
import VipiCore

enum LocalImmersion {
    /// Complete native sentence boundaries only; no approximate phrase windows.
    static func sentences(_ text:String,language:String) -> [NSRange] {
        let tokenizer=NLTokenizer(unit:.sentence)
        tokenizer.string=text;tokenizer.setLanguage(language=="zh" ? .simplifiedChinese : .init(rawValue:language))
        var ranges:[NSRange]=[]
        tokenizer.enumerateTokens(in:text.startIndex..<text.endIndex) { range,_ in
            var a=range.lowerBound,b=range.upperBound
            while a<b && text[a].isWhitespace {a=text.index(after:a)}
            while a<b && text[text.index(before:b)].isWhitespace {b=text.index(before:b)}
            if a<b {ranges.append(NSRange(a..<b,in:text))}
            return ranges.count<=128
        }
        // Never keep a truncated prefix as if it represented the whole message.
        return ranges.count<=128 ? ranges : []
    }
    static func words(_ text: String, language: String) -> [NSRange] {
        if language == "ko" {
            // Apple's Korean tokenizer stops after standalone punctuation,
            // e.g. "안녕하세요 🙂. 시간이 더 필요해요.". Tokenize each
            // whitespace-delimited eojeol natively so punctuation cannot hide
            // the remaining message. Never split an eojeol into guessed stems.
            let chunks = try! NSRegularExpression(pattern: #"\S+"#)
            return chunks.matches(in:text,range:NSRange(location:0,length:text.utf16.count)).flatMap { chunk -> [NSRange] in
                let fragment=(text as NSString).substring(with:chunk.range)
                let tokenizer=NLTokenizer(unit:.word)
                tokenizer.string=fragment;tokenizer.setLanguage(.korean)
                var ranges:[NSRange]=[]
                tokenizer.enumerateTokens(in:fragment.startIndex..<fragment.endIndex) { range,_ in
                    if fragment[range].unicodeScalars.contains(where:{CharacterSet.letters.contains($0)}) {
                        let local=NSRange(range,in:fragment)
                        ranges.append(NSRange(location:chunk.range.location+local.location,length:local.length))
                    }
                    return true
                }
                return ranges
            }
        }
        // NLTokenizer can omit the Japanese portion of mixed Japanese/English
        // text. Core Foundation's explicit locale retains those boundaries.
        if language == "ja" || language == "zh" {
            let tokenizer = CFStringTokenizerCreate(nil, text as CFString,
                CFRange(location: 0, length: text.utf16.count), CFOptionFlags(kCFStringTokenizerUnitWord),
                CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: language as CFString)))!
            var ranges: [NSRange] = []
            while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
                let token = CFStringTokenizerGetCurrentTokenRange(tokenizer)
                let range = NSRange(location: token.location, length: token.length)
                if (text as NSString).substring(with: range).unicodeScalars.contains(where: { CharacterSet.letters.contains($0) }) {
                    ranges.append(range)
                }
            }
            return ranges
        }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text; tokenizer.setLanguage(NLLanguage(rawValue: language))
        var ranges: [NSRange] = []
        tokenizer.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in
            if text[range].unicodeScalars.contains(where: { CharacterSet.letters.contains($0) }) { ranges.append(NSRange(range, in: text)) }
            return true
        }
        return ranges
    }
    static func align(original: String, translation: String, entries: [VocabularyEntry], density: Double, source: String, target: String,
                      supplementalEntries: [VocabularyEntry] = []) -> ImmersionResult {
        return autoreleasepool {
        let sourceWords = words(original, language: source), targetWords = words(translation, language: target)
        return ImmersionEngine().align(original: original, translation: translation, entries: entries, density: density, targetLanguage: target,
            sourceBoundaries: Set(sourceWords.flatMap { [$0.location, NSMaxRange($0)] }),
            targetBoundaries: Set(targetWords.flatMap { [$0.location, NSMaxRange($0)] }), sourceTokenCount: sourceWords.count,
            supplementalEntries: supplementalEntries)
        }
    }
}
