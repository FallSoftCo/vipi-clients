import Foundation
import Security

/// Enabling previews grants the extension access to this account's encrypted vault.
/// The app-only sign-in and refresh credentials are never shared.
struct NotificationGrant: Codable, Equatable {
    let account: UUID
    let epoch: UUID
    let key: Data
}

struct NotificationConsent: Codable, Equatable {
    let epoch: UUID
    let since: Double
    init(now: Date = Date()) { epoch = UUID(); since = now.timeIntervalSince1970 }
}

enum NotificationAccess {
    static let group = "group.co.fallsoft.vipi.notifications"
    static var root: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)?.appendingPathComponent("Messages", isDirectory: true)
    }
    static var legacyRoot: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages", isDirectory: true)
    }
    private static func query() throws -> [String: Any] {
        guard let group = Bundle.main.object(forInfoDictionaryKey: "VipiNotificationKeyGroup") as? String,
              !group.isEmpty, !group.contains("$") else { throw MessageVault.Failure.missingKey }
        return [kSecClass as String: kSecClassGenericPassword, kSecAttrAccessGroup as String: group,
                kSecAttrService as String: "co.fallsoft.vipi.notification-preview", kSecAttrAccount as String: "active"]
    }
    static func grant() throws -> NotificationGrant? {
        var query = try query()
        query[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw MessageVault.Failure.missingKey }
        return try JSONDecoder().decode(NotificationGrant.self, from: data)
    }
    static func revoke() throws {
        let status = SecItemDelete(try query() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw MessageVault.Failure.missingKey }
    }
    #if !VIPI_NOTIFICATION_EXTENSION
    static func authorize(_ grant: NotificationGrant) throws {
        let data = try JSONEncoder().encode(grant)
        var query = try query()
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly] as CFDictionary)
        if status == errSecSuccess { return }
        guard status == errSecItemNotFound else { throw MessageVault.Failure.missingKey }
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(query as CFDictionary, nil) == errSecSuccess else { throw MessageVault.Failure.missingKey }
    }
    static func storageRoot(for account: UUID, shared: URL? = root, legacy: URL = legacyRoot) throws -> URL {
        let marker = "notification-store-location-" + account.uuidString.lowercased()
        let migrated = try KeychainStore.read(account: marker) != nil
        guard let root = shared else {
            guard !migrated else { throw MessageVault.Failure.incompatible }
            return legacy
        }
        let fm = FileManager.default
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        let name = account.uuidString.lowercased()
        let old = legacy.appendingPathComponent(name)
        let destination = root.appendingPathComponent(name)
        if !migrated {
            // Pin the destination before rename. A crash can leave either original
            // folder, and the next open resumes the same move without creating a second DB.
            try KeychainStore.save(Data([1]), account: marker)
        }
        if fm.fileExists(atPath: old.path) {
            // Migrate only before opening any connection. Rename the entire folder including WAL
            // and SHM atomically. Never copy a live DB, merge directories or overwrite a newer store.
            guard renamex_np(old.path, destination.path, UInt32(RENAME_EXCL)) == 0 else {
                throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
            }
        }
        return root
    }
    #endif
    static func line(_ text: String, limit: Int = 160) -> String {
        let breaks = CharacterSet.controlCharacters.union(.whitespacesAndNewlines)
            .union(CharacterSet(charactersIn: "\u{061c}\u{200e}\u{200f}\u{202a}\u{202b}\u{202c}\u{202d}\u{202e}\u{2066}\u{2067}\u{2068}\u{2069}"))
        let line = text.components(separatedBy: breaks).filter { !$0.isEmpty }.joined(separator: " ")
        return line.count > limit ? String(line.prefix(limit - 1)) + "…" : line
    }
}
