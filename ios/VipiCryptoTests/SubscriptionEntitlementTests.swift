import XCTest
@testable import Vipi

@MainActor final class SubscriptionEntitlementTests: SubscriptionFixture {
    func testFreeServiceSnapshotGrantsFriendChatWithoutTrialOrCheckout() async throws {
        let api = Service()
        let store = SubscriptionStore(
            api: api, accountToken: api.account,
            loadProducts: {
                XCTFail("Reading free access must never load a store catalog")
                return []
            })
        defer { store.close() }
        let snapshot = try JSONDecoder().decode(
            EntitlementSnapshot.self,
            from: Data(
                """
                {"billing_account_id":"free-test","app_account_token":"\(api.account.uuidString)",
                 "server_time":"2026-11-21T12:00:00Z","purchases_ready":{"apple":false,"google":false},
                 "base":{"active":true,"expires_at":null,"trial_ends_at":null,"access_source":"free"},
                 "bot_mini":{"active":false,"available":false,"expires_at":null,"trial_ends_at":null}}
                """.utf8))
        try store.accept(snapshot, capturedAt: .now)
        XCTAssertTrue(store.baseActive)
        XCTAssertFalse(store.accessVerificationPending(.base))
        XCTAssertFalse(store.botAvailable)
        XCTAssertFalse(store.purchaseReady)
        for plan in VipiPlan.allCases {
            XCTAssertFalse(store.canPurchase(plan))
        }
        XCTAssertEqual(api.submitted, 0)
    }

    /// These domain/network regressions use the actual store and deferred
    /// transport. Applying a service snapshot is not StoreKit verification.
    func testDeferredEntitlementRefreshPreservesAcceptedServiceSnapshot() async throws {
        let api = Service()
        api.ready = false
        api.pauseNextEntitlements = true
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        let refreshing = Task { await store.refreshEntitlements() }
        defer {
            api.finishEntitlements()
            refreshing.cancel()
        }
        try await waitForState("deferred entitlement response captured") { api.pendingEntitlements != nil }
        api.base = true
        api.ready = true
        let confirmed: EntitlementSnapshot = try await api.request("GET", "/v1/entitlements")
        try store.accept(confirmed, capturedAt: .now)
        XCTAssertTrue(store.baseActive)
        api.finishEntitlements()
        await refreshing.value
        XCTAssertTrue(store.baseActive, "An older GET must not replace the newer accepted service snapshot")
        XCTAssertTrue(store.snapshot?.base.active == true)
        XCTAssertTrue(store.purchaseReady)
        XCTAssertEqual(api.submitted, 0)
        XCTAssertTrue(store.products.isEmpty)
        // A subsequent authoritative change still applies; this is ordering,
        // not a permanent override that preserves active access.
        api.base = false
        api.ready = false
        await store.refreshEntitlements()
        XCTAssertFalse(store.baseActive)
        XCTAssertFalse(store.purchaseReady)
    }
    func testDeferredEntitlementFailureCannotReplaceAcceptedServiceReadinessOrNotice() async throws {
        let api = Service()
        api.pauseNextEntitlements = true
        api.failDeferredEntitlements = true
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        let refreshing = Task { await store.refreshEntitlements() }
        defer {
            api.finishEntitlements()
            refreshing.cancel()
        }
        try await waitForState("deferred failing entitlement response captured") { api.pendingEntitlements != nil }
        api.base = true
        let confirmed: EntitlementSnapshot = try await api.request("GET", "/v1/entitlements")
        try store.accept(confirmed, capturedAt: .now)
        store.notice = "Current service confirmation"
        api.finishEntitlements()
        await refreshing.value
        XCTAssertTrue(store.baseActive)
        XCTAssertTrue(store.purchaseReady)
        XCTAssertEqual(store.notice, "Current service confirmation")
        XCTAssertEqual(api.submitted, 0)
        XCTAssertTrue(store.products.isEmpty)
    }
    func testRejectedAccountSnapshotDoesNotSupersedeDeferredRefresh() async throws {
        let api = Service()
        api.ready = false
        api.pauseNextEntitlements = true
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        let refreshing = Task { await store.refreshEntitlements() }
        defer {
            api.finishEntitlements()
            refreshing.cancel()
        }
        try await waitForState("deferred account-bound entitlement response captured") {
            api.pendingEntitlements != nil
        }
        api.base = true
        api.ready = true
        api.responseAccount = UUID()
        let wrongAccount: EntitlementSnapshot = try await api.request("GET", "/v1/entitlements")
        XCTAssertThrowsError(try store.accept(wrongAccount, capturedAt: .now))
        XCTAssertNil(store.snapshot)
        XCTAssertFalse(store.purchaseReady)
        api.finishEntitlements()
        await refreshing.value
        XCTAssertEqual(store.snapshot?.app_account_token, api.account)
        XCTAssertFalse(store.baseActive)
        XCTAssertFalse(store.purchaseReady)
        XCTAssertEqual(api.submitted, 0)
        XCTAssertTrue(store.products.isEmpty)
    }
}
