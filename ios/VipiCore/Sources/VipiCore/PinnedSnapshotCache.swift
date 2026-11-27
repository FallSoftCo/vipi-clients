import Foundation

/// Bounded per-owner LRU. Pinned keys may be visible or in flight; only inactive
/// entries are evicted. A fully pinned cache refuses insertion temporarily.
public struct PinnedSnapshotCache<Value> {
    private let capacity: Int
    private var values: [Data: Value] = [:], order: [Data] = [], pins: [Data: Int] = [:]
    public init(capacity: Int) {
        precondition(capacity > 0)
        self.capacity = capacity
    }
    public var count: Int { values.count }
    public mutating func pin(_ key: Data) { pins[key, default: 0] += 1 }
    public mutating func unpin(_ key: Data) {
        guard let count = pins[key] else { return }
        if count <= 1 { pins.removeValue(forKey: key) } else { pins[key] = count - 1 }
    }
    public mutating func value(for key: Data) -> Value? {
        guard let value = values[key] else { return nil }
        order.removeAll { $0 == key }
        order.append(key)
        return value
    }
    @discardableResult public mutating func insert(_ value: Value, for key: Data) -> Bool {
        if values[key] == nil && values.count >= capacity {
            guard let victim = order.first(where: { pins[$0] == nil }) else { return false }
            values.removeValue(forKey: victim)
            order.removeAll { $0 == victim }
        }
        values[key] = value
        order.removeAll { $0 == key }
        order.append(key)
        return true
    }
    public mutating func removeAll() {
        values.removeAll()
        order.removeAll()
        pins.removeAll()
    }
}
