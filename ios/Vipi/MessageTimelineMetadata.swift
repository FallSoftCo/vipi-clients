import Foundation

/// Routine chronology is grouped visually; every message retains its exact
/// date and delivery state in its accessibility context.
enum MessageTimelineMetadata {
    static func timeLabel(for date: Date, previous: Date?, now: Date = .now, calendar: Calendar = .current) -> String? {
        if let previous, calendar.isDate(date, inSameDayAs: previous), date.timeIntervalSince(previous) < 5 * 60 {
            return nil
        }
        return date.formatted(date: calendar.isDate(date, inSameDayAs: now) ? .omitted : .abbreviated, time: .shortened)
    }
    static func showsFriendState(_ state: String, outgoing: Bool, latestOutgoing: Bool) -> Bool {
        if state == "imported" { return true }
        guard outgoing else { return false }
        return latestOutgoing || (state != "delivered" && state != "accepted")
    }
}
