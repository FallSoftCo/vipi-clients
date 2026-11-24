import Foundation

/// Stable identity for account-local conversation preferences. Direct peers and
/// groups are deliberately namespaced: both use UUIDs, but their settings must
/// never collide.
enum ConversationRef: Hashable, Sendable {
    case direct(UUID)
    case group(UUID)

    var storageKey: String {
        switch self {
        case .direct(let peer): "direct:" + peer.uuidString.lowercased()
        case .group(let group): "group:" + group.uuidString.lowercased()
        }
    }
}

/// Encrypted, account-owned overrides for a conversation's learning language.
/// The absence of a row means "follow the account default"; clearing a row is
/// therefore a real user choice, not a temporary UI state.
struct ConversationLanguageStore {
    let vault: MessageVault

    private struct Record: Codable { let version: Int; let target: String }

    func all() throws -> [String: String] {
        try vault.transaction {
            var values: [String: String] = [:]
            for key in try vault.ids("conversation-language") {
                guard let data = try vault.get("conversation-language", key),
                      let row = try? JSONDecoder().decode(Record.self, from: data),
                      row.version == 1,
                      VipiLanguage.initial.contains(where: { $0.id == row.target }) else { continue }
                values[key] = row.target
            }
            return values
        }
    }

    func set(_ ref: ConversationRef, target: String) throws {
        guard VipiLanguage.initial.contains(where: { $0.id == target }) else { throw CocoaError(.validationMissingMandatoryProperty) }
        let data = try JSONEncoder().encode(Record(version: 1, target: target))
        try vault.transaction { try vault.put("conversation-language", ref.storageKey, data) }
    }

    func clear(_ ref: ConversationRef) throws { try clear(storageKey: ref.storageKey) }

    func clear(storageKey: String) throws {
        try vault.transaction { try vault.remove("conversation-language", storageKey) }
    }
}
