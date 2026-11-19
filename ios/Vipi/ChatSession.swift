import Foundation
import Observation

struct ChatProfile: Codable, Identifiable, Hashable {
    let id: UUID; let username: String; let display_name: String
}

/// Native application coordinator. Lifecycle, send, explicit refresh and
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
    private(set) var needsDeviceReplacement = false
    private(set) var needsRecentSignIn = false
    private(set) var authenticationRecovery = ChatAuthenticationRecovery()
    var needsReauthentication: Bool { authenticationRecovery.required }
    private(set) var hasPendingDeviceReplacement = false
    private(set) var changedIdentities = Set<UUID>()
    private(set) var threads: [ChatThread] = []
    private(set) var contacts: [UUID: ChatProfile] = [:]
    private(set) var importedPeers: [UUID: HistoryBackupPeer] = [:]
    private(set) var historyBusy = false
    private var cancelHistoryWork: (() -> Void)?
    private(set) var blockedPeers = Set<UUID>()
    private(set) var revision = 0
    var notice: String?
    private var syncAgain = false
    private var events: ForegroundEvents?
    private var closed = false
    private(set) var translationOwner: ConversationImmersion?
    private var translationReplay: Task<Void,Never>?
    func configureTranslation(pair:TranslationPair,services:MessageTranslationServices) async {
        guard !closed else { return }
        if let owner = translationOwner,owner.pair == pair { return }
        translationReplay?.cancel(); translationOwner?.close()
        let owner = services.makeOwner(); await owner.configure(pair:pair)
        if let vault { owner.attachCache(vault) }
        translationOwner = owner; replayTranslations()
    }
    private func replayTranslations() {
        translationReplay?.cancel()
        guard let owner = translationOwner,let history else { return }
        translationReplay = Task { @MainActor [weak self,weak owner] in
            guard let self,let owner else { return }
            for peer in (try? history.threads().map(\.peer)) ?? [] {
                var before: String?
                repeat {
                    guard !Task.isCancelled,!closed,translationOwner === owner else { return }
                    let page = (try? history.messages(peer:peer,before:before,limit:50)) ?? []
                    for message in page {
                        guard !Task.isCancelled,!closed,translationOwner === owner else { return }
                        await owner.prepareStoredMessage(id:message.id.uuidString,text:message.text); await Task.yield()
                    }
                    before = page.count == 50 ? page.map(\.cursor).min() : nil
                } while before != nil
            }
        }
    }

    @ObservationIgnored private var messageObservers: [UUID:(ChatMessageArrival)->Void] = [:]
    func observeNewMessages(_ callback:@escaping(ChatMessageArrival)->Void) -> UUID {
        let id = UUID(); if !closed { messageObservers[id] = callback }; return id
    }
    func removeMessageObserver(_ id:UUID) { messageObservers.removeValue(forKey:id) }
    private func messageCommitted(_ value:ChatMessageArrival) {
        guard let vault,let id = UUID(uuidString:value.id),let peer = value.peer else { return }
        let arrival = ChatMessageArrival(id:value.id,peer:peer) { [weak vault] in
            guard let vault else { return nil }
            return try? vault.transaction {
                let key = id.uuidString.lowercased()
                if let bytes = try vault.get("draft",key) {
                    let draft = try JSONDecoder().decode(DraftChat.self,from:bytes)
                    guard draft.id == id,draft.recipient == peer else { return nil }
                    return draft.text
                }
                for kind in ["outgoing","incoming"] {
                    if let bytes = try vault.get(kind,key) {
                        let stored = try JSONDecoder().decode(StoredChat.self,from:bytes)
                        guard stored.envelope.id == id,(kind == "incoming" ? stored.envelope.sender:stored.envelope.recipient) == peer else { return nil }
                        return stored.text
                    }
                }
                return nil
            }
        }
        translationOwner?.warmStored(id:arrival.id,load:arrival.load)
        for observer in Array(messageObservers.values) { observer(arrival) }
    }

    private var blockVersions: [UUID: Int] = [:]
    private var changingBlocks = Set<UUID>()
    private var nameLookupAfter: [UUID: Date] = [:]
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
    #if DEBUG
    /// Isolated transport qualification: no account/keychain/vault is opened.
    init(qualificationAPI: any ChatTransport, userID: String, ready: Bool = false, profile: ChatProfile? = nil) {
        self.userID = userID; self.api = qualificationAPI; self.ready = ready; self.profile = profile
    }
    #endif
    private func open(_ value: ChatProfile) throws {
        try ensureOpen()
        if let profile, profile.id != value.id { throw AuthenticationManager.SessionFailure.accountChanged }
        if vault == nil {
            let store = try MessageVault(account: value.id)
            vault = store; core = try MessagingCore(vault: store); history = try ConversationHistory(vault: store)
            ready = try store.transaction { try store.get("local", "registered-device") == Data(core!.device.id.uuidString.lowercased().utf8) }
            hasPendingDeviceReplacement = try store.transaction { try store.get("local", "replacement-consent") == Data(core!.device.id.uuidString.lowercased().utf8) }
            contacts = try store.transaction {
                var result: [UUID: ChatProfile] = [:]
                for key in try store.ids("contact") {
                    guard let data = try store.get("contact", key) else { continue }
                    let contact = try JSONDecoder().decode(ChatProfile.self, from: data); result[contact.id] = contact
                }
                return result
            }
            importedPeers = try store.transaction {
                var result: [UUID: HistoryBackupPeer] = [:]
                for key in try store.ids("imported-peer") {
                    guard let bytes = try store.get("imported-peer", key) else { continue }
                    let value = try JSONDecoder().decode(HistoryBackupPeer.self, from: bytes); result[value.id] = value
                }
                return result
            }
            changedIdentities = try store.transaction { Set(try store.ids("identity-change").compactMap(UUID.init(uuidString:))) }
            blockedPeers = try store.transaction { Set(try store.ids("blocked").compactMap(UUID.init(uuidString:))) }
        }
        if let vault { translationOwner?.attachCache(vault) }
        profile = value; needsProfile = false
        try KeychainStore.save(JSONEncoder().encode(value), account: cacheKey)
        try reload(); replayTranslations()
    }
    private func reload() throws { threads = try history?.threads() ?? []; revision += 1 }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    private var now: Int64 { Int64(Date().timeIntervalSince1970 * 1000) }

    func start() async {
        guard !busy, !closed else { return }; busy = true; notice = nil
        do {
            let value: ChatProfile = try await request("GET", "/v1/me")
            try open(value); authenticationRecovery.authenticated(); try await provision()
        } catch let error as ServiceFailure where error.code == "profile_required" { needsProfile = true }
        catch is CancellationError {}
        catch { notice = Self.explanation(error) }
        busy = false
        if ready { await synchronize() }
    }
    func createProfile(username: String, name: String) async {
        guard !busy, !closed else { return }; busy = true; notice = nil
        do {
            let value: ChatProfile = try await request("PUT", "/v1/me", body: body(["username": username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), "display_name": name]))
            try open(value); try await provision()
        } catch is CancellationError {}
        catch { notice = Self.explanation(error) }
        busy = false
        if ready { await synchronize() }
    }
    private func provision() async throws {
        guard let core, let vault else { return }
        if !ready {
            let replacement = try vault.transaction { try vault.get("local", "replacement-consent") == Data(core.device.id.uuidString.lowercased().utf8) }
            if needsDeviceReplacement && !replacement { throw ServiceFailure(status: 409, code: "device_replacement_confirmation_required") }
            let value: DeviceResult = try await request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret, "replace_active": replacement]))
            guard value.active, value.id == core.device.id else { throw MessageJournal.Failure.invalidMessage }
            try vault.transaction { try vault.put("local", "registered-device", Data(core.device.id.uuidString.lowercased().utf8)); try vault.remove("local", "replacement-consent") }
            ready = true; needsDeviceReplacement = false; needsRecentSignIn = false; hasPendingDeviceReplacement = false
        }
        try await replenish()
    }
    func deviceReplacementCandidate() throws -> OwnDeviceReplacement {
        guard needsDeviceReplacement, !busy, !syncing, !historyBusy, let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        return try core.replacementCandidate()
    }
    func confirmDeviceReplacement(_ candidate: OwnDeviceReplacement) async throws {
        guard needsDeviceReplacement, !busy, !syncing, !historyBusy, let core, let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        busy = true; defer { busy = false }
        events?.stop(); events = nil
        try core.confirmDeviceReplacement(candidate)
        self.core = try MessagingCore(vault: vault)
        ready = false; needsDeviceReplacement = false; hasPendingDeviceReplacement = true
        try reload()
        do { try await provision(); notice = nil }
        catch { notice = Self.explanation(error); throw error }
    }
    /// A lost response or reauthentication resumes the exact persisted candidate;
    /// it must never create another identity or silently retry a displaced device.
    func resumeDeviceReplacement() async throws {
        guard hasPendingDeviceReplacement, !needsDeviceReplacement, !busy, !syncing, !historyBusy else {
            throw ServiceFailure(status: 0, code: "device_not_ready")
        }
        busy = true; defer { busy = false }
        do { try await provision(); notice = nil }
        catch { notice = Self.explanation(error); throw error }
    }
    private func recordIdentityChange(_ peer: UUID) throws {
        guard let vault else { return }
        try vault.transaction { try vault.put("identity-change", peer.uuidString.lowercased(), Data([1])) }
        changedIdentities.insert(peer)
    }
    func reviewPeerIdentity(_ peer: UUID) async throws -> PeerIdentityChange {
        guard ready, !historyBusy, let core, let vault, !blockedPeers.contains(peer) else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let key = peer.uuidString.lowercased()
        let id: UUID = try vault.transaction {
            if let bytes = try vault.get("pending-review-claim", key), let id = UUID(uuidString: String(decoding: bytes, as: UTF8.self)) { return id }
            let id = UUID(); try vault.put("pending-review-claim", key, Data(id.uuidString.lowercased().utf8)); return id
        }
        do {
            let value: ClaimedKeys = try await request("POST", "/v1/people/\(key)/keys", body: body(["request_id": id.uuidString.lowercased()]), device: core.device)
            return try core.keys.reviewReplacement(peer: peer, requestID: id, response: value)
        } catch let error as ServiceFailure where error.status == 410 || error.code == "recipient_identity_changed" {
            try vault.transaction { try vault.remove("pending-review-claim", key) }; throw error
        }
    }
    func acceptPeerIdentity(_ candidate: PeerIdentityChange) async throws {
        guard ready, !historyBusy, let core, let vault, !blockedPeers.contains(candidate.response.user_id) else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let response = candidate.response, key = response.user_id.uuidString.lowercased()
        // Server rechecks the currently active recipient before replaying this
        // exact claim. An expired or displaced preview is never auto-retried.
        let current: ClaimedKeys
        do {
            current = try await request("POST", "/v1/people/\(key)/keys",
                body: body(["request_id": response.request_id.uuidString.lowercased()]), device: core.device)
        } catch let error as ServiceFailure where error.status == 410 || error.code == "recipient_identity_changed" {
            try vault.transaction { try vault.remove("pending-review-claim", key) }; throw error
        }
        guard ready, !historyBusy, self.core === core, current == response else { throw DurableSignalStore.Failure.identityChanged }
        _ = try core.keys.establish(peer: response.user_id, requestID: response.request_id, response: current, replacing: candidate)
        changedIdentities.remove(response.user_id); try reload()
        await synchronize()
    }
    private func replenish() async throws {
        guard let core, let vault else { return }
        let inventory: Inventory = try await request("GET", "/v1/keys", device: core.device)
        let hasPending = try vault.transaction { try vault.get("key-directory", "pending") != nil }
        if hasPending || inventory.remaining < 10 {
            let publication = try core.keys.publication(now: now)
            let response: Inventory = try await request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
            try core.keys.published(revision: response.revision)
        }
    }
    func find(_ input: String) async throws -> ChatProfile {
        guard ready, let core, let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard let username = FriendLookupUsername.normalize(input) else { throw ServiceFailure(status: 0, code: "invalid_username") }
        let value: ChatProfile = try await request("GET", "/v1/people/" + username, device: core.device)
        guard value.id != profile?.id else { throw ServiceFailure(status: 0, code: "own_username") }
        try vault.transaction { try vault.put("contact", value.id.uuidString.lowercased(), JSONEncoder().encode(value)) }
        contacts[value.id] = value
        return value
    }
    func name(_ peer: UUID) -> String { contacts[peer]?.display_name ?? importedPeers[peer]?.displayName ?? String(localized: "New conversation") }
    /// Display metadata is not a Signal identity assertion. One bounded pass
    /// follows a completed inbox sync; offline and deleted peers retain history.
    private func resolveUnknownNames() async throws {
        guard let core, let vault else { return }
        let candidates = threads.map(\.peer).filter {
            contacts[$0] == nil && !blockedPeers.contains($0) && (nameLookupAfter[$0] ?? .distantPast) <= Date()
        }.prefix(20)
        for peer in candidates {
            nameLookupAfter[peer] = Date().addingTimeInterval(300)
            do {
                let value: ChatProfile = try await request("GET", "/v1/people/by-id/" + peer.uuidString.lowercased(), device: core.device)
                guard value.id == peer, value.id != profile?.id,
                      value.username.range(of: "^[a-z][a-z0-9_]{2,23}$", options: .regularExpression) != nil,
                      !value.display_name.isEmpty, value.display_name.unicodeScalars.count <= 80,
                      !value.display_name.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { continue }
                try vault.transaction { try vault.put("contact", peer.uuidString.lowercased(), JSONEncoder().encode(value)) }
                contacts[peer] = value
            } catch is CancellationError { throw CancellationError() }
            catch let error as ServiceFailure where error.status == 404 { nameLookupAfter[peer] = Date().addingTimeInterval(3600) }
            catch { break }
        }
    }
    func report(peer: UUID, message: ChatItem?, reason: HumanReportReason) async throws {
        guard ready, let core, let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let report = try HumanReportStore.prepare(vault: vault, peer: peer, message: message, reason: reason)
        if report.reported { return }
        let reply: HumanReportReply = try await request("POST", "/v1/reports", body: JSONEncoder().encode(report.body), device: core.device)
        guard reply.reported, reply.report_id == report.body.report_id else { throw ServiceFailure(status: 0, code: "invalid_report_response") }
        try HumanReportStore.complete(vault: vault, report: report)
    }
    func refreshBlock(_ peer: UUID) async throws {
        guard let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard !changingBlocks.contains(peer) else { return }
        let version = blockVersions[peer, default: 0]
        let value: BlockStatus = try await request("GET", "/v1/blocks/" + peer.uuidString.lowercased(), device: core.device)
        guard version == blockVersions[peer, default: 0], !changingBlocks.contains(peer) else { return }
        try recordBlock(value.blocked, peer: peer)
    }
    func setBlocked(_ blocked: Bool, peer: UUID) async throws {
        guard ready, let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard changingBlocks.insert(peer).inserted else { throw ServiceFailure(status: 0, code: "block_in_progress") }
        blockVersions[peer, default: 0] += 1
        defer { changingBlocks.remove(peer) }
        let value: BlockStatus = try await request("PUT", "/v1/blocks/" + peer.uuidString.lowercased(), body: body(["blocked": blocked]), device: core.device)
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
        guard !historyBusy else { throw ServiceFailure(status: 0, code: "history_busy") }
        guard let core, ready else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard !blockedPeers.contains(peer) else { throw ServiceFailure(status: 0, code: "contact_blocked") }
        guard !changedIdentities.contains(peer) else { throw ServiceFailure(status: 0, code: "peer_identity_review_required") }
        let id = UUID()
        try core.journal.saveDraft(id:id,recipient:peer,text:text,createdAt:now,now:now,consumeCompose:true)
        messageCommitted(.init(id:id.uuidString,text:text,peer:peer))
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
            let response: ClaimedKeys = try await request("POST", "/v1/people/\(key)/keys", body: body(["request_id": requestID.uuidString.lowercased()]), device: core.device)
            _ = try core.keys.establish(peer: peer, requestID: requestID, response: response)
            try vault.transaction { try vault.remove("pending-claim", key) }
        } catch let error as ServiceFailure where error.status == 410 {
            try vault.transaction { try vault.remove("pending-claim", key) }; throw error
        } catch DurableSignalStore.Failure.identityChanged {
            try recordIdentityChange(peer)
            throw ServiceFailure(status: 0, code: "peer_identity_review_required")
        }
    }
    func synchronize() async {
        guard ready, !needsReauthentication, !closed, let core else { return }
        if historyBusy { syncAgain = true; return }
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
                    let inbox: Inbox = try await request("GET", "/v1/messages/pending", device: core.device, query: cursor.map { ["after": $0] } ?? [:])
                    for item in inbox.messages {
                        if blockedPeers.contains(item.sender_id) { continue }
                        do {
                            let alreadyStored = try vault?.transaction { try vault?.get("incoming",item.id.uuidString.lowercased()) != nil } ?? false
                            let received = try core.receive(item.routed(account:profile!.id),now:now)
                            if !alreadyStored { messageCommitted(.init(id:item.id.uuidString,text:received.text,peer:item.sender_id)) }
                        }
                        catch DurableSignalStore.Failure.retiredDevice { continue }
                        catch DurableSignalStore.Failure.identityChanged {
                            try recordIdentityChange(item.sender_id)
                            notice = String(localized: "A friend’s encryption keys changed. Review their encryption details before continuing.")
                        }
                        catch { notice = String(localized: "A message couldn’t be opened securely. Your existing conversations are saved.") }
                    }
                    guard let next = inbox.next_cursor else { break }
                    guard seenCursors.insert(next).inserted else { throw ServiceFailure(status: 0, code: "invalid_inbox_cursor") }
                    cursor = next
                }
                for id in try core.journal.pendingReceipts() {
                    do {
                        let status: Status = try await request("POST", "/v1/messages/\(id.uuidString.lowercased())/receipt", device: core.device)
                        if ["delivered", "expired", "unavailable", "identity_changed"].contains(status.state) { try core.journal.receiptAccepted(id) }
                    } catch let error as ServiceFailure where error.status == 404 && error.code == "message_not_found" {
                        // The plaintext was committed before this receipt was
                        // queued. Server metadata can expire while we're away.
                        try core.journal.receiptAccepted(id)
                    } catch let error as ServiceFailure where error.status == 429 { break }
                }
                for draft in try core.journal.pendingDrafts(now: now).sorted(by: { $0.createdAt < $1.createdAt }) {
                    do {
                        if blockedPeers.contains(draft.recipient) || changedIdentities.contains(draft.recipient) { continue }
                        try await establish(draft.recipient)
                        if blockedPeers.contains(draft.recipient) || changedIdentities.contains(draft.recipient) { continue }
                        _ = try core.queue(id: draft.id, peer: draft.recipient, text: draft.text, createdAt: draft.createdAt, now: now)
                    } catch is CancellationError { throw CancellationError() }
                    catch { notice = Self.explanation(error) }
                }
                for envelope in try core.journal.pending(now: now) {
                    if blockedPeers.contains(envelope.recipient) { continue }
                    do {
                        let routed = try core.queue(id: envelope.id, peer: envelope.recipient, text: core.journal.outgoing(envelope.id)!.text, createdAt: envelope.createdAt, now: now)
                        let status: Status = try await request("POST", "/v1/messages", body: routed.sendData(), device: core.device)
                        if status.state == "identity_changed" { try recordIdentityChange(envelope.recipient) }
                        let state = ["unavailable", "identity_changed"].contains(status.state) ? "failed" : status.state
                        try core.journal.applyStatus(envelope.id, state: state)
                    } catch let error as ServiceFailure {
                        if error.code == "recipient_identity_changed" { try recordIdentityChange(envelope.recipient) }
                        if let state = Self.terminalSendState(error) { try core.journal.applyStatus(envelope.id, state: state) }
                        else if error.code != "recipient_queue_full" { throw error }
                        notice = Self.explanation(error)
                    }
                }
            } catch is CancellationError { break }
            catch { notice = Self.explanation(error); break }
        } while syncAgain && !Task.isCancelled
        do { try reload(); try await resolveUnknownNames() }
        catch is CancellationError {}
        catch { notice = String(localized: "Your saved conversations couldn’t be opened. Please try again.") }
    }
    private struct PushResult: Decodable {}
    func identityLinkTarget(expectedUser: String) throws -> (accountID: UUID, device: DeviceCredential) {
        guard userID == expectedUser, !closed, ready, !needsReauthentication, let profile, let core else { throw AuthenticationManager.SessionFailure.signInRequired }
        return (profile.id, core.device)
    }
    func setForeground(_ active: Bool) {
        guard active, ready, !needsReauthentication, !closed, let core, let api = api as? ServiceClient else { events?.stop(); return }
        if events == nil {
            let device = core.device
            events = ForegroundEvents(connect: { try await api.openEvents(device: device) },
                                      hint: { [weak self] in await self?.synchronize() }, authorizationEnded: { [weak self] in
                Task { @MainActor [weak self] in
                    guard let self, !self.closed, self.ready, self.core === core else { return }
                    do { let _: Inventory = try await self.request("GET", "/v1/keys", device: device) }
                    catch {
                        if !self.closed {
                            if !self.needsReauthentication { self.ready = false }
                            self.notice = Self.explanation(error)
                        }
                    }
                }
            })
        }
        events?.start()
    }
    func registerPush(token: String, environment: String) async throws {
        guard ready, let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let _: PushResult = try await request("PUT", "/v1/devices/push",
            body: body(["provider": "apns", "token": token, "environment": environment]), device: core.device)
    }
    func removePushRegistration() async throws {
        guard ready, let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let _: PushResult = try await request("DELETE", "/v1/devices/push", device: core.device)
    }

    func close() throws {
        translationReplay?.cancel(); translationReplay = nil; translationOwner?.close(); translationOwner = nil
        messageObservers.removeAll()
        events?.stop(); events = nil
        cancelHistoryWork?(); cancelHistoryWork = nil
        closed = true; ready = false; needsProfile = false; syncAgain = false
        try vault?.close(); vault = nil; core = nil; history = nil
        profile = nil; threads = []; contacts = [:]; importedPeers = [:]; blockedPeers = []
    }

    private func historyWork<T: Sendable>(_ operation: @escaping @Sendable (MessageVault) throws -> T) async throws -> T {
        try ensureOpen()
        guard !historyBusy, !syncing, !busy, let vault else { throw ServiceFailure(status: 0, code: "history_busy") }
        historyBusy = true
        let task = Task.detached(priority: .userInitiated) { try operation(vault) }
        cancelHistoryWork = { task.cancel() }
        defer {
            historyBusy = false; cancelHistoryWork = nil
            if syncAgain && !closed { Task { @MainActor [weak self] in await self?.synchronize() } }
        }
        let result = try await withTaskCancellationHandler(operation: { try await task.value }, onCancel: { task.cancel() })
        try ensureOpen()
        return result
    }
    func exportHistory(password: String, to url: URL) async throws {
        try await historyWork { try HistoryBackupStore.export(vault: $0, password: password, to: url) }
    }
    func inspectHistory(selected: URL, password: String, staged: URL) async throws -> HistoryBackupCodec.Summary {
        try await historyWork { vault in
            _ = try HistoryBackupStore.stage(selected, to: staged)
            do { return try HistoryBackupCodec.inspect(url: staged, password: password, account: vault.account) }
            catch { try? FileManager.default.removeItem(at: staged); throw error }
        }
    }
    func importHistory(staged: URL, password: String, verified: HistoryBackupCodec.Summary) async throws -> HistoryBackupStore.ImportResult {
        let value = try await historyWork { try HistoryBackupStore.merge(vault: $0, staged: staged, password: password, verified: verified) }
        guard let vault else { throw CancellationError() }
        importedPeers = try vault.transaction {
            var result: [UUID: HistoryBackupPeer] = [:]
            for key in try vault.ids("imported-peer") {
                guard let bytes = try vault.get("imported-peer", key) else { continue }
                let peer = try JSONDecoder().decode(HistoryBackupPeer.self, from: bytes); result[peer.id] = peer
            }
            return result
        }
        try reload(); replayTranslations()
        return value
    }
    private func ensureOpen() throws {
        guard !closed else { throw CancellationError() }
        try Task.checkCancellation()
    }
    private func request<T: Decodable>(_ method: String, _ path: String, body: Data? = nil,
                                       device: DeviceCredential? = nil, query: [String: String] = [:]) async throws -> T {
        try ensureOpen()
        do {
            let value: T = try await api.request(method, path, body: body, device: device, query: query)
            try ensureOpen(); return value
        } catch {
            try ensureOpen()
            authenticationRecovery.failed(error, deviceRecovery: needsDeviceReplacement || hasPendingDeviceReplacement)
            if needsReauthentication { events?.stop(); events = nil }
            if let failure = error as? ServiceFailure,
               ["device_revoked", "device_registration_conflict", "device_replacement_confirmation_required"].contains(failure.code) {
                authenticationRecovery.authenticated()
                ready = false; needsDeviceReplacement = true; hasPendingDeviceReplacement = false; needsRecentSignIn = false; events?.stop(); events = nil
                if let vault { try vault.transaction { try vault.remove("local", "replacement-consent") } }
            }
            if let failure = error as? ServiceFailure, ["recent_sign_in_required", "sign_in_required"].contains(failure.code), needsDeviceReplacement || hasPendingDeviceReplacement {
                needsRecentSignIn = true
            }
            throw error
        }
    }
    static func explanation(_ error: Error) -> String {
        if let failure = error as? ServiceFailure {
            switch failure.code {
            case "username_unavailable": return String(localized: "That username isn’t available. Try another.")
            case "person_not_found": return String(localized: "No one was found with that username. Check the spelling with your friend.")
            case "invalid_username": return String(localized: "Use 3–24 letters, numbers or underscores, starting with a letter.")
            case "own_username": return String(localized: "That’s your username. Enter your friend’s username to start a conversation.")
            case "service_not_available": return String(localized: "Vipi is being prepared for launch. This account isn’t in the preview yet.")
            case "base_subscription_required": return String(localized: "Start or restore your Vipi plan in Settings → Subscriptions to send messages. Your saved chats and drafts remain available.")
            case "device_replacement_confirmation_required": return String(localized: "This account is already active on another device. Moving your account needs a separate confirmation.")
            case "recent_sign_in_required", "sign_in_required", "device_revoked": return String(localized: "Please sign in again to reconnect your account. Your saved conversations are still on this device.")
            case "recipient_keys_unavailable": return String(localized: "Your friend needs to open Vipi before this first message can be sent. Your message is saved.")
            case "peer_identity_review_required": return String(localized: "Review this friend’s changed encryption keys before sending another message.")
            case "device_not_ready": return String(localized: "Connect once to finish setting up this device.")
            case "contact_blocked": return String(localized: "Unblock this person to send a new message.")
            case "message_expired": return String(localized: "This message expired before delivery. You can send it again.")
            case "recipient_unavailable", "recipient_identity_changed", "message_id_conflict", "invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type": return String(localized: "A message couldn’t be delivered. Your other conversations can continue.")
            default: if failure.status == 429 { return String(localized: "Please wait a moment before trying again. Your messages are saved.") }
            }
        }
        return String(localized: "Can’t connect. Messages are saved here.")
    }
    private static func terminalSendState(_ failure: ServiceFailure) -> String? {
        if failure.status == 410 && failure.code == "message_expired" { return "expired" }
        if failure.status == 404 && failure.code == "recipient_unavailable" { return "failed" }
        if failure.status == 409 && ["recipient_identity_changed", "message_id_conflict"].contains(failure.code) { return "failed" }
        if failure.status == 400 && ["invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type"].contains(failure.code) { return "failed" }
        return nil
    }
}

/// Ordinary expired authentication never changes device ownership or local storage.
struct ChatAuthenticationRecovery {
    private(set) var required = false
    mutating func authenticated() { required = false }
    mutating func failed(_ error: Error, deviceRecovery: Bool) {
        guard !deviceRecovery else { required = false; return }
        if let failure = error as? ServiceFailure,
           ["sign_in_required", "recent_sign_in_required"].contains(failure.code) { required = true }
        if let failure = error as? AuthenticationManager.SessionFailure,
           case .signInRequired = failure { required = true }
    }
}

/// Accept the optional @ shown in invitations only for friend lookup.
enum FriendLookupUsername {
    static func normalize(_ input: String) -> String? {
        var value = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if value.hasPrefix("@") { value.removeFirst() }
        guard value.range(of: "^[a-z][a-z0-9_]{2,23}$", options: .regularExpression) != nil else { return nil }
        return value
    }
}
