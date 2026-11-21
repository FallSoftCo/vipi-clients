import Foundation
import XCTest
@testable import Vipi

@MainActor final class NetworkMessagingTests: XCTestCase {
    private struct Configuration: Decodable { let run: String; let username: String; let peer: String; let endpoint: URL; let use_existing_session: Bool?; let isolated_fresh_profile: Bool?; let expected_subject: String?; let isolated_signed_authentication: Bool?; let access_token: String? }
    private struct Profile: Codable { let id: UUID; let username: String; let display_name: String }
    private struct Status: Decodable { let state: String }
    private struct Inventory: Decodable { let revision: UInt32; let remaining: Int }
    private struct Inbox: Decodable { let messages: [RoutedMessage.Received] }
    private struct DeviceResult: Decodable { let id: UUID; let active: Bool }
    private struct State: Codable { let run: String; let account: UUID; let message: UUID }
    private func file(_ name: String) -> URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(name) }
    private func configuration() throws -> Configuration {
        guard FileManager.default.fileExists(atPath: file("network-config.json").path) else { throw XCTSkip("Requires explicitly prepared native HTTP QA harness") }
        let value = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: file("network-config.json")))
        guard value.username.hasPrefix("vqa_"), value.peer.hasPrefix("vqa_") else { throw ServiceFailure(status: 0, code: "owned_qa_configuration_required") }
        if value.isolated_signed_authentication == true {
            guard value.endpoint.scheme == "http", value.endpoint.host == "127.0.0.1", value.endpoint.port != nil,
                  value.use_existing_session != true, value.isolated_fresh_profile != true,
                  value.expected_subject?.hasPrefix("user_localpair_") == true,
                  (value.access_token?.count ?? 0) > 100 else {
                throw ServiceFailure(status: 0, code: "signed_local_fixture_required")
            }
        }
        if value.isolated_fresh_profile == true {
            guard value.endpoint.scheme == "http", value.endpoint.host == "127.0.0.1", value.endpoint.port != nil,
                  value.use_existing_session == true, value.expected_subject?.hasPrefix("user_") == true else {
                throw ServiceFailure(status: 0, code: "isolated_native_configuration_required")
            }
        }
        return value
    }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    func testInspectOwnedSessionWithoutExportingCredentials() throws {
        let config = try configuration()
        guard config.use_existing_session == true, let expected = config.expected_subject else {
            throw XCTSkip("Requires an explicitly bound owned native session")
        }
        let session = AuthenticationManager().session
        // Inspect only native metadata. No access token, refresh token, device
        // secret, or keychain bytes are written to the diagnostics artifact.
        try body(["run": config.run, "session_present": session != nil,
                  "matches_expected_subject": session?.userID == expected,
                  "authority": session?.authority.rawValue ?? "absent",
                  "credentials_exported": false]).write(to: file("network-session-readiness.json"), options: .atomic)
    }
    private func transport(_ config: Configuration, userID: String) throws -> any ChatTransport {
        if config.isolated_signed_authentication == true {
            return try SignedLoopbackPairTransport(endpoint: config.endpoint, token: XCTUnwrap(config.access_token))
        }
        return try ServiceClient(authentication: AuthenticationManager(), userID: userID, endpoint: config.endpoint)
    }
    func testPublishAndSendToAndroid() async throws {
        let config = try configuration()
        let original: VipiSession
        if config.isolated_signed_authentication == true {
            // Fresh local RS256 token only; the test-only transport never reads
            // or writes a native session and cannot contact production auth.
            original = VipiSession(userID: try XCTUnwrap(config.expected_subject), accessToken: try XCTUnwrap(config.access_token), refreshToken: "local-fixture-no-refresh")
        } else if config.use_existing_session == true {
            // Genuine hosted PKCE has already established this simulator's
            // session. No token fixture or replacement is used in this mode.
            original = try XCTUnwrap(AuthenticationManager().session)
            if let expected = config.expected_subject, original.userID != expected { throw ServiceFailure(status: 0, code: "owned_qa_session_required") }
        } else {
            if let old = try KeychainStore.read(account: "session") { try KeychainStore.save(old, account: "qa-session-backup") }
            original = try JSONDecoder().decode(VipiSession.self, from: Data(contentsOf: file("network-session.json")))
            try FileManager.default.removeItem(at: file("network-session.json"))
            let forced = VipiSession(userID: original.userID, accessToken: "expired-native-qa-token", refreshToken: original.refreshToken, authority: original.authority)
            try KeychainStore.save(JSONEncoder().encode(forced), account: "session")
        }
        let api = try transport(config, userID: original.userID)
        if config.use_existing_session == true && config.isolated_fresh_profile != true {
            let existing: Profile = try await api.request("GET", "/v1/me")
            XCTAssertEqual(existing.username, config.username)
            guard existing.username == config.username else { throw XCTSkip("Existing identity is not the owned QA account") }
        }
        let profile: Profile
        if config.use_existing_session == true && config.isolated_fresh_profile != true { profile = try await api.request("GET", "/v1/me") }
        else { profile = try await api.request("PUT", "/v1/me", body: body(["username": config.username, "display_name": "Vipi iOS QA"])) }
        let vault = try MessageVault(account: profile.id), core = try MessagingCore(vault: vault)
        if config.use_existing_session != true || config.isolated_fresh_profile == true {
            let device: DeviceResult = try await api.request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret]))
            XCTAssertEqual(device.id, core.device.id); XCTAssertTrue(device.active)
        }
        if config.use_existing_session == true && config.isolated_fresh_profile != true {
            let inventory: Inventory = try await api.request("GET", "/v1/keys", device: core.device)
            XCTAssertGreaterThan(inventory.remaining, 0)
        } else {
            let publication = try core.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000))
            let inventory: Inventory = try await api.request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
            try core.keys.published(revision: inventory.revision); XCTAssertEqual(inventory.remaining, 20)
        }
        let peer: Profile = try await api.request("GET", "/v1/people/\(config.peer)", device: core.device)
        let request = UUID(), path = "/v1/people/\(peer.id.uuidString.lowercased())/keys"
        let invitation = try XCTUnwrap(URL(string: "https://api.mambovipi.app/invite/\(config.peer)"))
        XCTAssertEqual(FriendInvitationLink.username(in: invitation), peer.username)
        if config.use_existing_session == true && config.isolated_fresh_profile != true { XCTAssertTrue(try core.hasSession(peer: peer.id)) }
        else {
            let claimed: ClaimedKeys = try await api.request("POST", path, body: body(["request_id": request.uuidString.lowercased()]), device: core.device)
            _ = try core.keys.establish(peer: peer.id, requestID: request, response: claimed)
        }
        let now = Int64(Date().timeIntervalSince1970 * 1000), id = UUID()
        let message = try core.queue(id: id, peer: peer.id, text: "Swift over the real relay — café ☕ مرحباً", createdAt: now, now: now)
        // No transport is consulted while queued; a reopened vault must preserve
        // the exact ID and ciphertext before the first real HTTP dispatch.
        let reopened = try MessagingCore(vault: MessageVault(account: profile.id))
        XCTAssertTrue(try reopened.journal.pending(now: now).contains { $0.id == id })
        let retry = try reopened.queue(id: id, peer: peer.id, text: "Swift over the real relay — café ☕ مرحباً", createdAt: now, now: now)
        XCTAssertEqual(retry.envelope.id, message.envelope.id)
        XCTAssertEqual(retry.envelope.ciphertext, message.envelope.ciphertext)
        let status: Status = try await api.request("POST", "/v1/messages", body: retry.sendData(), device: reopened.device)
        XCTAssertEqual(status.state, "accepted"); try core.journal.applyStatus(id, state: status.state)
        if config.use_existing_session == true {
            let replayed: Status = try await api.request("POST", "/v1/messages", body: message.sendData(), device: core.device)
            XCTAssertTrue(["accepted", "delivered"].contains(replayed.state))
        } else {
            let again: ClaimedKeys = try await api.request("POST", path, body: body(["request_id": request.uuidString.lowercased()]), device: core.device)
            _ = try core.keys.establish(peer: peer.id, requestID: request, response: again)
        }
        try JSONEncoder().encode(State(run: config.run, account: profile.id, message: id)).write(to: file("network-state.json"), options: .atomic)
        try body(["run": config.run, "accepted": true, "offline_queue_reopened": true, "stable_id_and_ciphertext": true, "invitation_username_preserved": true]).write(to: file("network-sent.json"), options: .atomic)
    }
    func testReceiveAndroidOutOfOrderAndRestoreSession() async throws {
        let config = try configuration(), state = try JSONDecoder().decode(State.self, from: Data(contentsOf: file("network-state.json")))
        XCTAssertEqual(state.run, config.run)
        let userID: String
        if config.isolated_signed_authentication == true { userID = try XCTUnwrap(config.expected_subject) }
        else { userID = try XCTUnwrap(AuthenticationManager().session?.userID) }
        let api = try transport(config, userID: userID)
        let core = try MessagingCore(vault: MessageVault(account: state.account))
        let delivered: Status = try await api.request("GET", "/v1/messages/\(state.message.uuidString.lowercased())", device: core.device)
        XCTAssertEqual(delivered.state, "delivered"); try core.journal.applyStatus(state.message, state: delivered.state)
        let inbox: Inbox = try await api.request("GET", "/v1/messages/pending", device: core.device)
        XCTAssertEqual(inbox.messages.count, 3)
        for index in [2, 0, 1] {
            let reopened = try MessagingCore(vault: MessageVault(account: state.account))
            let value = try inbox.messages[index].routed(account: state.account)
            let received = try reopened.receive(value, now: Int64(Date().timeIntervalSince1970 * 1000))
            XCTAssertEqual(received.text, "Android HTTP reply \(index) — río ☕")
            XCTAssertEqual(try reopened.receive(value, now: Int64(Date().timeIntervalSince1970 * 1000)).text, received.text)
            let acknowledged: Status = try await api.request("POST", "/v1/messages/\(value.envelope.id.uuidString.lowercased())/receipt", device: reopened.device)
            XCTAssertEqual(acknowledged.state, "delivered")
        }
        let empty: Inbox = try await api.request("GET", "/v1/messages/pending", device: core.device)
        XCTAssertTrue(empty.messages.isEmpty)
        if config.use_existing_session != true && config.isolated_signed_authentication != true {
            if let old = try KeychainStore.read(account: "qa-session-backup") { try KeychainStore.save(old, account: "session") }
            else { KeychainStore.delete(account: "session") }
            KeychainStore.delete(account: "qa-session-backup")
        }
        try FileManager.default.removeItem(at: file("network-config.json"))
        try body(["run": config.run, "received_out_of_order": 3, "inbox_empty_after_receipts": true, "authentication_lane": config.isolated_signed_authentication == true ? "explicit local signed test authentication" : "real WorkOS",
                  "scope": "native libsignal and durable storage over real HTTP; not hosted sign-up UI or APNs/FCM"]).write(to: file("network-complete.json"), options: .atomic)
    }
}


