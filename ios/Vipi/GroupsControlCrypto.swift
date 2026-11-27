import Foundation
import LibSignalClient

struct GroupPendingControl: Codable, Identifiable {
    let id: UUID
    let group: UUID
    let sender: UUID
    let senderDevice: UUID
    let pinnedIdentity: Data
    let transition: GroupRosterTransition
}
private struct GroupHeldControl: Codable {
    let item: GroupIncoming
    let firstSeenAt: Int64
    let fingerprint: Data
}
private struct GroupControlBinding: Decodable {
    let version: Int
    let kind: String
    let id: UUID
    let sender: UUID
    let recipient: UUID
    let sender_device_id: UUID
    let createdAt: Int64
    let group_id: UUID
    let group_epoch: Int
    let group_message_id: UUID
}

/// Controls are data-plane Signal messages with a distinct, strictly dispatched
/// type. No relay snapshot or unpinned incoming identity can authorize a roster.
final class GroupsControlCrypto {
    private let vault: MessageVault
    private let core: MessagingCore
    private let membership: GroupsMembership
    private let holdBudget: GroupsHoldBudget
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    private let context = NullContext()
    init(vault: MessageVault, core: MessagingCore) {
        self.vault = vault
        self.core = core
        membership = GroupsMembership(vault: vault)
        holdBudget = GroupsHoldBudget(vault: vault)
    }
    private func key(_ group: UUID, _ id: UUID) -> String {
        group.uuidString.lowercased() + "/" + id.uuidString.lowercased()
    }
    func prepare(id: UUID, roster: GroupSnapshot, change: GroupRosterTransition, now: Int64) throws -> GroupFanout {
        try vault.transaction {
            let recordKey = key(roster.id, id)
            if let bytes = try vault.get("group-control-outgoing", recordKey) {
                guard let prior = try vault.get("group-control-outgoing-change", recordKey),
                    try decoder.decode(GroupRosterTransition.self, from: prior) == change
                else { throw MessageJournal.Failure.conflict }
                return try decoder.decode(GroupFanout.self, from: bytes)
            }
            guard let previous = try membership.currentInTransaction(roster.id), change.actor_id == vault.account,
                previous.matches(roster)
                    || (change.action == .add
                        && Set(change.members).isSubset(
                            of: Set(roster.members.map { GroupApprovedPerson(user_id: $0.id, role: $0.role) })))
            else { throw GroupsFailure.unapprovedMembership }
            _ = try change.validated(group: roster.id, previous: previous, authenticatedSender: vault.account)
            let local = try ProtocolAddress(name: vault.account.uuidString.lowercased(), deviceId: 1)
            var envelopes: [[String: Any]] = []
            if change.action == .add, roster.members.first(where: { $0.id == change.target_id })?.device_id == nil {
                throw GroupsFailure.identityChanged
            }
            // The complete approved roster/delta remains authenticated. Only
            // CONTROL omits nil routes; ordinary DATA requires every member.
            for member in roster.members where member.id != vault.account && member.device_id != nil {
                guard let device = member.device_id,
                    try vault.get("peer-device", member.id.uuidString.lowercased())
                        == Data(device.uuidString.lowercased().utf8),
                    try vault.get("identity", member.id.uuidString.lowercased() + "/1") != nil,
                    try vault.get("identity-change", member.id.uuidString.lowercased()) == nil,
                    try vault.get("blocked", member.id.uuidString.lowercased()) == nil
                else { throw GroupsFailure.identityChanged }
                let envelope = UUID()
                var payload = try JSONSerialization.jsonObject(with: encoder.encode(change)) as! [String: Any]
                payload.merge([
                    "version": 2, "kind": "group-control", "id": envelope.uuidString.lowercased(),
                    "sender": vault.account.uuidString.lowercased(), "recipient": member.id.uuidString.lowercased(),
                    "sender_device_id": core.device.id.uuidString.lowercased(), "createdAt": now,
                    "group_id": roster.id.uuidString.lowercased(), "group_epoch": roster.epoch,
                    "group_message_id": id.uuidString.lowercased()
                ]) { _, new in new }
                let cipher = try signalEncrypt(
                    message: JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
                    for: ProtocolAddress(name: member.id.uuidString.lowercased(), deviceId: 1), localAddress: local,
                    sessionStore: core.store, identityStore: core.store, context: context)
                guard [2, 3].contains(Int(cipher.messageType.rawValue)), cipher.serialize().count <= 65536 else {
                    throw GroupsFailure.invalidMessage
                }
                envelopes.append([
                    "id": envelope.uuidString.lowercased(), "recipient_id": member.id.uuidString.lowercased(),
                    "recipient_device_id": device.uuidString.lowercased(),
                    "cipher_type": Int(cipher.messageType.rawValue),
                    "ciphertext": cipher.serialize().base64EncodedString()
                ])
            }
            let date = ISO8601DateFormatter()
            date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let body = try JSONSerialization.data(
                withJSONObject: [
                    "id": id.uuidString.lowercased(), "epoch": roster.epoch,
                    "created_at": date.string(from: Date(timeIntervalSince1970: Double(now) / 1000)),
                    "envelopes": envelopes
                ], options: [.sortedKeys])
            let result = GroupFanout(groupID: roster.id, messageID: id, epoch: roster.epoch, body: body)
            try vault.put("group-control-outgoing", recordKey, encoder.encode(result))
            try vault.put("group-control-outgoing-change", recordKey, encoder.encode(change))
            return result
        }
    }
    func accepted(_ response: GroupFanout.Acceptance, fanout: GroupFanout) throws {
        guard response.admitted, response.id == fanout.messageID, response.group_id == fanout.groupID,
            response.epoch == fanout.epoch,
            let object = try JSONSerialization.jsonObject(with: fanout.body) as? [String: Any],
            let envelopes = object["envelopes"] as? [[String: Any]],
            Set(envelopes.compactMap { $0["id"] as? String })
                == Set(response.deliveries.map { $0.id.uuidString.lowercased() }),
            response.deliveries.allSatisfy({
                ["accepted", "delivered", "expired", "failed", "unavailable", "identity_changed"].contains($0.state)
            })
        else { throw GroupsFailure.invalidResponse }
        try vault.transaction {
            let recordKey = key(fanout.groupID, fanout.messageID)
            guard let bytes = try vault.get("group-control-outgoing-change", recordKey) else {
                throw GroupsFailure.invalidResponse
            }
            let change = try decoder.decode(GroupRosterTransition.self, from: bytes)
            if let saved = try vault.get("group-control-logical", recordKey) {
                guard try decoder.decode(GroupRosterTransition.self, from: saved) == change else {
                    throw MessageJournal.Failure.conflict
                }
            } else {
                try membership.applyInTransaction(change, group: fanout.groupID, authenticatedSender: vault.account)
                try vault.put("group-control-logical", recordKey, bytes)
            }
        }
    }
    /// Called after the exact corresponding HTTP roster mutation succeeds (or
    /// after an add-existing-join approval). Until then text fanout stays frozen.
    func reconciled(_ fanout: GroupFanout) throws {
        try vault.transaction {
            let recordKey = key(fanout.groupID, fanout.messageID)
            try vault.remove("group-control-outgoing", recordKey)
            try vault.remove("group-control-outgoing-change", recordKey)
        }
    }

