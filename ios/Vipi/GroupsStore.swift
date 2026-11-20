import Foundation

/// All group content, drafts and notification/read preferences live in the same
/// account-bound encrypted vault as direct chats. Never UserDefaults/plain files.
final class GroupsStore {
    let vault: MessageVault
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    init(vault: MessageVault) { self.vault = vault }
    private func key(_ id: UUID) -> String { id.uuidString.lowercased() }
    func snapshots() throws -> [GroupSnapshot] { try vault.transaction {
        try vault.ids("group-roster").compactMap { id in try vault.get("group-roster", id).map { try decoder.decode(GroupSnapshot.self, from: $0) } }
    } }
    func activeIDs() throws -> Set<UUID>? { try vault.transaction { try vault.get("group-active", "ids").map { Set(try decoder.decode([UUID].self, from: $0)) } } }
    func saveActiveIDs(_ ids: Set<UUID>) throws { try vault.transaction { try vault.put("group-active", "ids", encoder.encode(Array(ids))) } }
    func save(_ value: GroupSnapshot) throws { try value.validate(); try vault.transaction {
        if let bytes = try vault.get("group-roster", key(value.id)) {
            let old = try decoder.decode(GroupSnapshot.self, from: bytes)
            guard value.epoch >= old.epoch else { throw GroupsFailure.membershipChanged }
        }
        try vault.put("group-roster", key(value.id), encoder.encode(value))
        for person in value.members { try vault.put("group-member", key(value.id) + "/" + key(person.id), encoder.encode(person)) }
    } }
    func cachedMember(_ group: UUID, person: UUID) throws -> GroupMember? { try vault.transaction {
        try vault.get("group-member", key(group) + "/" + key(person)).map { try decoder.decode(GroupMember.self, from: $0) }
    } }
    func preferences(_ id: UUID) throws -> GroupLocalPreferences { try vault.transaction {
        try vault.get("group-preferences", key(id)).map { try decoder.decode(GroupLocalPreferences.self, from: $0) } ?? .init()
    } }
    func updatePreferences(_ id: UUID, _ change: (inout GroupLocalPreferences) -> Void) throws { try vault.transaction {
        var value = try vault.get("group-preferences", key(id)).map { try decoder.decode(GroupLocalPreferences.self, from: $0) } ?? GroupLocalPreferences()
        change(&value); try vault.put("group-preferences", key(id), encoder.encode(value))
    } }
    func messages(_ group: UUID) throws -> [GroupMessage] { try vault.transaction {
        try messagesInTransaction(group)
    } }
    func messagesInTransaction(_ group: UUID) throws -> [GroupMessage] {
        try vault.ids("group-message").filter { $0.hasPrefix(key(group) + "/") }.compactMap { id in
            try vault.get("group-message", id).map { try decoder.decode(GroupMessage.self, from: $0) }
        }.sorted { ($0.createdAt, $0.id.uuidString) < ($1.createdAt, $1.id.uuidString) }
    }
    func saveMessageInTransaction(_ value: GroupMessage) throws {
        let id = key(value.groupID) + "/" + key(value.id)
        if let bytes = try vault.get("group-message", id) {
            let saved = try decoder.decode(GroupMessage.self, from: bytes)
            guard saved.id == value.id, saved.groupID == value.groupID, saved.epoch == value.epoch, saved.membershipRevision == value.membershipRevision,
                  saved.sender == value.sender, saved.text == value.text, saved.createdAt == value.createdAt else { throw MessageJournal.Failure.conflict }
        }
        try vault.put("group-message", id, encoder.encode(value))
    }
    func saveMessage(_ value: GroupMessage) throws { try vault.transaction { try saveMessageInTransaction(value) } }
    func unread(_ group: UUID, account: UUID) throws -> Int {
        let read = try preferences(group).readIDs
        return try messages(group).filter { $0.sender != account && $0.delivery == .received && !read.contains($0.id) }.count
    }
    func markRead(_ group: UUID, visible: Set<UUID>) throws { try updatePreferences(group) { $0.readIDs.formUnion(visible) } }
}
