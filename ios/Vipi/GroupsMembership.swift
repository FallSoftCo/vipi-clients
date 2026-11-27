import Foundation

/// The relay roster is a proposal. Only this locally authenticated chain can
/// authorize plaintext fanout or a sender's membership. Server epochs are fences,
/// not membership proof. Revisions advance only through authenticated controls.
struct GroupApprovedPerson: Codable, Equatable, Hashable {
    let user_id: UUID
    let role: GroupRole
    init(user_id: UUID, role: GroupRole) {
        self.user_id = user_id
        self.role = role
    }
    private struct Key: CodingKey {
        let stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: Key.self)
        guard Set(values.allKeys.map(\.stringValue)) == ["user_id", "role"] else { throw GroupsFailure.invalidResponse }
        user_id = try values.decode(UUID.self, forKey: Key(stringValue: "user_id"))
        role = try values.decode(GroupRole.self, forKey: Key(stringValue: "role"))
    }
}
struct GroupApprovedRoster: Codable, Equatable {
    let group_id: UUID
    let revision: Int
    let members: [GroupApprovedPerson]
    func contains(_ user: UUID) -> Bool { members.contains { $0.user_id == user } }
    func matches(_ snapshot: GroupSnapshot) -> Bool {
        snapshot.id == group_id
            && Set(members) == Set(snapshot.members.map { GroupApprovedPerson(user_id: $0.id, role: $0.role) })
    }
    func validate(allowEmpty: Bool = false) throws {
        guard revision > 0, members.count <= 16, Set(members.map(\.user_id)).count == members.count,
            members.filter({ $0.role == .owner }).count == (allowEmpty && members.isEmpty ? 0 : 1)
        else { throw GroupsFailure.invalidResponse }
    }
}
enum GroupControlAction: String, Codable { case add, remove, role, transfer, leave }
struct GroupRosterTransition: Codable, Equatable {
    let actor_id: UUID
    let action: GroupControlAction
    let target_id: UUID
    let from_revision: Int
    let to_revision: Int
    let server_epoch: Int
    let previous_members: [GroupApprovedPerson]
    let members: [GroupApprovedPerson]
    let role: GroupRole?
    init(
        actor_id: UUID, action: GroupControlAction, target_id: UUID, from_revision: Int, to_revision: Int,
        server_epoch: Int, previous_members: [GroupApprovedPerson], members: [GroupApprovedPerson],
        role: GroupRole? = nil
    ) {
        self.actor_id = actor_id
        self.action = action
        self.target_id = target_id
        self.from_revision = from_revision
        self.to_revision = to_revision
        self.server_epoch = server_epoch
        self.previous_members = previous_members
        self.members = members
        self.role = role
    }
    private struct Key: CodingKey {
        let stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: Key.self)
        let keys = Set(values.allKeys.map(\.stringValue))
        let base: Set<String> = [
            "version", "kind", "id", "sender", "recipient", "sender_device_id", "createdAt", "group_id", "group_epoch",
            "group_message_id"
        ]
        let required: Set<String> = [
            "actor_id", "action", "target_id", "from_revision", "to_revision", "server_epoch", "previous_members",
            "members"
        ]
        action = try values.decode(GroupControlAction.self, forKey: Key(stringValue: "action"))
        let expected = required.union(action == .role ? ["role"] : [])
        guard keys == expected || keys == expected.union(base) else { throw GroupsFailure.invalidResponse }
        actor_id = try values.decode(UUID.self, forKey: Key(stringValue: "actor_id"))
        target_id = try values.decode(UUID.self, forKey: Key(stringValue: "target_id"))
        from_revision = try values.decode(Int.self, forKey: Key(stringValue: "from_revision"))
        to_revision = try values.decode(Int.self, forKey: Key(stringValue: "to_revision"))
        server_epoch = try values.decode(Int.self, forKey: Key(stringValue: "server_epoch"))
        previous_members = try values.decode([GroupApprovedPerson].self, forKey: Key(stringValue: "previous_members"))
        members = try values.decode([GroupApprovedPerson].self, forKey: Key(stringValue: "members"))
        role = action == .role ? try values.decode(GroupRole.self, forKey: Key(stringValue: "role")) : nil
    }

    /// Pure policy; authenticatedSender MUST come from a successfully decrypted
    /// Signal control whose identity was pinned before decryption.
    func validated(group: UUID, previous: GroupApprovedRoster, authenticatedSender: UUID) throws -> GroupApprovedRoster
    {
        try previous.validate()
        guard actor_id == authenticatedSender, from_revision == previous.revision, from_revision < Int.max,
            to_revision == from_revision + 1, server_epoch > 0,
            (action == .role || role == nil),
            Set(previous_members) == Set(previous.members), previous_members.count == previous.members.count
        else { throw GroupsFailure.invalidResponse }
        let next = GroupApprovedRoster(group_id: group, revision: to_revision, members: members)
        try next.validate(allowEmpty: action == .leave)
        guard previous.group_id == group, let actor = previous.members.first(where: { $0.user_id == actor_id }) else {
            throw GroupsFailure.noPermission
        }
        let before = Dictionary(uniqueKeysWithValues: previous.members.map { ($0.user_id, $0.role) })
        let after = Dictionary(uniqueKeysWithValues: members.map { ($0.user_id, $0.role) })
        var expected = before
        switch action {
        case .add:
            guard [.owner, .admin].contains(actor.role), before[target_id] == nil, after[target_id] == .member else {
                throw GroupsFailure.noPermission
            }
            expected[target_id] = .member
        case .remove:
            guard target_id != actor_id, let target = before[target_id], target != .owner,
                actor.role == .owner || (actor.role == .admin && target == .member)
            else { throw GroupsFailure.noPermission }
            expected.removeValue(forKey: target_id)
        case .role:
            guard actor.role == .owner, target_id != actor_id, let old = before[target_id], old != .owner,
                let new = after[target_id], new == role, [.member, .admin].contains(new), old != new
            else { throw GroupsFailure.noPermission }
            expected[target_id] = new
        case .transfer:
            guard actor.role == .owner, target_id != actor_id, before[target_id] != nil else {
                throw GroupsFailure.noPermission
            }
            expected[actor_id] = .admin
            expected[target_id] = .owner
        case .leave:
            guard target_id == actor_id, actor.role != .owner || before.count == 1 else {
                throw GroupsFailure.noPermission
            }
            expected.removeValue(forKey: actor_id)
        }
        guard expected == after else { throw GroupsFailure.invalidResponse }
        return next
    }
}

