import Foundation
import NaturalLanguage
let requested = ["en", "es", "fr", "de", "pt", "it", "ar", "hi", "zh", "ja", "ko", "sw"]
let rows: [[String: Any]] = requested.map { code in
    let schemes = NLTagger.availableTagSchemes(for: .word, language: NLLanguage(rawValue: code))
    return ["requested_language": code, "queried_language_raw_value": code, "word_schemes": schemes.map { $0.rawValue }]
}
let aliases: [[String: Any]] = [NLLanguage.simplifiedChinese, NLLanguage.traditionalChinese].map { language in
    ["api_language_raw_value": language.rawValue, "word_schemes": NLTagger.availableTagSchemes(for: .word, language: language).map { $0.rawValue }]
}
let output: [String: Any] = ["schema": "vipi.native-tag-scheme-inventory.1", "requested_languages_exact": requested, "requested_count": requested.count, "os": ProcessInfo.processInfo.operatingSystemVersionString, "unit": "word", "rows": rows, "chinese_api_aliases_supplemental": aliases, "limits": "Availability inventory only; no tagger inference, asset request or download. Not accuracy, local-data completeness, phone availability or source-role qualification."]
let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[1]), options: .atomic)
