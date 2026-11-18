#if DEBUG
import SwiftUI
import Security
import CryptoKit
import Observation

/// Actual hosted reauthentication using only the already-owned staging account.
/// Never supplies a token, creates a device, rotates keys, or takes over another
/// device. Only safe metadata is retained; Release has no launch route.
struct ReauthenticationQualificationView: View {
    @Environment(AuthenticationManager.self) private var authentication
    @State private var subject: String?
    @State private var account: UUID?
    @State private var device: DeviceCredential?
    @State private var before: TimeInterval?
    @State private var status = "Checking owned staging session"
    @State private var started = false
    @State private var completing = false
    @State private var proof: [String: Any] = [:]
    private var receipt: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("reauth-native-r01.json")
    }
    var body: some View {
        VStack(spacing: 20) {
            Text("Owned staging sign-in check").font(.title2)
            Text(status).accessibilityIdentifier("reauth-qa-status")
            if subject != nil && !started {
                Button("Sign in again") {
                    started = true
                    authentication.signIn(expectedUser: subject)
                }
            }
            if let error = authentication.errorMessage { Text(error) }
        }.padding().task { await prepare() }
        .onChange(of: authentication.session?.accessToken) { _, _ in
            guard started, !completing else { return }
            completing = true; Task { await finish() }
        }
    }
    private func authTime(_ token: String) throws -> TimeInterval {
        // Decode solely for observation. ServiceClient independently proves that
        // the provider-issued token authenticates to the actual live service.
        let parts = token.split(separator: ".")
        guard parts.count == 3 else { throw ServiceFailure(status: 0, code: "invalid_observed_token") }
        var encoded = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
        guard let data = Data(base64Encoded: encoded),
              let claims = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let value = claims["auth_time"] as? Double else { throw ServiceFailure(status: 0, code: "missing_auth_time") }
        return value
    }
    private func save(_ stage: String) throws {
        proof["stage"] = stage; proof["recorded_at"] = Date().timeIntervalSince1970
        try JSONSerialization.data(withJSONObject: proof, options: [.sortedKeys, .prettyPrinted]).write(to: receipt, options: .atomic)
    }
    private func prepare() async {
        do {
            guard !FileManager.default.fileExists(atPath: receipt.path),
                  Bundle.main.object(forInfoDictionaryKey: "WorkOSClientID") as? String == "client_01M5S2CDSQ8F7FEX26G3CY9VS1",
                  let session = authentication.session else { throw ServiceFailure(status: 0, code: "owned_staging_session_required") }
            let api = try ServiceClient(authentication: authentication, userID: session.userID)
            let profile: ChatProfile = try await api.request("GET", "/v1/me")
            guard profile.username == "vqa_1107_ios01", let current = authentication.session,
                  current.userID == session.userID else { throw ServiceFailure(status: 0, code: "owned_staging_identity_required") }
            let vault = try MessageVault(account: profile.id)
            guard let saved = try vault.transaction({ try vault.get("local", "service-device") }) else { throw ServiceFailure(status: 0, code: "existing_device_required") }
            let credential = try JSONDecoder().decode(DeviceCredential.self, from: saved)
            guard try vault.transaction({ try vault.get("local", "registered-device") }) == Data(credential.id.uuidString.lowercased().utf8) else {
                throw ServiceFailure(status: 0, code: "registered_device_required")
            }
            let time = try authTime(current.accessToken)
            before = time; account = profile.id; device = credential; subject = current.userID
            proof = ["subject": current.userID, "account": profile.id.uuidString.lowercased(),
                "device": credential.id.uuidString.lowercased(), "before_auth_time": time,
                "native_hosted_pkce": true, "requested_max_age": 0, "replace_active": false,
                "token_injection": false, "credentials_logged": false]
            try save("prepared"); status = "Ready to sign in again"
        } catch { status = "Preparation failed: " + ((error as? ServiceFailure)?.code ?? String(describing: type(of: error))) }
    }
    private func finish() async {
        do {
            guard let before, let account, let device, let session = authentication.session,
                  session.userID == subject else { throw ServiceFailure(status: 0, code: "same_account_required") }
            let after = try authTime(session.accessToken), now = Date().timeIntervalSince1970
            guard after > before, (0..<600).contains(now-after) else { throw ServiceFailure(status: 0, code: "active_authentication_not_advanced") }
            let api = try ServiceClient(authentication: authentication, userID: session.userID)
            let profile: ChatProfile = try await api.request("GET", "/v1/me")
            guard profile.id == account, profile.username == "vqa_1107_ios01" else { throw ServiceFailure(status: 0, code: "profile_changed") }
            let vault = try MessageVault(account: account)
            guard let saved = try vault.transaction({ try vault.get("local", "service-device") }),
                  let currentDevice = try? JSONDecoder().decode(DeviceCredential.self, from: saved),
                  currentDevice.id == device.id, currentDevice.secret == device.secret else {
                throw ServiceFailure(status: 0, code: "device_changed")
            }
            struct Registered: Decodable { let id: UUID; let active: Bool }
            let body = try JSONSerialization.data(withJSONObject: ["device_id": device.id.uuidString.lowercased(), "secret": device.secret, "replace_active": false])
            let result: Registered = try await api.request("POST", "/v1/devices", body: body)
            guard result.active, result.id == device.id else { throw ServiceFailure(status: 0, code: "registration_changed") }
            proof["after_auth_time"] = after; proof["auth_time_advanced_seconds"] = after-before
            proof["same_account"] = true; proof["same_device"] = true; proof["live_idempotent_registration_accepted"] = true
            try save("complete"); status = "Fresh sign-in verified"
        } catch {
            proof["failure_code"] = (error as? ServiceFailure)?.code ?? "local_validation"
            try? save("failed"); status = "Reauthentication proof failed"
        }
    }
}

