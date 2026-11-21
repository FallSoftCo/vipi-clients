import Foundation

struct NotificationEnvelope: Decodable {
    let id: UUID
    let peer: UUID
    let display_name: String
    let accepted_at: Double
    let messages: [RoutedMessage.Received]

    func preview(grant: NotificationGrant, vault: MessageVault, device: DeviceCredential,
                 checkGrant: () throws -> NotificationGrant?) throws -> (sender: String, body: String, repeated: Bool) {
        let name = NotificationAccess.line(display_name, limit: 80)
        guard !name.isEmpty, grant.account == vault.account, peer != grant.account,
              messages.count <= 8, messages.allSatisfy({ !$0.hasGroupContext }) else { throw MessageVault.Failure.invalidRecord }
        let peerKey = peer.uuidString.lowercased()
        let idKey = id.uuidString.lowercased()
        func check() throws {
            guard try checkGrant() == grant, let consent = try vault.notificationConsent(),
                  consent.epoch == grant.epoch, accepted_at >= consent.since,
                  try vault.get("local", "registered-device") == Data(device.id.uuidString.lowercased().utf8),
                  try vault.get("local", "replacement-consent") == nil,
                  try vault.get("blocked", peerKey) == nil, try vault.get("identity-change", peerKey) == nil,
                  try vault.get("local", "initialized") != nil else { throw MessageVault.Failure.invalidRecord }
        }
        try vault.transaction { try check() }
        let core = try MessagingCore(vault: vault)
        guard core.device.id == device.id else { throw MessageVault.Failure.invalidRecord }
        for message in messages {
            guard message.sender_id == peer, message.recipient_device_id == device.id else { throw MessageVault.Failure.invalidRecord }
            _ = try core.receive(message.routed(account: grant.account), now: Int64(Date().timeIntervalSince1970 * 1000),
                                 validate: check, commitMetadata: {
                try vault.put("notification-sync", message.id.uuidString.lowercased(), Data([1]))
            })
        }
        return try vault.transaction {
            try check()
            guard try ConversationHistory.isLatestUnread(vault, peer: peer, message: id),
                  let data = try vault.get("incoming", idKey) else { throw MessageVault.Failure.invalidRecord }
            let saved = try JSONDecoder().decode(StoredChat.self, from: data)
            guard saved.envelope.id == id, saved.envelope.sender == peer, saved.envelope.recipient == grant.account else {
                throw MessageVault.Failure.invalidRecord
            }
            let text = NotificationAccess.line(saved.text)
            guard !text.isEmpty else { throw MessageVault.Failure.invalidRecord }
            // One bounded marker per conversation. Older messages fail the latest-unread check.
            let fingerprint = Data(idKey.utf8)
            let repeated = try vault.get("notification-shown", peerKey) == fingerprint
            if !repeated { try vault.put("notification-shown", peerKey, fingerprint) }
            return (name, text, repeated)
        }
    }
}
