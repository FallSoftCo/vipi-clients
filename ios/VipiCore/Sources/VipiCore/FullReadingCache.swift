import Foundation

/// Display metadata only. Spoken text and original message bytes never come from
/// this value. A local transliteration may have different guarantees from an
/// explicitly reviewed authored reading.
public struct FullReading: Sendable, Equatable {
    public enum Provenance: String, Sendable { case authored, localTransliteration }
    public let text: String
    /// Detailed producers may report a known static failure without retaining
    /// their oversized/partial text. Ordinary producers remain source-compatible.
    public enum Failure: String, Sendable { case outputLimit, unresolved }
    public let provenance: Provenance
    public let failure: Failure?
    public init(text: String, provenance: Provenance, failure: Failure? = nil) {
        self.text = text; self.provenance = provenance; self.failure = failure
    }
}

/// Lifetime belongs to one conversation/configuration. Rendering does a cached
/// lookup; native tokenization/dictionary work is dispatched away from rendering.
@MainActor public final class FullReadingCache {
    public typealias Producer = @Sendable (String, String) async -> FullReading?
    private struct Key: Hashable {
        let utf8: Data, language: String, policy: String
    }
    public struct Resolution: Sendable { public let value: FullReading?; public let failure: FullReading.Failure? }
    private let policy: String
    private let producer: Producer
    private let byteLimit: Int
    private var costs: [Key:Int] = [:]
    public var residentBytes: Int { costs.values.reduce(0,+) }
    private var epoch = UUID()
    private var values: [Key: Resolution] = [:]
    private var order: [Key] = []
    private var pending: [Key: (UUID, Task<Resolution, Never>)] = [:]
    public var count: Int { values.count }
    public init(policy: String, byteLimit: Int = FullMessageBudget.residentBytes, producer: @escaping Producer) {
        precondition(!policy.isEmpty && byteLimit > 0)
        self.byteLimit = byteLimit
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
    public func failure(text:String, language:String) -> FullReading.Failure? {
        values[key(text,language)]?.failure
    }
    public func resolve(text: String, language: String) async -> FullReading? {
        let resolved = await resolveDetailed(text:text,language:language)
        return resolved.value
    }
    /// Keep the exact completed reason with its caller even if another request
    /// evicts the bounded cache before the caller resumes. No output cap changes.
    public func resolveDetailed(text:String, language:String) async -> Resolution {
        guard !Task.isCancelled, (1...FullMessageBudget.recordBytes).contains(text.utf8.count),
              ["ar", "zh", "ja", "ko"].contains(language) else { return .init(value:nil,failure:nil) }
        let key = key(text, language), active = epoch
        // Resolution wraps optional so an honest unavailable outcome is cached too.
        if let saved = values[key] { return saved }
        let entry: (UUID, Task<Resolution, Never>)
        if let task = pending[key] { entry = task }
        else {
            guard pending.count < 128 else { return .init(value:nil,failure:nil) }
            let producer = self.producer
            let task = Task.detached(priority: .userInitiated) {
                guard !Task.isCancelled else { return Resolution(value:nil,failure:nil) }
                let value = await producer(text, language)
                guard !Task.isCancelled, let value else { return Resolution(value:nil,failure:nil) }
                if let reason = value.failure { return Resolution(value:nil,failure:reason) }
                guard value.text.utf8.count <= FullMessageBudget.recordBytes else { return Resolution(value:nil,failure:.outputLimit) }
                guard !value.text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else { return Resolution(value:nil,failure:.unresolved) }
                return Resolution(value:value,failure:nil)
            }
            entry = (UUID(), task); pending[key] = entry
        }
        let resolved = await entry.1.value
        guard active == epoch else { return .init(value:nil,failure:nil) }
        if pending[key]?.0 == entry.0 {
            pending.removeValue(forKey: key)
            values[key] = resolved
            costs[key] = key.utf8.count + (resolved.value?.text.utf8.count ?? 0) + 128
            order.removeAll { $0 == key }; order.append(key)
            while order.count > 128 || residentBytes > byteLimit {
                let removed = order.removeFirst(); values.removeValue(forKey:removed); costs.removeValue(forKey:removed)
            }
        }
        // Cancelling one waiter does not cancel another row's shared work.
        return Task.isCancelled ? .init(value:nil,failure:nil) : resolved
    }
    /// Explicit retry replaces only this derivative reading; it never requests translation.
    public func removeResolved(text: String, language: String) {
        let key = key(text, language)
        // Another message may already be retrying identical text. Preserve its
        // pending producer and let resolve share it; invalidate only the result.
        values.removeValue(forKey:key); costs.removeValue(forKey:key); order.removeAll { $0 == key }
    }
    public func removeAll() {
        epoch = UUID()
        for (_, task) in pending.values { task.cancel() }
        pending.removeAll(); values.removeAll(); order.removeAll(); costs.removeAll()
    }
}