/// Explicit debug-only observation of owned live QA sessions. Contains no
/// message text, keys, tokens or audio; it never changes presentation state.
@MainActor enum LiveImmersionQualification {
    private static func digest(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    static func recordResult(_ result: ManualTranslationResult) {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") else { return }
        record(["event": "manual_result", "message_id": result.request.messageID, "generation": result.request.generation,
            "raw_sha256": digest(result.request.originalText), "raw_utf16": result.request.originalText.utf16.count,
            "selection_start": result.request.startUTF16, "selection_end": result.request.endUTF16,
            "source_context_sha256": digest(result.sourceContextText), "source_context_utf16": result.sourceContextText.utf16.count,
            "context_start": result.sourceContextStartUTF16, "context_end": result.sourceContextEndUTF16,
            "target_sha256": digest(result.targetText), "target_utf16": result.targetText.utf16.count,
            "source_language": result.sourceLanguage, "target_language": result.targetLanguage,
            "source_reading_sha256": result.sourceReading.map { digest($0.text) } ?? "",
            "target_reading_sha256": result.reading.map { digest($0.text) } ?? ""])
    }
    static func recordSelection(raw: String, displayed: String, selected: NSRange, mapped: ManualSourceRange) {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") else { return }
        record(["event": "manual_source_selection", "raw_sha256": digest(raw), "displayed_sha256": digest(displayed),
            "displayed_start": selected.location, "displayed_end": NSMaxRange(selected),
            "raw_start": mapped.startUTF16, "raw_end": mapped.endUTF16, "expanded": mapped.expanded])
    }
    static func recordSpeech(_ message: String, spans: [(text: String, language: String)]) {
        let arguments = ProcessInfo.processInfo.arguments
        let authoredWelcome = arguments.contains("-vipi-welcome") && Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
        guard (arguments.contains("-vipi-timeline-qa") || authoredWelcome), arguments.contains("-vipi-live-immersion-state") else { return }
        record(["event": "speech_input", "message_id": message, "inputs": spans.map { span in
            ["language": span.language, "utf8_bytes": span.text.utf8.count,
             "sha256": SHA256.hash(data: Data(span.text.utf8)).map { String(format: "%02x", $0) }.joined()] as [String: Any]
        }])
    }
    static func record(_ fields: [String: Any]) {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "-vipi-live-immersion-state"), index + 1 < arguments.count else { return }
        let revision = arguments[index + 1]
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else { return }
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("live-immersion-state-\(revision).jsonl")
        if let size = try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize, size > 524_288 { return }
        var row = fields; row["at"] = Date().timeIntervalSince1970
        guard var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else { return }
        data.append(10)
        if !FileManager.default.fileExists(atPath: file.path) { FileManager.default.createFile(atPath: file.path, contents: nil) }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }; try? handle.seekToEnd(); try? handle.write(contentsOf: data)
    }
}

/// Records real platform state only in the explicitly selected synthetic QA
/// conversation. Absent from Release, and never enabled for a signed-in chat.
@MainActor enum VoiceOverQualification {
    static func record(_ event: String, enabled: Bool, original: Bool) {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("-vipi-timeline-qa"),
              let index = arguments.firstIndex(of: "-vipi-voiceover-qa"), index + 1 < arguments.count else { return }
        let revision = arguments[index + 1]
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else { return }
        let row: [String: Any] = ["event": event, "at": Date().timeIntervalSince1970,
            "swiftui_voiceover": enabled, "uikit_voiceover": UIAccessibility.isVoiceOverRunning,
            "original_phase": original, "app_state": UIApplication.shared.applicationState.rawValue]
        guard var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else { return }
        data.append(10)
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("voiceover-state-\(revision).jsonl")
        if !FileManager.default.fileExists(atPath: file.path) { FileManager.default.createFile(atPath: file.path, contents: nil) }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        try? handle.seekToEnd(); try? handle.write(contentsOf: data)
    }
}

/// Isolated synthetic history for native UI automation. No service requests or
/// changes to the signed-in account. Entire harness is absent from Release.
private actor TimelineReadingGate {
    private var opened = false
    private var waiting: [CheckedContinuation<Void, Never>] = []
    func hold() async {
        guard !opened else { return }
        await withCheckedContinuation { waiting.append($0) }
    }
    func release() {
        opened = true; let pending = waiting; waiting.removeAll()
        for value in pending { value.resume() }
    }
}

