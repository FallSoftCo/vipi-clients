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
    private struct Inbox: Decodable { let messages: [RoutedMessage.Received] }
    let userID: String
    private let api: ServiceClient
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
    private(set) var revision = 0
    var notice: String?
    private var syncAgain = false
    private var cacheKey: String { "profile-" + userID }
    init(authentication: AuthenticationManager, userID: String) throws {
        self.userID = userID; api = try ServiceClient(authentication: authentication, userID: userID)
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
    func messages(_ peer: UUID, before: String? = nil) throws -> [ChatItem] { try history?.messages(peer: peer, before: before) ?? [] }
    func markRead(_ peer: UUID) throws {
        guard threads.contains(where: { $0.peer == peer && $0.unread > 0 }) else { return }
        try history?.markRead(peer); try reload()
    }
    func compose(_ peer: UUID) throws -> String { try history?.composeDraft(peer) ?? "" }
    func saveCompose(_ text: String, peer: UUID) throws { try history?.saveComposeDraft(text, peer: peer) }
    /// Returns only after the user's text and timeline row have committed locally.
    func send(_ text: String, peer: UUID) throws {
        guard let core, ready else { throw ServiceFailure(status: 0, code: "device_not_ready") }
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
                let inbox: Inbox = try await api.request("GET", "/v1/messages/pending", device: core.device)
                for item in inbox.messages {
                    do { _ = try core.receive(item.routed(account: profile!.id), now: now) }
                    catch { notice = "A message couldn’t be opened securely. Your existing conversations are saved." }
                }
                for id in try core.journal.pendingReceipts() {
                    let status: Status = try await api.request("POST", "/v1/messages/\(id.uuidString.lowercased())/receipt", device: core.device)
                    if ["delivered", "expired", "unavailable", "identity_changed"].contains(status.state) { try core.journal.receiptAccepted(id) }
                }
                for draft in try core.journal.pendingDrafts(now: now).sorted(by: { $0.createdAt < $1.createdAt }) {
                    do {
                        try await establish(draft.recipient)
                        _ = try core.queue(id: draft.id, peer: draft.recipient, text: draft.text, createdAt: draft.createdAt, now: now)
                    } catch { notice = Self.explanation(error) }
                }
                for envelope in try core.journal.pending(now: now) {
                    let routed = try core.queue(id: envelope.id, peer: envelope.recipient, text: core.journal.outgoing(envelope.id)!.text, createdAt: envelope.createdAt, now: now)
                    let status: Status = try await api.request("POST", "/v1/messages", body: routed.sendData(), device: core.device)
                    let state = ["unavailable", "identity_changed"].contains(status.state) ? "failed" : status.state
                    try core.journal.applyStatus(envelope.id, state: state)
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
            default: if failure.status == 429 { return "Please wait a moment before trying again. Your messages are saved." }
            }
        }
        return "We couldn’t connect. Your messages are saved on this device. Try again when you’re online."
    }
}
