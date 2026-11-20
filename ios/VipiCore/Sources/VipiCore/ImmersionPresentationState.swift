import Foundation

/// Identity of the visible request, not just its text or availability revision.
/// Native generation changes on direction/configuration/input-language changes.
public struct ImmersionRequestIdentity: Sendable, Equatable, Hashable {
    public let messageID: String, text: String, source: String, target: String
    public let inputLanguage: String?
    public let generation: UUID
    // Synthesized Equatable/Hashable must also distinguish the original raw
    // encoding: Swift String's canonical equivalence is not request identity.
    private let encodedText: Data
    public init(messageID: String, text: String, source: String, target: String,
                inputLanguage: String?, generation: UUID) {
        self.messageID = messageID; self.text = text; self.source = source; self.target = target
        self.inputLanguage = inputLanguage; self.generation = generation
        self.encodedText = Data(text.utf8)
    }
}

/// Used by the native view, including the paused result path. An optional value
/// inside a pending envelope distinguishes "clear when resumed" from no update.
public struct ImmersionPresentationState: Sendable {
    private struct Bound: Sendable {
        let identity: ImmersionRequestIdentity
        let value: ImmersionPresentation?
    }
    private var visible: Bound?
    private var waiting: Bound?
    public init() {}
    public func value(for current: ImmersionRequestIdentity) -> ImmersionPresentation? {
        visible?.identity == current ? visible?.value : nil
    }
    public mutating func publish(_ value: ImmersionPresentation?, for produced: ImmersionRequestIdentity,
                                 current: ImmersionRequestIdentity, paused: Bool) {
        guard produced == current else { return }
        let bound = Bound(identity: produced, value: value)
        if paused { waiting = bound } else { visible = bound; waiting = nil }
    }
    public mutating func invalidate(for current: ImmersionRequestIdentity) {
        if visible?.identity != current { visible = nil }
        if waiting?.identity != current { waiting = nil }
    }
    public mutating func resume(for current: ImmersionRequestIdentity) {
        if let waiting, waiting.identity == current { visible = waiting }
        waiting = nil
        invalidate(for: current)
    }
}

/// Every insertion (including onPartial before a suspended/cancelled provider)
/// goes through the same bound. This is result state, not a provider/model cache.
public struct ImmersionPresentationCache {
    // Convert raw keys BEFORE dictionary/order aggregation. Keep the external
    // String API and all source/range bytes unchanged; do not normalize keys.
    private var values: [Data: LookupFirstOutcome] = [:]
    private var order: [Data] = []
    public init() {}
    public var count: Int { values.count }
    public subscript(key: String) -> ImmersionPresentation? { values[Data(key.utf8)]?.result }
    public func cachedInvocation(key: String) -> LookupFirstOutcome? { values[Data(key.utf8)]?.cachedInvocation() }
    public mutating func remember(_ value: ImmersionPresentation, key: String) {
        let partial: Bool
        if case .partial = value { partial = true } else { partial = false }
        remember(.init(result: value, origin: partial ? .sourceReferencePartial : .localFullContext,
            status: partial ? .partial : .ready, localTranslationCalls: 0, fallbackStatus: nil), key: key)
    }
    public mutating func remember(_ value: LookupFirstOutcome, key: String) {
        guard value.result != nil || value.isRejectedLocalTranslation else { return }
        let encodedKey = Data(key.utf8)
        // A rejected late response cannot erase usable visible immersion.
        if value.isRejectedLocalTranslation, values[encodedKey]?.result != nil { return }
        // Concurrent rows may request the same text. A late partial callback or
        // failed extension must not erase an already validated whole reference.
        if values[encodedKey]?.result?.translation != nil, value.result?.translation == nil { return }
        values[encodedKey] = value; order.removeAll { $0 == encodedKey }; order.append(encodedKey)
        while order.count > 128 { values.removeValue(forKey: order.removeFirst()) }
    }
    /// Availability changes invalidate only deterministic provider rejections;
    /// approved partials/full references retain their existing cache behavior.
    public mutating func removeRejectedTranslations() {
        let rejected = Set(values.filter { $0.value.isRejectedLocalTranslation }.map(\.key))
        for key in rejected { values.removeValue(forKey: key) }
        order.removeAll { rejected.contains($0) }
    }
    public mutating func removeAll() { values.removeAll(); order.removeAll() }
}