struct TimelineQualificationView: View {
    @State private var chat: ChatSession?
    @State private var owner = UUID()
    @State private var peer = UUID()
    @State private var user = "timeline-ui-" + UUID().uuidString
    @State private var status = "Preparing synthetic conversation"
    @State private var finished = false
    @State private var readingGate = TimelineReadingGate()
    @State private var readingOwner: ConversationImmersion?
    @State private var readingReleased = false
    private var delayedReading: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-delayed-reading-qa") }
    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("-vipi-base-expiry-qa") {
            BaseExpiryQualificationView()
        } else { timeline }
    }
    private var timeline: some View {
        NavigationStack {
            Group {
                if let chat { FriendConversationView(chat: chat, peer: peer, immersion: readingOwner) }
                else { Text(status).accessibilityIdentifier("timeline-qa-status") }
            }.toolbar {
                if delayedReading && !readingReleased {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Release reading") {
                            readingReleased = true; Task { await readingGate.release() }
                        }.accessibilityIdentifier("timeline-qa-release-reading")
                    }
                }
                if !ProcessInfo.processInfo.arguments.contains("-vipi-timeline-audit") {
                    ToolbarItem(placement: .topBarLeading) {
                        if let chat { Button("Append QA") { try? chat.send("Appended while reading earlier messages.", peer: peer) }.accessibilityIdentifier("timeline-qa-append") }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        if !finished { Button("Finish QA", action: finish).accessibilityIdentifier("timeline-qa-finish") }
                    }
                }
            }
        }.task {
            guard chat == nil && !finished else { return }
            do {
                try removeAbandonedTimelineFixtures()
                if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-cleanup") {
                    finished = true; status = "Synthetic conversation removed"; return
                }
                let value = try ChatSession(api: TimelineTransport(owner: owner, peer: peer), userID: user)
                await value.start()
                guard value.ready else { throw ServiceFailure(status: 0, code: "fixture_not_ready") }
                _ = try await value.find("alex")
                if delayedReading {
                    let gate = readingGate
                    readingOwner = ConversationImmersion(modelStatus: { _ in .unsupported }, fullReadingProducer: { text, language in
                        await gate.hold()
                        return FullSentenceReadings.resolve(text, language: language)
                    })
                }
                let immersionQA = ProcessInfo.processInfo.arguments.contains("-vipi-immersion-chat-qa")
                let immersionMessages = ProcessInfo.processInfo.arguments.contains("-vipi-reverse-spanish-qa")
                    ? ["Estoy leyendo un libro ahora."]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-reverse-chinese-qa")
                    ? ["我正在读一本书。"]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-source-unit-routing-qa")
                    ? ["I need water. Did you finish the report?"]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-learning-language-qa")
                    ? ["Ninapenda muziki."]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-response-qa")
                    ? ["yes"]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-opener-qa")
                    ? ["Thank you very much."]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-request-qa")
                    ? ["I need a phone charger."]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-single-qa")
                    ? ["I like music."]
                    : ["I am reading a book now.", "I am drinking water now.", "Where is the phone charger?", "I like music."]
                let immersionHistory = ProcessInfo.processInfo.arguments.contains("-vipi-immersion-history-qa")
                for index in 1...(immersionQA && !immersionHistory ? immersionMessages.count : 70) {
                    let extra = index <= 20 ? String(repeating: " We can meet by the station and decide where to walk.", count: index % 5) : ""
                    try value.send(immersionQA ? immersionMessages[(index-1) % immersionMessages.count] : "History message \(index). We are making plans for tomorrow." + extra, peer: peer)
                    try await Task.sleep(for: .milliseconds(2))
                }
                chat = value
            } catch { status = "Fixture failed: \(error.localizedDescription)" }
        }.onDisappear { Task { await readingGate.release() } }
    }
    private func finish() {
        do {
            try chat?.close(); chat = nil
            let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages")
            let directory = root.appendingPathComponent(owner.uuidString.lowercased())
            if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
            try KeychainStore.deleteChecked(account: "profile-" + user)
            try KeychainStore.deleteChecked(account: "messages-" + owner.uuidString.lowercased())
            finished = true; status = "Synthetic conversation removed"
        } catch { status = "Fixture cleanup failed: \(error.localizedDescription)" }
    }
}

/// XCTest can terminate the app before Swift defer/onDisappear runs. Enumerate
/// attributes only, then read/remove solely our synthetic profile namespace.
private func removeAbandonedTimelineFixtures() throws {
    try removeAbandonedBaseExpiryFixtures()
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "co.fallsoft.vipi.private", kSecReturnAttributes as String: true,
        kSecMatchLimit as String: kSecMatchLimitAll]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return }
    guard status == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    for item in (result as? [[String: Any]]) ?? [] {
        guard let key = item[kSecAttrAccount as String] as? String, key.hasPrefix("profile-timeline-ui-"),
              UUID(uuidString: String(key.dropFirst("profile-timeline-ui-".count))) != nil,
              let data = try KeychainStore.read(account: key),
              let profile = try? JSONDecoder().decode(ChatProfile.self, from: data), profile.username == "timeline_qa" else { continue }
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages")
        let directory = root.appendingPathComponent(profile.id.uuidString.lowercased())
        if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
        try KeychainStore.deleteChecked(account: "messages-" + profile.id.uuidString.lowercased())
        try KeychainStore.deleteChecked(account: key)
    }
}

/// This is the production HomeView navigation owner, not a copied auth/root
/// router. Only the service/store boundary and isolated encrypted accounts are
/// supplied. Release builds contain neither this fixture nor its launch flag.
private struct BaseExpiryQualificationView: View {
    @State private var fixture: BaseExpiryFixture?
    @State private var status = "Preparing isolated expiry QA"
    var body: some View {
        Group {
            if let fixture {
                VStack(spacing: 0) {
                    HomeView(chat: fixture.chat, subscriptions: fixture.subscriptions, botOwner: fixture.owner)
                    // Read-only fixture evidence, outside the production view.
                    // No test button dispatches navigation, sends or purchases.
                    TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                        Text(fixture.proof).font(.caption2).lineLimit(1)
                            .accessibilityIdentifier("base-expiry-qa-proof")
                    }
                }
            } else { Text(status).accessibilityIdentifier("base-expiry-qa-status") }
        }.task {
            guard fixture == nil, Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { return }
            do {
                try removeAbandonedTimelineFixtures()
                let value = try BaseExpiryFixture()
                try await value.prepare()
                fixture = value
            } catch { status = "Synthetic expiry preparation failed" }
        }
    }
}

