import Foundation

/// Spaced visual exposure, never a claim of mastery. No chat text or message ID.
public struct VocabularyFamiliarity: Codable, Equatable, Sendable {
    public private(set) var exposureDays: Int
    public private(set) var lastDay: Int
    public init(exposureDays: Int = 0, lastDay: Int = -1) {
        self.exposureDays = max(0, min(exposureDays, 3650)); self.lastDay = max(-1, lastDay)
    }
    public mutating func observe(day: Int) -> Bool {
        guard day >= 0, day > lastDay else { return false }
        exposureDays = min(exposureDays + 1, 3650); lastDay = day
        return true
    }
    /// A familiar face stays visible longer. Meanings continue to reappear.
    /// A long absence brings back the beginner pace without deleting history.
    public func targetMilliseconds(day: Int) -> Int {
        guard day >= lastDay, day - lastDay <= 30 else { return 4500 }
        return exposureDays >= 12 ? 9000 : exposureDays >= 4 ? 6000 : 4500
    }
}
