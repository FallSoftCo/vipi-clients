import XCTest
import StoreKit
import StoreKitTest
@testable import Vipi

/// Real StoreKit 2 client behavior against Apple's local zero-charge test
/// environment. The service transport is a fixture, not provider verification.
@MainActor final class SubscriptionStoreTests: XCTestCase {
    private final class Service: ChatTransport {
        let account = UUID()
        var ready = true, base = false, bot = false, botService = true
        var rejectSubmission = false
        var historicalAccount: UUID?
        var responseAccount: UUID?
        var submitted = 0
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            if path == "/v1/bot/allowance" {
                return try decode(["available": base && bot && botService, "service_ready": botService, "remaining_replies": 150, "monthly_replies": 150, "resets_at": "2026-12-01T00:00:00Z", "max_context_bytes": 8192], as: type)
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
            return try decode(["server_time": clock.string(from: now), "base": ["active": base, "expires_at": expiry], "bot_mini": ["active": bot, "available": base && bot, "expires_at": expiry], "billing_account_id": "local-test-only", "app_account_token": (responseAccount ?? account).uuidString, "purchases_ready": ["apple": ready, "google": false]], as: type)
        }
        private func decode<T: Decodable>(_ value: [String: Any], as type: T.Type) throws -> T {
            try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    private func environment() async throws -> SKTestSession {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "Vipi", withExtension: "storekit"))
        let session = try SKTestSession(contentsOf: file)
        // Some iOS simulator versions log configuration failure without
        // throwing from init. Require a working test-only service operation
        // before loading products or exercising any purchase API.
        try await session.setSimulatedError(nil, forAPI: .purchase)
        session.resetToDefaultState(); session.disableDialogs = true; session.clearTransactions()
        return session
    }
    func testSeparateAnnualTrialsAndServiceReadiness() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service(); api.ready = false
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start()
        XCTAssertEqual(Set(store.products.keys), Set(VipiPlan.allCases))
        XCTAssertEqual(store.introductoryEligible, Set(VipiPlan.allCases))
        XCTAssertNotEqual(store.products[.base]?.subscription?.subscriptionGroupID, store.products[.botMini]?.subscription?.subscriptionGroupID)
        XCTAssertFalse(store.canPurchase(.base)); XCTAssertFalse(store.canPurchase(.botMini)); XCTAssertTrue(environment.allTransactions().isEmpty)
        api.ready = true; await store.refresh()
        XCTAssertTrue(store.canPurchase(.base)); XCTAssertFalse(store.canPurchase(.botMini))
        await store.purchase(.base)
        XCTAssertTrue(store.baseActive); XCTAssertFalse(store.botAvailable)
        XCTAssertEqual(environment.allTransactions().count, 1)
        api.botService = false; await store.refresh(); XCTAssertFalse(store.canPurchase(.botMini))
        api.botService = true; await store.refresh(); XCTAssertTrue(store.canPurchase(.botMini))
    }
    func testUnconfirmedChargeStaysUnfinishedAndPreventsAnotherPurchase() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service(); api.rejectSubmission = true
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start(); await store.purchase(.base)
        XCTAssertFalse(store.baseActive); XCTAssertFalse(store.canPurchase(.base)); XCTAssertTrue(store.awaitingConfirmation.contains(.base))
        var unfinished = 0
        for await result in Transaction.unfinished { if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { unfinished += 1 } }
        XCTAssertEqual(unfinished, 1)
        api.rejectSubmission = false; await store.start()
        XCTAssertTrue(store.baseActive); XCTAssertFalse(store.awaitingConfirmation.contains(.base))
        var remaining = 0
        for await result in Transaction.unfinished { if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { remaining += 1 } }
        XCTAssertEqual(remaining, 0); XCTAssertGreaterThanOrEqual(api.submitted, 2)
    }
    func testServerOwnershipRejectionBlocksAnotherChargeAndAllowsVerifiedRetry() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let other = UUID()
        let transaction = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(other)])
        XCTAssertEqual(transaction.environment, .xcode)
        let api = Service()
        let actual = SubscriptionStore(api: api, accountToken: api.account); defer { actual.close() }
        await actual.start()
        XCTAssertFalse(actual.baseActive); XCTAssertFalse(actual.canPurchase(.base)); XCTAssertGreaterThanOrEqual(api.submitted, 1)
        XCTAssertTrue(actual.accountConflicts.contains(.base))
        XCTAssertFalse(actual.awaitingConfirmation.contains(.base))
        // A later explicit, server-verified identity link can make the old
        // purchase rightful. Conflict UI must not permanently block restore.
        api.historicalAccount = other
        await actual.start()
        XCTAssertTrue(actual.baseActive)
        XCTAssertFalse(actual.accountConflicts.contains(.base))
        XCTAssertFalse(actual.awaitingConfirmation.contains(.base))
    }
    func testOldProfileTokenReachesServiceAndFinishesOnlyAfterCurrentAccountReadback() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let old = UUID()
        _ = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(old)])
        let api = Service(); api.historicalAccount = old
        let actual = SubscriptionStore(api: api, accountToken: api.account); defer { actual.close() }
        await actual.start()
        XCTAssertGreaterThanOrEqual(api.submitted, 1); XCTAssertTrue(actual.baseActive)
        var unfinished = 0
        for await result in Transaction.unfinished { if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { unfinished += 1 } }
        XCTAssertEqual(unfinished, 0)
    }
    func testRestoredOldTokenCannotFinishOnWrongCurrentAccountReadback() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let old = UUID()
        _ = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(old)])
        let api = Service(); api.historicalAccount = old; api.responseAccount = UUID()
        let actual = SubscriptionStore(api: api, accountToken: api.account); defer { actual.close() }
        await actual.start()
        XCTAssertGreaterThanOrEqual(api.submitted, 1); XCTAssertFalse(actual.baseActive)
        var unfinished = 0
        for await result in Transaction.unfinished { if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { unfinished += 1 } }
        XCTAssertEqual(unfinished, 1)
    }
}
