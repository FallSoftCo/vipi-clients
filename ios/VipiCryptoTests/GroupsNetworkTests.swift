import Foundation
import XCTest
@testable import Vipi

/// Opt-in synthetic local accounts, normal API and production native Signal.
/// Alice/Bob are independent Android vaults; this process owns only Carol.
/// This is deliberately separate from owner auth and group UI qualification.
@MainActor final class GroupsNetworkTests: XCTestCase {
    struct Credential: Decodable { let username: String; let access_token: String? }
    struct Configuration: Decodable {
        let run: String; let endpoint: URL; let isolated_signed_authentication: Bool
        let alice: Credential; let bob: Credential; let carol: Credential
    }
    struct State: Codable { let run: String; let account: UUID; var group: UUID? }
    struct Profile: Decodable { let id: UUID; let username: String }
    struct Inventory: Decodable { let revision: UInt32; let remaining: Int }
    struct DeviceResult: Decodable { let id: UUID; let active: Bool }
    struct Status: Decodable { let state: String }
    struct Packet: Decodable {
        let direct: RoutedMessage.Received?
        let group: GroupIncoming?
        private enum Keys: String, CodingKey { case group_id, group_epoch, group_message_id, group_kind }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            if c.allKeys.isEmpty { direct = try RoutedMessage.Received(from: decoder); group = nil }
            else {
                guard c.allKeys.count == 4 else { throw GroupsFailure.invalidResponse }
                group = try GroupIncoming(from: decoder); direct = nil
            }
        }
    }
    struct Inbox: Decodable { let messages: [Packet] }
    private func file(_ name: String) -> URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("groups-" + name + ".json") }
    private func configuration() throws -> Configuration {
        guard FileManager.default.fileExists(atPath: file("config").path) else { throw XCTSkip("Explicit isolated three-member local fixture required") }
        let c = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: file("config")))
        XCTAssertTrue(c.run.hasPrefix("groupsqa_")); XCTAssertTrue(c.isolated_signed_authentication)
        XCTAssertEqual(c.endpoint.scheme, "http"); XCTAssertEqual(c.endpoint.host, "127.0.0.1")
        XCTAssertTrue(c.carol.username.hasPrefix("vqa_")); XCTAssertTrue(c.alice.username.hasPrefix("vqa_")); XCTAssertTrue(c.bob.username.hasPrefix("vqa_"))
        XCTAssertFalse(GroupsUpgrade.enabled)
        guard Bundle.main.bundleIdentifier?.hasPrefix("co.fallsoft.vipi.groupsqa") == true else { throw GroupsFailure.invalidResponse }
        return c
    }
    private func state(_ c: Configuration) throws -> State {
        let s = try JSONDecoder().decode(State.self, from: Data(contentsOf: file("state"))); XCTAssertEqual(s.run, c.run); return s
    }
    private func body(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
    private func save(_ state: State) throws { try JSONEncoder().encode(state).write(to: file("state"), options: .atomic) }
    private func receipt(_ c: Configuration, _ stage: String, values: [String: Any] = [:]) throws {
        var value = values
        value.merge(["run": c.run, "complete": true, "normal_http": true, "real_libsignal": true, "owner_or_native_session_access": false,
            "scope": "native API/Signal/storage; local read only; no group UI, hosted auth or push proof"], uniquingKeysWith: { _, b in b })
        try body(value).write(to: file(stage), options: .atomic)
    }
    private func now() -> Int64 { Int64(Date().timeIntervalSince1970 * 1000) }
    private func transport(_ c: Configuration) throws -> GroupsLoopbackTransport { try GroupsLoopbackTransport(endpoint: c.endpoint, token: XCTUnwrap(c.carol.access_token)) }
    private func greet(_ peer: UUID, text: String, core: MessagingCore, http: GroupsLoopbackTransport) async throws {
        if try !core.hasSession(peer: peer) {
            let request = UUID()
            let claim: ClaimedKeys = try await http.request("POST", "/v1/people/\(peer.uuidString.lowercased())/keys", body: body(["request_id": request.uuidString.lowercased()]), device: core.device)
            _ = try core.keys.establish(peer: peer, requestID: request, response: claim)
        }
        let n = now(); let message = try core.queue(id: UUID(), peer: peer, text: text, createdAt: n, now: n)
        let status: Status = try await http.request("POST", "/v1/messages", body: message.sendData(), device: core.device)
        XCTAssertEqual(status.state, "accepted")
    }
    private func ack(_ id: UUID, core: MessagingCore, http: GroupsLoopbackTransport) async throws {
        let status: Status = try await http.request("POST", "/v1/messages/\(id.uuidString.lowercased())/receipt", device: core.device)
        XCTAssertEqual(status.state, "delivered")
    }
    func testPublishCarolKeysAndSendGreetings() async throws {
        let c = try configuration(), http = try transport(c)
        XCTAssertFalse(FileManager.default.fileExists(atPath: file("state").path))
        let profile: Profile = try await http.request("PUT", "/v1/me", body: body(["username": c.carol.username, "display_name": "Local Carol"]))
        let vault = try MessageVault(account: profile.id); defer { try? vault.close() }; let core = try MessagingCore(vault: vault)
        let device: DeviceResult = try await http.request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret]))
        XCTAssertEqual(device.id, core.device.id); XCTAssertTrue(device.active)
        let publication = try core.keys.publication(now: now())
        let inventory: Inventory = try await http.request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
        try core.keys.published(revision: inventory.revision); XCTAssertGreaterThanOrEqual(inventory.remaining, 20)
        let alice: Profile = try await http.request("GET", "/v1/people/\(c.alice.username)", device: core.device)
        let bob: Profile = try await http.request("GET", "/v1/people/\(c.bob.username)", device: core.device)
        try await greet(alice.id, text: "Carol to Alice — native Apple keys", core: core, http: http)
        try await greet(bob.id, text: "Carol to Bob — native Apple keys", core: core, http: http)
        try save(.init(run: c.run, account: profile.id)); try receipt(c, "apple-published", values: ["sent_direct": 2, "carol": profile.id.uuidString.lowercased()])
    }
    func testReceiveGreetingsAndAcceptGroup() async throws {
        let c = try configuration(); var s = try state(c); let http = try transport(c)
        let vault = try MessageVault(account: s.account); defer { try? vault.close() }; let core = try MessagingCore(vault: vault)
        let inbox: Inbox = try await http.request("GET", "/v1/messages/pending", device: core.device)
        XCTAssertEqual(inbox.messages.count, 2)
        var originals = Set<String>()
        for packet in inbox.messages {
            let routed = try XCTUnwrap(packet.direct).routed(account: s.account)
            originals.insert(try core.receive(routed, now: now()).text); try await ack(routed.envelope.id, core: core, http: http)
        }
        XCTAssertEqual(originals, ["Alice to Carol — native Android keys", "Bob to Carol — native Android keys"])
        let api = GroupsAPI(transport: http, device: core.device)
        let listing = try await api.list(); let invitation = try XCTUnwrap(listing.invitations.only)
        let accepted = try await api.answer(invitation, accept: true, request: UUID())
        let joined = try XCTUnwrap(accepted)
        XCTAssertEqual(joined.members.count, 3); s.group = joined.id; try save(s)
        XCTAssertNil(try GroupsMembership(vault: vault).current(joined.id)) // Relay membership never authorizes crypto alone.
        try receipt(c, "apple-accepted", values: ["group": joined.id.uuidString.lowercased(), "server_members": 3, "local_membership_unapproved": true])
    }
    func testBootstrapReceiveAndReplyWhileBobOffline() async throws {
        let c = try configuration(), s = try state(c), group = try XCTUnwrap(s.group), http = try transport(c)
        let vault = try MessageVault(account: s.account); defer { try? vault.close() }; let core = try MessagingCore(vault: vault)
        let store = GroupsStore(vault: vault), membership = GroupsMembership(vault: vault)
        let controls = GroupsControlCrypto(vault: vault, core: core), crypto = GroupsCrypto(vault: vault, core: core, store: store)
        let inbox: Inbox = try await http.request("GET", "/v1/messages/pending", device: core.device)
        let controlsIn = inbox.messages.compactMap(\.group).filter { $0.group_kind == "control" }
        XCTAssertEqual(controlsIn.count, 1)
        for item in controlsIn { try controls.receive(item, now: now()); try controls.receive(item, now: now()); try await ack(item.id, core: core, http: http) }
        XCTAssertNil(try membership.current(group))
        let reviewed = try XCTUnwrap(controls.pending().only)
        XCTAssertEqual(reviewed.group, group); XCTAssertEqual(reviewed.transition.target_id, s.account)
        try controls.confirmBootstrap(reviewed) // Explicit whole-control review in this test; not a UI consent claim.
        XCTAssertEqual(try membership.current(group)?.revision, 3)
        var received = [GroupMessage]()
        for item in inbox.messages.compactMap(\.group).filter({ $0.group_kind == "message" }) {
            let message = try XCTUnwrap(crypto.receive(item, now: now()))
            XCTAssertEqual(message.delivery, .received); XCTAssertEqual(try crypto.receive(item, now: now())?.id, message.id)
            received.append(message); try await ack(item.id, core: core, http: http)
        }
        XCTAssertEqual(Set(received.map(\.text)), ["Coffee at six? ☕ مرحباً", "I can bring bread."])
        XCTAssertEqual(try store.unread(group, account: s.account), 2)
        try store.markRead(group, visible: Set(received.map(\.id))); XCTAssertEqual(try store.unread(group, account: s.account), 0)
        let api = GroupsAPI(transport: http, device: core.device), roster = try await api.detail(group)
        let original = GroupMessage(id: UUID(), groupID: group, epoch: roster.epoch, membershipRevision: 3, sender: s.account, text: "Yes, six works. Nos vemos.", createdAt: now(), delivery: .queued)
        let fanout = try crypto.prepare(original, roster: roster, now: now())
        XCTAssertEqual(try crypto.prepare(original, roster: roster, now: now()).body, fanout.body)
        let admitted = try await api.send(fanout)
        try crypto.accepted(admitted, fanout: fanout)
        try receipt(c, "apple-replied", values: ["received_ids": received.map { $0.id.uuidString.lowercased() }, "reply_id": original.id.uuidString.lowercased(), "received": 2, "read_local": 2])
    }
    func testCatchUpBobAndVerifyDurableIDs() async throws {
        let c = try configuration(), s = try state(c), group = try XCTUnwrap(s.group), http = try transport(c)
        var storedIDs = Set<UUID>()
        do {
            let vault = try MessageVault(account: s.account); defer { try? vault.close() }; let core = try MessagingCore(vault: vault)
            let store = GroupsStore(vault: vault), crypto = GroupsCrypto(vault: vault, core: core, store: GroupsStore(vault: vault))
            let inbox: Inbox = try await http.request("GET", "/v1/messages/pending", device: core.device)
            XCTAssertEqual(inbox.messages.count, 1)
            let item = try XCTUnwrap(inbox.messages.first?.group)
            let message = try XCTUnwrap(crypto.receive(item, now: now()))
            XCTAssertEqual(message.text, "Caught up after being offline. See you!"); XCTAssertEqual(try crypto.receive(item, now: now())?.id, message.id)
            try await ack(item.id, core: core, http: http)
            try store.markRead(group, visible: [message.id]); storedIDs = Set(try store.messages(group).map(\.id)); XCTAssertEqual(storedIDs.count, 4)
        }
        do {
            let vault = try MessageVault(account: s.account); defer { try? vault.close() }; let store = GroupsStore(vault: vault), core = try MessagingCore(vault: vault)
            XCTAssertEqual(Set(try store.messages(group).map(\.id)), storedIDs); XCTAssertEqual(try store.unread(group, account: s.account), 0)
            let inbox: Inbox = try await http.request("GET", "/v1/messages/pending", device: core.device); XCTAssertTrue(inbox.messages.isEmpty)
        }
        try receipt(c, "apple-catchup", values: ["durable_message_ids": storedIDs.map { $0.uuidString.lowercased() }.sorted(), "read_state_survived_reopen": true, "duplicate_messages": 0])
    }
}
private extension Array { var only: Element? { count == 1 ? first : nil } }
private final class GroupsNoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}
@MainActor private final class GroupsLoopbackTransport: ChatTransport {
    let endpoint: URL; let token: String; let session: URLSession
    init(endpoint: URL, token: String) throws {
        guard endpoint.scheme == "http", endpoint.host == "127.0.0.1", endpoint.port != nil, endpoint.user == nil, endpoint.password == nil,
              endpoint.query == nil, endpoint.fragment == nil, endpoint.path.isEmpty || endpoint.path == "/", token.count > 100 else { throw GroupsFailure.invalidResponse }
        self.endpoint = endpoint; self.token = token
        let c = URLSessionConfiguration.ephemeral; c.urlCache = nil; c.httpCookieStorage = nil; c.timeoutIntervalForRequest = 20; c.timeoutIntervalForResource = 30
        session = URLSession(configuration: c, delegate: GroupsNoRedirects(), delegateQueue: nil)
    }
    deinit { session.invalidateAndCancel() }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        guard path.hasPrefix("/v1/"), !path.contains(".."), !path.contains("?"), !path.contains("#") else { throw GroupsFailure.invalidResponse }
        var c = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)!; c.path = path
        c.queryItems = query.isEmpty ? nil : query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: try XCTUnwrap(c.url)); request.httpMethod = method; request.httpBody = body
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let device { request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID"); request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret") }
        let (bytes, response) = try await session.data(for: request)
        guard bytes.count <= 2_000_000, let response = response as? HTTPURLResponse else { throw GroupsFailure.invalidResponse }
        if !(200...299).contains(response.statusCode) {
            let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any]
            throw ServiceFailure(status: response.statusCode, code: value?["error"] as? String ?? "local_fixture_error")
        }
        return try JSONDecoder().decode(T.self, from: bytes)
    }
}
