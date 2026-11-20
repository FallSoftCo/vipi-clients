import Foundation
import XCTest
@testable import Vipi

@MainActor final class NetworkMessagingTests: XCTestCase {
    private struct Configuration: Decodable { let run: String; let username: String; let peer: String; let endpoint: URL; let use_existing_session: Bool?; let isolated_fresh_profile: Bool?; let expected_subject: String? }
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
        if value.isolated_fresh_profile == true {
            guard value.endpoint.scheme == "http", value.endpoint.host == "127.0.0.1", value.endpoint.port != nil,
                  value.use_existing_session == true, value.expected_subject?.hasPrefix("user_") == true else {
                throw ServiceFailure(status: 0, code: "isolated_native_configuration_required")
            }
        }
        return value
    }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    func testPublishAndSendToAndroid() async throws {
        let config = try configuration()
        let original: VipiSession
        if config.use_existing_session == true {
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
        let auth = AuthenticationManager(), api = try ServiceClient(authentication: auth, userID: original.userID, endpoint: config.endpoint)
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
        let auth = AuthenticationManager(), api = try ServiceClient(authentication: auth, userID: XCTUnwrap(auth.session?.userID), endpoint: config.endpoint)
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
        if config.use_existing_session != true {
            if let old = try KeychainStore.read(account: "qa-session-backup") { try KeychainStore.save(old, account: "session") }
            else { KeychainStore.delete(account: "session") }
            KeychainStore.delete(account: "qa-session-backup")
        }
        try FileManager.default.removeItem(at: file("network-config.json"))
        try body(["run": config.run, "received_out_of_order": 3, "inbox_empty_after_receipts": true, "scope": "native libsignal and durable storage over real HTTP; existing sign-in, not sign-up UI or APNs/FCM"]).write(to: file("network-complete.json"), options: .atomic)
    }
}
