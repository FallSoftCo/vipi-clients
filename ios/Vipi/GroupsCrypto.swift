import Foundation
import LibSignalClient

struct GroupFanout: Codable {
    struct Acceptance: Decodable {
        struct Delivery: Decodable { let id: UUID; let state: String; let expires_at: String }
        let id: UUID; let group_id: UUID; let epoch: Int; let deliveries: [Delivery]
    }
    let groupID: UUID
    let messageID: UUID
    let epoch: Int
    let body: Data
}
private struct GroupCleartext: Codable {
    let version: Int; let kind: String
    let id: UUID; let sender: UUID; let recipient: UUID; let sender_device_id: UUID
    let createdAt: Int64; let text: String
    let group_id: UUID; let group_epoch: Int; let group_message_id: UUID; let group_revision: Int
}
struct GroupIncoming: Decodable {
    let id: UUID; let sender_id: UUID; let sender_device_id: UUID; let recipient_device_id: UUID
    let created_at: String; let cipher_type: Int; let ciphertext: Data
    let group_id: UUID; let group_epoch: Int; let group_message_id: UUID; let group_kind: String
}

/// Pairwise Signal ratchets and the COMPLETE durable fanout commit together.
/// A failure for any member rolls back every ratchet. HTTP retries reuse bytes.
final class GroupsCrypto {
    private let vault: MessageVault
    private let core: MessagingCore
    var messagingCore: MessagingCore { core }
    private let localStore: GroupsStore
    private let membership: GroupsMembership
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    private let context = NullContext()
    init(vault: MessageVault, core: MessagingCore, store: GroupsStore) { self.vault = vault; self.core = core; localStore = store; membership = GroupsMembership(vault: vault) }
    private func key(_ id: UUID) -> String { id.uuidString.lowercased() }
    private func index(_ group: UUID, _ message: UUID) -> String { key(group) + "/" + key(message) }
    func prepare(_ message: GroupMessage, roster: GroupSnapshot, now: Int64) throws -> GroupFanout {
        try roster.validate()
        return try vault.transaction {
            let recordID = index(message.groupID, message.id)
            if let saved = try vault.get("group-fanout", recordID) {
                let fanout = try decoder.decode(GroupFanout.self, from: saved)
                guard fanout.groupID == message.groupID, fanout.messageID == message.id, fanout.epoch == message.epoch else { throw MessageJournal.Failure.conflict }
                return fanout
            }
            guard message.groupID == roster.id, message.epoch == roster.epoch, message.sender == vault.account,
                  roster.role(for: vault.account) != nil, !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  message.text.utf8.count <= 32768, message.createdAt >= 0, message.createdAt <= now + 300_000,
                  now < message.createdAt + MessageJournal.ttl else { throw GroupsFailure.invalidMessage }
            guard try !vault.ids("group-control-outgoing").contains(where: { $0.hasPrefix(roster.id.uuidString.lowercased() + "/") }) else { throw GroupsFailure.unapprovedMembership }
            guard let approved = try membership.currentInTransaction(roster.id), approved.matches(roster),
                  message.membershipRevision == approved.revision else { throw GroupsFailure.unapprovedMembership }
            let recipients = roster.members.filter { $0.user_id != vault.account }
            guard !recipients.isEmpty else { throw GroupsFailure.notMember }
            let local = try ProtocolAddress(name: key(vault.account), deviceId: 1)
            var envelopes: [[String: Any]] = []
            for member in recipients {
                guard try vault.get("blocked", key(member.user_id)) == nil, let device = member.device_id,
                      try vault.get("peer-device", key(member.user_id)) == Data(key(device).utf8),
                      try vault.get("identity-change", key(member.user_id)) == nil else { throw GroupsFailure.identityChanged }
                let id = UUID()
                let clear = GroupCleartext(version: 2, kind: "group", id: id, sender: vault.account, recipient: member.user_id,
                    sender_device_id: core.device.id, createdAt: message.createdAt, text: message.text,
                    group_id: roster.id, group_epoch: roster.epoch, group_message_id: message.id, group_revision: approved.revision)
                let encrypted = try signalEncrypt(message: encoder.encode(clear), for: ProtocolAddress(name: key(member.user_id), deviceId: 1),
                    localAddress: local, sessionStore: core.store, identityStore: core.store, context: context)
                guard [2, 3].contains(Int(encrypted.messageType.rawValue)), encrypted.serialize().count <= 65536 else { throw GroupsFailure.invalidMessage }
                envelopes.append(["id": key(id), "recipient_id": key(member.user_id), "recipient_device_id": key(device),
                    "cipher_type": Int(encrypted.messageType.rawValue), "ciphertext": encrypted.serialize().base64EncodedString()])
            }
            let date = ISO8601DateFormatter(); date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let bytes = try JSONSerialization.data(withJSONObject: ["id": key(message.id), "epoch": roster.epoch,
                "created_at": date.string(from: Date(timeIntervalSince1970: Double(message.createdAt) / 1000)), "envelopes": envelopes], options: [.sortedKeys])
            guard bytes.count <= 1_400_000 else { throw GroupsFailure.invalidMessage }
            let result = GroupFanout(groupID: roster.id, messageID: message.id, epoch: roster.epoch, body: bytes)
            try localStore.saveMessageInTransaction(message)
            try vault.put("group-fanout", recordID, encoder.encode(result))
            return result
        }
    }
    func pending(_ group: UUID, _ message: UUID) throws -> GroupFanout? { try vault.transaction {
        try vault.get("group-fanout", index(group, message)).map { try decoder.decode(GroupFanout.self, from: $0) }
    } }
    func accepted(_ response: GroupFanout.Acceptance, fanout: GroupFanout) throws {
        guard response.id == fanout.messageID, response.group_id == fanout.groupID, response.epoch == fanout.epoch,
              let object = try JSONSerialization.jsonObject(with: fanout.body) as? [String: Any],
              let envelopes = object["envelopes"] as? [[String: Any]],
              Set(envelopes.compactMap { $0["id"] as? String }) == Set(response.deliveries.map { key($0.id) }),
              response.deliveries.allSatisfy({ ["accepted", "delivered", "expired", "failed"].contains($0.state) }) else { throw GroupsFailure.invalidResponse }
        try vault.transaction {
            guard var message = try localStore.messagesInTransaction(fanout.groupID).first(where: { $0.id == fanout.messageID }) else { throw GroupsFailure.invalidResponse }
            message.delivery = response.deliveries.allSatisfy { ["accepted", "delivered"].contains($0.state) } ? .accepted : .failed
            try localStore.saveMessageInTransaction(message)
            if message.delivery == .accepted { try vault.remove("group-fanout", index(fanout.groupID, fanout.messageID)) }
        }
    }
    /// Return only after plaintext + replay fingerprint + receipt commit.
    func receive(_ item: GroupIncoming, now: Int64) throws -> GroupMessage {
        try vault.transaction {
            guard item.group_kind == "message", item.recipient_device_id == core.device.id, item.group_epoch > 0,
                  item.sender_id != vault.account, [2, 3].contains(item.cipher_type), (32...65536).contains(item.ciphertext.count) else { throw GroupsFailure.invalidMessage }
            let parser = ISO8601DateFormatter(); parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var date = parser.date(from: item.created_at)
            if date == nil { parser.formatOptions = [.withInternetDateTime]; date = parser.date(from: item.created_at) }
            guard let date else { throw GroupsFailure.invalidMessage }
            guard date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 < 10_000_000_000 else { throw GroupsFailure.invalidMessage }
            let created = Int64((date.timeIntervalSince1970 * 1000).rounded())
            let envelope = ChatEnvelope(id: item.id, sender: item.sender_id, recipient: vault.account, createdAt: created, type: item.cipher_type, ciphertext: item.ciphertext)
            let fingerprint = envelope.fingerprint() + Data("\(item.group_id)/\(item.group_epoch)/\(item.group_message_id)/\(item.sender_device_id)/\(item.recipient_device_id)".utf8)
            if let saved = try vault.get("group-envelope", key(item.id)) {
                guard saved == fingerprint, let message = try localStore.messagesInTransaction(item.group_id).first(where: { $0.id == item.group_message_id && $0.sender == item.sender_id }) else { throw MessageJournal.Failure.conflict }
                try vault.put("group-receipt", key(item.id), Data([1])); return message
            }
            guard created >= 0, created <= now + 300_000, now < created + MessageJournal.ttl,
                  try vault.get("blocked", key(item.sender_id)) == nil,
                  try vault.get("retired-peer-device", key(item.sender_id) + "/" + key(item.sender_device_id)) == nil else { throw GroupsFailure.invalidMessage }
            if let route = try vault.get("peer-device", key(item.sender_id)), route != Data(key(item.sender_device_id).utf8) { throw GroupsFailure.identityChanged }
            let remote = try ProtocolAddress(name: key(item.sender_id), deviceId: 1)
            let local = try ProtocolAddress(name: key(vault.account), deviceId: 1)
            let clear: Data
            if item.cipher_type == 3 { clear = try signalDecryptPreKey(message: PreKeySignalMessage(bytes: item.ciphertext), from: remote, localAddress: local, sessionStore: core.store, identityStore: core.store, preKeyStore: core.store, signedPreKeyStore: core.store, kyberPreKeyStore: core.store, context: context) }
            else { clear = try signalDecrypt(message: SignalMessage(bytes: item.ciphertext), from: remote, to: local, sessionStore: core.store, identityStore: core.store, context: context) }
            let payload = try decoder.decode(GroupCleartext.self, from: clear)
            guard payload.version == 2, payload.kind == "group", payload.id == item.id, payload.sender == item.sender_id,
                  payload.recipient == vault.account, payload.sender_device_id == item.sender_device_id,
                  payload.group_id == item.group_id, payload.group_epoch == item.group_epoch, payload.group_message_id == item.group_message_id,
                  payload.createdAt == created, !payload.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, payload.text.utf8.count <= 32768 else { throw GroupsFailure.invalidMessage }
            guard let approved = try membership.currentInTransaction(item.group_id), approved.revision == payload.group_revision,
                  approved.contains(item.sender_id), approved.contains(vault.account) else { throw GroupsFailure.unapprovedMembership }
            let value = GroupMessage(id: item.group_message_id, groupID: item.group_id, epoch: item.group_epoch, membershipRevision: payload.group_revision, sender: item.sender_id,
                text: payload.text, createdAt: created, delivery: .received)
            try localStore.saveMessageInTransaction(value)
            try vault.put("peer-device", key(item.sender_id), Data(key(item.sender_device_id).utf8))
            try vault.put("group-envelope", key(item.id), fingerprint)
            try vault.put("group-receipt", key(item.id), Data([1]))
            return value
        }
    }
    func receipts() throws -> [UUID] { try vault.transaction { try vault.ids("group-receipt").compactMap(UUID.init(uuidString:)) } }
    func receiptAccepted(_ id: UUID) throws { try vault.transaction { try vault.remove("group-receipt", key(id)) } }
}
