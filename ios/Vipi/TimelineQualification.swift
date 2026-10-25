#if DEBUG
import SwiftUI
import Security

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
                for index in 1...70 {
                    let extra = index <= 20 ? String(repeating: " We can meet by the station and decide where to walk.", count: index % 5) : ""
                    try value.send("History message \(index). We are making plans for tomorrow." + extra, peer: peer)
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
