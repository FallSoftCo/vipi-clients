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
        var cardlessTrial = false
        var rejectSubmission = false
        var historicalAccount: UUID?
        var responseAccount: UUID?
        var submitted = 0
        var pauseNextEntitlements = false
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
            }
            return captured
        }
        private func decode<T: Decodable>(_ value: [String: Any], as type: T.Type) throws -> T {
            try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    private func environment(resource: String = "Vipi") async throws -> SKTestSession {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: resource, withExtension: "storekit"))
        let session = try SKTestSession(contentsOf: file)
        // Some iOS simulator versions log configuration failure without
        // throwing from init. Require a working test-only service operation
        // before loading products or exercising any purchase API.
        try await session.setSimulatedError(nil, forAPI: .purchase)
        session.resetToDefaultState(); session.disableDialogs = true; session.clearTransactions()
        return session
    }
    private enum StoreKitWaitFailure: Error { case timedOut }
    /// StoreKit publishes transactions asynchronously even after purchase()
    /// returns. Keep the expected state strict while bounding that propagation.
    private func waitForStoreKit(_ description: String, file: StaticString = #filePath, line: UInt = #line,
                                 until condition: @MainActor () async -> Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while !(await condition()) {
            guard ContinuousClock.now < deadline else {
                XCTFail("Timed out waiting for StoreKit: \(description)", file: file, line: line)
                throw StoreKitWaitFailure.timedOut
            }
            try await Task.sleep(for: .milliseconds(25))
        }
    }
    private func unfinishedBaseCount() async -> Int {
        var count = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { count += 1 }
        }
        return count
    }
    func testBaseAnnualWithoutExtraTrialAndSeparateBotMiniTrialRespectServiceReadiness() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service(); api.ready = false
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start()
        XCTAssertEqual(Set(store.products.keys), Set(VipiPlan.allCases))
        XCTAssertEqual(store.introductoryEligible, [.botMini])
        XCTAssertNil(store.products[.base]?.subscription?.introductoryOffer)
        XCTAssertEqual(store.products[.base]?.price, Decimal(12))
        XCTAssertEqual(store.products[.botMini]?.subscription?.introductoryOffer?.period.unit, .month)
        XCTAssertEqual(store.products[.botMini]?.subscription?.introductoryOffer?.period.value, 1)
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
    func testUnexpectedBaseStoreTrialBlocksCheckoutWithoutCreatingTransaction() async throws {
        let environment = try await environment(resource: "VipiWrongBaseTrial")
        defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service()
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start()
        XCTAssertTrue(store.purchaseReady)
        XCTAssertTrue(store.introductoryEligible.contains(.base))
        XCTAssertTrue(store.baseStoreTrialStillOffered)
        XCTAssertFalse(store.canPurchase(.base))
        await store.purchase(.base)
        XCTAssertTrue(environment.allTransactions().isEmpty)
        XCTAssertEqual(api.submitted, 0)
    }
    func testOlderRefreshCannotReplaceServiceConfirmedStoreKitPurchase() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service()
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start()
        XCTAssertFalse(store.baseActive)
        api.ready = false; api.pauseNextEntitlements = true
        let refreshing = Task { await store.refresh() }
        defer { api.finishEntitlements(); refreshing.cancel() }
        try await waitForStoreKit("older entitlement response captured before purchase") { api.pendingEntitlements != nil }
        api.ready = true
        let transaction = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(api.account)])
        XCTAssertEqual(transaction.environment, .xcode)
        try await waitForStoreKit("transaction listener accepts service-confirmed access") {
            api.submitted > 0 && store.baseActive && !store.awaitingConfirmation.contains(.base)
        }
        api.finishEntitlements()
        await refreshing.value
        XCTAssertTrue(store.baseActive, "An older GET must not undo the accepted purchase response")
        XCTAssertTrue(store.snapshot?.base.active == true)
        XCTAssertTrue(store.purchaseReady, "Readiness belongs to the latest accepted service snapshot")
        XCTAssertFalse(store.canPurchase(.base), "The confirmed purchase must not offer another charge")
        XCTAssertEqual(environment.allTransactions().count, 1)
    }
    func testCardlessBaseTrialPreventsPaidBaseCheckoutAndLeavesBotMiniOptional() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service(); api.cardlessTrial = true
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start()
        XCTAssertTrue(store.baseActive); XCTAssertFalse(store.canPurchase(.base))
        XCTAssertTrue(store.canPurchase(.botMini)); XCTAssertFalse(store.botAvailable)
        await store.purchase(.base)
        XCTAssertTrue(environment.allTransactions().isEmpty); XCTAssertEqual(api.submitted, 0)
        api.cardlessTrial = false; await store.refresh()
        XCTAssertFalse(store.baseActive); XCTAssertTrue(store.canPurchase(.base)); XCTAssertFalse(store.canPurchase(.botMini))
    }
    func testUnconfirmedChargeStaysUnfinishedAndPreventsAnotherPurchase() async throws {
        let environment = try await environment(); defer { environment.clearTransactions(); environment.resetToDefaultState() }
        let api = Service(); api.rejectSubmission = true
        let store = SubscriptionStore(api: api, accountToken: api.account); defer { store.close() }
        await store.start(); await store.purchase(.base)
        XCTAssertFalse(store.baseActive); XCTAssertFalse(store.canPurchase(.base)); XCTAssertTrue(store.awaitingConfirmation.contains(.base))
        try await waitForStoreKit("denied purchase remains unfinished") { await self.unfinishedBaseCount() == 1 }
        var unfinished = 0
        for await result in Transaction.unfinished { if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { unfinished += 1 } }
        XCTAssertEqual(unfinished, 1)
        // An explicit second checkout remains blocked while the service is
        // unavailable. Reading/receiving the transaction must never finish it.
        await store.purchase(.base)
        XCTAssertEqual(environment.allTransactions().count, 1)
        XCTAssertFalse(store.baseActive); XCTAssertFalse(store.canPurchase(.base))
        XCTAssertTrue(store.awaitingConfirmation.contains(.base))
        let stillUnfinished = await unfinishedBaseCount()
        XCTAssertEqual(stillUnfinished, 1)
        api.rejectSubmission = false; await store.start()
        try await waitForStoreKit("service-confirmed purchase becomes active") {
            store.baseActive && !store.awaitingConfirmation.contains(.base)
        }
        XCTAssertTrue(store.baseActive); XCTAssertFalse(store.awaitingConfirmation.contains(.base))
        try await waitForStoreKit("confirmed purchase is finished") { await self.unfinishedBaseCount() == 0 }
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
