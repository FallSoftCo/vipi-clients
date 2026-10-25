import Foundation
import XCTest
@testable import Vipi

@MainActor final class NetworkMessagingTests: XCTestCase {
    private struct Configuration: Decodable { let run: String; let username: String; let peer: String; let endpoint: URL }
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
        XCTAssertTrue(value.username.hasPrefix("vqa_")); XCTAssertTrue(value.peer.hasPrefix("vqa_")); return value
    }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    func testPublishAndSendToAndroid() async throws {
        let config = try configuration()
        if let old = try KeychainStore.read(account: "session") { try KeychainStore.save(old, account: "qa-session-backup") }
        let original = try JSONDecoder().decode(VipiSession.self, from: Data(contentsOf: file("network-session.json")))
        try FileManager.default.removeItem(at: file("network-session.json"))
        let forced = VipiSession(userID: original.userID, accessToken: "expired-native-qa-token", refreshToken: original.refreshToken)
        try KeychainStore.save(JSONEncoder().encode(forced), account: "session")
        let auth = AuthenticationManager(), api = try ServiceClient(authentication: auth, userID: original.userID, endpoint: config.endpoint)
        let profile: Profile = try await api.request("PUT", "/v1/me", body: body(["username": config.username, "display_name": "Vipi iOS QA"]))
        let vault = try MessageVault(account: profile.id), core = try MessagingCore(vault: vault)
        let device: DeviceResult = try await api.request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret]))
        XCTAssertEqual(device.id, core.device.id); XCTAssertTrue(device.active)
        let publication = try core.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000))
        let inventory: Inventory = try await api.request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
        try core.keys.published(revision: inventory.revision); XCTAssertEqual(inventory.remaining, 20)
        let peer: Profile = try await api.request("GET", "/v1/people/\(config.peer)", device: core.device)
        let request = UUID(), path = "/v1/people/\(peer.id.uuidString.lowercased())/keys"
        let claimed: ClaimedKeys = try await api.request("POST", path, body: body(["request_id": request.uuidString.lowercased()]), device: core.device)
        _ = try core.keys.establish(peer: peer.id, requestID: request, response: claimed)
        let now = Int64(Date().timeIntervalSince1970 * 1000), id = UUID()
        let message = try core.queue(id: id, peer: peer.id, text: "Swift over the real relay — café ☕ مرحباً", createdAt: now, now: now)
        let status: Status = try await api.request("POST", "/v1/messages", body: message.sendData(), device: core.device)
        XCTAssertEqual(status.state, "accepted"); try core.journal.applyStatus(id, state: status.state)
        let again: ClaimedKeys = try await api.request("POST", path, body: body(["request_id": request.uuidString.lowercased()]), device: core.device)
        _ = try core.keys.establish(peer: peer.id, requestID: request, response: again)
        try JSONEncoder().encode(State(run: config.run, account: profile.id, message: id)).write(to: file("network-state.json"), options: .atomic)
        try body(["run": config.run, "accepted": true]).write(to: file("network-sent.json"), options: .atomic)
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
        if let old = try KeychainStore.read(account: "qa-session-backup") { try KeychainStore.save(old, account: "session") }
        else { KeychainStore.delete(account: "session") }
        KeychainStore.delete(account: "qa-session-backup"); try FileManager.default.removeItem(at: file("network-config.json"))
        try body(["run": config.run, "received_out_of_order": 3, "inbox_empty_after_receipts": true]).write(to: file("network-complete.json"), options: .atomic)
    }
}
