import Foundation
import LibSignalClient

struct GroupFanout: Codable {
    struct Acceptance: Decodable {
        struct Delivery: Decodable {
            let id: UUID
            let state: String
            let expires_at: String
        }
        let id: UUID
        let group_id: UUID
        let epoch: Int
        let admitted: Bool
        let deliveries: [Delivery]
    }
    let groupID: UUID
    let messageID: UUID
    let epoch: Int
    let body: Data
}
private struct GroupCleartext: Codable {
    let version: Int
    let kind: String
    let id: UUID
    let sender: UUID
    let recipient: UUID
    let sender_device_id: UUID
    let createdAt: Int64
    let text: String
    let group_id: UUID
    let group_epoch: Int
    let group_message_id: UUID
    let group_revision: Int
    var chat_features: WireChatFeatures? = nil
}
struct GroupIncoming: Codable {
    let id: UUID
    let sender_id: UUID
    let sender_device_id: UUID
    let recipient_device_id: UUID
    let created_at: String
    let cipher_type: Int
    let ciphertext: Data
    let group_id: UUID
    let group_epoch: Int
    let group_message_id: UUID
    let group_kind: String
}

private struct GroupQuarantineProof: Codable {
    let pinnedIdentity: Data
    let senderDevice: UUID
}
private struct GroupHeldCiphertext: Codable {
    let item: GroupIncoming
    let firstSeenAt: Int64
    let fingerprint: Data
}

