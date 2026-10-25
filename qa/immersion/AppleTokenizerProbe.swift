// Native-framework investigation on macOS. Not iPad or release acceptance.
import Foundation
import CoreFoundation
import NaturalLanguage

let samples = [
    ("ja", "私の妹は銀行で働いています。 She will help me open an account tomorrow."),
    ("ja", "18:30に会おう。今日は水面が穏やかだね。"),
    ("ja", "明日、銀行に行きます。生きています。生の魚と生ビール。"),
    ("zh", "银行的行长明天有空。"),
    ("ko", "같이 학교에 갑니다."),
    ("ar", "ستساعدني في فتح حساب غدا.")
]
var rows: [[String: Any]] = []
for (language, text) in samples {
    let tokenizer = CFStringTokenizerCreate(nil, text as CFString, CFRange(location: 0, length: text.utf16.count),
        CFOptionFlags(kCFStringTokenizerUnitWord) | CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription),
        CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: language as CFString)))!
    var words: [[String: Any]] = []
    while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
        let range = CFStringTokenizerGetCurrentTokenRange(tokenizer)
        let reading = CFStringTokenizerCopyCurrentTokenAttribute(tokenizer, CFOptionFlags(kCFStringTokenizerAttributeLatinTranscription)) as? String
        words.append(["text": (text as NSString).substring(with: NSRange(location: range.location, length: range.length)),
                      "reading": reading.map { $0 as Any } ?? NSNull(), "start": range.location, "length": range.length])
    }
    let native = NLTokenizer(unit: .word); native.string = text; native.setLanguage(NLLanguage(rawValue: language))
    var nlWords: [String] = []
    native.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in nlWords.append(String(text[range])); return true }
    rows.append(["language": language, "text": text, "cf_tokens": words, "nl_tokens": nlWords])
}
print(String(data: try JSONSerialization.data(withJSONObject: ["platform": "macOS probe only", "results": rows], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
