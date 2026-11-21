import XCTest
@testable import Vipi

@MainActor class SubscriptionFixture: XCTestCase {
    final class Service: ChatTransport {
        let account = UUID()
        var ready = true, base = false, bot = false, botService = true
        var cardlessTrial = false
        var rejectSubmission = false
        var historicalAccount: UUID?
        var responseAccount: UUID?
        var submitted = 0
        var pauseNextEntitlements = false
        var failDeferredEntitlements = false
        var pendingEntitlements: CheckedContinuation<Void, Never>?
        func finishEntitlements() {
            let pending = pendingEntitlements; pendingEntitlements = nil; pending?.resume()
        }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            if path == "/v1/bot/allowance" {
                return try decode(["available": (base || cardlessTrial) && bot && botService, "service_ready": botService, "remaining_replies": 150, "monthly_replies": 150, "resets_at": "2026-12-01T00:00:00Z", "max_context_bytes": 8192], as: type)
            }
            if path == "/v1/purchases/apple" {
                submitted += 1
                if rejectSubmission { throw URLError(.notConnectedToInternet) }
                let request = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: String])
                let jws = try XCTUnwrap(request["signed_transaction_info"])
                let pieces = jws.split(separator: "."); XCTAssertEqual(pieces.count, 3)
                var payload = String(pieces[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
                while payload.count % 4 != 0 { payload += "=" }
                let object = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(Data(base64Encoded: payload))) as? [String: Any])
                XCTAssertEqual(object["environment"] as? String, "Xcode", "Only local zero-charge StoreKit transactions belong in this test")
                let token = (object["appAccountToken"] as? String).flatMap(UUID.init(uuidString:))
                guard token == account || (historicalAccount != nil && token == historicalAccount) else {
                    throw ServiceFailure(status: 409, code: "purchase_account_mismatch")
                }
                if object["productId"] as? String == VipiPlan.base.rawValue { base = true }
                if object["productId"] as? String == VipiPlan.botMini.rawValue { bot = true }
            }
            let clock = ISO8601DateFormatter()
            let now = Date()
            let expiry = clock.string(from: now.addingTimeInterval(365 * 24 * 60 * 60))
            let trialEnd = clock.string(from: now.addingTimeInterval(30 * 24 * 60 * 60))
            let captured = try decode(["server_time": clock.string(from: now), "base": ["active": base || cardlessTrial,
                "expires_at": cardlessTrial && !base ? trialEnd : expiry,
                "access_source": base ? "store" : "cardless_trial",
                "cardless_trial": ["active": cardlessTrial, "started_at": clock.string(from: now), "ends_at": trialEnd]],
                "bot_mini": ["active": bot, "available": (base || cardlessTrial) && bot, "expires_at": expiry],
                "billing_account_id": "local-test-only", "app_account_token": (responseAccount ?? account).uuidString,
                "purchases_ready": ["apple": ready, "google": false]], as: type)
            if path == "/v1/entitlements" && pauseNextEntitlements {
                pauseNextEntitlements = false
                await withCheckedContinuation { pendingEntitlements = $0 }
                if failDeferredEntitlements { throw URLError(.notConnectedToInternet) }
            }
            return captured
        }
        private func decode<T: Decodable>(_ value: [String: Any], as type: T.Type) throws -> T {
            try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    private enum StateWaitFailure: Error { case timedOut }
    /// Bound asynchronous transaction propagation and deferred transport setup
    /// while keeping each expected state strict.
    func waitForState(_ description: String, file: StaticString = #filePath, line: UInt = #line,
                                 until condition: @MainActor () async -> Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while !(await condition()) {
            guard ContinuousClock.now < deadline else {
                XCTFail("Timed out waiting for state: \(description)", file: file, line: line)
                throw StateWaitFailure.timedOut
            }
            try await Task.sleep(for: .milliseconds(25))
        }
    }
}