private struct BaseExpiryOwnership: Codable {
    let account: UUID
    let peer: UUID
    let user: String
    static var root: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("TimelineExpiryQualification", isDirectory: true)
    }
}

private func removeAbandonedBaseExpiryFixtures() throws {
    guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { return }
    let root = BaseExpiryOwnership.root
    guard FileManager.default.fileExists(atPath: root.path) else { return }
    for directory in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
        let record = try JSONDecoder().decode(BaseExpiryOwnership.self, from: Data(contentsOf: directory.appendingPathComponent("owner.json")))
        guard directory.lastPathComponent == record.account.uuidString.lowercased(), record.account != record.peer,
              record.user.hasPrefix("timeline-ui-"), UUID(uuidString: String(record.user.dropFirst("timeline-ui-".count))) != nil else {
            throw ServiceFailure(status: 0, code: "invalid_expiry_fixture_ownership")
        }
        if let data = try KeychainStore.read(account: "profile-" + record.user) {
            let profile = try JSONDecoder().decode(ChatProfile.self, from: data)
            guard profile.id == record.account, profile.username == "timeline_qa" else {
                throw ServiceFailure(status: 0, code: "expiry_fixture_profile_mismatch")
            }
        }
        let accountDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(record.account.uuidString.lowercased())
        if FileManager.default.fileExists(atPath: accountDirectory.path) { try FileManager.default.removeItem(at: accountDirectory) }
        try KeychainStore.deleteChecked(account: "profile-" + record.user)
        for id in [record.account, record.peer] { try KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased()) }
        try FileManager.default.removeItem(at: directory)
    }
}

