import UIKit
import Observation

struct ChatProfile: Codable, Identifiable, Hashable {
    let id: UUID; let username: String; let display_name: String
}

/// Only an authenticated self-profile response can negotiate the groups protocol.
struct AuthenticatedChatProfile: Decodable {
    let profile: ChatProfile
    let supportsGroups: Bool
    private enum CodingKeys: String, CodingKey { case group_protocol_version }
    init(from decoder: Decoder) throws {
        profile = try ChatProfile(from: decoder)
        let fields = try decoder.container(keyedBy: CodingKeys.self)
        supportsGroups = (try? fields.decode(Int.self, forKey: .group_protocol_version)) == GroupsUpgrade.protocolVersion
    }
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
    private var advertisedMediaDevice: UUID?
    private var mediaRegistration: Task<Bool, Never>?
    private var mediaOverride: CiphertextTransport?
    private var mediaTransport: CiphertextTransport? { mediaOverride ?? (api as? ServiceClient)?.media }
    private var vault: MessageVault?
    private var core: MessagingCore?
    private var history: ConversationHistory?
    struct IncomingPreview: Identifiable {
        let id: UUID
        let peer: UUID
        let text: String
    }
    private(set) var previewsWhileOpen = false
    private(set) var previewsOutsideApp = false
    func notificationDestination(account: UUID?, peer: UUID?, message: UUID?) -> UUID? {
        guard ready, !needsReauthentication, !closed, let account, profile?.id == account, let peer, let message,
              !blockedPeers.contains(peer), !changedIdentities.contains(peer), let vault else { return nil }
        return try? vault.transaction {
            guard try vault.get("blocked", peer.uuidString.lowercased()) == nil,
                  try vault.get("identity-change", peer.uuidString.lowercased()) == nil,
                  let row = try vault.get("incoming", message.uuidString.lowercased()) else { return nil }
            let saved = try JSONDecoder().decode(StoredChat.self, from: row)
            return saved.envelope.recipient == account && saved.envelope.sender == peer ? peer : nil
        }
    }
    func setOutsidePreviews(_ enabled: Bool) throws {
        guard let vault, ready, !closed, !needsReauthentication else { throw MessageVault.Failure.missingKey }
        let consent = enabled ? NotificationConsent() : nil
        try vault.transaction {
            let data = try consent.map { try JSONEncoder().encode($0) } ?? Data([0])
            try vault.put("local", "outside-previews", data)
        }
        previewsOutsideApp = enabled
        if enabled { try reconcileOutsidePreviews(allowed: PushNotifications.shared.canShowAlerts) }
        else { PushNotifications.shared.clearOutsidePreviews() }
    }
    func reconcileOutsidePreviews(allowed: Bool) throws {
        guard allowed, ready, !closed, !needsReauthentication, let vault,
              let consent = try vault.transaction({ try vault.notificationConsent() }) else {
            PushNotifications.shared.clearOutsidePreviews(); return
        }
        try vault.authorizeNotifications(consent)
    }
    private(set) var incomingPreview: IncomingPreview?
    func setPreviewsWhileOpen(_ enabled: Bool) throws {
        guard let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        try vault.transaction {
            if enabled { try vault.put("local", "foreground-previews", Data([1])) }
            else { try vault.remove("local", "foreground-previews") }
        }
        previewsWhileOpen = enabled
        if !enabled { incomingPreview = nil }
    }
    func clearPreview() { incomingPreview = nil }
    private func offerPreview(id: UUID, peer: UUID, text: String) {
        guard previewsWhileOpen, ready, !closed, !needsReauthentication,
              !blockedPeers.contains(peer), !changedIdentities.contains(peer),
              UIApplication.shared.applicationState == .active,
              UIApplication.shared.isProtectedDataAvailable else { return }
        let line = NotificationAccess.line(text)
        guard !line.isEmpty else { return }
        incomingPreview = IncomingPreview(id: id, peer: peer, text: line)
    }
    var groupDraftStore: GroupsStore? {
        guard ready, !needsReauthentication, !closed, let vault else { return nil }
        return GroupsStore(vault: vault)
    }
    private(set) var groups: GroupsSession? {
        didSet { (api as? ServiceClient)?.acceptsGroupEnvelopes = groups != nil }
    }
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
    private var activity: ChatActivityEvents?
    func isPeerTyping(_ peer: UUID) -> Bool { activity?.isTyping(peer) == true }
    func composerActivity(_ peer: UUID, active: Bool) { activity?.composer(peer, active:active) }
    func visibleMessages(_ peer: UUID, incoming: [UUID], outgoing: [UUID]) { activity?.visible(peer, incoming:incoming, outgoing:outgoing) }
    func peerActivityEvent(_ event: ChatForegroundEvent) { activity?.event(event) }
    private func configureActivity(_ vault: MessageVault) {
        activity = ChatActivityEvents(vault:vault, eligible:{ [weak self] peer in
            guard let self else { return false }
            return ready && !closed && !needsReauthentication && !blockedPeers.contains(peer) && !changedIdentities.contains(peer)
        }, sendTyping:{ [weak self] peer, active in
            guard let self, let device = core?.device else { return }
            let _: PushResult = try await request("POST", "/v1/conversations/\(peer.uuidString.lowercased())/typing", body:body(["active":active]), device:device)
        }, receipts:{ [weak self] peer, seen, check in
            guard let self, let device = core?.device else { throw CancellationError() }
            return try await request("POST", "/v1/conversations/\(peer.uuidString.lowercased())/receipts",
                body:body(["seen":seen.map{$0.uuidString.lowercased()}, "check":check.map{$0.uuidString.lowercased()}]), device:device)
        }, changed:{ [weak self] in try? self?.reload() })
    }
    private var closed = false
    private var feedbackSession = UUID()
    private var surveyUnavailable = false
    private var uploadingFundingChoice = false
    private(set) var showingFundingSurvey = false

