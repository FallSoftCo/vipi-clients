import Foundation
import Observation

struct ChatProfile: Codable, Identifiable, Hashable {
    let id: UUID; let username: String; let display_name: String
}

/// Native application coordinator. Lifecycle, send, explicit refresh and future
/// contentless relay/push events all enter the same serialized synchronization.
@MainActor @Observable final class ChatSession {
    private struct Inventory: Decodable { let revision: UInt32; let remaining: Int }
    private struct Status: Decodable { let state: String }
    private struct DeviceResult: Decodable { let id: UUID; let active: Bool }
    private struct Inbox: Decodable { let messages: [RoutedMessage.Received]; let next_cursor: String? }
    private struct BlockStatus: Decodable { let blocked: Bool }
    let userID: String
    private let api: any ChatTransport
    private var vault: MessageVault?
    private var core: MessagingCore?
    private var history: ConversationHistory?
    private(set) var profile: ChatProfile?
    private(set) var needsProfile = false
    private(set) var busy = false
    private(set) var syncing = false
    private(set) var ready = false
    private(set) var threads: [ChatThread] = []
    private(set) var contacts: [UUID: ChatProfile] = [:]
    private(set) var blockedPeers = Set<UUID>()
    private(set) var revision = 0
    var notice: String?
    private var syncAgain = false
    private var blockVersions: [UUID: Int] = [:]
    private var changingBlocks = Set<UUID>()
    private var cacheKey: String { "profile-" + userID }
    convenience init(authentication: AuthenticationManager, userID: String) throws {
        try self.init(api: ServiceClient(authentication: authentication, userID: userID), userID: userID)
    }
    init(api: any ChatTransport, userID: String) throws {
        self.userID = userID; self.api = api
        if let data = try KeychainStore.read(account: cacheKey) {
            let value = try JSONDecoder().decode(ChatProfile.self, from: data)
            try open(value)
        }
    }
    private func open(_ value: ChatProfile) throws {
        if let profile, profile.id != value.id { throw AuthenticationManager.SessionFailure.accountChanged }
        if vault == nil {
            let store = try MessageVault(account: value.id)
            vault = store; core = try MessagingCore(vault: store); history = try ConversationHistory(vault: store)
            ready = try store.transaction { try store.get("local", "registered-device") == Data(core!.device.id.uuidString.lowercased().utf8) }
            contacts = try store.transaction {
                var result: [UUID: ChatProfile] = [:]
                for key in try store.ids("contact") {
                    guard let data = try store.get("contact", key) else { continue }
                    let contact = try JSONDecoder().decode(ChatProfile.self, from: data); result[contact.id] = contact
                }
                return result
            }
            blockedPeers = try store.transaction { Set(try store.ids("blocked").compactMap(UUID.init(uuidString:))) }
        }
        profile = value; needsProfile = false
        try KeychainStore.save(JSONEncoder().encode(value), account: cacheKey)
        try reload()
    }
    private func reload() throws { threads = try history?.threads() ?? []; revision += 1 }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    private var now: Int64 { Int64(Date().timeIntervalSince1970 * 1000) }