final class GroupsMembership {
    private let vault: MessageVault
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    init(vault: MessageVault) { self.vault = vault }
    func current(_ group: UUID) throws -> GroupApprovedRoster? {
        try vault.transaction { try currentInTransaction(group) }
    }
    func currentInTransaction(_ group: UUID) throws -> GroupApprovedRoster? {
        try vault.get("group-approved", group.uuidString.lowercased()).map {
            try decoder.decode(GroupApprovedRoster.self, from: $0)
        }
    }
    func historyInTransaction(_ group: UUID, revision: Int) throws -> GroupApprovedRoster? {
        try vault.get("group-approved-history", group.uuidString.lowercased() + "/" + String(revision)).map {
            try decoder.decode(GroupApprovedRoster.self, from: $0)
        }
    }
    private func putInTransaction(_ roster: GroupApprovedRoster) throws {
        try roster.validate(allowEmpty: true)
        let data = try encoder.encode(roster), key = roster.group_id.uuidString.lowercased()
        let historyID = key + "/" + String(roster.revision)
        if let bytes = try vault.get("group-approved-history", historyID) {
            guard try decoder.decode(GroupApprovedRoster.self, from: bytes) == roster else {
                throw MessageJournal.Failure.conflict
            }
        }
        try vault.put("group-approved-history", historyID, data)
        try vault.put("group-approved", key, data)
    }
    /// Only the local CREATE intent can seed this; never a GET snapshot.
    func createdLocally(_ snapshot: GroupSnapshot, expectedID: UUID) throws {
        guard snapshot.id == expectedID, snapshot.members.count == 1, snapshot.members[0].id == vault.account,
            snapshot.members[0].role == .owner
        else { throw GroupsFailure.invalidResponse }
        try vault.transaction {
            guard try currentInTransaction(snapshot.id) == nil else { return }
            try putInTransaction(
                .init(group_id: snapshot.id, revision: 1, members: [.init(user_id: vault.account, role: .owner)]))
        }
    }
    func applyInTransaction(_ change: GroupRosterTransition, group: UUID, authenticatedSender: UUID) throws {
        guard let current = try currentInTransaction(group),
            let previous = try historyInTransaction(group, revision: change.from_revision)
        else { throw GroupsFailure.retryRequiresReview }
        let next = try change.validated(group: group, previous: previous, authenticatedSender: authenticatedSender)
        if let existing = try historyInTransaction(group, revision: next.revision) {
            guard Set(existing.members) == Set(next.members) else { throw MessageJournal.Failure.conflict }
            return  // Reissued/equivalent approved transition never rewinds state.
        }
        guard current.revision == change.from_revision else { throw GroupsFailure.retryRequiresReview }
        try putInTransaction(next)
    }
    /// Explicit bootstrap is restricted to a pending, authenticated add-self
    /// control from a previously pinned inviter/admin. UI must show its full
    /// roster and bind confirmation to that exact control/identity, never GET.
    func bootstrapInTransaction(
        _ change: GroupRosterTransition, group: UUID, authenticatedSender: UUID, confirmedInviter: UUID
    ) throws {
        guard try currentInTransaction(group) == nil, authenticatedSender == confirmedInviter,
            change.action == .add, change.target_id == vault.account
        else { throw GroupsFailure.noPermission }
        let previous = GroupApprovedRoster(
            group_id: group, revision: change.from_revision, members: change.previous_members)
        let next = try change.validated(group: group, previous: previous, authenticatedSender: authenticatedSender)
        try putInTransaction(previous)  // Explicitly reviewed trust anchor; no network-derived authority.
        try putInTransaction(next)
    }
}
