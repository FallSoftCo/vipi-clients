#if DEBUG
import CryptoKit
import Foundation

/// Dependency/bootstrap fixture only. VipiApp, ConnectedChatRoot, Settings,
/// AccountDeletionProgressView and AccountDeletion perform the entire flow.
/// No fixture method begins, accepts, resumes or finishes a deletion manager.
@MainActor final class ConnectedDeletionUIQualification: ChatTransport, DeletionTransport {
    private(set) static var current: ConnectedDeletionUIQualification?
    private struct Ledger: Codable {
        let account: UUID, other: UUID, user: String, otherUser: String
        var starts = 0, chats = 0
        var submissions = 0, statusReads = 0, confirmations = 0
        var unexpected = 0
        var accepted = false
        var secretHash: String?
        var otherKeyHash = "", otherProfileHash = ""
        var failure: String?
    }
    private static var directory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ConnectedDeletionQualification", isDirectory: true)
    }
    private static var ledgerURL: URL { directory.appendingPathComponent("owner.json") }
    private var ledger: Ledger
    private weak var authentication: AuthenticationManager?
    private weak var manager: AccountDeletion?
    private var chats: [ChatSession] = []
    private static let ownMarker = Data("Owned encrypted deletion marker".utf8)
    private static let otherMarker = Data("Unrelated encrypted marker must remain".utf8)
    static func prepareIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-qa") else { return }
        precondition(Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa", "Owned root qualification only")
        do {
            if ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-cleanup") {
                try cleanup()
                return
            }
            if current == nil { current = try ConnectedDeletionUIQualification() }
        } catch {
            // Never fall back to a live service after a partial QA bootstrap.
            preconditionFailure("Reconcile the owned synthetic deletion fixture before qualification")
        }
    }
    private static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    private func save() throws { try JSONEncoder().encode(ledger).write(to: Self.ledgerURL, options: .atomic) }
    private static func validate(_ value: Ledger) throws {
        guard value.account != value.other, value.user.hasPrefix("deletion-root-ui-"),
            UUID(uuidString: String(value.user.dropFirst("deletion-root-ui-".count))) != nil,
            value.otherUser == "deletion-root-other-" + value.other.uuidString.lowercased()
        else {
            throw ServiceFailure(status: 0, code: "invalid_root_fixture_ownership")
        }
    }
    private static func requireDisposableAudio() throws {
        let audio = MessageSpeechCache.directory.deletingLastPathComponent()
        guard FileManager.default.fileExists(atPath: audio.path) else { return }
        guard try audio.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true else {
            throw ServiceFailure(status: 0, code: "preserve_existing_qa_audio")
        }
        func inspect(_ url: URL) throws {
            let values = try url.resourceValues(forKeys: [
                .isDirectoryKey, .isRegularFileKey, .fileSizeKey, .isSymbolicLinkKey
            ])
            guard values.isSymbolicLink != true else {
                throw ServiceFailure(status: 0, code: "preserve_existing_qa_audio")
            }
            if values.isDirectory == true {
                for child in try FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: nil) {
                    try inspect(child)
                }
            } else {
                guard values.isRegularFile == true, values.fileSize == 0 else {
                    throw ServiceFailure(status: 0, code: "preserve_existing_qa_audio")
                }
            }
        }
        try inspect(audio)
    }
    private static func validateSavedAuthority(_ ledger: Ledger, expected: DeletionRecord? = nil) throws {
        // AccountDeletion.resume may erase a saved requested/completed receipt
        // BEFORE calling its transport. Validate global keys before the actual
        // manager exists, including on a resumed fixture/bootstrap.
        if let data = try KeychainStore.read(account: "session") {
            let value = try JSONDecoder().decode(VipiSession.self, from: data)
            guard value.userID == ledger.user, value.authority == .fallsoftVipiProduction,
                value.accessToken == "synthetic-root-access-never-transmitted",
                value.refreshToken == "synthetic-root-refresh-never-transmitted"
            else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_root_session")
            }
        }
        for key in ["pending-sign-in", "pending-identity-link"] {
            guard try KeychainStore.read(account: key) == nil else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_root_authentication")
            }
        }
        let pending = try KeychainDeletionStore().load()
        if let pending {
            guard pending.account == ledger.account, pending.userID == ledger.user else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_root_deletion")
            }
            if let fingerprint = ledger.secretHash {
                guard Self.hash(Data(pending.secret.utf8)) == fingerprint else {
                    throw ServiceFailure(status: 0, code: "preserve_unrelated_root_capability")
                }
            }
            if pending.phase != .prepared || pending.localErased {
                guard ledger.accepted, ledger.secretHash != nil else {
                    throw ServiceFailure(status: 0, code: "unowned_confirmed_root_receipt")
                }
            }
        }
        if let expected {
            guard let pending, pending.account == expected.account, pending.userID == expected.userID,
                pending.secret == expected.secret, pending.phase == expected.phase
            else {
                throw ServiceFailure(status: 0, code: "root_erasure_receipt_changed")
            }
        }
    }
    private init() throws {
        if FileManager.default.fileExists(atPath: Self.ledgerURL.path) {
            ledger = try JSONDecoder().decode(Ledger.self, from: Data(contentsOf: Self.ledgerURL))
            try Self.validate(ledger)
        } else {
            for key in ["session", "account-deletion", "pending-sign-in", "pending-identity-link"] {
                guard try KeychainStore.read(account: key) == nil else {
                    throw ServiceFailure(status: 0, code: "empty_owned_qa_identity_required")
                }
            }
            // Production erasure removes the private audio parent. Do not use
            // this fixture if it would erase preexisting QA recordings.
            try Self.requireDisposableAudio()
            let account = UUID(), other = UUID()
            ledger = Ledger(
                account: account, other: other, user: "deletion-root-ui-" + UUID().uuidString,
                otherUser: "deletion-root-other-" + other.uuidString.lowercased())
            try FileManager.default.createDirectory(at: Self.directory, withIntermediateDirectories: true)
            try save()  // Record ownership before creating any private records.
            try seed()
        }
        try Self.validateSavedAuthority(ledger)
        try Self.requireDisposableAudio()
        ledger.starts += 1
        try save()
    }
    private func seed() throws {
        for (id, marker) in [(ledger.account, Self.ownMarker), (ledger.other, Self.otherMarker)] {
            let vault = try MessageVault(account: id)
            defer { try? vault.close() }
            try vault.transaction { try vault.put("root-deletion-qa", "marker", marker) }
            if id == ledger.account {
                let core = try MessagingCore(vault: vault)
                try vault.transaction {
                    try vault.put("local", "registered-device", Data(core.device.id.uuidString.lowercased().utf8))
                }
            }
        }
        let profile = ChatProfile(id: ledger.account, username: "deletion_qa", display_name: "Deletion QA")
        let other = ChatProfile(id: ledger.other, username: "preserved_qa", display_name: "Preserved QA")
        try KeychainStore.save(JSONEncoder().encode(profile), account: "profile-" + ledger.user)
        let otherData = try JSONEncoder().encode(other)
        try KeychainStore.save(otherData, account: "profile-" + ledger.otherUser)
        ledger.otherProfileHash = Self.hash(otherData)
        guard let key = try KeychainStore.read(account: "messages-" + ledger.other.uuidString.lowercased()) else {
            throw MessageVault.Failure.missingKey
        }
        ledger.otherKeyHash = Self.hash(key)
        try KeychainStore.save(
            JSONEncoder().encode(
                VipiSession(
                    userID: ledger.user, accessToken: "synthetic-root-access-never-transmitted",
                    refreshToken: "synthetic-root-refresh-never-transmitted", authority: .fallsoftVipiProduction)),
            account: "session")
        try save()
    }
    var connection: ConnectedChatRoot.Qualification {
        .init(
            makeChat: { [self] auth, user in
                guard user == ledger.user, auth.session?.userID == ledger.user else {
                    throw ServiceFailure(status: 0, code: "root_fixture_identity_mismatch")
                }
                ledger.chats += 1
                try save()
                let chat = try ChatSession(api: self, userID: user)
                chats.append(chat)
                return chat
            },
            makeSubscriptions: { [self] _, _, _ in
                ledger.unexpected += 1
                try save()
                throw ServiceFailure(status: 0, code: "unexpected_subscription_store")
            },
            makeBotOwner: { [self] account in
                if account != nil {
                    ledger.failure = "Unexpected account-bound bot owner"
                    try? save()
                }
                return BotConversationOwner()
            })
    }
    func makeDeletion(_ authentication: AuthenticationManager) throws -> AccountDeletion {
        try Self.validateSavedAuthority(ledger)
        try Self.requireDisposableAudio()
        self.authentication = authentication
        let value = AccountDeletion(
            store: KeychainDeletionStore(), service: self,
            erase: { [self] record in
                // Recheck immediately before the unchanged real eraser, rather
                // than relying on bootstrap or a later service.status binding.
                try Self.validateSavedAuthority(ledger, expected: record)
                try Self.requireDisposableAudio()
                try AccountDeletion.eraseLocal(record)
            }
        ) { user in
            try authentication.eraseLocalSession(for: user)
        }
        manager = value
        return value
    }
    private func bind(_ record: DeletionRecord) throws {
        guard record.account == ledger.account, record.userID == ledger.user else {
            throw ServiceFailure(status: 0, code: "root_fixture_receipt_mismatch")
        }
        let fingerprint = Self.hash(Data(record.secret.utf8))
        if let previous = ledger.secretHash {
            guard previous == fingerprint else {
                throw ServiceFailure(status: 0, code: "root_fixture_capability_changed")
            }
        } else {
            ledger.secretHash = fingerprint
        }
    }
    func submit(_ record: DeletionRecord) async throws -> DeletionReply {
        try bind(record)
        ledger.submissions += 1
        guard !ledger.accepted, ledger.submissions == 1 else {
            ledger.unexpected += 1
            try save()
            throw ServiceFailure(status: 0, code: "root_fixture_repeated_delete")
        }
        ledger.accepted = true
        try save()
        throw URLError(.networkConnectionLost)
    }
    func status(_ record: DeletionRecord) async throws -> DeletionReply {
        try bind(record)
        ledger.statusReads += 1
        try save()
        guard ledger.accepted else { throw ServiceFailure(status: 404, code: "deletion_receipt_unavailable") }
        guard ledger.starts > 1 else { throw URLError(.networkConnectionLost) }
        ledger.confirmations += 1
        try save()
        return DeletionReply(
            account_id: ledger.account, status: ledger.confirmations == 1 ? "deletion_requested" : "deleted")
    }
    func request<T: Decodable>(
        _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
        as type: T.Type
    ) async throws -> T {
        let value: [String: Any]
        switch (method, path) {
        case ("GET", "/v1/me"):
            guard !ledger.accepted else { throw ServiceFailure(status: 410, code: "account_deleted") }
            value = ["id": ledger.account.uuidString, "username": "deletion_qa", "display_name": "Deletion QA"]
        case ("GET", "/v1/keys"): value = ["revision": 1, "remaining": 20]
        case ("GET", "/v1/messages/pending"): value = ["messages": [], "next_cursor": NSNull()]
        case ("PUT", "/v1/devices/chat-features"):
            guard let body, try JSONDecoder().decode([String: Int].self, from: body) == ["version": 1],
                let device, !ledger.accepted
            else {
                ledger.unexpected += 1
                try save()
                throw ServiceFailure(status: 0, code: "unexpected_chat_features")
            }
            let vault = try MessageVault(account: ledger.account)
            defer { try? vault.close() }
            let registered = try DeviceCredential.registered(vault: vault)
            guard device.id == registered.id, device.secret == registered.secret else {
                ledger.unexpected += 1
                try save()
                throw ServiceFailure(status: 0, code: "unknown_chat_device")
            }
            value = ["version": 1, "device_id": device.id.uuidString]
        default:
            ledger.unexpected += 1
            try save()
            throw ServiceFailure(status: 0, code: "unexpected_root_fixture_request")
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
    private static func accountDirectory(_ account: UUID) -> URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(account.uuidString.lowercased())
    }
    private func marker(_ account: UUID, expected: Data) throws -> Bool {
        // Do not instantiate a vault after erasure: doing so would create the
        // very key/directory resurrection this regression must detect.
        guard FileManager.default.fileExists(atPath: Self.accountDirectory(account).path),
            try KeychainStore.read(account: "messages-" + account.uuidString.lowercased()) != nil
        else { return false }
        let vault = try MessageVault(account: account)
        defer { try? vault.close() }
        return try vault.transaction {
            try vault.get("root-deletion-qa", "marker") == expected
        }
    }
    var proof: String {
        do {
            let own = try marker(ledger.account, expected: Self.ownMarker)
            let other = try marker(ledger.other, expected: Self.otherMarker)
            let pending = try KeychainDeletionStore().load()
            let otherKey = try KeychainStore.read(account: "messages-" + ledger.other.uuidString.lowercased())
            let otherProfile = try KeychainStore.read(account: "profile-" + ledger.otherUser)
            let value: [String: Any] = [
                "starts": ledger.starts, "chat_creations": ledger.chats, "ready_chats": chats.filter(\.ready).count,
                "open_chat_owners": chats.filter { $0.ready || $0.profile != nil }.count,
                "submissions": ledger.submissions, "status_reads": ledger.statusReads,
                "confirmations": ledger.confirmations,
                "server_accepted": ledger.accepted, "unexpected_requests": ledger.unexpected,
                "fixture_failure": ledger.failure != nil,
                "session_key_present": try KeychainStore.read(account: "session") != nil,
                "auth_signed_out": authentication?.session == nil,
                "receipt_present": pending != nil, "phase": pending?.phase.rawValue ?? "none",
                "local_erased": pending?.localErased ?? false,
                "receipt_matches_owner": pending.map { $0.account == ledger.account && $0.userID == ledger.user }
                    ?? false,
                "own_marker": own,
                "own_directory": FileManager.default.fileExists(atPath: Self.accountDirectory(ledger.account).path),
                "own_key": try KeychainStore.read(account: "messages-" + ledger.account.uuidString.lowercased()) != nil,
                "own_profile": try KeychainStore.read(account: "profile-" + ledger.user) != nil,
                "other_marker": other, "other_key_unchanged": otherKey.map { Self.hash($0) } == ledger.otherKeyHash,
                "other_profile_unchanged": otherProfile.map { Self.hash($0) } == ledger.otherProfileHash
            ]
            return String(
                decoding: try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), as: UTF8.self)
        } catch { return "{\"proof_read_failed\":true}" }
    }
    private static func cleanup() throws {
        guard FileManager.default.fileExists(atPath: ledgerURL.path) else { return }
        let record = try JSONDecoder().decode(Ledger.self, from: Data(contentsOf: ledgerURL))
        try validate(record)
        try validateSavedAuthority(record)
        if let pending = try KeychainDeletionStore().load() {
            guard pending.account == record.account, pending.userID == record.user else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_deletion_record")
            }
            try KeychainDeletionStore().remove()
        }
        if let data = try KeychainStore.read(account: "session") {
            guard try JSONDecoder().decode(VipiSession.self, from: data).userID == record.user else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_session")
            }
            try KeychainStore.deleteChecked(account: "session")
        }
        for id in [record.account, record.other] {
            let directory = accountDirectory(id)
            if FileManager.default.fileExists(atPath: directory.path) {
                try FileManager.default.removeItem(at: directory)
            }
            try KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased())
        }
        for user in [record.user, record.otherUser] { try KeychainStore.deleteChecked(account: "profile-" + user) }
        try FileManager.default.removeItem(at: directory)
    }
}
#endif