/// Exact stored message and the two complete on-device translation faces.
/// Reading is display metadata; playback always uses practiceText in its native script.
public struct WordReplacement: Sendable, Equatable, Codable {
    public let start: Int
    public let length: Int
    public let source: String
    public let target: String
    public let reading: String?
    public init(start:Int,length:Int,source:String,target:String,reading:String?) {
        self.start = start; self.length = length; self.source = source; self.target = target; self.reading = reading
    }
}

public struct FullMessageTranslation: Sendable, Equatable, Codable {
    public let original: String
    public let practiceText: String
    public let meaningText: String
    public let inputLanguage: String
    public let practiceLanguage: String
    public let meaningLanguage: String
    public let practiceReading: String?
    public let readingState: FullMessageReadingState?
    /// nil identifies retained full-message fixtures; [] is a completed
    /// incremental message with no new/repeated translatable word.
    public let words: [WordReplacement]?
    public init(original: String, practiceText: String, meaningText: String,
                inputLanguage: String, practiceLanguage: String, meaningLanguage: String, practiceReading:String? = nil, readingState:FullMessageReadingState? = nil, words:[WordReplacement]? = nil) {
        self.original = original; self.practiceText = practiceText; self.meaningText = meaningText
        self.inputLanguage = inputLanguage; self.practiceLanguage = practiceLanguage; self.meaningLanguage = meaningLanguage; self.practiceReading = practiceReading; self.readingState = readingState
        self.words = words
    }
    private enum CodingKeys: String, CodingKey {
        case original, practiceText, meaningText, inputLanguage, practiceLanguage, meaningLanguage, practiceReading, readingState, words
    }
    public init(from decoder:Decoder) throws {
        let values = try decoder.container(keyedBy:CodingKeys.self)
        original = try values.decode(String.self,forKey:.original)
        practiceText = try values.decode(String.self,forKey:.practiceText)
        meaningText = try values.decode(String.self,forKey:.meaningText)
        inputLanguage = try values.decode(String.self,forKey:.inputLanguage)
        practiceLanguage = try values.decode(String.self,forKey:.practiceLanguage)
        meaningLanguage = try values.decode(String.self,forKey:.meaningLanguage)
        // Unknown or damaged derivative metadata triggers only a reading refresh.
        // The complete translated message must not become a model cache miss.
        practiceReading = try? values.decodeIfPresent(String.self,forKey:.practiceReading)
        readingState = try? values.decodeIfPresent(FullMessageReadingState.self,forKey:.readingState)
        words = try values.decodeIfPresent([WordReplacement].self,forKey:.words)
    }
    public func withReading(_ reading: String?, state: FullMessageReadingState) -> Self {
        .init(original:original, practiceText:practiceText, meaningText:meaningText,
              inputLanguage:inputLanguage, practiceLanguage:practiceLanguage, meaningLanguage:meaningLanguage,
              practiceReading:reading, readingState:state,words:words)
    }
    /// Compatibility with source selection/copy primitives; no word spans or invented alignment.
    public var presentation: ImmersionPresentation {
        var offset = 0
        let spans = (words ?? []).map { word in
            let targetRange = NSRange(location:word.start+offset,length:word.target.utf16.count)
            offset += word.target.utf16.count-word.length
            return ImmersionSpan(range:NSRange(location:word.start,length:word.length),original:word.source,
                translated:word.target,targetRange:targetRange,romanization:word.reading)
        }
        return .complete(.init(original: meaningText, translation: practiceText, spans: spans))
    }
    public var practiceSpeech: [SpeechSpan] {
        if let words {
            var spans:[SpeechSpan] = [], end:Int?
            let source = original as NSString
            for word in words {
                let gap = end.map{NSRange(location:$0,length:max(0,word.start-$0))}
                if let gap,NSMaxRange(gap) <= source.length,
                   source.substring(with:gap).allSatisfy({$0.isWhitespace || $0.isPunctuation}),let last = spans.last {
                    spans[spans.count-1] = .init(text:last.text+source.substring(with:gap)+word.target,language:practiceLanguage)
                } else { spans.append(.init(text:word.target,language:practiceLanguage)) }
                end = word.start+word.length
            }
            return spans
        }
        return [.init(text:practiceText,language:practiceLanguage)]
    }
}