    func dismissFundingCard() { showingFundingSurvey = false }
    func leftForeground() {
        feedbackSession = UUID(); surveyUnavailable = false; showingFundingSurvey = false
    }
    var feedbackVault: MessageVault? {
        guard ready, !closed, !needsReauthentication, !needsDeviceReplacement, !needsProfile,
              profile?.id == vault?.account else { return nil }
        return vault
    }
    func considerChatIntervention(whileIdle: () -> Bool) async -> ChatIntervention? {
        guard let vault = feedbackVault, whileIdle(), !showingFundingSurvey,
              let usage = try? vault.transaction({ try ChatFeedback.load(vault) }) else { return nil }
        let session = feedbackSession
        func claim(_ kind: ChatIntervention) -> Bool {
            guard !Task.isCancelled, feedbackVault === vault, session == feedbackSession, whileIdle() else { return false }
            return (try? vault.transaction {
                var current = try ChatFeedback.load(vault)
                guard current.claim(kind, now: Date(), session: session) else { return false }
                try current.save(vault); return true
            }) == true
        }
        if !surveyUnavailable, usage.eligible(.survey, now: Date(), session: session) {
            struct Availability: Decodable { let available: Bool }
            let result: Availability? = try? await api.request("GET", ChatFeedback.route)
            if session == feedbackSession, result?.available == false { surveyUnavailable = true }
            if result?.available == true, claim(.survey) { showingFundingSurvey = true; return .survey }
        }
        if usage.eligible(.review, now: Date(), session: session), claim(.review) { return .review }
        return nil
    }
    func chooseFundingResponse(_ choice: FundingChoice) {
        guard showingFundingSurvey, let vault = feedbackVault else { return }
        do {
            try vault.transaction {
                var record = try ChatFeedback.load(vault)
                record.choose(choice); try record.save(vault)
            }
            showingFundingSurvey = false
            Task { await retryFundingResponse() }
        } catch { return }
    }
    func reconcileFeedbackHistory() async {
        guard let vault = feedbackVault else { return }
        for _ in 0..<4 {
            guard !Task.isCancelled, feedbackVault === vault, (try? ChatFeedback.backfillPage(vault)) == true else { return }
            await Task.yield()
        }
    }
    func retryFundingResponse() async {
        guard !uploadingFundingChoice, let vault = feedbackVault,
              let choice = try? vault.transaction({ try ChatFeedback.load(vault).pending }) else { return }
        uploadingFundingChoice = true
        defer { uploadingFundingChoice = false }
        do {
            let _: NoContentResponse = try await api.request("PUT", ChatFeedback.route, body: JSONEncoder().encode(["choice": choice.rawValue]))
            guard feedbackVault === vault else { return }
            try vault.transaction {
                var record = try ChatFeedback.load(vault)
                guard record.pending == choice else { return }
                record.acknowledged(); try record.save(vault)
            }
        } catch { /* A later foreground or return to Chats retries the same account's explicit choice. */ }
    }

    private(set) var translationOwner: ConversationImmersion?
    private var translationReplay: Task<Void,Never>?
    private var translationOwners: [TranslationPair: ConversationImmersion] = [:]
    private var translationOwnerTasks: [TranslationPair: Task<Void,Never>] = [:]
    private var translationServices: MessageTranslationServices?
    private var translationSource = "en"
    private var translationDefaultTarget = "es"
    private var translationMode = ImmersionMode.incremental
    private var activeConversation: ConversationRef?
    private var conversationLanguages: [String: String] = [:]
    private(set) var translationGeneration = 0

