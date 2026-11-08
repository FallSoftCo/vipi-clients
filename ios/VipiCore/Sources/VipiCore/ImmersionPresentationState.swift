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
