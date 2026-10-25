import Foundation
import XCTest
@testable import Vipi

@MainActor final class ChatClosureTests: XCTestCase {
    private final class Transport: ChatTransport {
        let account: UUID; let peer: UUID
        var calls = 0
        var pending: CheckedContinuation<Data, any Error>?
        var began: CheckedContinuation<Void, Never>?
        init(account: UUID, peer: UUID) { self.account = account; self.peer = peer }
        func waitForLookup() async {
            if pending != nil { return }
            await withCheckedContinuation { began = $0 }
        }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            calls += 1
            let value: Data
            switch path {
            case "/v1/me": value = try JSONEncoder().encode(ChatProfile(id: account, username: "close_qa", display_name: "Closure QA"))
            case "/v1/devices":
                let input = try JSONSerialization.jsonObject(with: body!) as! [String: Any]
                value = try JSONSerialization.data(withJSONObject: ["id": input["device_id"]!, "active": true])
            case "/v1/keys": value = Data(#"{"revision":1,"remaining":20}"#.utf8)
            case "/v1/messages/pending": value = Data(#"{"messages":[],"next_cursor":null}"#.utf8)
            case "/v1/people/alex":
                value = try await withCheckedThrowingContinuation { pending = $0; began?.resume(); began = nil }
            default: throw ServiceFailure(status: 500, code: "unexpected_fixture_path")
            }
            return try JSONDecoder().decode(T.self, from: value)
        }
    }
    func testClosedSessionRejectsLateResponseAndNeverReopensStorage() async throws {
        let account = UUID(), peer = UUID(), userID = "closure-" + UUID().uuidString
        let api = Transport(account: account, peer: peer)
        let chat = try ChatSession(api: api, userID: userID)
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(account.uuidString.lowercased())
        defer {
            api.pending?.resume(throwing: CancellationError()); api.pending = nil
            try? chat.close()
            KeychainStore.delete(account: "profile-" + userID)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
            try? FileManager.default.removeItem(at: folder)
        }
        await chat.start(); XCTAssertTrue(chat.ready)
        let lookup = Task { try await chat.find("alex") }
        await api.waitForLookup()
        try chat.close(); try chat.close()
        let response = try JSONEncoder().encode(ChatProfile(id: peer, username: "alex", display_name: "Alex"))
        api.pending?.resume(returning: response); api.pending = nil
        do { _ = try await lookup.value; XCTFail("A late response reopened a closed session") }
        catch is CancellationError {} catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertFalse(chat.ready); XCTAssertNil(chat.profile); XCTAssertTrue(chat.contacts.isEmpty)
        let count = api.calls; await chat.start(); await chat.synchronize(); XCTAssertEqual(api.calls, count)
        let vault = try MessageVault(account: account)
        defer { try? vault.close() }
        try vault.transaction {
            XCTAssertNil(try vault.get("contact", peer.uuidString.lowercased()))
            XCTAssertNotNil(try vault.get("local", "identity"))
        }
    }
}