    func start() async {
        guard !busy else { return }; busy = true; notice = nil
        do {
            let value: ChatProfile = try await api.request("GET", "/v1/me")
            try open(value); try await provision()
        } catch let error as ServiceFailure where error.code == "profile_required" { needsProfile = true }
        catch is CancellationError {}
        catch { notice = Self.explanation(error) }
        busy = false
        if ready { await synchronize() }
    }
    func createProfile(username: String, name: String) async {
        guard !busy else { return }; busy = true; notice = nil
        do {
            let value: ChatProfile = try await api.request("PUT", "/v1/me", body: body(["username": username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), "display_name": name]))
            try open(value); try await provision()
        } catch is CancellationError {}
        catch { notice = Self.explanation(error) }
        busy = false
        if ready { await synchronize() }
    }
    private func provision() async throws {
        guard let core, let vault else { return }
        if !ready {
            let value: DeviceResult = try await api.request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret]))
            guard value.active, value.id == core.device.id else { throw MessageJournal.Failure.invalidMessage }
            try vault.transaction { try vault.put("local", "registered-device", Data(core.device.id.uuidString.lowercased().utf8)) }
            ready = true
        }
        try await replenish()
    }
    private func replenish() async throws {
        guard let core, let vault else { return }
        let inventory: Inventory = try await api.request("GET", "/v1/keys", device: core.device)
        let hasPending = try vault.transaction { try vault.get("key-directory", "pending") != nil }
        if hasPending || inventory.remaining < 10 {
            let publication = try core.keys.publication(now: now)
            let response: Inventory = try await api.request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
            try core.keys.published(revision: response.revision)
        }
    }
    func find(_ input: String) async throws -> ChatProfile {
        guard ready, let core, let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let username = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard username.range(of: "^[a-z][a-z0-9_]{2,23}$", options: .regularExpression) != nil else { throw ServiceFailure(status: 0, code: "invalid_username") }
        let value: ChatProfile = try await api.request("GET", "/v1/people/" + username, device: core.device)
        guard value.id != profile?.id else { throw ServiceFailure(status: 0, code: "own_username") }
        try vault.transaction { try vault.put("contact", value.id.uuidString.lowercased(), JSONEncoder().encode(value)) }
        contacts[value.id] = value
        return value
    }
    func name(_ peer: UUID) -> String { contacts[peer]?.display_name ?? "New conversation" }
    func refreshBlock(_ peer: UUID) async throws {
        guard let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard !changingBlocks.contains(peer) else { return }
        let version = blockVersions[peer, default: 0]
        let value: BlockStatus = try await api.request("GET", "/v1/blocks/" + peer.uuidString.lowercased(), device: core.device)
        guard version == blockVersions[peer, default: 0], !changingBlocks.contains(peer) else { return }
        try recordBlock(value.blocked, peer: peer)
    }
    func setBlocked(_ blocked: Bool, peer: UUID) async throws {
        guard ready, let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard changingBlocks.insert(peer).inserted else { throw ServiceFailure(status: 0, code: "block_in_progress") }
        blockVersions[peer, default: 0] += 1
        defer { changingBlocks.remove(peer) }
        let value: BlockStatus = try await api.request("PUT", "/v1/blocks/" + peer.uuidString.lowercased(), body: body(["blocked": blocked]), device: core.device)
        guard value.blocked == blocked else { throw ServiceFailure(status: 0, code: "invalid_block_response") }
        try recordBlock(blocked, peer: peer)
    }
    private func recordBlock(_ blocked: Bool, peer: UUID) throws {
        guard let core else { return }
        try core.journal.setBlocked(blocked, peer: peer)
        if blocked { blockedPeers.insert(peer) } else { blockedPeers.remove(peer) }
        try reload()
    }
    func messages(_ peer: UUID, before: String? = nil) throws -> [ChatItem] { try history?.messages(peer: peer, before: before) ?? [] }
    func securityNumber(_ peer: UUID) throws -> SecurityNumber? {
        guard let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        return try core.securityNumber(peer: peer)
    }
    func setIdentityVerified(_ verified: Bool, peer: UUID, compared: SecurityNumber) throws {
        guard let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        try core.setIdentityVerified(verified, peer: peer, compared: compared); revision += 1
    }
    func markRead(_ peer: UUID) throws {
        guard threads.contains(where: { $0.peer == peer && $0.unread > 0 }) else { return }
        try history?.markRead(peer); try reload()
    }
    func compose(_ peer: UUID) throws -> String { try history?.composeDraft(peer) ?? "" }
    func saveCompose(_ text: String, peer: UUID) throws { try history?.saveComposeDraft(text, peer: peer) }
    /// Returns only after the user's text and timeline row have committed locally.
    func send(_ text: String, peer: UUID) throws {
        guard let core, ready else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard !blockedPeers.contains(peer) else { throw ServiceFailure(status: 0, code: "contact_blocked") }
        try core.journal.saveDraft(id: UUID(), recipient: peer, text: text, createdAt: now, now: now, consumeCompose: true)
        try reload()
    }
    private func establish(_ peer: UUID) async throws {
        guard let core, let vault else { return }
        if try core.hasSession(peer: peer) { return }
        let key = peer.uuidString.lowercased()
        let requestID: UUID = try vault.transaction {
            if let data = try vault.get("pending-claim", key), let value = UUID(uuidString: String(decoding: data, as: UTF8.self)) { return value }
            let value = UUID(); try vault.put("pending-claim", key, Data(value.uuidString.lowercased().utf8)); return value
        }
        do {
            let response: ClaimedKeys = try await api.request("POST", "/v1/people/\(key)/keys", body: body(["request_id": requestID.uuidString.lowercased()]), device: core.device)
            _ = try core.keys.establish(peer: peer, requestID: requestID, response: response)
            try vault.transaction { try vault.remove("pending-claim", key) }
        } catch let error as ServiceFailure where error.status == 410 {
            try vault.transaction { try vault.remove("pending-claim", key) }; throw error
        }
    }
    func synchronize() async {
        guard ready, let core else { return }
        if syncing { syncAgain = true; return }
        syncing = true; defer { syncing = false }
        repeat {
            syncAgain = false
            do {
                var cursor: String? = nil
                var seenCursors = Set<String>()
                // The server bounds a recipient's queue at 10,000. Start from
                // the beginning on each sync so failed items can recover.
                for _ in 0..<100 {
                    let inbox: Inbox = try await api.request("GET", "/v1/messages/pending", device: core.device, query: cursor.map { ["after": $0] } ?? [:])
                    for item in inbox.messages {
                        if blockedPeers.contains(item.sender_id) { continue }
                        do { _ = try core.receive(item.routed(account: profile!.id), now: now) }
                        catch { notice = "A message couldn’t be opened securely. Your existing conversations are saved." }
                    }
                    guard let next = inbox.next_cursor else { break }
                    guard seenCursors.insert(next).inserted else { throw ServiceFailure(status: 0, code: "invalid_inbox_cursor") }
                    cursor = next
                }
                for id in try core.journal.pendingReceipts() {
                    do {
                        let status: Status = try await api.request("POST", "/v1/messages/\(id.uuidString.lowercased())/receipt", device: core.device)
                        if ["delivered", "expired", "unavailable", "identity_changed"].contains(status.state) { try core.journal.receiptAccepted(id) }
                    } catch let error as ServiceFailure where error.status == 404 && error.code == "message_not_found" {
                        // The plaintext was committed before this receipt was
                        // queued. Server metadata can expire while we're away.
                        try core.journal.receiptAccepted(id)
                    } catch let error as ServiceFailure where error.status == 429 { break }
                }
                for draft in try core.journal.pendingDrafts(now: now).sorted(by: { $0.createdAt < $1.createdAt }) {
                    do {
                        if blockedPeers.contains(draft.recipient) { continue }
                        try await establish(draft.recipient)
                        if blockedPeers.contains(draft.recipient) { continue }
                        _ = try core.queue(id: draft.id, peer: draft.recipient, text: draft.text, createdAt: draft.createdAt, now: now)
                    } catch is CancellationError { throw CancellationError() }
                    catch { notice = Self.explanation(error) }
                }
                for envelope in try core.journal.pending(now: now) {
                    if blockedPeers.contains(envelope.recipient) { continue }
                    do {
                        let routed = try core.queue(id: envelope.id, peer: envelope.recipient, text: core.journal.outgoing(envelope.id)!.text, createdAt: envelope.createdAt, now: now)
                        let status: Status = try await api.request("POST", "/v1/messages", body: routed.sendData(), device: core.device)
                        let state = ["unavailable", "identity_changed"].contains(status.state) ? "failed" : status.state
                        try core.journal.applyStatus(envelope.id, state: state)
                    } catch let error as ServiceFailure {
                        if let state = Self.terminalSendState(error) { try core.journal.applyStatus(envelope.id, state: state) }
                        else if error.code != "recipient_queue_full" { throw error }
                        notice = Self.explanation(error)
                    }
                }
            } catch is CancellationError { break }
            catch { notice = Self.explanation(error); break }
        } while syncAgain && !Task.isCancelled
        do { try reload() } catch { notice = "Your saved conversations couldn’t be opened. Please try again." }
    }
    static func explanation(_ error: Error) -> String {
        if let failure = error as? ServiceFailure {
            switch failure.code {
            case "username_unavailable": return "That username isn’t available. Try another."
            case "person_not_found": return "No one was found with that username. Check the spelling with your friend."
            case "invalid_username": return "Use 3–24 letters, numbers or underscores, starting with a letter."
            case "own_username": return "That’s your username. Enter your friend’s username to start a conversation."
            case "service_not_available": return "Vipi is being prepared for launch. This account isn’t in the preview yet."
            case "device_replacement_confirmation_required": return "This account is already active on another device. Moving your account needs a separate confirmation."
            case "recent_sign_in_required", "sign_in_required", "device_revoked": return "Please sign in again to reconnect your account. Your saved conversations are still on this device."
            case "recipient_keys_unavailable": return "Your friend needs to open Vipi before this first message can be sent. Your message is saved."
            case "device_not_ready": return "Connect once to finish setting up this device."
            case "contact_blocked": return "Unblock this person to send a new message."
            case "message_expired": return "This message expired before delivery. You can send it again."
            case "recipient_unavailable", "recipient_identity_changed", "message_id_conflict", "invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type": return "A message couldn’t be delivered. Your other conversations can continue."
            default: if failure.status == 429 { return "Please wait a moment before trying again. Your messages are saved." }
            }
        }
        return "We couldn’t connect. Your messages are saved on this device. Try again when you’re online."
    }
    private static func terminalSendState(_ failure: ServiceFailure) -> String? {
        if failure.status == 410 && failure.code == "message_expired" { return "expired" }
        if failure.status == 404 && failure.code == "recipient_unavailable" { return "failed" }
        if failure.status == 409 && ["recipient_identity_changed", "message_id_conflict"].contains(failure.code) { return "failed" }
        if failure.status == 400 && ["invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type"].contains(failure.code) { return "failed" }
        return nil
    }
}
