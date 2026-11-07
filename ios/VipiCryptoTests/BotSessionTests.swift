import Foundation
import XCTest
@testable import Vipi

@MainActor final class BotSessionTests: XCTestCase {
    private final class Transport: ChatTransport {
        var requests: [(String, String, Data?)] = []
        var failReply = false
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            requests.append((method, path, body))
            let allowance: [String: Any] = ["available": true, "service_ready": true, "remaining_replies": 149, "monthly_replies": 150, "resets_at": "2026-12-01T00:00:00Z", "max_context_bytes": 8192]
            let value: [String: Any]
            if path == "/v1/bot/messages" {
                if failReply { throw URLError(.timedOut) }
                let request = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                value = ["request_id": request["request_id"]!, "reply": "Coffee tomorrow sounds good.", "allowance": allowance]
            } else if path == "/v1/bot/reports" { value = ["reported": true] }
            else { value = allowance }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    private func withVault(_ body: (MessageVault) async throws -> Void) async throws {
        let account = UUID()
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("vipi-bot-test-" + UUID().uuidString)
        let vault = try MessageVault(account: account, directory: folder)
        defer { try? vault.close(); try? FileManager.default.removeItem(at: folder); KeychainStore.delete(account: "messages-" + account.uuidString.lowercased()) }
        try await body(vault)
    }
    func testConsentAndDurableBotOnlyHistory() async throws {
        try await withVault { vault in
            try vault.transaction { try vault.put("message", "private-friend", Data("Friend-only secret".utf8)) }
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); session.draft = "Coffee tomorrow?"
            await session.send()
            XCTAssertFalse(api.requests.contains { $0.1 == "/v1/bot/messages" })
            try session.setConsent(true); await session.send()
            XCTAssertEqual(session.messages.count, 2)
            XCTAssertTrue(session.messages.allSatisfy { $0.state == "complete" })
            let sent = try XCTUnwrap(api.requests.first { $0.1 == "/v1/bot/messages" }?.2)
            XCTAssertFalse(String(decoding: sent, as: UTF8.self).contains("Friend-only"))
            let reopened = try BotSession(api: api, vault: vault)
            XCTAssertEqual(reopened.messages.map(\.text), session.messages.map(\.text))
            XCTAssertTrue(reopened.consent)
            try reopened.setConsent(false)
            XCTAssertFalse(try BotSession(api: api, vault: vault).consent)
        }
    }
    func testUncertainReplyNeverAutomaticallyRetriesAfterReopen() async throws {
        try await withVault { vault in
            let api = Transport(); api.failReply = true
            let session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true); session.draft = "Hello"; await session.send()
            XCTAssertEqual(session.messages.first?.state, "unconfirmed")
            let reopened = try BotSession(api: api, vault: vault); await reopened.refresh()
            XCTAssertEqual(reopened.messages.first?.state, "unconfirmed")
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
            XCTAssertEqual(BotSession.context(history: reopened.messages, newText: "Next", maximumBytes: 8192)?.map(\.content), ["Next"])
        }
    }
    func testContextIsBoundedByUTF8BytesAndRecentMessages() throws {
        let history = (0..<20).map { index in BotMessage(id: UUID(), role: index.isMultiple(of: 2) ? "user" : "assistant", text: String(repeating: "猫", count: 500), createdAt: Date(), state: "complete") }
        let values = try XCTUnwrap(BotSession.context(history: history, newText: "Coffee?", maximumBytes: 8192))
        XCTAssertLessThanOrEqual(values.count, 12)
        XCTAssertLessThanOrEqual(values.reduce(0) { $0 + $1.content.utf8.count }, 8192)
        XCTAssertEqual(values.last?.role, "user")
        XCTAssertEqual(values.last?.content, "Coffee?")
        XCTAssertNil(BotSession.context(history: [], newText: String(repeating: "猫", count: 3000), maximumBytes: 8192))
    }
    func testReportContainsOnlySelectedReply() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            var selected = BotMessage(id: UUID(), role: "assistant", text: String(repeating: "猫", count: 2000), createdAt: Date(), state: "complete")
            selected.requestID = UUID()
            try await session.report(selected, reason: "inaccurate")
            let sent = try XCTUnwrap(api.requests.last?.2)
            let value = try XCTUnwrap(JSONSerialization.jsonObject(with: sent) as? [String: String])
            XCTAssertEqual(Set(value.keys), ["request_id", "reason", "selected_reply"])
            XCTAssertLessThanOrEqual(try XCTUnwrap(value["selected_reply"]).utf8.count, 4000)
            XCTAssertFalse(try XCTUnwrap(value["selected_reply"]).contains("�"))
        }
    }
}