@MainActor private final class BaseExpiryFixture {
    let account = UUID(), peer = UUID()
    let user = "timeline-ui-" + UUID().uuidString
    let owner = BotConversationOwner()
    let api: BaseExpiryTransport
    let chat: ChatSession
    let subscriptions: SubscriptionStore
    private let peerVault: MessageVault
    init() throws {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { throw ServiceFailure(status: 0, code: "qa_bundle_required") }
        let directory = BaseExpiryOwnership.root.appendingPathComponent(account.uuidString.lowercased(), isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONEncoder().encode(BaseExpiryOwnership(account: account, peer: peer, user: user))
            .write(to: directory.appendingPathComponent("owner.json"), options: .atomic)
        peerVault = try MessageVault(account: peer, directory: directory.appendingPathComponent("peer"))
        api = try BaseExpiryTransport(account: account, peer: peer, peerCore: MessagingCore(vault: peerVault))
        chat = try ChatSession(api: api, userID: user)
        subscriptions = SubscriptionStore(api: api, accountToken: account)
    }
    func prepare() async throws {
        await chat.start()
        guard chat.ready else { throw ServiceFailure(status: 0, code: "expiry_fixture_not_ready") }
        _ = try await chat.find("alex")
        try chat.send("Saved before the free period ended.", peer: peer)
        await chat.synchronize()
        let saved = try chat.messages(peer)
        guard saved.count == 1, saved.first?.state == "delivered", api.setupDecryptions == 1 else {
            throw ServiceFailure(status: 0, code: "expiry_fixture_setup_not_delivered")
        }
        await subscriptions.refreshEntitlements()
        guard subscriptions.baseActive, !subscriptions.botAvailable, !subscriptions.purchaseReady else {
            throw ServiceFailure(status: 0, code: "expiry_fixture_trial_required")
        }
        api.setupComplete = true
    }
    var proof: String {
        // Observe actual model revisions, then independently reopen encrypted
        // storage. Never insert a row, draft or navigation state for the test.
        _ = chat.revision
        do {
            let vault = try MessageVault(account: account)
            defer { try? vault.close() }
            let history = try ConversationHistory(vault: vault)
            let rows = try history.messages(peer: peer)
            let queued = rows.filter { $0.text != "Saved before the free period ended." }
            let data = try JSONSerialization.data(withJSONObject: [
                "setup_decryptions": api.setupDecryptions, "expired_posts": api.expiredPosts,
                "expired_ids": api.expiredIDs.sorted(), "rows": rows.count,
                "queued_count": queued.count, "queued_text": queued.first?.text ?? "",
                "queued_id": queued.first?.id.uuidString.lowercased() ?? "",
                "queued_state": queued.first?.state ?? "", "draft": try history.composeDraft(peer),
                "base_active": subscriptions.baseActive, "bot_active": subscriptions.botAvailable,
                "purchase_ready": subscriptions.purchaseReady, "unexpected_requests": api.unexpectedRequests
            ], options: [.sortedKeys])
            return String(decoding: data, as: UTF8.self)
        } catch { return "{\"durable_read_failed\":true}" }
    }
}

@MainActor @Observable private final class BaseExpiryTransport: ChatTransport {
    let account: UUID, peer: UUID
    let peerCore: MessagingCore
    let publication: KeyPublication
    var setupComplete = false
    var setupDecryptions = 0
    var expiredPosts = 0
    var expiredIDs = Set<String>()
    var unexpectedRequests = 0
    private var device: DeviceCredential?
    init(account: UUID, peer: UUID, peerCore: MessagingCore) throws {
        self.account = account; self.peer = peer; self.peerCore = peerCore
        publication = try peerCore.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000), count: 2)
        try peerCore.keys.published(revision: publication.revision)
    }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        let input: [String: Any]
        if let body { input = try JSONSerialization.jsonObject(with: body) as? [String: Any] ?? [:] }
        else { input = [:] }
        let value: [String: Any]
        switch (method, path) {
        case ("GET", "/v1/me"):
            value = ["id": account.uuidString, "username": "timeline_qa", "display_name": "Expiry QA"]
        case ("POST", "/v1/devices"):
            guard let id = input["device_id"] as? String, let uuid = UUID(uuidString: id), let secret = input["secret"] as? String else { throw ServiceFailure(status: 0, code: "invalid_qa_device") }
            self.device = DeviceCredential(id: uuid, secret: secret); value = ["id": id, "active": true]
        case ("GET", "/v1/keys"): value = ["revision": 1, "remaining": 20]
        case ("GET", "/v1/messages/pending"): value = ["messages": [], "next_cursor": NSNull()]
        case ("GET", "/v1/people/alex"), ("GET", "/v1/people/by-id/" + peer.uuidString.lowercased()):
            value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
        case ("GET", "/v1/blocks/" + peer.uuidString.lowercased()): value = ["blocked": false]
        case ("POST", "/v1/people/" + peer.uuidString.lowercased() + "/keys"):
            guard let raw = input["request_id"] as? String, let request = UUID(uuidString: raw) else { throw ServiceFailure(status: 0, code: "invalid_qa_claim") }
            let claim = ClaimedKeys(request_id: request, user_id: peer, device_id: peerCore.device.id, signal_device_id: 1,
                registration_id: publication.registration_id, identity_key: publication.identity_key, signed: publication.signed, one_time: publication.one_time[0])
            return try JSONDecoder().decode(type, from: JSONEncoder().encode(claim))
        case ("POST", "/v1/messages"):
            guard device?.id == self.device?.id, let body, let id = input["id"] as? String else { throw ServiceFailure(status: 0, code: "invalid_qa_message") }
            if setupComplete {
                expiredPosts += 1; expiredIDs.insert(id)
                throw ServiceFailure(status: 402, code: "base_subscription_required")
            }
            var routed = try JSONSerialization.jsonObject(with: body) as! [String: Any]
            routed["sender_id"] = account.uuidString; routed["sender_device_id"] = device!.id.uuidString
            let received = try JSONDecoder().decode(RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: routed))
            let message = try peerCore.receive(received.routed(account: peer), now: Int64(Date().timeIntervalSince1970 * 1000))
            guard message.text == "Saved before the free period ended." else { throw ServiceFailure(status: 0, code: "unexpected_qa_plaintext") }
            setupDecryptions += 1; value = ["state": "delivered"]
        case ("GET", "/v1/entitlements"):
            // The controlled server crosses its exact exclusive trial end on
            // the user's first POST. No device clock or paid grant is changed.
            let ended = expiredPosts > 0
            let end = Date(timeIntervalSince1970: 1_800_000_000)
            let format = ISO8601DateFormatter()
            var base: [String: Any] = ["active": !ended,
                "cardless_trial": ["started_at": format.string(from: end.addingTimeInterval(-30 * 86400)),
                    "ends_at": format.string(from: end), "active": !ended]]
            if ended { base["expires_at"] = NSNull(); base["access_source"] = NSNull() }
            else { base["expires_at"] = format.string(from: end); base["access_source"] = "cardless_trial" }
            value = ["server_time": format.string(from: ended ? end : end.addingTimeInterval(-3600)),
                "base": base,
                "bot_mini": ["active": false, "available": false], "billing_account_id": "synthetic-expiry-only",
                "app_account_token": account.uuidString, "purchases_ready": ["apple": false, "google": false]]
        case ("GET", "/v1/bot/allowance"): throw ServiceFailure(status: 503, code: "bot_not_available")
        default:
            unexpectedRequests += 1
            throw ServiceFailure(status: 0, code: "unexpected_expiry_qa_request")
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
}

/// Dependency/bootstrap fixture only. VipiApp, ConnectedChatRoot, Settings,
/// AccountDeletionProgressView and AccountDeletion perform the entire flow.
/// No fixture method begins, accepts, resumes or finishes a deletion manager.
@MainActor final class ConnectedDeletionUIQualification: ChatTransport, DeletionTransport {
    private(set) static var current: ConnectedDeletionUIQualification?
    private struct Ledger: Codable {
        let account: UUID, other: UUID, user: String, otherUser: String
        var starts = 0, chats = 0, stores = 0, seededOwners = 0
        var botPosts = 0, lateResults = 0, submissions = 0, statusReads = 0, confirmations = 0
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
    private var botOwners: [BotConversationOwner] = []
    private var botSessions: [BotSession] = []
    private var botVaults: [MessageVault] = []
    private var heldBot: CheckedContinuation<Void, Never>?
    private static let ownMarker = Data("Owned encrypted deletion marker".utf8)
    private static let otherMarker = Data("Unrelated encrypted marker must remain".utf8)
    private static let lateReply = "Late response must never resurrect deleted data."