private final class NoPairRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

/// Explicit fixture lane only. Real HTTP + bearer signature verification at the
/// normal API; no native/customer credential access and no production refresh.
@MainActor final class SignedLoopbackPairTransport: ChatTransport {
    private let endpoint: URL, token: String
    private let http = URLSession(configuration: .ephemeral, delegate: NoPairRedirects(), delegateQueue: nil)
    init(endpoint: URL, token: String) throws {
        guard endpoint.scheme == "http", endpoint.host == "127.0.0.1", endpoint.port != nil,
              endpoint.user == nil, endpoint.password == nil, endpoint.query == nil, endpoint.fragment == nil,
              endpoint.path.isEmpty || endpoint.path == "/" else { throw ServiceFailure(status: 0, code: "loopback_only") }
        self.endpoint = endpoint; self.token = token
    }
    deinit { http.invalidateAndCancel() }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
        guard path.hasPrefix("/v1/"), !path.contains(".."), !path.contains("?"), !path.contains("#") else { throw ServiceFailure(status: 0, code: "invalid_path") }
        var url = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)!
        url.path = path; url.queryItems = query.sorted(by: { $0.key < $1.key }).map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: url.url!); request.httpMethod = method; request.httpBody = body
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let device {
            request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
            request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
        }
        let (data, response) = try await http.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard data.count <= 12_000_000, (200...299).contains(status) else { throw ServiceFailure(status: status, code: "local_fixture_request_failed") }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