    func defaultTargetLanguage() -> String { translationDefaultTarget }

    /// The source language belongs to the account. Only the target can be
    /// overridden by a direct or group conversation.
    func targetLanguage(_ ref: ConversationRef?) -> String {
        _ = translationGeneration
        let candidate = ref.flatMap { conversationLanguages[$0.storageKey] } ?? translationDefaultTarget
        if candidate != translationSource { return candidate }
        if translationDefaultTarget != translationSource { return translationDefaultTarget }
        return VipiLanguage.initial.first { $0.id != translationSource }?.id ?? "es"
    }

    func usesDefaultLanguage(_ ref: ConversationRef) -> Bool {
        _ = translationGeneration
        return conversationLanguages[ref.storageKey] == nil
    }

    func setConversationLanguage(_ ref: ConversationRef, target: String) {
        guard target != translationSource,
              VipiLanguage.initial.contains(where: { $0.id == target }),
              let vault else { return }
        do {
            try ConversationLanguageStore(vault: vault).set(ref, target: target)
            conversationLanguages[ref.storageKey] = target
            translationGeneration += 1
            if activeConversation == ref { refreshActiveTranslationOwner(replay: true) }
        } catch { return }
    }

    func useDefaultConversationLanguage(_ ref: ConversationRef) {
        guard let vault else { return }
        do {
            try ConversationLanguageStore(vault: vault).clear(ref)
            conversationLanguages.removeValue(forKey: ref.storageKey)
            translationGeneration += 1
            if activeConversation == ref { refreshActiveTranslationOwner(replay: true) }
        } catch { return }
    }

    /// Pair owners are shared across conversations. An override is conversation
    /// state; the expensive translator and encrypted result cache depend only
    /// on source, target and immersion mode.
    func translationFor(_ ref: ConversationRef) -> ConversationImmersion? {
        guard !closed else { return nil }
        _ = translationGeneration
        return owner(for: pair(for: ref))
    }

    func activateConversation(_ ref: ConversationRef) {
        if activeConversation != ref {
            activeConversation = ref
            translationGeneration += 1
            refreshActiveTranslationOwner(replay: true)
        } else if translationOwner == nil {
            refreshActiveTranslationOwner(replay: false)
        }
    }

    private func pair(for ref: ConversationRef?) -> TranslationPair {
        .init(source: translationSource, target: targetLanguage(ref))
    }

    private func owner(for pair: TranslationPair) -> ConversationImmersion? {
        guard pair.valid, let services = translationServices else { return nil }
        if let existing = translationOwners[pair] { return existing }
        let owner = services.makeOwner()
        if let vault { owner.attachCache(vault) }
        translationOwners[pair] = owner
        let mode = translationMode
        translationOwnerTasks[pair] = Task { @MainActor [weak self, weak owner] in
            guard let self, let owner, !self.closed else { return }
            await owner.configure(pair: pair, mode: mode)
        }
        return owner
    }

    private func refreshActiveTranslationOwner(replay: Bool) {
        translationReplay?.cancel()
        let activePair = pair(for: activeConversation)
        let owner = owner(for: activePair)
        translationOwner = owner
        if let owner {
            let mode = translationMode
            Task { @MainActor [weak owner] in await owner?.configure(pair: activePair, mode: mode) }
        }
        if replay { replayTranslations() }
    }

    private func closeTranslationOwners() {
        translationReplay?.cancel(); translationReplay = nil
        for task in translationOwnerTasks.values { task.cancel() }
        translationOwnerTasks.removeAll()
        for owner in translationOwners.values { owner.close() }
        translationOwners.removeAll()
        translationOwner = nil
    }

