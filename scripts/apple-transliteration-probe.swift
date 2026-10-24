import Foundation
import CoreFoundation

let samples: [(String, String)] = [
    ("zh", "重庆的银行今天开门。"), ("zh", "队长长大了。音乐很好听。"), ("zh", "我要还书。"),
    ("ja", "明日は日本橋に行きます。"), ("ja", "生ビールを一杯ください。"), ("ja", "今日は銀行に行きます。"),
    ("ar", "هل نشرب القهوة غدًا؟"), ("ar", "أريد أن أفتح حسابًا في البنك."),
    ("ko", "내일 커피 마실래?"), ("ko", "같이 한국어를 공부해요.")
]
var rows: [[String: Any]] = []
for (language, text) in samples {
    let tokenizer = CFStringTokenizerCreate(nil, text as CFString, CFRange(location: 0, length: (text as NSString).length),
        kCFStringTokenizerUnitWord, CFLocaleCreate(nil, CFLocaleIdentifier(rawValue: language as CFString)))!
    var tokens: [[String: Any]] = []
    while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
        let range = CFStringTokenizerGetCurrentTokenRange(tokenizer)
        let original = (text as NSString).substring(with: NSRange(location: range.location, length: range.length))
        let latin = CFStringTokenizerCopyCurrentTokenAttribute(tokenizer, kCFStringTokenizerAttributeLatinTranscription) as? String
        tokens.append(["text": original, "latin": latin as Any? ?? NSNull()])
    }
    rows.append(["language": language, "text": text, "generic_to_latin": text.applyingTransform(.toLatin, reverse: false) ?? "",
        "tokenizer": tokens, "quality_status": "unreviewed_probe_not_accepted"])
}
let data = try JSONSerialization.data(withJSONObject: ["platform": "macOS", "results": rows], options: [.prettyPrinted, .sortedKeys])
print(String(decoding: data, as: UTF8.self))
