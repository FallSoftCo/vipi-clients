import Foundation

/// Bounded recovery inbox, measured from encoded recovery payload sizes (not total SQLite/WAL disk).
/// Admission failure keeps existing holds and leaves the new relay item unacked.
final class GroupsHoldBudget {
    private struct Entry: Codable { let group: UUID; let bytes: Int }
    private let vault: MessageVault
    init(vault: MessageVault) { self.vault = vault }
    func reserveInTransaction(kind: String, id: String, group: UUID, bytes: Int) throws {
        let key = kind + "/" + id
        if try vault.get("group-hold-budget", key) != nil { return }
        let entries = try vault.ids("group-hold-budget").compactMap { key in try vault.get("group-hold-budget", key).map { try JSONDecoder().decode(Entry.self, from: $0) } }
        let local = entries.filter { $0.group == group }
        guard bytes >= 0, entries.count < 1024, local.count < 128,
              entries.reduce(0, { $0 + $1.bytes }) + bytes <= 32 * 1024 * 1024,
              local.reduce(0, { $0 + $1.bytes }) + bytes <= 8 * 1024 * 1024 else { throw GroupsFailure.holdCapacity }
        try vault.put("group-hold-budget", key, JSONEncoder().encode(Entry(group: group, bytes: bytes)))
    }
    func releaseInTransaction(kind: String, id: String) throws { try vault.remove("group-hold-budget", kind + "/" + id) }
}
