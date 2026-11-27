import Foundation
import XCTest
@testable import Vipi

@MainActor final class BotSessionTests: XCTestCase {
    private final class Generator: LocalBotGenerating {
        let provider = "apple-foundation-models"
        let maximumContextBytes = 3072
        var state: LocalBotAvailability = .ready
        var failure: LocalBotFailure?
        var calls: [[LocalBotTurn]] = []
        var pause = false
        var held: CheckedContinuation<Void, Never>?
        var started: CheckedContinuation<Void, Never>?
        func availability(language: String) -> LocalBotAvailability { state }
        func waitUntilStarted() async {
            if held != nil { return }
            await withCheckedContinuation { started = $0 }
        }
        func finish() {
            let value = held
            held = nil
            value?.resume()
        }
        func reply(to turns: [LocalBotTurn], language: String) async throws -> String {
            calls.append(turns)
            if pause {
                await withCheckedContinuation {
                    held = $0
                    started?.resume()
                    started = nil
                }
            }
            if let failure { throw failure }
            return "Coffee tomorrow sounds good."
        }
    }
    private final class Transport: ChatTransport {
        var requests: [(String, Data?)] = []
        var failReport = false
        func request<T: Decodable>(
            _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
            as type: T.Type
        ) async throws -> T {
            requests.append((path, body))
            guard method == "POST", ["/v1/bot/local-reports", "/v1/bot/reports"].contains(path), device != nil else {
                XCTFail("Generation or availability must not call the server: \(path)")
                throw URLError(.unsupportedURL)
            }
            if failReport { throw URLError(.timedOut) }
            let request = try JSONSerialization.jsonObject(with: XCTUnwrap(body)) as! [String: Any]
            var response: [String: Any] = ["reported": true]
            if let id = request["report_id"] { response["report_id"] = id }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: response))
        }
    }
    private func withVault(_ body: (MessageVault) async throws -> Void) async throws {
        let account = UUID()
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("vipi-bot-test-" + UUID().uuidString)
        let vault = try MessageVault(account: account, directory: folder)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: folder)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        let device = DeviceCredential(id: UUID(), secret: String(repeating: "x", count: 43))
        try vault.transaction {
            try vault.put("local", "service-device", JSONEncoder().encode(device))
            try vault.put("local", "registered-device", Data(device.id.uuidString.lowercased().utf8))
        }
        try await body(vault)
    }

    func testLocalConversationNeedsNoCloudConsentPurchaseOrDeviceCredential() async throws {
        try await withVault { vault in
            try vault.transaction {
                try vault.put("message", "private-friend", Data("Friend-only secret".utf8))
                try vault.remove("local", "registered-device")
            }
            let api = Transport(), engine = Generator()
            let session = try BotSession(api: api, vault: vault, generator: engine)
            await session.refresh()
            session.draft = "Coffee tomorrow?"
            await session.send()
            XCTAssertEqual(session.messages.map(\.state), ["complete", "complete"])
            XCTAssertEqual(engine.calls.first?.map(\.content), ["Coffee tomorrow?"])
            XCTAssertTrue(api.requests.isEmpty)
            let reopened = try BotSession(api: api, vault: vault, generator: engine)
            XCTAssertEqual(reopened.messages.map(\.text), session.messages.map(\.text))
            await reopened.refresh()
            reopened.draft = "At noon?"
            await reopened.send()
            XCTAssertEqual(
                engine.calls.last?.map(\.content), ["Coffee tomorrow?", "Coffee tomorrow sounds good.", "At noon?"])
            XCTAssertTrue(api.requests.isEmpty)
        }
    }
    func testUnavailableAndOversizedMessagesRetainEditableDraftAcrossReopen() async throws {
        try await withVault { vault in
            let api = Transport(), engine = Generator()
            engine.state = .unavailable("Device unavailable")
            let session = try BotSession(api: api, vault: vault, generator: engine)
            await session.refresh()
            session.draft = "Keep my words"
            session.saveDraft()
            await session.send()
            XCTAssertEqual(session.draft, "Keep my words")
            XCTAssertTrue(session.messages.isEmpty)
            engine.state = .ready
            await session.refresh()
            session.draft = String(repeating: "界", count: 1025)
            session.saveDraft()
            await session.send()
            XCTAssertFalse(session.canSend)
            XCTAssertTrue(engine.calls.isEmpty)
            XCTAssertEqual(try BotSession(api: api, vault: vault, generator: engine).draft, session.draft)
            session.draft = "Shortened café ☕"
            await session.send()
            XCTAssertEqual(engine.calls.count, 1)
            XCTAssertTrue(api.requests.isEmpty)
        }
    }
    func testFailureRestoresDraftAndNeverReplaysOnReopen() async throws {
        try await withVault { vault in
            let api = Transport(), engine = Generator()
            engine.failure = .busy
            let session = try BotSession(api: api, vault: vault, generator: engine)
            await session.refresh()
            session.draft = "Hello"
            await session.send()
            XCTAssertEqual(session.messages.first?.state, "stopped")
            XCTAssertEqual(session.draft, "Hello")
            let reopened = try BotSession(api: api, vault: vault, generator: engine)
            await reopened.refresh()
            XCTAssertEqual(reopened.draft, "Hello")
            XCTAssertEqual(engine.calls.count, 1)
            XCTAssertEqual(
                BotSession.context(history: reopened.messages, newText: "Next", maximumBytes: 3072)?.map(\.content),
                ["Next"])
        }
    }
    func testBackgroundCancellationIgnoresLateResultAndPreservesNewerDraft() async throws {
        try await withVault { vault in
            let api = Transport(), engine = Generator()
            engine.pause = true
            let session = try BotSession(api: api, vault: vault, generator: engine)
            await session.refresh()
            session.draft = "First message"
            let sending = Task { await session.send() }
            await engine.waitUntilStarted()
            session.draft = "A newer draft"
            session.saveDraft()
            session.cancelGeneration()
            engine.finish()
            await sending.value
            XCTAssertEqual(session.messages.map(\.state), ["stopped"])
            XCTAssertEqual(session.draft, "A newer draft")
            XCTAssertEqual(try BotSession(api: api, vault: vault, generator: engine).draft, "A newer draft")
            XCTAssertTrue(api.requests.isEmpty)
        }
    }
    func testInterruptedLocalSendIsRestoredWithoutTouchingLegacyUnconfirmedCloudMessage() async throws {
        try await withVault { vault in
            var interrupted = BotMessage(
                id: UUID(), role: "user", text: "Interrupted local message", createdAt: Date(), state: "sending")
            interrupted.provider = "apple-foundation-models"
            try vault.transaction { try vault.put("bot-message", interrupted.key, JSONEncoder().encode(interrupted)) }
            let engine = Generator(), session = try BotSession(api: Transport(), vault: vault, generator: engine)
            XCTAssertEqual(session.draft, interrupted.text)
            XCTAssertEqual(session.messages.first?.state, "stopped")
            XCTAssertTrue(engine.calls.isEmpty)
        }
    }
    func testContextKeepsLatestMessageWholeAndLimitsHistoryByUTF8() throws {
        let history = (0..<20).map { index in
            BotMessage(
                id: UUID(), role: index.isMultiple(of: 2) ? "user" : "assistant",
                text: String(repeating: "猫", count: 300), createdAt: Date(), state: "complete")
        }
        let values = try XCTUnwrap(BotSession.context(history: history, newText: "Coffee?", maximumBytes: 3072))
        XCTAssertLessThanOrEqual(values.count, 12)
        XCTAssertLessThanOrEqual(values.reduce(0) { $0 + $1.content.utf8.count }, 3072)
        XCTAssertEqual(values.last?.content, "Coffee?")
        XCTAssertNil(BotSession.context(history: [], newText: String(repeating: "猫", count: 1025), maximumBytes: 3072))
    }
    func testSelectedLocalReportHasStableRetryIdentityAndNoOtherChatContent() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault, generator: Generator())
            var selected = BotMessage(
                id: UUID(), role: "assistant", text: String(repeating: "猫", count: 2000), createdAt: Date(),
                state: "complete")
            selected.requestID = UUID()
            selected.provider = "apple-foundation-models"
            api.failReport = true
            do {
                try await session.report(selected, reason: "inaccurate")
                XCTFail("Unconfirmed report must throw")
            } catch {}
            api.failReport = false
            let reopened = try BotSession(api: api, vault: vault, generator: Generator())
            try await reopened.report(selected, reason: "inaccurate")
            let first = try JSONSerialization.jsonObject(with: XCTUnwrap(api.requests.first?.1)) as! [String: String]
            let second = try JSONSerialization.jsonObject(with: XCTUnwrap(api.requests.last?.1)) as! [String: String]
            XCTAssertEqual(first, second)
            XCTAssertEqual(Set(first.keys), ["report_id", "provider", "reason", "selected_reply", "consent_version"])
            XCTAssertLessThanOrEqual(try XCTUnwrap(first["selected_reply"]).utf8.count, 4000)
            XCTAssertEqual(first["consent_version"], "local-bot-report-v1")
            XCTAssertTrue(api.requests.allSatisfy { $0.0 == "/v1/bot/local-reports" })
            try await reopened.report(selected, reason: "other")
            let changed = try JSONSerialization.jsonObject(with: XCTUnwrap(api.requests.last?.1)) as! [String: String]
            XCTAssertNotEqual(first["report_id"], changed["report_id"])
        }
    }
    func testHistoricCloudReplyRetainsItsOriginalReportEndpoint() async throws {
        try await withVault { vault in
            let api = Transport(), session = try BotSession(api: api, vault: vault, generator: Generator())
            var selected = BotMessage(
                id: UUID(), role: "assistant", text: "Historic reply", createdAt: Date(), state: "complete")
            selected.requestID = UUID()
            try await session.report(selected, reason: "inaccurate")
            XCTAssertEqual(api.requests.last?.0, "/v1/bot/reports")
        }
    }
    func testOwnerDisposalPreventsLateReplyFromRecreatingErasedAccount() async throws {
        try await withVault { vault in
            let api = Transport(), engine = Generator(), owner = BotConversationOwner()
            engine.pause = true
            let session = try XCTUnwrap(
                owner.session(for: vault.account) { try BotSession(api: api, vault: vault, generator: engine) })
            XCTAssertTrue(
                try owner.session(for: vault.account) {
                    XCTFail("Recreated live owner")
                    return nil
                } === session)
            XCTAssertThrowsError(
                try owner.session(for: UUID()) {
                    XCTFail("Cross-account owner")
                    return nil
                })
            await session.refresh()
            session.draft = "Keep private"
            let sending = Task { await session.send() }
            await engine.waitUntilStarted()
            try owner.close()
            let folder = vault.url.deletingLastPathComponent()
            try FileManager.default.removeItem(at: folder)
            try KeychainStore.deleteChecked(account: "messages-" + vault.account.uuidString.lowercased())
            engine.finish()
            await sending.value
            XCTAssertTrue(session.messages.isEmpty)
            XCTAssertTrue(session.draft.isEmpty)
            XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
            XCTAssertFalse(session.canSend)
            XCTAssertTrue(api.requests.isEmpty)
        }
    }
    func testClockCorrectionPreservesConversationOrderAfterReopen() async throws {
        try await withVault { vault in
            var clock = Date(timeIntervalSince1970: 1_790_000_000)
            let api = Transport(), engine = Generator()
            let session = try BotSession(api: api, vault: vault, generator: engine, now: { clock })
            await session.refresh()
            session.draft = "First prompt"
            await session.send()
            clock = clock.addingTimeInterval(-60)
            session.draft = "Second prompt"
            await session.send()
            let reopened = try BotSession(api: api, vault: vault, generator: engine)
            XCTAssertEqual(
                reopened.messages.map(\.text),
                ["First prompt", "Coffee tomorrow sounds good.", "Second prompt", "Coffee tomorrow sounds good."])
            for (a, b) in zip(reopened.messages, reopened.messages.dropFirst()) { XCTAssertLessThan(a.key, b.key) }
        }
    }
}