    private func drainInTransaction(_ group: UUID) throws {
        for _ in 0..<100 {
            guard let current = try membership.currentInTransaction(group) else { return }
            var advanced = false
            for id in try vault.ids("group-control-pending") where id.hasPrefix(group.uuidString.lowercased() + "/") {
                guard let bytes = try vault.get("group-control-pending", id) else { continue }
                let candidate = try decoder.decode(GroupPendingControl.self, from: bytes)
                guard candidate.transition.from_revision == current.revision,
                    try vault.get("identity", candidate.sender.uuidString.lowercased() + "/1")
                        == candidate.pinnedIdentity,
                    try vault.get("identity-change", candidate.sender.uuidString.lowercased()) == nil,
                    try vault.get("blocked", candidate.sender.uuidString.lowercased()) == nil,
                    try vault.get("peer-device", candidate.sender.uuidString.lowercased())
                        == Data(candidate.senderDevice.uuidString.lowercased().utf8),
                    try vault.get(
                        "retired-peer-device",
                        candidate.sender.uuidString.lowercased() + "/" + candidate.senderDevice.uuidString.lowercased())
                        == nil
                else { continue }
                guard
                    (try? candidate.transition.validated(
                        group: group, previous: current, authenticatedSender: candidate.sender)) != nil
                else {
                    let marker = try JSONSerialization.data(withJSONObject: [
                        "sender": candidate.sender.uuidString.lowercased(), "reason": "invalid_group_approval"
                    ])
                    try vault.put("group-last-rejection", group.uuidString.lowercased(), marker)
                    try vault.remove("group-control-pending", id)
                    try holdBudget.releaseInTransaction(kind: "approval", id: id)
                    continue
                }
                try membership.applyInTransaction(
                    candidate.transition, group: group, authenticatedSender: candidate.sender)
                try vault.put("group-control-logical", id, encoder.encode(candidate.transition))
                try vault.remove("group-control-pending", id)
                try holdBudget.releaseInTransaction(kind: "approval", id: id)
                advanced = true
                break
            }
            if !advanced { return }
        }
    }
    func heldEnvelopes() throws -> [GroupIncoming] {
        try vault.transaction {
            try vault.ids("group-held-control").compactMap { id in
                try vault.get("group-held-control", id).map { try decoder.decode(GroupHeldControl.self, from: $0).item }
            }
        }
    }
    func pending() throws -> [GroupPendingControl] {
        try vault.transaction {
            try vault.ids("group-control-pending").compactMap { id in
                try vault.get("group-control-pending", id).map {
                    try decoder.decode(GroupPendingControl.self, from: $0)
                }
            }
        }
    }
    func receive(_ item: GroupIncoming, now: Int64) throws {
        try vault.transaction {
            guard item.group_kind == "control", item.recipient_device_id == core.device.id,
                item.sender_id != vault.account,
                item.group_epoch > 0, [2, 3].contains(item.cipher_type), (32...65536).contains(item.ciphertext.count),
                try vault.get("blocked", item.sender_id.uuidString.lowercased()) == nil
            else { throw GroupsFailure.identityChanged }
            let parser = ISO8601DateFormatter()
            parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var date = parser.date(from: item.created_at)
            if date == nil {
                parser.formatOptions = [.withInternetDateTime]
                date = parser.date(from: item.created_at)
            }
            guard let date, date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 < 10_000_000_000 else {
                throw GroupsFailure.invalidMessage
            }
            let created = Int64((date.timeIntervalSince1970 * 1000).rounded())
            let envelope = ChatEnvelope(
                id: item.id, sender: item.sender_id, recipient: vault.account, createdAt: created,
                type: item.cipher_type, ciphertext: item.ciphertext)
            let fingerprint =
                envelope.fingerprint()
                + Data(
                    "control/\(item.group_id)/\(item.group_epoch)/\(item.group_message_id)/\(item.sender_device_id)/\(item.recipient_device_id)"
                        .utf8)
            if let saved = try vault.get("group-control-envelope", item.id.uuidString.lowercased()) {
                guard saved == fingerprint else { throw MessageJournal.Failure.conflict }
                try vault.put("group-receipt", item.id.uuidString.lowercased(), Data([1]))
                return
            }
            let held = try vault.get("group-held-control", item.id.uuidString.lowercased()).map {
                try decoder.decode(GroupHeldControl.self, from: $0)
            }
            if let held { guard held.fingerprint == fingerprint else { throw MessageJournal.Failure.conflict } }
            let firstSeen = held?.firstSeenAt ?? now
            guard created <= firstSeen + 300_000, firstSeen < created + MessageJournal.ttl,
                try vault.get(
                    "retired-peer-device",
                    item.sender_id.uuidString.lowercased() + "/" + item.sender_device_id.uuidString.lowercased()) == nil
            else { throw GroupsFailure.identityChanged }
            guard let pinned = try vault.get("identity", item.sender_id.uuidString.lowercased() + "/1"),
                try vault.get("identity-change", item.sender_id.uuidString.lowercased()) == nil,
                try vault.get("peer-device", item.sender_id.uuidString.lowercased())
                    == Data(item.sender_device_id.uuidString.lowercased().utf8)
            else {
                if held == nil {
                    let bytes = try encoder.encode(
                        GroupHeldControl(item: item, firstSeenAt: now, fingerprint: fingerprint))
                    try holdBudget.reserveInTransaction(
                        kind: "control", id: item.id.uuidString.lowercased(), group: item.group_id, bytes: bytes.count)
                    try vault.put("group-held-control", item.id.uuidString.lowercased(), bytes)
                }
                return
            }
            let remote = try ProtocolAddress(name: item.sender_id.uuidString.lowercased(), deviceId: 1)
            let local = try ProtocolAddress(name: vault.account.uuidString.lowercased(), deviceId: 1)
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
            guard try vault.get("identity", item.sender_id.uuidString.lowercased() + "/1") == pinned else {
                throw GroupsFailure.identityChanged
            }
            let binding = try decoder.decode(GroupControlBinding.self, from: clear)
            guard binding.version == 2, binding.kind == "group-control", binding.id == item.id,
                binding.sender == item.sender_id,
                binding.recipient == vault.account, binding.sender_device_id == item.sender_device_id,
                binding.createdAt == created,
                binding.group_id == item.group_id, binding.group_epoch == item.group_epoch,
                binding.group_message_id == item.group_message_id
            else { throw GroupsFailure.invalidMessage }
            let transition = try decoder.decode(GroupRosterTransition.self, from: clear)
            guard transition.actor_id == item.sender_id else { throw GroupsFailure.noPermission }
            try holdBudget.releaseInTransaction(kind: "control", id: item.id.uuidString.lowercased())
            try vault.remove("group-held-control", item.id.uuidString.lowercased())
            let logicalKey = key(item.group_id, item.group_message_id)
            if let previous = try vault.get("group-control-logical", logicalKey) {
                guard try decoder.decode(GroupRosterTransition.self, from: previous) == transition else {
                    throw MessageJournal.Failure.conflict
                }
            } else {
                let pending = GroupPendingControl(
                    id: item.group_message_id, group: item.group_id, sender: item.sender_id,
                    senderDevice: item.sender_device_id, pinnedIdentity: pinned, transition: transition)
                if let bytes = try vault.get("group-control-pending", logicalKey) {
                    let saved = try decoder.decode(GroupPendingControl.self, from: bytes)
                    guard saved.transition == transition, saved.sender == item.sender_id,
                        saved.senderDevice == item.sender_device_id, saved.pinnedIdentity == pinned
                    else { throw MessageJournal.Failure.conflict }
                }
                if try membership.currentInTransaction(item.group_id) != nil,
                    let prior = try membership.historyInTransaction(item.group_id, revision: transition.from_revision)
                {
                    let candidate = try transition.validated(
                        group: item.group_id, previous: prior, authenticatedSender: item.sender_id)
                    if let existing = try membership.historyInTransaction(
                        item.group_id, revision: transition.to_revision),
                        Set(existing.members) != Set(candidate.members)
                    {
                        try vault.put(
                            "group-membership-conflict", item.group_id.uuidString.lowercased(), encoder.encode(pending))
                        try holdBudget.reserveInTransaction(
                            kind: "approval", id: logicalKey, group: item.group_id, bytes: encoder.encode(pending).count
                        )
                        try vault.put("group-control-pending", logicalKey, encoder.encode(pending))
                    } else {
                        try membership.applyInTransaction(
                            transition, group: item.group_id, authenticatedSender: item.sender_id)
                        try vault.put("group-control-logical", logicalKey, encoder.encode(transition))
                    }
                } else {
                    // Missing-chain and first-join controls are retained securely
                    // for recovery. They cannot approve themselves through HTTP.
                    try holdBudget.reserveInTransaction(
                        kind: "approval", id: logicalKey, group: item.group_id, bytes: encoder.encode(pending).count)
                    try vault.put("group-control-pending", logicalKey, encoder.encode(pending))
                }
            }
            try drainInTransaction(item.group_id)
            try vault.put("group-control-envelope", item.id.uuidString.lowercased(), fingerprint)
            try vault.put("group-receipt", item.id.uuidString.lowercased(), Data([1]))
        }
    }
    func confirmBootstrap(_ reviewed: GroupPendingControl) throws {
        try vault.transaction {
            let recordKey = key(reviewed.group, reviewed.id)
            guard let data = try vault.get("group-control-pending", recordKey),
                let saved = try? decoder.decode(GroupPendingControl.self, from: data), saved.id == reviewed.id,
                saved.group == reviewed.group, saved.sender == reviewed.sender,
                saved.senderDevice == reviewed.senderDevice, saved.transition == reviewed.transition,
                saved.pinnedIdentity == reviewed.pinnedIdentity,
                try vault.get("identity", saved.sender.uuidString.lowercased() + "/1") == saved.pinnedIdentity,
                try vault.get("identity-change", saved.sender.uuidString.lowercased()) == nil,
                try vault.get("blocked", saved.sender.uuidString.lowercased()) == nil,
                try vault.get("peer-device", saved.sender.uuidString.lowercased())
                    == Data(saved.senderDevice.uuidString.lowercased().utf8),
                try vault.get(
                    "retired-peer-device",
                    saved.sender.uuidString.lowercased() + "/" + saved.senderDevice.uuidString.lowercased()) == nil
            else { throw GroupsFailure.identityChanged }
            try membership.bootstrapInTransaction(
                saved.transition, group: saved.group, authenticatedSender: saved.sender, confirmedInviter: saved.sender)
            try vault.put("group-control-logical", recordKey, encoder.encode(saved.transition))
            try vault.remove("group-control-pending", recordKey)
            try holdBudget.releaseInTransaction(kind: "approval", id: recordKey)
            try drainInTransaction(saved.group)
        }
    }
}
