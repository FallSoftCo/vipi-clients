import Foundation
import XCTest
@testable import Vipi

@MainActor final class BotSessionTests: XCTestCase {
    private final class Transport: ChatTransport {
        var requests: [(String, String, Data?)] = []
        var failReply = false
        var failAllowance = false
        var refusal: String?
        var devices: [DeviceCredential?] = []
        var remaining = 150
        var reset = "2099-01-01T00:00:00Z"
        var serviceReady = true
        var pauseReply = false
        var pauseAllowance = false
        var pendingReply: CheckedContinuation<Void, Never>?
        var pendingAllowance: CheckedContinuation<Void, Never>?
        var replyStarted: CheckedContinuation<Void, Never>?
        var allowanceStarted: CheckedContinuation<Void, Never>?
        func waitForReply() async {
            if pendingReply != nil { return }
            await withCheckedContinuation { replyStarted = $0 }
        }
        func waitForAllowance() async {
            if pendingAllowance != nil { return }
            await withCheckedContinuation { allowanceStarted = $0 }
        }
        func finishReply() { let pending = pendingReply; pendingReply = nil; pending?.resume() }
        func finishAllowance() { let pending = pendingAllowance; pendingAllowance = nil; pending?.resume() }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            requests.append((method, path, body))
            if path == "/v1/bot/allowance" && failAllowance { throw URLError(.notConnectedToInternet) }
            if method == "POST" { devices.append(device) }
            var allowance: [String: Any] = ["available": true, "service_ready": serviceReady, "remaining_replies": remaining, "monthly_replies": 150, "resets_at": reset, "max_context_bytes": 8192]
            if path == "/v1/bot/allowance" && pauseAllowance {
                await withCheckedContinuation { pendingAllowance = $0; allowanceStarted?.resume(); allowanceStarted = nil }
            }
            let value: [String: Any]
            if path == "/v1/bot/messages" {
                if let refusal { throw ServiceFailure(status: 401, code: refusal) }
                if failReply { throw URLError(.timedOut) }
                if pauseReply { await withCheckedContinuation { pendingReply = $0; replyStarted?.resume(); replyStarted = nil } }
                remaining -= 1; allowance["remaining_replies"] = remaining
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
        let device = DeviceCredential(id: UUID(), secret: String(repeating: "x", count: 43))
        try vault.transaction {
            try vault.put("local", "service-device", JSONEncoder().encode(device))
            try vault.put("local", "registered-device", Data(device.id.uuidString.lowercased().utf8))
        }
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
            let device = try DeviceCredential.registered(vault: vault)
            XCTAssertEqual(api.devices.compactMap { $0 }.first?.id, device.id)
            XCTAssertEqual(api.devices.compactMap { $0 }.first?.secret, device.secret)
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
            XCTAssertEqual(api.devices.compactMap { $0 }.last?.id, try DeviceCredential.registered(vault: vault).id)
            let sent = try XCTUnwrap(api.requests.last?.2)
            let value = try XCTUnwrap(JSONSerialization.jsonObject(with: sent) as? [String: String])
            XCTAssertEqual(Set(value.keys), ["request_id", "reason", "selected_reply"])
            XCTAssertLessThanOrEqual(try XCTUnwrap(value["selected_reply"]).utf8.count, 4000)
            XCTAssertFalse(try XCTUnwrap(value["selected_reply"]).contains("�"))
        }
    }
    func testUnconfirmedSendNoticeSurvivesAllowanceFailure() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true)
            api.failReply = true; api.failAllowance = true
            session.draft = "One request"; await session.send()
            XCTAssertEqual(session.messages.first?.state, "unconfirmed")
            XCTAssertTrue(session.notice?.contains("won’t be resent automatically") == true)
            XCTAssertNil(session.allowance)
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
        }
    }
    func testDefinitiveDeviceRefusalIsNotReplayed() async throws {
        try await withVault { vault in
            let api = Transport(); api.refusal = "device_revoked"
            let session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true)
            session.draft = "One request"; await session.send()
            XCTAssertEqual(session.messages.first?.state, "rejected")
            XCTAssertTrue(session.notice?.contains("wasn’t accepted") == true)
            let reopened = try BotSession(api: api, vault: vault)
            await reopened.refresh(); await reopened.send()
            XCTAssertEqual(reopened.messages.first?.state, "rejected")
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
        }
    }
    func testMissingRegistrationPreservesDraftWithoutSending() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true)
            session.draft = "Keep this draft"; session.saveDraft()
            try vault.transaction { try vault.remove("local", "registered-device") }
            await session.send()
            XCTAssertEqual(session.draft, "Keep this draft")
            XCTAssertTrue(session.messages.isEmpty)
            XCTAssertFalse(api.requests.contains { $0.1 == "/v1/bot/messages" })
            XCTAssertEqual(try BotSession(api: api, vault: vault).draft, "Keep this draft")
        }
    }

    func testExpiredOrInvalidAllowanceKeepsDraftUntilFreshAccessArrives() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            try session.setConsent(true)
            session.draft = "Keep my message while access recovers"; session.saveDraft()
            for reset in ["2000-01-01T00:00:00Z", "not-a-date"] {
                api.reset = reset; await session.refresh()
                XCTAssertFalse(session.canSend, "An expired or invalid quota must not authorize a request")
                await session.send()
                XCTAssertEqual(session.draft, "Keep my message while access recovers")
                XCTAssertTrue(session.messages.isEmpty)
            }
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 0)
            api.reset = "2099-01-01T00:00:00Z"; await session.refresh()
            XCTAssertTrue(session.canSend)
            await session.send()
            XCTAssertEqual(session.messages.map(\.state), ["complete", "complete"])
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
        }
    }

    func testDuplicateSendAndTypingNextDraftDuringSlowReply() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true)
            session.draft = "First message"; session.saveDraft(); api.pauseReply = true
            let sending = Task { await session.send() }
            await api.waitForReply()
            XCTAssertTrue(session.busy); XCTAssertFalse(session.canSend)
            session.draft = "My next message"; session.saveDraft()
            await session.send()
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
            api.finishReply(); await sending.value
            XCTAssertFalse(session.busy)
            XCTAssertEqual(session.messages.map(\.text), ["First message", "Coffee tomorrow sounds good."])
            XCTAssertEqual(session.draft, "My next message")
            let reopened = try BotSession(api: api, vault: vault)
            XCTAssertEqual(reopened.draft, "My next message")
            XCTAssertEqual(reopened.messages.map(\.text), session.messages.map(\.text))
        }
    }

    func testConfirmedReplySurvivesLeavingConversationWithoutAnotherRequest() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true); session.draft = "Finish my reply"
            api.pauseReply = true
            let sending = Task { await session.send() }; await api.waitForReply()
            session.close(); api.finishReply(); await sending.value
            let reopened = try BotSession(api: api, vault: vault)
            XCTAssertEqual(reopened.messages.map(\.state), ["complete", "complete"])
            XCTAssertEqual(reopened.messages.last?.text, "Coffee tomorrow sounds good.")
            XCTAssertTrue(reopened.draft.isEmpty)
            await reopened.refresh(); await reopened.send()
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
        }
    }

    func testLateAllowanceCannotUndoConfirmedReplyCount() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            await session.refresh(); try session.setConsent(true); session.draft = "One counted reply"
            api.pauseAllowance = true
            let oldRead = Task { await session.refresh() }; await api.waitForAllowance()
            await session.send()
            XCTAssertEqual(session.allowance?.remaining_replies, 149)
            api.finishAllowance(); await oldRead.value
            XCTAssertEqual(session.allowance?.remaining_replies, 149, "An older read must not restore spent replies")
            XCTAssertEqual(session.messages.filter { $0.role == "assistant" }.count, 1)
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 1)
        }
    }

    func testNewerAllowanceWinsWhenEarlierReadFinishesLast() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault)
            api.pauseAllowance = true
            let oldRead = Task { await session.refresh() }; await api.waitForAllowance()
            api.pauseAllowance = false; api.remaining = 0; await session.refresh()
            api.finishAllowance(); await oldRead.value
            try session.setConsent(true); session.draft = "Wait for next month"; session.saveDraft()
            XCTAssertEqual(session.allowance?.remaining_replies, 0)
            XCTAssertFalse(session.canSend); await session.send()
            XCTAssertFalse(api.requests.contains { $0.1 == "/v1/bot/messages" })
            XCTAssertEqual(try BotSession(api: api, vault: vault).draft, "Wait for next month")
        }
    }

    func testImmediateRepliesAndClockCorrectionKeepConversationOrderAfterReopen() async throws {
        try await withVault { vault in
            var clock = Date(timeIntervalSince1970: 1_790_000_000)
            let api = Transport(), session = try BotSession(api: api, vault: vault, now: { clock })
            await session.refresh(); try session.setConsent(true)
            session.draft = "First prompt"; await session.send()
            clock = clock.addingTimeInterval(-60)
            session.draft = "Second prompt"; await session.send()
            let expected = ["First prompt", "Coffee tomorrow sounds good.", "Second prompt", "Coffee tomorrow sounds good."]
            XCTAssertEqual(session.messages.map(\.text), expected)
            let timeKeys = session.messages.map { String($0.key.prefix(20)) }
            for (earlier, later) in zip(timeKeys, timeKeys.dropFirst()) {
                XCTAssertLessThan(earlier, later, "Conversation order must never depend on random UUID sorting")
            }
            XCTAssertEqual(try BotSession(api: api, vault: vault).messages.map(\.text), expected)
            XCTAssertEqual(api.requests.filter { $0.1 == "/v1/bot/messages" }.count, 2)
        }
    }

}
