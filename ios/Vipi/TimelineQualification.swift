#if DEBUG
import SwiftUI
import Security

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
                let immersionMessages = ProcessInfo.processInfo.arguments.contains("-vipi-source-unit-routing-qa")
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
