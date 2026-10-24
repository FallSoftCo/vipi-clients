import Foundation

public enum DeliveryState: String, Codable, Sendable {
    case queued, accepted, delivered, failed, expired
}

/// Delivery lifetime is independent of reconnects and local history retention.
public struct DeliveryWindow: Codable, Equatable, Sendable {
    public static let lifetime: TimeInterval = 72 * 60 * 60
    public let messageID: UUID
    public let createdAt: Date
    public var expiresAt: Date { createdAt.addingTimeInterval(Self.lifetime) }
    public init(messageID: UUID = UUID(), createdAt: Date) {
        self.messageID = messageID; self.createdAt = createdAt
    }
    public func canRetry(at now: Date, state: DeliveryState) -> Bool {
        now < expiresAt && (state == .queued || state == .accepted)
    }
}
