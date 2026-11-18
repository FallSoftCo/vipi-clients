#if DEBUG
import SwiftUI
import Observation

/// Hosts the actual conversation with account-isolated, encrypted local state.
/// Neither this route nor its transport can reach authentication or a service.
struct BotUIQualificationView: View {
    @State private var fixture: BotUIFixture?
    @State private var status = "Preparing isolated Bot QA"
    @State private var finished = false
    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                if let fixture {
                    Text("posts=\(fixture.api.posts);completed=\(fixture.api.completed);pending=\(fixture.api.pending);sessions=\(fixture.opened);hold=\(fixture.api.holdNext);durableComplete=\(fixture.durableCompleted)")
                        .accessibilityIdentifier("bot-qa-proof")
                    NavigationLink("Open vBot") {
                        BotConversationView(account: fixture.account, subscriptions: fixture.subscriptions, owner: fixture.owner,
                            sessionFactory: { _, account in try fixture.makeSession(account: account) })
                    }
                    Button("Hold next reply") { fixture.api.holdNext = true }
                    Button("Finish Bot QA") {
                        do { try fixture.finish(); self.fixture = nil; finished = true; status = "Synthetic Bot conversation removed" }
                        catch { status = "Synthetic Bot cleanup failed" }
                    }.disabled(fixture.api.pending || fixture.sessions.contains { $0.busy })
                } else { Text(status).accessibilityIdentifier("bot-qa-status") }
            }.padding().navigationTitle("Bot QA")
        }.task {
            guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa", fixture == nil, !finished else { return }
            do {
                let value = try BotUIFixture(); fixture = value
                await value.subscriptions.refreshEntitlements()
            } catch { status = "Synthetic Bot preparation failed" }
        }
    }
}

@MainActor @Observable private final class BotUIFixture {
    let account = UUID()
    let owner = BotConversationOwner()
    let directory: URL
    let api: BotUITransport
    let subscriptions: SubscriptionStore
    var opened = 0
    var sessions: [BotSession] = []
    private var vaults: [MessageVault] = []
    var durableCompleted: Int {
        guard let vault = vaults.first else { return 0 }
        return (try? vault.transaction {
            try vault.ids("bot-message").filter { id in
                guard let data = try vault.get("bot-message", id) else { return false }
                return try JSONDecoder().decode(BotMessage.self, from: data).state == "complete"
            }.count
        }) ?? -1
    }
    init() throws {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { throw ServiceFailure(status: 0, code: "qa_bundle_required") }
        directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("BotUIQualification", isDirectory: true).appendingPathComponent(UUID().uuidString, isDirectory: true)
        api = BotUITransport(account: account)
        subscriptions = SubscriptionStore(api: api, accountToken: account)
        let vault = try MessageVault(account: account, directory: directory)
        try vault.transaction {
            try vault.put("local", "service-device", JSONEncoder().encode(api.device))
            try vault.put("local", "registered-device", Data(api.device.id.uuidString.lowercased().utf8))
        }
        vaults.append(vault)
        try JSONSerialization.data(withJSONObject: ["account_id": account.uuidString.lowercased(), "synthetic": true])
            .write(to: directory.appendingPathComponent("owner.json"), options: .atomic)
    }
    func makeSession(account: UUID) throws -> BotSession {
        guard account == self.account else { throw ServiceFailure(status: 0, code: "qa_account_mismatch") }
        let vault = try MessageVault(account: account, directory: directory)
        let session = try BotSession(api: api, vault: vault)
        vaults.append(vault); sessions.append(session); opened += 1
        return session
    }
    func finish() throws {
        guard !api.pending && !sessions.contains(where: { $0.busy }) else { throw ServiceFailure(status: 0, code: "qa_request_pending") }
        try owner.close(); subscriptions.close()
        try vaults.forEach { try $0.close() }
        try FileManager.default.removeItem(at: directory)
        try KeychainStore.deleteChecked(account: "messages-" + account.uuidString.lowercased())
    }
}

@MainActor @Observable private final class BotUITransport: ChatTransport {
    let account: UUID
    let device = DeviceCredential(id: UUID(), secret: String(repeating: "x", count: 43))
    var posts = 0
    var completed = 0
    var remaining = 150
    var holdNext = false
    var pending = false
    @ObservationIgnored private var continuation: CheckedContinuation<Void, Never>?
    private var requestIDs = Set<UUID>()
    init(account: UUID) { self.account = account }
    private var allowance: [String: Any] {
        ["available": true, "service_ready": true, "remaining_replies": remaining, "monthly_replies": 150,
         "resets_at": "2099-01-01T00:00:00Z", "max_context_bytes": 8192]
    }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        let value: [String: Any]
        if method == "GET", path == "/v1/entitlements" {
            value = ["server_time": "2026-11-17T00:00:00Z", "base": ["active": true, "expires_at": "2099-01-01T00:00:00Z"],
                "bot_mini": ["active": true, "available": true, "expires_at": "2099-01-01T00:00:00Z"],
                "billing_account_id": "synthetic-ui-only", "app_account_token": account.uuidString,
                "purchases_ready": ["apple": false, "google": false]]
        } else if method == "GET", path == "/v1/bot/allowance" {
            // The actual view refreshes when it appears again. The original
            // POST remains held until that ordinary navigation return.
            if pending {
                Task {
                    try? await Task.sleep(for: .seconds(2))
                    let held = continuation; continuation = nil; held?.resume()
                }
            }
            value = allowance
        } else if method == "POST", path == "/v1/bot/messages", let body,
                  device?.id == self.device.id, device?.secret == self.device.secret,
                  let payload = try JSONSerialization.jsonObject(with: body) as? [String: Any],
                  payload["consent_version"] as? String == "deepseek-v1",
                  let rawID = payload["request_id"] as? String, let id = UUID(uuidString: rawID), requestIDs.insert(id).inserted {
            posts += 1
            if holdNext {
                holdNext = false; pending = true
                await withCheckedContinuation { continuation = $0 }
                pending = false
            }
            remaining -= 1; completed += 1
            value = ["request_id": rawID, "reply": posts == 1 ? "Confirmed QA reply." : "Pending QA reply completed.", "allowance": allowance]
        } else { throw ServiceFailure(status: 0, code: "unexpected_qa_request") }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
}
#endif