    static func prepareIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-qa") else { return }
        precondition(Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa", "Owned root qualification only")
        do {
            if ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-cleanup") { try cleanup(); return }
            if current == nil { current = try ConnectedDeletionUIQualification() }
        } catch {
            // Never fall back to a live service after a partial QA bootstrap.
            preconditionFailure("Reconcile the owned synthetic deletion fixture before qualification")
        }
    }
    private static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func save() throws { try JSONEncoder().encode(ledger).write(to: Self.ledgerURL, options: .atomic) }
    private static func validate(_ value: Ledger) throws {
        guard value.account != value.other, value.user.hasPrefix("deletion-root-ui-"),
              UUID(uuidString: String(value.user.dropFirst("deletion-root-ui-".count))) != nil,
              value.otherUser == "deletion-root-other-" + value.other.uuidString.lowercased() else {
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
            let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .fileSizeKey, .isSymbolicLinkKey])
            guard values.isSymbolicLink != true else { throw ServiceFailure(status: 0, code: "preserve_existing_qa_audio") }
            if values.isDirectory == true {
                for child in try FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: nil) { try inspect(child) }
            } else {
                guard values.isRegularFile == true, values.fileSize == 0 else { throw ServiceFailure(status: 0, code: "preserve_existing_qa_audio") }
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
                  value.refreshToken == "synthetic-root-refresh-never-transmitted" else {
                throw ServiceFailure(status: 0, code: "preserve_unrelated_root_session")
            }
        }
        for key in ["pending-sign-in", "pending-identity-link"] {
            guard try KeychainStore.read(account: key) == nil else { throw ServiceFailure(status: 0, code: "preserve_unrelated_root_authentication") }
        }
        let pending = try KeychainDeletionStore().load()
        if let pending {
            guard pending.account == ledger.account, pending.userID == ledger.user else { throw ServiceFailure(status: 0, code: "preserve_unrelated_root_deletion") }
            if let fingerprint = ledger.secretHash {
                guard Self.hash(Data(pending.secret.utf8)) == fingerprint else { throw ServiceFailure(status: 0, code: "preserve_unrelated_root_capability") }
            }
            if pending.phase != .prepared || pending.localErased {
                guard ledger.accepted, ledger.secretHash != nil else { throw ServiceFailure(status: 0, code: "unowned_confirmed_root_receipt") }
            }
        }
        if let expected {
            guard let pending, pending.account == expected.account, pending.userID == expected.userID,
                  pending.secret == expected.secret, pending.phase == expected.phase else {
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
                guard try KeychainStore.read(account: key) == nil else { throw ServiceFailure(status: 0, code: "empty_owned_qa_identity_required") }
            }
            // Production erasure removes the private audio parent. Do not use
            // this fixture if it would erase preexisting QA recordings.
            try Self.requireDisposableAudio()
            let account = UUID(), other = UUID()
            ledger = Ledger(account: account, other: other, user: "deletion-root-ui-" + UUID().uuidString,
                otherUser: "deletion-root-other-" + other.uuidString.lowercased())
            try FileManager.default.createDirectory(at: Self.directory, withIntermediateDirectories: true)
            try save() // Record ownership before creating any private records.
            try seed()
        }
        try Self.validateSavedAuthority(ledger)
        try Self.requireDisposableAudio()
        ledger.starts += 1; try save()
    }
    private func seed() throws {
        for (id, marker) in [(ledger.account, Self.ownMarker), (ledger.other, Self.otherMarker)] {
            let vault = try MessageVault(account: id)
            defer { try? vault.close() }
            try vault.transaction { try vault.put("root-deletion-qa", "marker", marker) }
            if id == ledger.account {
                let core = try MessagingCore(vault: vault)
                try vault.transaction { try vault.put("local", "registered-device", Data(core.device.id.uuidString.lowercased().utf8)) }
            }
        }
        let profile = ChatProfile(id: ledger.account, username: "deletion_qa", display_name: "Deletion QA")
        let other = ChatProfile(id: ledger.other, username: "preserved_qa", display_name: "Preserved QA")
        try KeychainStore.save(JSONEncoder().encode(profile), account: "profile-" + ledger.user)
        let otherData = try JSONEncoder().encode(other)
        try KeychainStore.save(otherData, account: "profile-" + ledger.otherUser)
        ledger.otherProfileHash = Self.hash(otherData)
        guard let key = try KeychainStore.read(account: "messages-" + ledger.other.uuidString.lowercased()) else { throw MessageVault.Failure.missingKey }
        ledger.otherKeyHash = Self.hash(key)
        try KeychainStore.save(JSONEncoder().encode(VipiSession(userID: ledger.user, accessToken: "synthetic-root-access-never-transmitted",
            refreshToken: "synthetic-root-refresh-never-transmitted", authority: .fallsoftVipiProduction)), account: "session")
        try save()
    }
    var connection: ConnectedChatRoot.Qualification {
        .init(makeChat: { [self] auth, user in
            guard user == ledger.user, auth.session?.userID == ledger.user else { throw ServiceFailure(status: 0, code: "root_fixture_identity_mismatch") }
            ledger.chats += 1; try save()
            let chat = try ChatSession(api: self, userID: user); chats.append(chat); return chat
        }, makeSubscriptions: { [self] auth, user, account in
            guard user == ledger.user, auth.session?.userID == user, account == ledger.account else { throw ServiceFailure(status: 0, code: "root_fixture_account_mismatch") }
            ledger.stores += 1; try save()
            return SubscriptionStore(api: self, accountToken: account)
        }, makeBotOwner: { [self] account in
            let owner = BotConversationOwner()
            guard let account else { return owner }
            do {
                guard account == ledger.account else { throw ServiceFailure(status: 0, code: "root_fixture_bot_mismatch") }
                let vault = try MessageVault(account: account)
                let session = try BotSession(api: self, vault: vault)
                _ = try owner.session(for: account) { session }
                botOwners.append(owner); botSessions.append(session); botVaults.append(vault)
                ledger.seededOwners += 1; try save()
            } catch { ledger.failure = "Root Bot preparation failed"; try? save() }
            return owner
        })
    }
    func makeDeletion(_ authentication: AuthenticationManager) throws -> AccountDeletion {
        try Self.validateSavedAuthority(ledger)
        try Self.requireDisposableAudio()
        self.authentication = authentication
        let value = AccountDeletion(store: KeychainDeletionStore(), service: self, erase: { [self] record in
            // Recheck immediately before the unchanged real eraser, rather
            // than relying on bootstrap or a later service.status binding.
            try Self.validateSavedAuthority(ledger, expected: record)
            try Self.requireDisposableAudio()
            try AccountDeletion.eraseLocal(record)
        }) { user in
            try authentication.eraseLocalSession(for: user)
        }
        manager = value; return value
    }
    private func bind(_ record: DeletionRecord) throws {
        guard record.account == ledger.account, record.userID == ledger.user else { throw ServiceFailure(status: 0, code: "root_fixture_receipt_mismatch") }
        let fingerprint = Self.hash(Data(record.secret.utf8))
        if let previous = ledger.secretHash {
            guard previous == fingerprint else { throw ServiceFailure(status: 0, code: "root_fixture_capability_changed") }
        } else { ledger.secretHash = fingerprint }
    }
    func submit(_ record: DeletionRecord) async throws -> DeletionReply {
        try bind(record)
        ledger.submissions += 1
        guard !ledger.accepted, ledger.submissions == 1 else { ledger.unexpected += 1; try save(); throw ServiceFailure(status: 0, code: "root_fixture_repeated_delete") }
        ledger.accepted = true; try save()
        // The actual owner has already closed. Deliberately return a late
        // response anyway; merely cancelling the transport would not test the
        // production BotSession closed-result guard.
        let waiting = heldBot; heldBot = nil; waiting?.resume()
        throw URLError(.networkConnectionLost)
    }
    func status(_ record: DeletionRecord) async throws -> DeletionReply {
        try bind(record); ledger.statusReads += 1; try save()
        guard ledger.accepted else { throw ServiceFailure(status: 404, code: "deletion_receipt_unavailable") }
        guard ledger.starts > 1 else { throw URLError(.networkConnectionLost) }
        ledger.confirmations += 1; try save()
        return DeletionReply(account_id: ledger.account, status: ledger.confirmations == 1 ? "deletion_requested" : "deleted")
    }
    private var allowance: [String: Any] {
        ["available": true, "service_ready": true, "remaining_replies": 150, "monthly_replies": 150,
         "resets_at": "2099-01-01T00:00:00Z", "max_context_bytes": 8192]
    }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        let value: [String: Any]
        switch (method, path) {
        case ("GET", "/v1/me"):
            guard !ledger.accepted else { throw ServiceFailure(status: 410, code: "account_deleted") }
            value = ["id": ledger.account.uuidString, "username": "deletion_qa", "display_name": "Deletion QA"]
        case ("GET", "/v1/keys"): value = ["revision": 1, "remaining": 20]
        case ("GET", "/v1/messages/pending"): value = ["messages": [], "next_cursor": NSNull()]
        case ("GET", "/v1/entitlements"):
            let plan: [String: Any] = ["active": true, "access_source": "review_complimentary", "review_access": true]
            var bot = plan; bot["available"] = true
            value = ["server_time": ISO8601DateFormatter().string(from: Date()), "base": plan, "bot_mini": bot,
                "billing_account_id": "synthetic-deletion-root-only", "app_account_token": ledger.account.uuidString,
                "purchases_ready": ["apple": false, "google": false]]
        case ("GET", "/v1/bot/allowance"): value = allowance
        case ("POST", "/v1/bot/messages"):
            guard let body, let payload = try JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let requestID = payload["request_id"] as? String, UUID(uuidString: requestID) != nil,
                  let context = payload["messages"] as? [[String: String]], context.count == 1,
                  context.first?["content"] == "Hold this reply while I review deletion.",
                  payload["consent_version"] as? String == "deepseek-v1", device != nil, ledger.botPosts == 0, !ledger.accepted else {
                ledger.unexpected += 1; try save(); throw ServiceFailure(status: 0, code: "root_fixture_bot_request_mismatch")
            }
            let vault = try MessageVault(account: ledger.account)
            let registered: DeviceCredential
            do { registered = try DeviceCredential.registered(vault: vault); try vault.close() }
            catch { try? vault.close(); throw error }
            guard device?.id == registered.id, device?.secret == registered.secret else {
                ledger.unexpected += 1; try save(); throw ServiceFailure(status: 0, code: "root_fixture_bot_device_mismatch")
            }
            ledger.botPosts += 1; try save()
            await withCheckedContinuation { heldBot = $0 }
            ledger.lateResults += 1; try save()
            value = ["request_id": requestID, "reply": Self.lateReply, "allowance": allowance]
        default:
            ledger.unexpected += 1; try save()
            throw ServiceFailure(status: 0, code: "unexpected_root_fixture_request")
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
    private static func accountDirectory(_ account: UUID) -> URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(account.uuidString.lowercased())
    }
    private func marker(_ account: UUID, expected: Data) throws -> (Bool, Int, [String]) {
        // Do not instantiate a vault after erasure: doing so would create the
        // very key/directory resurrection this regression must detect.
        guard FileManager.default.fileExists(atPath: Self.accountDirectory(account).path),
              try KeychainStore.read(account: "messages-" + account.uuidString.lowercased()) != nil else { return (false, 0, []) }
        let vault = try MessageVault(account: account); defer { try? vault.close() }
        return try vault.transaction {
            let marker = try vault.get("root-deletion-qa", "marker") == expected
            let ids = try vault.ids("bot-message")
            let late = try ids.filter { key in
                guard let data = try vault.get("bot-message", key) else { return false }
                return try JSONDecoder().decode(BotMessage.self, from: data).text == Self.lateReply
            }.count
            return (marker, late, ids.sorted())
        }
    }
    var proof: String {
        do {
            let own = try marker(ledger.account, expected: Self.ownMarker)
            let other = try marker(ledger.other, expected: Self.otherMarker)
            let pending = try KeychainDeletionStore().load()
            let otherKey = try KeychainStore.read(account: "messages-" + ledger.other.uuidString.lowercased())
            let otherProfile = try KeychainStore.read(account: "profile-" + ledger.otherUser)
            let closed = botOwners.allSatisfy { owner in
                do { _ = try owner.session(for: ledger.account) { nil }; return false }
                catch { return true }
            }
            let value: [String: Any] = [
                "starts": ledger.starts, "chat_creations": ledger.chats, "store_creations": ledger.stores,
                "seeded_bot_owners": ledger.seededOwners, "bot_posts": ledger.botPosts, "bot_pending": heldBot != nil,
                "late_results": ledger.lateResults, "busy_bot_sessions": botSessions.filter(\.busy).count,
                "late_memory_replies": botSessions.flatMap(\.messages).filter { $0.text == Self.lateReply }.count,
                "all_bot_owners_closed": closed, "open_chat_owners": chats.filter { $0.ready || $0.profile != nil }.count,
                "submissions": ledger.submissions, "status_reads": ledger.statusReads, "confirmations": ledger.confirmations,
                "server_accepted": ledger.accepted, "unexpected_requests": ledger.unexpected, "fixture_failure": ledger.failure != nil,
                "session_key_present": try KeychainStore.read(account: "session") != nil, "auth_signed_out": authentication?.session == nil,
                "receipt_present": pending != nil, "phase": pending?.phase.rawValue ?? "none", "local_erased": pending?.localErased ?? false,
                "receipt_matches_owner": pending.map { $0.account == ledger.account && $0.userID == ledger.user } ?? false,
                "own_marker": own.0, "late_disk_replies": own.1, "bot_row_ids": own.2,
                "own_directory": FileManager.default.fileExists(atPath: Self.accountDirectory(ledger.account).path),
                "own_key": try KeychainStore.read(account: "messages-" + ledger.account.uuidString.lowercased()) != nil,
                "own_profile": try KeychainStore.read(account: "profile-" + ledger.user) != nil,
                "other_marker": other.0, "other_key_unchanged": otherKey.map { Self.hash($0) } == ledger.otherKeyHash,
                "other_profile_unchanged": otherProfile.map { Self.hash($0) } == ledger.otherProfileHash]
            return String(decoding: try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), as: UTF8.self)
        } catch { return "{\"proof_read_failed\":true}" }
    }
    private static func cleanup() throws {
        guard FileManager.default.fileExists(atPath: ledgerURL.path) else { return }
        let record = try JSONDecoder().decode(Ledger.self, from: Data(contentsOf: ledgerURL)); try validate(record)
        try validateSavedAuthority(record)
        if let pending = try KeychainDeletionStore().load() {
            guard pending.account == record.account, pending.userID == record.user else { throw ServiceFailure(status: 0, code: "preserve_unrelated_deletion_record") }
            try KeychainDeletionStore().remove()
        }
        if let data = try KeychainStore.read(account: "session") {
            guard try JSONDecoder().decode(VipiSession.self, from: data).userID == record.user else { throw ServiceFailure(status: 0, code: "preserve_unrelated_session") }
            try KeychainStore.deleteChecked(account: "session")
        }
        for id in [record.account, record.other] {
            let directory = accountDirectory(id)
            if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
            try KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased())
        }
        for user in [record.user, record.otherUser] { try KeychainStore.deleteChecked(account: "profile-" + user) }
        try FileManager.default.removeItem(at: directory)
    }
}

private final class TimelineTransport: ChatTransport {
    let owner: UUID, peer: UUID
    init(owner: UUID, peer: UUID) { self.owner = owner; self.peer = peer }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        var value: [String: Any]
        switch path {
        case "/v1/me": value = ["id": owner.uuidString, "username": "timeline_qa", "display_name": "Timeline QA"]
        case "/v1/people/alex": value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
        case "/v1/devices":
            guard let body, let input = try JSONSerialization.jsonObject(with: body) as? [String: Any], let id = input["device_id"] else { throw ServiceFailure(status: 0, code: "invalid_fixture") }
            value = ["id": id, "active": true]
        case "/v1/keys": value = ["revision": 1, "remaining": 20]
        case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
        default:
            guard path.hasPrefix("/v1/blocks/") else { throw ServiceFailure(status: 0, code: "offline") }
            value = ["blocked": false]
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
}
#endif