/// Pairwise Signal ratchets and the COMPLETE durable fanout commit together.
/// A failure for any member rolls back every ratchet. HTTP retries reuse bytes.
final class GroupsCrypto {
    private let vault: MessageVault
    private let core: MessagingCore
    var messagingCore: MessagingCore { core }
    private let localStore: GroupsStore
    private let membership: GroupsMembership
    private let holdBudget: GroupsHoldBudget
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    private let context = NullContext()
    init(vault: MessageVault, core: MessagingCore, store: GroupsStore) {
        self.vault = vault
        self.core = core
        localStore = store
        membership = GroupsMembership(vault: vault)
        holdBudget = GroupsHoldBudget(vault: vault)
    }
    private func key(_ id: UUID) -> String { id.uuidString.lowercased() }
    private func index(_ group: UUID, _ message: UUID) -> String { key(group) + "/" + key(message) }
    func featuresToSend(_ message: GroupMessage) throws -> ChatFeatures? {
        guard message.features?.link_preview != nil else { return message.features }
        // All fanout IDs and recipient UUIDs have the same serialized length.
        return try ChatFeatures.fit(message.features) { candidate in
            try encoder.encode(
                GroupCleartext(
                    version: 2, kind: "group", id: message.id, sender: message.sender, recipient: message.sender,
                    sender_device_id: core.device.id, createdAt: message.createdAt, text: message.text,
                    group_id: message.groupID,
                    group_epoch: message.epoch, group_message_id: message.id,
                    group_revision: message.membershipRevision,
                    chat_features: candidate.map(WireChatFeatures.init)))
        }.0
    }
    func prepare(_ message: GroupMessage, roster: GroupSnapshot, now: Int64) throws -> GroupFanout {
        try roster.validate()
        return try vault.transaction {
            let recordID = index(message.groupID, message.id)
            if let saved = try vault.get("group-fanout", recordID) {
                let fanout = try decoder.decode(GroupFanout.self, from: saved)
                guard fanout.groupID == message.groupID, fanout.messageID == message.id, fanout.epoch == message.epoch,
                    let saved = try localStore.messagesInTransaction(message.groupID).first(where: {
                        $0.id == message.id
                    }),
                    saved.sender == message.sender, saved.membershipRevision == message.membershipRevision,
                    saved.text == message.text, saved.features == message.features, saved.createdAt == message.createdAt
                else { throw MessageJournal.Failure.conflict }
                return fanout
            }
            guard message.groupID == roster.id, message.epoch == roster.epoch, message.sender == vault.account,
                roster.role(for: vault.account) != nil,
                !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                message.text.utf8.count <= 32768, message.createdAt >= 0, message.createdAt <= now + 300_000,
                now < message.createdAt + MessageJournal.ttl
            else { throw GroupsFailure.invalidMessage }
            guard
                try !vault.ids("group-control-outgoing").contains(where: {
                    $0.hasPrefix(roster.id.uuidString.lowercased() + "/")
                }),
                try !vault.ids("group-mutation").contains(where: { $0.contains(roster.id.uuidString.lowercased()) }),
                try !vault.ids("group-join-plan").contains(where: {
                    $0.hasPrefix(roster.id.uuidString.lowercased() + "/")
                })
            else { throw GroupsFailure.unapprovedMembership }
            guard try vault.get("group-membership-conflict", key(roster.id)) == nil,
                let approved = try membership.currentInTransaction(roster.id), approved.matches(roster),
                message.membershipRevision == approved.revision
            else { throw GroupsFailure.unapprovedMembership }
            let recipients = roster.members.filter { $0.user_id != vault.account }
            guard message.features?.reaction == nil || recipients.allSatisfy({ $0.chat_features_version == 1 }) else {
                throw GroupsFailure.reactionsUnavailable
            }
            guard !recipients.isEmpty else { throw GroupsFailure.notMember }
            let local = try ProtocolAddress(name: key(vault.account), deviceId: 1)
            var envelopes: [[String: Any]] = []
            for member in recipients {
                guard try vault.get("blocked", key(member.user_id)) == nil, let device = member.device_id,
                    try vault.get("peer-device", key(member.user_id)) == Data(key(device).utf8),
                    try vault.get("identity-change", key(member.user_id)) == nil
                else { throw GroupsFailure.identityChanged }
                let id = UUID()
                let clear = GroupCleartext(
                    version: 2, kind: "group", id: id, sender: vault.account, recipient: member.user_id,
                    sender_device_id: core.device.id, createdAt: message.createdAt, text: message.text,
                    group_id: roster.id, group_epoch: roster.epoch, group_message_id: message.id,
                    group_revision: approved.revision, chat_features: message.features.map(WireChatFeatures.init))
                let fitted = try ChatFeatures.fit(message.features) { value in
                    var candidate = clear
                    candidate.chat_features = value.map(WireChatFeatures.init)
                    return try encoder.encode(candidate)
                }
                let encrypted = try signalEncrypt(
                    message: fitted.1, for: ProtocolAddress(name: key(member.user_id), deviceId: 1),
                    localAddress: local, sessionStore: core.store, identityStore: core.store, context: context)
                guard [2, 3].contains(Int(encrypted.messageType.rawValue)), encrypted.serialize().count <= 65536 else {
                    throw GroupsFailure.invalidMessage
                }
                envelopes.append([
                    "id": key(id), "recipient_id": key(member.user_id), "recipient_device_id": key(device),
                    "cipher_type": Int(encrypted.messageType.rawValue),
                    "ciphertext": encrypted.serialize().base64EncodedString()
                ])
            }
            let date = ISO8601DateFormatter()
            date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var body: [String: Any] = [
                "id": key(message.id), "epoch": roster.epoch,
                "created_at": date.string(from: Date(timeIntervalSince1970: Double(message.createdAt) / 1000)),
                "envelopes": envelopes
            ]
            if message.features?.reaction != nil { body["required_chat_features_version"] = 1 }
            let bytes = try JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
            guard bytes.count <= 1_400_000 else { throw GroupsFailure.invalidMessage }
            let result = GroupFanout(groupID: roster.id, messageID: message.id, epoch: roster.epoch, body: bytes)
            try localStore.saveMessageInTransaction(message)
            try vault.put("group-fanout", recordID, encoder.encode(result))
            return result
        }
    }
    func pending(_ group: UUID, _ message: UUID) throws -> GroupFanout? {
        try vault.transaction {
            try vault.get("group-fanout", index(group, message)).map { try decoder.decode(GroupFanout.self, from: $0) }
        }
    }
    func accepted(_ response: GroupFanout.Acceptance, fanout: GroupFanout) throws {
        guard response.admitted, response.id == fanout.messageID, response.group_id == fanout.groupID,
            response.epoch == fanout.epoch,
            let object = try JSONSerialization.jsonObject(with: fanout.body) as? [String: Any],
            let envelopes = object["envelopes"] as? [[String: Any]],
            Set(envelopes.compactMap { $0["id"] as? String }) == Set(response.deliveries.map { key($0.id) }),
            response.deliveries.allSatisfy({
                ["accepted", "delivered", "expired", "failed", "unavailable", "identity_changed"].contains($0.state)
            })
        else { throw GroupsFailure.invalidResponse }
        try vault.transaction {
            guard
                var message = try localStore.messagesInTransaction(fanout.groupID).first(where: {
                    $0.id == fanout.messageID
                })
            else { throw GroupsFailure.invalidResponse }
            if response.deliveries.allSatisfy({ ["accepted", "delivered"].contains($0.state) }) {
                if message.features?.reaction == nil, message.delivery != .accepted, message.sender == vault.account,
                    !response.deliveries.isEmpty
                {
                    try? recordSuccessfulChatSend(
                        vault, key: "group-message/" + index(message.groupID, message.id), authoredAt: message.createdAt
                    )
                }
                message.delivery = .accepted
            } else if response.deliveries.contains(where: { $0.state == "identity_changed" }) {
                message.delivery = .identityChanged
            } else if response.deliveries.contains(where: { $0.state == "unavailable" }) {
                message.delivery = .membershipChanged
            } else if response.deliveries.contains(where: { $0.state == "expired" }) {
                message.delivery = .expired
            } else {
                message.delivery = .failed
            }
            try localStore.saveMessageInTransaction(message)
            if message.delivery == .accepted {
                try reduce(message, device: core.device.id)
                try vault.remove("group-fanout", index(fanout.groupID, fanout.messageID))
            }
        }
    }
    private func reduce(_ message: GroupMessage, device: UUID) throws {
        if let reaction = message.features?.reaction {
            let target = try vault.get("group-message", index(message.groupID, reaction.message_id)).map {
                try decoder.decode(GroupMessage.self, from: $0)
            }
            let known =
                target?.sender == reaction.target_sender_id && target?.features?.reaction == nil
                && (target?.delivery == .accepted || target?.delivery == .received)
            try MessageReactions.apply(
                vault, scope: .group, conversation: message.groupID, actor: message.sender, device: device,
                event: message.id, reaction: reaction, targetKnown: known)
        } else {
            try MessageReactions.resolve(
                vault, id: MessageReactions.key(.group, message.groupID, message.id, message.sender))
        }
    }
    /// Return only after plaintext + replay fingerprint + receipt commit.
    func receive(_ item: GroupIncoming, now: Int64) throws -> GroupMessage? {
        try vault.transaction {
            guard item.group_kind == "message", item.recipient_device_id == core.device.id, item.group_epoch > 0,
                item.sender_id != vault.account, [2, 3].contains(item.cipher_type),
                (32...65536).contains(item.ciphertext.count)
            else { throw GroupsFailure.invalidMessage }
            let parser = ISO8601DateFormatter()
            parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var date = parser.date(from: item.created_at)
            if date == nil {
                parser.formatOptions = [.withInternetDateTime]
                date = parser.date(from: item.created_at)
            }
            guard let date else { throw GroupsFailure.invalidMessage }
            guard date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 < 10_000_000_000 else {
                throw GroupsFailure.invalidMessage
            }
            let created = Int64((date.timeIntervalSince1970 * 1000).rounded())
            let envelope = ChatEnvelope(
                id: item.id, sender: item.sender_id, recipient: vault.account, createdAt: created,
                type: item.cipher_type, ciphertext: item.ciphertext)
            let fingerprint =
                envelope.fingerprint()
                + Data(
                    "\(item.group_id)/\(item.group_epoch)/\(item.group_message_id)/\(item.sender_device_id)/\(item.recipient_device_id)"
                        .utf8)
            if let saved = try vault.get("group-envelope", key(item.id)) {
                guard saved == fingerprint,
                    let message = try localStore.messagesInTransaction(item.group_id).first(where: {
                        $0.id == item.group_message_id && $0.sender == item.sender_id
                    })
                else { throw MessageJournal.Failure.conflict }
                try vault.put("group-receipt", key(item.id), Data([1]))
                return message
            }
            let held = try vault.get("group-held-envelope", key(item.id)).map {
                try decoder.decode(GroupHeldCiphertext.self, from: $0)
            }
            if let held { guard held.fingerprint == fingerprint else { throw MessageJournal.Failure.conflict } }
            let firstSeen = held?.firstSeenAt ?? now
            guard created >= 0, created <= firstSeen + 300_000, firstSeen < created + MessageJournal.ttl,
                try vault.get("blocked", key(item.sender_id)) == nil,
                try vault.get("retired-peer-device", key(item.sender_id) + "/" + key(item.sender_device_id)) == nil
            else { throw GroupsFailure.invalidMessage }
            guard let pinned = try vault.get("identity", key(item.sender_id) + "/1"),
                try vault.get("peer-device", key(item.sender_id)) == Data(key(item.sender_device_id).utf8),
                try vault.get("identity-change", key(item.sender_id)) == nil
            else {
                if held == nil {
                    let bytes = try encoder.encode(
                        GroupHeldCiphertext(item: item, firstSeenAt: now, fingerprint: fingerprint))
                    try holdBudget.reserveInTransaction(
                        kind: "message", id: key(item.id), group: item.group_id, bytes: bytes.count)
                    try vault.put("group-held-envelope", key(item.id), bytes)
                }
                return nil
            }
            let remote = try ProtocolAddress(name: key(item.sender_id), deviceId: 1)
            let local = try ProtocolAddress(name: key(vault.account), deviceId: 1)
            let clear: Data
            if item.cipher_type == 3 {
                clear = try signalDecryptPreKey(
                    message: PreKeySignalMessage(bytes: item.ciphertext), from: remote, localAddress: local,
                    sessionStore: core.store, identityStore: core.store, preKeyStore: core.store,
                    signedPreKeyStore: core.store, kyberPreKeyStore: core.store, context: context)
            } else {
                clear = try signalDecrypt(
                    message: SignalMessage(bytes: item.ciphertext), from: remote, to: local, sessionStore: core.store,
                    identityStore: core.store, context: context)
            }
            guard try vault.get("identity", key(item.sender_id) + "/1") == pinned else {
                throw GroupsFailure.identityChanged
            }
            let payload = try decoder.decode(GroupCleartext.self, from: clear)
            guard payload.version == 2, payload.kind == "group", payload.id == item.id,
                payload.sender == item.sender_id,
                payload.recipient == vault.account, payload.sender_device_id == item.sender_device_id,
                payload.group_id == item.group_id, payload.group_epoch == item.group_epoch,
                payload.group_message_id == item.group_message_id,
                payload.group_revision > 0, payload.createdAt == created,
                !payload.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, payload.text.utf8.count <= 32768
            else { throw GroupsFailure.invalidMessage }
            let approved = try membership.currentInTransaction(item.group_id)
            let authorized =
                try vault.get("group-membership-conflict", key(item.group_id)) == nil
                && approved?.revision == payload.group_revision && approved?.contains(item.sender_id) == true
                && approved?.contains(vault.account) == true
            var value = GroupMessage(
                id: item.group_message_id, groupID: item.group_id, epoch: item.group_epoch,
                membershipRevision: payload.group_revision, sender: item.sender_id,
                text: payload.text, createdAt: created, delivery: authorized ? .received : .withheld,
                features: payload.chat_features?.value?.validated(in: payload.text))
            if !authorized {
                value.withheldReason =
                    approved == nil || payload.group_revision > (approved?.revision ?? 0) ? "approval" : "changed"
            }
            if let prior = try localStore.messagesInTransaction(value.groupID).first(where: { $0.id == value.id }),
                prior.delivery == .received
            {
                // saveMessage still rejects changed immutable context. A new
                // envelope cannot hide already committed legitimate history.
                value.delivery = .received
                value.withheldReason = nil
            }
            let quarantineKey = index(value.groupID, value.id)
            try holdBudget.releaseInTransaction(kind: "message", id: key(item.id))
            if value.delivery == .withheld {
                let proof = try encoder.encode(
                    GroupQuarantineProof(pinnedIdentity: pinned, senderDevice: item.sender_device_id))
                try holdBudget.reserveInTransaction(
                    kind: "quarantine", id: quarantineKey, group: value.groupID,
                    bytes: encoder.encode(value).count + proof.count)
                try vault.put("group-quarantine-proof", quarantineKey, proof)
            } else {
                try holdBudget.releaseInTransaction(kind: "quarantine", id: quarantineKey)
                try vault.remove("group-quarantine-proof", quarantineKey)
            }
            try localStore.saveMessageInTransaction(value)
            if authorized { try reduce(value, device: item.sender_device_id) }
            try vault.put("peer-device", key(item.sender_id), Data(key(item.sender_device_id).utf8))
            try vault.put("group-envelope", key(item.id), fingerprint)
            try vault.put("group-receipt", key(item.id), Data([1]))
            try vault.remove("group-held-envelope", key(item.id))
            return value
        }
    }
    func heldEnvelopes() throws -> [GroupIncoming] {
        try vault.transaction {
            try vault.ids("group-held-envelope").compactMap { id in
                try vault.get("group-held-envelope", id).map {
                    try decoder.decode(GroupHeldCiphertext.self, from: $0).item
                }
            }
        }
    }
    func releaseAuthorized(_ group: UUID) throws -> [GroupMessage] {
        try vault.transaction {
            guard try vault.get("group-membership-conflict", key(group)) == nil,
                let approved = try membership.currentInTransaction(group)
            else { return [] }
            var released: [GroupMessage] = []
            for var message in try localStore.messagesInTransaction(group) where message.delivery == .withheld {
                guard message.membershipRevision == approved.revision, approved.contains(message.sender),
                    approved.contains(vault.account),
                    let proofBytes = try vault.get("group-quarantine-proof", index(message.groupID, message.id))
                else { continue }
                let proof = try decoder.decode(GroupQuarantineProof.self, from: proofBytes)
                guard try vault.get("identity", key(message.sender) + "/1") == proof.pinnedIdentity,
                    try vault.get("peer-device", key(message.sender)) == Data(key(proof.senderDevice).utf8),
                    try vault.get("blocked", key(message.sender)) == nil,
                    try vault.get("identity-change", key(message.sender)) == nil,
                    try vault.get("retired-peer-device", key(message.sender) + "/" + key(proof.senderDevice)) == nil
                else { continue }
                message.delivery = .received
                message.withheldReason = nil
                try reduce(message, device: proof.senderDevice)
                try localStore.saveMessageInTransaction(message)
                try holdBudget.releaseInTransaction(kind: "quarantine", id: index(message.groupID, message.id))
                try vault.remove("group-quarantine-proof", index(message.groupID, message.id))
                released.append(message)
            }
            return released
        }
    }
    func receipts() throws -> [UUID] {
        try vault.transaction { try vault.ids("group-receipt").compactMap(UUID.init(uuidString:)) }
    }
    func receiptAccepted(_ id: UUID) throws { try vault.transaction { try vault.remove("group-receipt", key(id)) } }
}
