import Foundation
import VipiCore

/// Live full-text transliteration only. No authored sentence overrides or
/// translation dictionaries participate; native-script audio is authoritative.
struct FullSentenceReadings: Sendable {
    let chinese: ChineseFullReading?
    static let policy = "live-full-text-2-byte-contract:" + ChineseFullReading.policy + ":" + ChineseFullReading.dataSHA256 + ":" + KoreanFullReading.policy + ":" + JapaneseFullReading.policy + ":cf-any-latin-literals-1"
    static let statePolicy = "reading-status-3:" + policy
    /// Preserve the existing translation-cache namespace independently of reading
    /// revisions. This exact historical suffix is compatibility, not reader policy.
    static let translationCacheCompatibilitySuffix = "live-full-text-2-byte-contract:pinyin-pro-3.29.5-marked-native-2:ec2f31077ea4aa2f531e0711366bb3d07af495c8ab53f144f32a5b231ed3f35c:cf-hangul-orthographic-guard-1:cf-japanese-guard-sokuon-1:cf-arabic-latin"
    static func state(text:String, language:String, reading:FullReading?, failure:FullReading.Failure? = nil) -> FullMessageReadingState {
        guard text.utf8.count <= FullMessageBudget.recordBytes else {
            return .init(status:.unavailable,failure:.inputLimit,policy:statePolicy)
        }
        guard FullReadingRequirement.needsReading(text) else { return .init(status:.notNeeded,policy:statePolicy) }
        guard LocalLanguageCatalog.codes.contains(language) else {
            return .init(status:.unavailable,failure:.unsupportedLanguage,policy:statePolicy)
        }
        if let reason = reading?.failure ?? failure {
            return .init(status:.unavailable,failure:reason == .outputLimit ? .outputLimit : .unresolved,policy:statePolicy)
        }
        guard let reading else { return .init(status:.unavailable,failure:.producerUnavailable,policy:statePolicy) }
        guard reading.text.utf8.count <= FullMessageBudget.recordBytes else {
            return .init(status:.unavailable,failure:.outputLimit,policy:statePolicy)
        }
        guard !reading.text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              !FullReadingRequirement.needsReading(reading.text), !reading.text.unicodeScalars.contains("◌") else {
            return .init(status:.unavailable,failure:.unresolved,policy:statePolicy)
        }
        return .init(status:.available,policy:statePolicy)
    }
    /// Compatibility callers receive only a usable reading or nil. Detailed
    /// failure metadata belongs to the conversation producer, never display text.
    func reading(_ text:String, language:String) -> FullReading? {
        guard let value = detailedReading(text,language:language),value.failure == nil else { return nil }
        return value
    }
    func detailedReading(_ text:String, language:String) -> FullReading? {
        guard (1...FullMessageBudget.recordBytes).contains(text.utf8.count) else { return nil }
        guard FullReadingRequirement.needsReading(text) else { return nil }
        func failed(_ reason:FullReading.Failure) -> FullReading {
            .init(text:"",provenance:.localTransliteration,failure:reason)
        }
        let value:String?
        switch language {
        case "zh":
            // Missing reader/throw is unavailable; explicit unresolved spans are
            // known static output failure, not an endlessly retryable nil.
            guard let chinese,let result = try? chinese.resolve(text) else { return nil }
            if !result.unresolved.isEmpty { return failed(.unresolved) }
            value = result.reading
        case "ja":
            let result = JapaneseFullReading.resolve(text)
            if result.issues.contains("tokenizer_unavailable") { return nil }
            if !result.issues.isEmpty { return failed(.unresolved) }
            value = result.reading
        case "ko":
            let result = KoreanFullReading.resolve(text)
            if result.issues.contains("tokenizer_unavailable") { return nil }
            if !result.issues.isEmpty { return failed(.unresolved) }
            value = result.reading
        default:
            guard LocalLanguageCatalog.codes.contains(language) else { return nil }
            value = FullReadingRequirement.transformingReadableText(text) {
                $0.applyingTransform(.toLatin, reverse: false)
            }
        }
        // Native failure never invokes a different reader or translation provider.
        guard let value else { return nil }
        guard value.utf8.count <= FullMessageBudget.recordBytes else { return failed(.outputLimit) }
        guard !value.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              !FullReadingRequirement.needsReading(value), !value.unicodeScalars.contains("◌") else { return failed(.unresolved) }
        return .init(text:value,provenance:.localTransliteration)
    }
    struct Alignment: Sendable {
        let source:NSRange, displayed:NSRange
    }
    /// The same complete reader that produced the visible face supplies its
    /// alignment. Never divide romanization proportionally or guess syllables.
    static func alignment(text:String,reading:String,language:String) -> [Alignment] {
        if text.utf8.elementsEqual(reading.utf8) { return [.init(source:NSRange(location:0,length:text.utf16.count),displayed:NSRange(location:0,length:reading.utf16.count))] }
        var pieces:[(NSRange,String)] = []
        switch language {
        case "ja":
            let result = JapaneseFullReading.resolve(text)
            guard result.reading?.utf8.elementsEqual(reading.utf8) == true else { return [] }
            pieces = result.pieces.map{(NSRange(location:$0.startUTF16,length:$0.endUTF16-$0.startUTF16),$0.rendered)}
        case "ko":
            let result = KoreanFullReading.resolve(text)
            guard result.reading?.utf8.elementsEqual(reading.utf8) == true else { return [] }
            pieces = result.pieces.map{(NSRange(location:$0.startUTF16,length:$0.endUTF16-$0.startUTF16),$0.rendered)}
        case "zh":
            guard let result = try? current.chinese?.resolve(text),result.reading?.utf8.elementsEqual(reading.utf8) == true else { return [] }
            pieces = result.pieces.map{(NSRange(location:$0.startUTF16,length:$0.endUTF16-$0.startUTF16),$0.reading)}
        default:
            let source = text as NSString
            var cursor = 0
            text.enumerateSubstrings(in:text.startIndex..<text.endIndex,options:.byWords) { _,range,_,_ in
                let native = NSRange(range,in:text)
                if native.location > cursor { let gap = NSRange(location:cursor,length:native.location-cursor); pieces.append((gap,source.substring(with:gap))) }
                let word = source.substring(with:native)
                pieces.append((native,word.applyingTransform(.toLatin,reverse:false) ?? word)); cursor = NSMaxRange(native)
            }
            if cursor < source.length { let gap = NSRange(location:cursor,length:source.length-cursor); pieces.append((gap,source.substring(with:gap))) }
        }
        let display = reading as NSString
        var cursor = 0, result:[Alignment] = []
        for (source,value) in pieces {
            guard !value.isEmpty else { continue }
            let found = display.range(of:value,options:.literal,range:NSRange(location:cursor,length:display.length-cursor))
            guard found.location != NSNotFound else { return [] }
            let separator = display.substring(with:NSRange(location:cursor,length:found.location-cursor))
            guard separator.allSatisfy({$0 == " " || $0 == "'"}) else { return [] }
            result.append(.init(source:source,displayed:found)); cursor = NSMaxRange(found)
        }
        guard cursor == display.length else { return [] }
        return result
    }
    static func displayedRange(_ native:NSRange,text:String,reading:String,alignment:[Alignment]) -> NSRange? {
        guard native.location >= 0,native.length > 0,NSMaxRange(native) <= text.utf16.count else { return nil }
        if text.utf8.elementsEqual(reading.utf8) { return native }
        let matches = alignment.filter{NSIntersectionRange($0.source,native).length > 0}
        guard let first = matches.first,let last = matches.last else { return nil }
        return NSRange(location:first.displayed.location,length:NSMaxRange(last.displayed)-first.displayed.location)
    }
    private static let current: Self = {
        guard let file = Bundle.main.url(forResource:"chinese-ordinary",withExtension:"json"),
              let bytes = try? Data(contentsOf:file), let reader = try? ChineseFullReading(data:bytes) else { return .init(chinese:nil) }
        return .init(chinese:reader)
    }()
    static func resolve(_ text: String, language: String) -> FullReading? { current.reading(text,language:language) }
    static func resolveDetailed(_ text:String, language:String) -> FullReading? { current.detailedReading(text,language:language) }
}
