#if DEBUG
import SwiftUI
import Security

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
struct TimelineQualificationView: View {
    @State private var chat: ChatSession?
    @State private var owner = UUID()
    @State private var peer = UUID()
    @State private var user = "timeline-ui-" + UUID().uuidString
    @State private var status = "Preparing synthetic conversation"
    @State private var finished = false
    var body: some View {
        NavigationStack {
            Group {
                if let chat { FriendConversationView(chat: chat, peer: peer) }
                else { Text(status).accessibilityIdentifier("timeline-qa-status") }
            }.toolbar {
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
                let immersionQA = ProcessInfo.processInfo.arguments.contains("-vipi-immersion-chat-qa")
                let immersionMessages = ProcessInfo.processInfo.arguments.contains("-vipi-learning-language-qa")
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
        }
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
