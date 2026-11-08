import Foundation

/// Display metadata only. Spoken text and original message bytes never come from
/// this value. A local transliteration may have different guarantees from an
/// explicitly reviewed authored reading.
public struct FullReading: Sendable, Equatable {
    public enum Provenance: String, Sendable { case authored, localTransliteration }
    public let text: String
    public let provenance: Provenance
    public init(text: String, provenance: Provenance) {
        self.text = text; self.provenance = provenance
    }
}

/// Lifetime belongs to one conversation/configuration. Rendering does a cached
/// lookup; native tokenization/dictionary work is dispatched away from rendering.
@MainActor public final class FullReadingCache {
    public typealias Producer = @Sendable (String, String) async -> FullReading?
    private struct Key: Hashable {
        let utf8: Data, language: String, policy: String
    }
    private struct Entry { let value: FullReading? }
    private let policy: String
    private let producer: Producer
    private var epoch = UUID()
    private var values: [Key: Entry] = [:]
    private var order: [Key] = []
    private var pending: [Key: (UUID, Task<FullReading?, Never>)] = [:]
    public var count: Int { values.count }
    public init(policy: String, producer: @escaping Producer) {
        precondition(!policy.isEmpty)
        self.policy = policy; self.producer = producer
    }
    private func key(_ text: String, _ language: String) -> Key {
        .init(utf8: Data(text.utf8), language: language, policy: policy)
    }
    public func hasResolved(text: String, language: String) -> Bool {
        values[key(text, language)] != nil
    }
    public func cached(text: String, language: String) -> FullReading? {
        values[key(text, language)]?.value
    }
    public func resolve(text: String, language: String) async -> FullReading? {
        guard !Task.isCancelled, (1...16_384).contains(text.utf16.count),
              ["ar", "zh", "ja", "ko"].contains(language) else { return nil }
        let key = key(text, language), active = epoch
        // Entry wraps optional so an honest unavailable outcome is cached too.
        if let saved = values[key] { return saved.value }
        let entry: (UUID, Task<FullReading?, Never>)
        if let task = pending[key] { entry = task }
        else {
            guard pending.count < 128 else { return nil }
            let producer = self.producer
            let task = Task.detached(priority: .userInitiated) {
                guard !Task.isCancelled else { return nil as FullReading? }
                let value = await producer(text, language)
                guard !Task.isCancelled, let value, !value.text.isEmpty,
                      value.text.utf16.count <= 65_536 else { return nil }
                return value
            }
            entry = (UUID(), task); pending[key] = entry
        }
        let value = await entry.1.value
        guard active == epoch else { return nil }
        if pending[key]?.0 == entry.0 {
            pending.removeValue(forKey: key)
            values[key] = Entry(value: value)
            order.removeAll { $0 == key }; order.append(key)
            while order.count > 128 { values.removeValue(forKey: order.removeFirst()) }
        }
        // Cancelling one waiter does not cancel another row's shared work.
        return Task.isCancelled ? nil : value
    }
    public func removeAll() {
        epoch = UUID()
        for (_, task) in pending.values { task.cancel() }
        pending.removeAll(); values.removeAll(); order.removeAll()
    }
}