    func configureTranslation(pair:TranslationPair,mode:ImmersionMode = .incremental,services:MessageTranslationServices) async {
        guard !closed else { return }
        let servicesChanged = translationServices !== services
        let sourceChanged = translationSource != pair.source
        let defaultChanged = translationDefaultTarget != pair.target
        let modeChanged = translationMode != mode
        if servicesChanged { closeTranslationOwners() }
        translationServices = services
        translationSource = pair.source
        translationDefaultTarget = pair.target
        translationMode = mode
        if let vault {
            conversationLanguages = (try? ConversationLanguageStore(vault: vault).all()) ?? conversationLanguages
            if sourceChanged {
                let store = ConversationLanguageStore(vault: vault)
                let stale = conversationLanguages.filter { $0.value == pair.source }.map(\.key)
                for key in stale {
                    try? store.clear(storageKey: key)
                    conversationLanguages.removeValue(forKey: key)
                }
            }
        }
        if sourceChanged {
            let stale = translationOwners.filter { $0.key.source != pair.source }
            for (key, owner) in stale {
                translationOwnerTasks.removeValue(forKey: key)?.cancel()
                owner.close(); translationOwners.removeValue(forKey: key)
            }
        }
        if modeChanged {
            for (key, owner) in translationOwners {
                Task { @MainActor [weak owner] in await owner?.configure(pair: key, mode: mode) }
            }
        }
        if sourceChanged || defaultChanged || modeChanged || servicesChanged { translationGeneration += 1 }
        let activePair = self.pair(for: activeConversation)
        let owner = owner(for: activePair)
        if let owner, owner.pair != activePair || owner.mode != mode {
            await owner.configure(pair: activePair, mode: mode)
        }
        translationOwner = owner
        replayTranslations()
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
            for message in groups?.historyForImmersion() ?? [] {
                guard !Task.isCancelled, !closed, translationOwner === owner else { return }
                await owner.prepareStoredMessage(id: message.renderID, text: message.text); await Task.yield()
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
    init(api: any ChatTransport, userID: String, media: CiphertextTransport? = nil) throws {
        self.userID = userID; self.api = api; mediaOverride = media
        if let data = try KeychainStore.read(account: cacheKey) {
            let value = try JSONDecoder().decode(ChatProfile.self, from: data)
            try open(value)
        }
    }
    #if DEBUG
    /// Isolated transport qualification: no account/keychain/vault is opened.
    init(qualificationAPI: any ChatTransport, userID: String, ready: Bool = false, profile: ChatProfile? = nil, vault: MessageVault? = nil) {
        self.userID = userID; self.api = qualificationAPI; self.ready = ready; self.profile = profile; self.vault = vault
    }
    #endif
    private final class GroupTransport: ChatTransport {
        weak var owner: ChatSession?
        init(_ owner: ChatSession) { self.owner = owner }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            guard let owner, owner.groups != nil, !owner.needsReauthentication else { throw CancellationError() }
            do { return try await owner.request(method, path, body: body, device: device, query: query) }
            catch let error as ServiceFailure {
                if error.status == 404 && (error.code == "groups_not_available" || (method == "GET" && path == "/v1/groups")) {
                    owner.closeGroups()
                }
                throw error
            }
        }
    }
    private func openGroups(_ vault: MessageVault, core: MessagingCore) throws {
        guard groups == nil else { return }
        let store = GroupsStore(vault: vault)
        groups = try GroupsSession(account: vault.account, api: GroupsAPI(transport: GroupTransport(self), device: core.device), store: store,
            crypto: GroupsCrypto(vault: vault, core: core, store: store), preparePeer: { [weak self] peer in
                guard let self, self.ready, !self.closed, !self.blockedPeers.contains(peer), !self.changedIdentities.contains(peer) else { throw GroupsFailure.identityChanged }
                try await self.establish(peer)
            }, identityReview: { [weak self] peer in self?.changedIdentities.contains(peer) ?? true }, committed: { [weak self] message in
                guard let self, !self.closed else { return }
                self.translationFor(.group(message.groupID))?.warmStored(id: message.renderID) { [weak self] in
                    self?.groups?.messageOriginal(message.id, group: message.groupID)
                }
            })
    }
    private func open(_ value: ChatProfile) throws {
        try ensureOpen()
        if let profile, profile.id != value.id { throw AuthenticationManager.SessionFailure.accountChanged }
        if vault == nil {
            let store = try MessageVault(account: value.id)
            vault = store; core = try MessagingCore(vault: store); history = try ConversationHistory(vault: store)
            configureActivity(store)
            previewsOutsideApp = try store.transaction { try store.notificationConsent() != nil }
            previewsWhileOpen = try store.transaction { try store.get("local", "foreground-previews") == Data([1]) }
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
        if let vault {
            translationOwner?.attachCache(vault)
            for owner in translationOwners.values { owner.attachCache(vault) }
            conversationLanguages = (try? ConversationLanguageStore(vault: vault).all()) ?? [:]
        }
        profile = value; needsProfile = false
        try KeychainStore.save(JSONEncoder().encode(value), account: cacheKey)
        try reload(); replayTranslations()
    }
    private func openAuthenticatedProfile(_ response: AuthenticatedChatProfile) throws {
        try open(response.profile)
        if response.supportsGroups, let vault, let core {
            try openGroups(vault, core: core)
        } else {
            closeGroups()
        }
    }
    private func closeGroups() { groups?.close(); groups = nil }
    private func reload() throws { threads = try history?.threads() ?? []; revision += 1 }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    private var now: Int64 { Int64(Date().timeIntervalSince1970 * 1000) }

    func start() async {
        guard !busy, !closed else { return }; busy = true; notice = nil
        do {
            let value: AuthenticatedChatProfile = try await request("GET", "/v1/me")
            try openAuthenticatedProfile(value); authenticationRecovery.authenticated(); try await provision()
        } catch let error as ServiceFailure where error.code == "profile_required" { closeGroups(); needsProfile = true }
        catch is CancellationError {}
        catch { notice = Self.explanation(error) }
        busy = false
        if ready { await synchronize() }
    }
    func createProfile(username: String, name: String) async {
        guard !busy, !closed else { return }; busy = true; notice = nil
        do {
            let value: AuthenticatedChatProfile = try await request("PUT", "/v1/me", body: body(["username": username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), "display_name": name]))
            try openAuthenticatedProfile(value); try await provision()
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
        if mediaTransport != nil, advertisedMediaDevice != core.device.id, mediaRegistration == nil {
            mediaRegistration = Task { [weak self] in
                guard let self else { return false }
                defer { self.mediaRegistration = nil }
                do {
                    let result: MediaCapability = try await self.request("PUT", "/v1/media/capability", body: self.body(["version": 1]), device: core.device)
                    guard self.core === core, result.version == 1 else { return false }
                    self.advertisedMediaDevice = core.device.id
                    return true
                } catch { return false }
            }
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
    func savedFriends(matching query: String) -> [ChatProfile] {
        guard !closed, !needsReauthentication, let account = profile?.id else { return [] }
        var search = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let handleOnly = search.hasPrefix("@")
        if handleOnly { search.removeFirst() }
        return contacts.values.filter { person in
            person.id != account && !blockedPeers.contains(person.id) &&
            (search.isEmpty || person.username.localizedStandardContains(search) ||
                (!handleOnly && person.display_name.localizedStandardContains(search)))
        }.sorted {
            let order = $0.display_name.localizedStandardCompare($1.display_name)
            return order == .orderedSame ? $0.username < $1.username : order == .orderedAscending
        }
    }

    func savedFriend(_ peer: UUID, account: UUID) -> ChatProfile? {
        guard !closed, !needsReauthentication, account == profile?.id, account != peer,
              !blockedPeers.contains(peer) else { return nil }
        return contacts[peer]
    }

    func find(_ input: String) async throws -> ChatProfile {
        guard ready, !needsReauthentication, let account = profile?.id, let core, let vault else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard let username = FriendLookupUsername.normalize(input) else { throw ServiceFailure(status: 0, code: "invalid_username") }
        let value: ChatProfile = try await request("GET", "/v1/people/" + username, device: core.device)
        guard profile?.id == account, self.vault === vault, !needsReauthentication else { throw CancellationError() }
        guard value.id != account else { throw ServiceFailure(status: 0, code: "own_username") }
        guard !blockedPeers.contains(value.id) else { throw ServiceFailure(status: 0, code: "contact_blocked") }
        try vault.transaction { try vault.put("contact", value.id.uuidString.lowercased(), JSONEncoder().encode(value)) }
        contacts[value.id] = value
        return value
    }
    func name(_ peer: UUID) -> String { contacts[peer]?.display_name ?? importedPeers[peer]?.displayName ?? String(localized: "New conversation") }
    /// Display metadata is not a Signal identity assertion. One bounded pass
    /// follows a completed inbox sync; offline and deleted peers retain history.
    private func resolveUnknownNames() async throws {
        guard let core, let vault else { return }
        let knownGroupPeers = groups?.groups.flatMap { $0.members.map(\.id) } ?? []
        let candidates = Array(Set(threads.map(\.peer) + knownGroupPeers)).filter {
            $0 != profile?.id && contacts[$0] == nil && !blockedPeers.contains($0) && (nameLookupAfter[$0] ?? .distantPast) <= Date()
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
        _ = try enqueue(text, peer: peer, attachments: [])
    }
    /// Commit authenticated manifests before the lifecycle outbox uploads or
    /// encrypts an envelope. A retry never prepares a new key or blob ID.
    func sendAttachments(_ text: String, peer: UUID, attachments: [AttachmentManifest]) throws -> UUID {
        guard !attachments.isEmpty, mediaTransport != nil else { throw ServiceFailure(status: 0, code: "media_not_enabled") }
        return try enqueue(text, peer: peer, attachments: attachments)
    }
    private struct MediaCapability: Decodable { let version: Int; let device_id: UUID? }
    func confirmMediaCapability(_ peer: UUID) async throws {
        guard canViewPhoto(peer: peer), let core, mediaTransport != nil else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        if let mediaRegistration { _ = await mediaRegistration.value }
        let value: MediaCapability = try await request("GET", "/v1/media/capability/" + peer.uuidString.lowercased(), device: core.device)
        guard canViewPhoto(peer: peer), self.core === core, value.version == 1, value.device_id != nil else {
            throw ServiceFailure(status: 0, code: "peer_media_unavailable")
        }
    }
    func avatar(_ peer: UUID) -> Data? {
        _ = revision
        return try? core?.journal.avatar(peer)?.jpeg
    }
    func setAvatar(_ jpeg: Data?) throws {
        try ensureOpen()
        guard let core else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        try core.journal.setOwnAvatar(jpeg, now: now)
        revision += 1
    }
    func openMedia(_ manifest: AttachmentManifest, peer: UUID) async throws -> URL {
        guard canViewPhoto(peer: peer), let account = profile?.id, let device = core?.device, let bytes = mediaTransport else { throw CancellationError() }
        let url = try await AttachmentRepository(account: account).open(manifest, thumbnail: false, bytes: bytes, device: device)
        guard !Task.isCancelled, canViewPhoto(peer: peer), profile?.id == account, core?.device.id == device.id else {
            try? FileManager.default.removeItem(at: url)
            throw CancellationError()
        }
        return url
    }
    func voiceDraft(peer: UUID) throws -> AttachmentManifest? {
        guard let vault else { return nil }
        return try vault.transaction {
            try vault.get("voice-compose", peer.uuidString.lowercased()).map { try JSONDecoder().decode(AttachmentManifest.self, from: $0) }
        }
    }
    func saveVoiceDraft(_ manifest: AttachmentManifest, peer: UUID) throws {
        try ensureOpen()
        guard let vault, manifest.kind == .voice else { throw MessageJournal.Failure.invalidMessage }
        try manifest.validate()
        let key = peer.uuidString.lowercased()
        try vault.transaction {
            if let existing = try vault.get("voice-compose", key) {
                guard try JSONDecoder().decode(AttachmentManifest.self, from: existing).id == manifest.id else { throw MessageJournal.Failure.conflict }
            }
            try vault.put("voice-compose", key, JSONEncoder().encode(manifest))
        }
    }
    func discardVoiceDraft(_ manifest: AttachmentManifest, peer: UUID) throws {
        try ensureOpen()
        guard let vault else { return }
        let key = peer.uuidString.lowercased()
        let removed = try vault.transaction {
            guard let data = try vault.get("voice-compose", key),
                  try JSONDecoder().decode(AttachmentManifest.self, from: data).id == manifest.id else { return false }
            try vault.remove("voice-compose", key); return true
        }
        if removed { try AttachmentRepository(account: vault.account).discardPrepared(manifest) }
    }
    func sendVoiceDraft(_ manifest: AttachmentManifest, peer: UUID) throws {
        _ = try enqueue(String(localized: "Voice message"), peer: peer, attachments: [manifest], consumeVoice: manifest.id)
    }
    func canViewPhoto(peer: UUID) -> Bool {
        ready && !closed && !needsReauthentication && !needsDeviceReplacement &&
            !blockedPeers.contains(peer) && !changedIdentities.contains(peer)
    }
    func viewPhoto(_ manifest: AttachmentManifest, peer: UUID) async throws -> CGImage {
        guard canViewPhoto(peer: peer), let account = profile?.id, let device = core?.device,
              let bytes = mediaTransport else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        let repository = try AttachmentRepository(account: account)
        let image = try await repository.viewPhoto(manifest, bytes: bytes, device: device)
        try Task.checkCancellation()
        guard canViewPhoto(peer: peer), profile?.id == account, core?.device.id == device.id else { throw CancellationError() }
        return image
    }
    private func enqueue(_ text: String, peer: UUID, attachments: [AttachmentManifest], consumeVoice: String? = nil) throws -> UUID {
        try ensureOpen()
        guard !historyBusy else { throw ServiceFailure(status: 0, code: "history_busy") }
        guard let core, ready else { throw ServiceFailure(status: 0, code: "device_not_ready") }
        guard !blockedPeers.contains(peer) else { throw ServiceFailure(status: 0, code: "contact_blocked") }
        guard !changedIdentities.contains(peer) else { throw ServiceFailure(status: 0, code: "peer_identity_review_required") }
        let id = UUID()
        try core.journal.saveDraft(id:id,recipient:peer,text:text,createdAt:now,now:now,consumeCompose:attachments.isEmpty,consumeVoice:consumeVoice,attachments:attachments)
        messageCommitted(.init(id:id.uuidString,text:text,peer:peer))
        try reload()
        return id
    }
    private func uploadAttachments(_ attachments: [AttachmentManifest], core: MessagingCore) async throws {
        if attachments.isEmpty { return }
        try ensureOpen()
        guard let bytes = mediaTransport, let profile else { throw ServiceFailure(status: 0, code: "media_not_enabled") }
        let repository = try AttachmentRepository(account: profile.id)
        for manifest in attachments {
            try await repository.ensureUploaded(manifest, api: api, bytes: bytes, device: core.device)
            try ensureOpen()
            guard self.core === core else { throw CancellationError() }
        }
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
                        if item.hasGroupContext {
                            // Incomplete/unknown metadata can never fall through to direct chat.
                            guard let groups else { continue }
                            do {
                                let incoming = try item.groupIncoming()
                                guard let vault else { throw CancellationError() }
                                let changedRoute = try vault.transaction { try vault.get("identity", item.sender_id.uuidString.lowercased() + "/1") != nil && vault.get("peer-device", item.sender_id.uuidString.lowercased()) != Data(item.sender_device_id.uuidString.lowercased().utf8) }
                                if changedRoute { try recordIdentityChange(item.sender_id) }
                                if incoming.group_kind == "control" { try groups.receivedControl(incoming) }
                                else { _ = try groups.received(incoming) }
                            } catch DurableSignalStore.Failure.identityChanged { try recordIdentityChange(item.sender_id); groups.notice = GroupsSession.explanation(GroupsFailure.identityChanged) }
                            catch { groups.notice = GroupsSession.explanation(error) }
                            continue
                        }
                        if blockedPeers.contains(item.sender_id) { continue }
                        do {
                            var inserted = false
                            let received = try core.receive(item.routed(account:profile!.id),now:now, onNew: { inserted = true })
                            let notificationArrival = try vault?.transaction {
                                let id = item.id.uuidString.lowercased()
                                guard try vault?.get("notification-sync", id) != nil else { return false }
                                try vault?.remove("notification-sync", id)
                                return true
                            } ?? false
                            if inserted || notificationArrival {
                                activity?.event(.typing(item.sender_id,false))
                                messageCommitted(.init(id:item.id.uuidString,text:received.text,peer:item.sender_id))
                                offerPreview(id: item.id, peer: item.sender_id, text: received.text)
                            }
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
                        try await uploadAttachments(draft.attachments ?? [], core: core)
                        if blockedPeers.contains(draft.recipient) || changedIdentities.contains(draft.recipient) { continue }
                        try await establish(draft.recipient)
                        if blockedPeers.contains(draft.recipient) || changedIdentities.contains(draft.recipient) { continue }
                        _ = try core.queue(id: draft.id, peer: draft.recipient, text: draft.text, createdAt: draft.createdAt, now: now, attachments: draft.attachments ?? [])
                    } catch is CancellationError { throw CancellationError() }
                    catch { notice = Self.explanation(error) }
                }
                for envelope in try core.journal.pending(now: now) {
                    if blockedPeers.contains(envelope.recipient) { continue }
                    do {
                        guard let saved = try core.journal.outgoing(envelope.id) else { continue }
                        if saved.state == "queued" { try await uploadAttachments(saved.attachments ?? [], core: core) }
                        if blockedPeers.contains(envelope.recipient) || changedIdentities.contains(envelope.recipient) { continue }
                        let routed = try core.queue(id: envelope.id, peer: envelope.recipient, text: saved.text, createdAt: envelope.createdAt, now: now, attachments: saved.attachments ?? [])
                        let status: Status = try await request("POST", "/v1/messages", body: routed.sendData(), device: core.device)
                        if status.state == "identity_changed" { try recordIdentityChange(envelope.recipient) }
                        let state = ["unavailable", "identity_changed"].contains(status.state) ? "failed" : status.state
                        try core.journal.applyStatus(envelope.id, state: state)
                        if !["accepted", "delivered", "read"].contains(saved.state), ["accepted", "delivered"].contains(state) {
                            activity?.outgoingAccepted(envelope.id, peer: envelope.recipient)
                        }
                    } catch let error as ServiceFailure {
                        if error.code == "recipient_identity_changed" { try recordIdentityChange(envelope.recipient) }
                        if let state = Self.terminalSendState(error) { try core.journal.applyStatus(envelope.id, state: state) }
                        else if error.code != "recipient_queue_full" { throw error }
                        notice = Self.explanation(error)
                    }
                }
                if let groups {
                    await groups.synchronize()
                    for id in try groups.pendingReceipts() {
                        do {
                            let status: Status = try await request("POST", "/v1/messages/\(id.uuidString.lowercased())/receipt", device: core.device)
                            if ["delivered", "expired", "unavailable", "identity_changed"].contains(status.state) { try groups.receiptAccepted(id) }
                        } catch let failure as ServiceFailure where failure.status == 404 && failure.code == "message_not_found" { try groups.receiptAccepted(id) }
                        catch let failure as ServiceFailure where failure.status == 429 { break }
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
                                      hint: { [weak self] in await self?.synchronize() }, activity: { [weak self] in self?.peerActivityEvent($0) }, authorizationEnded: { [weak self] in
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
        mediaRegistration?.cancel(); mediaRegistration = nil; advertisedMediaDevice = nil
        closeTranslationOwners()
        activity?.close(); activity = nil
        clearPreview(); previewsWhileOpen = false; previewsOutsideApp = false
        messageObservers.removeAll()
        events?.stop(); events = nil
        cancelHistoryWork?(); cancelHistoryWork = nil
        closed = true; ready = false; needsProfile = false; syncAgain = false
        groups?.close(); groups = nil
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
            if needsReauthentication { closeGroups(); PushNotifications.shared.clearOutsidePreviews(); events?.stop(); events = nil }
            if let failure = error as? ServiceFailure,
               ["device_revoked", "device_registration_conflict", "device_replacement_confirmation_required"].contains(failure.code) {
                authenticationRecovery.authenticated()
                PushNotifications.shared.clearOutsidePreviews()
                closeGroups(); ready = false; needsDeviceReplacement = true; hasPendingDeviceReplacement = false; needsRecentSignIn = false; events?.stop(); events = nil
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
            case "base_subscription_required": return String(localized: "Can’t connect. Messages are saved here.")
            case "device_replacement_confirmation_required": return String(localized: "This account is already active on another device. Moving your account needs a separate confirmation.")
            case "recent_sign_in_required", "sign_in_required", "device_revoked": return String(localized: "Please sign in again to reconnect your account. Your saved conversations are still on this device.")
            case "recipient_media_unsupported", "peer_media_unavailable": return String(localized: "Attachments aren’t available for this chat right now.")
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
        if failure.status == 409 && ["recipient_identity_changed", "message_id_conflict", "recipient_media_unsupported"].contains(failure.code) { return "failed" }
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

/// Account-scoped optional education, stored with the encrypted local account.
/// Call only after a genuinely new message has committed locally; queue retries,
/// imported history and peer receipts never claim this invitation.
extension ChatSession {
    func claimReplyNotificationInvitation() -> Bool {
        guard !closed,let vault,profile != nil else { return false }
        return (try? vault.transaction {
            let key = "reply-notification-invitation-v1"
            guard try vault.get("local",key) == nil else { return false }
            try vault.put("local",key,Data([1]))
            return true
        }) ?? false
    }
}

#if DEBUG
extension ChatSession {
    /// Explicitly authored inbox visuals in an owned simulator vault. Imported
    /// rows cannot send receipt events and are never network-delivery evidence.
    func seedOwnedInboxPresentation() throws {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
              ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa"),
              userID.hasPrefix("first-month-root-ui-"),let vault else { return }
        guard try vault.transaction({ try vault.get("local","inbox-presentation-seeded") }) == nil else { return }
        let rows:[(String,String,Int,Int)] = [
            ("Maya Johnson","See you at the café at ten ☕",1,0),
            ("Alexandria María Hernández-Wong","I've saved the directions. Shall we meet outside the station?",12,1),
            ("👩🏽‍🚀 Noor","The view is incredible. I'll tell you everything when I'm home.",0,3),
            ("朋子 佐藤","明日、駅で会いましょう。",2,12),
            ("لُمى حداد","سأصل بعد قليل. أراك قريبًا!",0,40),
            ("Élodie Martin","The recipe worked beautifully. Thank you!",0,400)]
        try vault.transaction {
            for (index,row) in rows.enumerated() {
                let peer = UUID(),contact = ChatProfile(id:peer,username:"inbox_qa_\(index)",display_name:row.0)
                try vault.put("contact",peer.uuidString.lowercased(),JSONEncoder().encode(contact)); contacts[peer] = contact
                for offset in 0..<max(1,row.2) {
                    let date = Calendar.current.date(byAdding:.day,value:-row.3,to:Date())!
                    let created = Int64(date.timeIntervalSince1970*1000)-Int64(max(1,row.2)-offset)*1000
                    let value = HistoryBackupMessage(id:UUID(),peer:peer,outgoing:false,createdAt:created,text:row.1)
                    try vault.put("imported",value.id.uuidString.lowercased(),JSONEncoder().encode(value))
                    try ConversationHistory.record(vault,kind:"imported",id:value.id,peer:peer,createdAt:created,unread:row.2 > 0)
                }
            }
            try vault.put("local","inbox-presentation-seeded",Data([1]))
        }
        try reload()
    }
}
#endif
