import XCTest
import StoreKit
import StoreKitTest
@testable import Vipi

/// Real StoreKit 2 client behavior against Apple's local zero-charge test
/// environment. The service transport is a fixture, not provider verification.
@MainActor final class SubscriptionStoreTests: SubscriptionFixture {
    private func environment(resource: String = "Vipi") async throws -> SKTestSession {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: resource, withExtension: "storekit"))
        let session = try SKTestSession(contentsOf: file)
        session.resetToDefaultState()
        session.disableDialogs = true
        session.clearTransactions()
        // Clearing nil returned successfully on a broken local service while
        // configuration writes logged Code3. Require a non-nil test condition
        // to round-trip and clear before loading products or attempting a buy.
        print("VIPI_STOREKIT_READINESS begin")
        let probe = SKTestFailures.Purchase.generic(.notAvailableInStorefront)
        do {
            try await session.setSimulatedError(probe, forAPI: .purchase)
            let observed = await session.simulatedError(forAPI: .purchase)
            guard observed == probe else { throw LocalStoreKitReadinessFailure.overrideNotObserved }
            print("VIPI_STOREKIT_READINESS override_observed")
            try await session.setSimulatedError(nil, forAPI: .purchase)
            let cleared = await session.simulatedError(forAPI: .purchase)
            guard cleared == nil else { throw LocalStoreKitReadinessFailure.overrideNotCleared }
        } catch {
            try? await session.setSimulatedError(nil, forAPI: .purchase)
            throw error
        }
        // A nil override readback alone did not restore Product.purchase on
        // the qualified native host. Reset every documented session override
        // after the positive probe, then restore automatic local dialogs.
        session.resetToDefaultState()
        session.disableDialogs = true
        let baseline = await session.simulatedError(forAPI: .purchase)
        guard baseline == nil, session.allTransactions().isEmpty else {
            throw LocalStoreKitReadinessFailure.overrideNotCleared
        }
        print("VIPI_STOREKIT_READINESS configuration_reset_ready")
        print("VIPI_STOREKIT_READINESS ready")
        return session
    }
    private enum LocalStoreKitReadinessFailure: Error { case overrideNotObserved, overrideNotCleared }
    private func unfinishedBaseCount() async -> Int {
        var count = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue { count += 1 }
        }
        return count
    }
    func testLocalReadinessRoundTripMakesNoTransaction() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        XCTAssertTrue(environment.allTransactions().isEmpty)
    }
    func testExplicitRestoreReconcilesFinishedXcodeTransactionIntoFreshStore() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        let original = SubscriptionStore(api: api, accountToken: api.account)
        defer { original.close() }
        await original.start()
        await original.purchase(.base)
        try await waitForState("original local purchase accepted and finished") {
            let unfinished = await self.unfinishedBaseCount()
            return original.baseActive && !original.awaitingConfirmation.contains(.base) && unfinished == 0
        }
        XCTAssertEqual(environment.allTransactions().count, 1)
        var verifiedXcode = false
        // Finishing/accepting a purchase can precede StoreKit's asynchronous
        // current-entitlement propagation. Observe the actual verified result
        // instead of treating the first empty enumeration as final.
        try await waitForState("verified finished Xcode entitlement becomes observable") {
            for await item in Transaction.currentEntitlements {
                if case .verified(let transaction) = item, transaction.productID == VipiPlan.base.rawValue {
                    XCTAssertEqual(transaction.environment, .xcode)
                    XCTAssertEqual(transaction.appAccountToken, api.account)
                    verifiedXcode = transaction.environment == .xcode && transaction.appAccountToken == api.account
                }
            }
            return verifiedXcode
        }
        XCTAssertTrue(verifiedXcode, "Explicit restore may run only with an existing verified local Xcode purchase")
        guard verifiedXcode else { return }
        let submissions = api.submitted
        original.close()
        // A fresh client owner sees a stale/inactive service response first.
        // Only actual AppStore.sync + production reconciliation may restore it.
        api.base = false
        let restored = SubscriptionStore(api: api, accountToken: api.account)
        defer { restored.close() }
        await restored.refreshEntitlements()
        XCTAssertFalse(restored.baseActive)
        await restored.restore()
        try await waitForState("explicit restore re-verifies finished local entitlement") {
            restored.baseActive && !restored.awaitingConfirmation.contains(.base)
        }
        XCTAssertGreaterThan(api.submitted, submissions)
        XCTAssertEqual(environment.allTransactions().count, 1, "Restore must not create another checkout")
        XCTAssertFalse(restored.canPurchase(.base))
        let unfinished = await unfinishedBaseCount()
        XCTAssertEqual(unfinished, 0)
    }
    func testBaseAnnualWithoutExtraTrialAndNoNewBotMiniPurchase() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        api.ready = false
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        await store.start()
        XCTAssertEqual(Set(store.products.keys), [.base])
        XCTAssertTrue(store.introductoryEligible.isEmpty)
        XCTAssertNil(store.products[.base]?.subscription?.introductoryOffer)
        XCTAssertEqual(store.products[.base]?.price, Decimal(12))
        XCTAssertFalse(store.canPurchase(.base))
        XCTAssertFalse(store.canPurchase(.botMini))
        XCTAssertTrue(environment.allTransactions().isEmpty)
        api.ready = true
        await store.refresh()
        XCTAssertTrue(store.canPurchase(.base))
        XCTAssertFalse(store.canPurchase(.botMini))
        await store.purchase(.base)
        XCTAssertTrue(store.baseActive)
        XCTAssertFalse(store.botAvailable)
        XCTAssertEqual(environment.allTransactions().count, 1)
        api.botService = false
        await store.refresh()
        XCTAssertFalse(store.canPurchase(.botMini))
        api.botService = true
        await store.refresh()
        XCTAssertFalse(store.canPurchase(.botMini))
    }
    func testUnexpectedBaseStoreTrialBlocksCheckoutWithoutCreatingTransaction() async throws {
        let environment = try await environment(resource: "VipiWrongBaseTrial")
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
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
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        await store.start()
        XCTAssertFalse(store.baseActive)
        api.ready = false
        api.pauseNextEntitlements = true
        let refreshing = Task { await store.refresh() }
        defer {
            api.finishEntitlements()
            refreshing.cancel()
        }
        try await waitForState("older entitlement response captured before purchase") { api.pendingEntitlements != nil }
        api.ready = true
        let transaction = try await environment.buyProduct(
            identifier: VipiPlan.base.rawValue, options: [.appAccountToken(api.account)])
        XCTAssertEqual(transaction.environment, .xcode)
        try await waitForState("transaction listener accepts service-confirmed access") {
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
    func testCardlessBaseTrialPreventsPaidCheckoutAndLocalBotNeedsNoPlan() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        api.cardlessTrial = true
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        await store.start()
        XCTAssertTrue(store.baseActive)
        XCTAssertFalse(store.canPurchase(.base))
        XCTAssertFalse(store.canPurchase(.botMini))
        XCTAssertFalse(store.botAvailable)
        await store.purchase(.base)
        XCTAssertTrue(environment.allTransactions().isEmpty)
        XCTAssertEqual(api.submitted, 0)
        api.cardlessTrial = false
        await store.refresh()
        XCTAssertFalse(store.baseActive)
        XCTAssertTrue(store.canPurchase(.base))
        XCTAssertFalse(store.canPurchase(.botMini))
    }
    func testUnconfirmedChargeStaysUnfinishedAndPreventsAnotherPurchase() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let api = Service()
        api.rejectSubmission = true
        let store = SubscriptionStore(api: api, accountToken: api.account)
        defer { store.close() }
        await store.start()
        await store.purchase(.base)
        XCTAssertFalse(store.baseActive)
        XCTAssertFalse(store.canPurchase(.base))
        XCTAssertTrue(store.awaitingConfirmation.contains(.base))
        try await waitForState("denied purchase remains unfinished") { await self.unfinishedBaseCount() == 1 }
        var unfinished = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue {
                unfinished += 1
            }
        }
        XCTAssertEqual(unfinished, 1)
        // An explicit second checkout remains blocked while the service is
        // unavailable. Reading/receiving the transaction must never finish it.
        await store.purchase(.base)
        XCTAssertEqual(environment.allTransactions().count, 1)
        XCTAssertFalse(store.baseActive)
        XCTAssertFalse(store.canPurchase(.base))
        XCTAssertTrue(store.awaitingConfirmation.contains(.base))
        let stillUnfinished = await unfinishedBaseCount()
        XCTAssertEqual(stillUnfinished, 1)
        api.rejectSubmission = false
        await store.start()
        try await waitForState("service-confirmed purchase becomes active") {
            store.baseActive && !store.awaitingConfirmation.contains(.base)
        }
        XCTAssertTrue(store.baseActive)
        XCTAssertFalse(store.awaitingConfirmation.contains(.base))
        try await waitForState("confirmed purchase is finished") { await self.unfinishedBaseCount() == 0 }
        var remaining = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue {
                remaining += 1
            }
        }
        XCTAssertEqual(remaining, 0)
        XCTAssertGreaterThanOrEqual(api.submitted, 2)
    }
    func testServerOwnershipRejectionBlocksAnotherChargeAndAllowsVerifiedRetry() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let other = UUID()
        let transaction = try await environment.buyProduct(
            identifier: VipiPlan.base.rawValue, options: [.appAccountToken(other)])
        XCTAssertEqual(transaction.environment, .xcode)
        let api = Service()
        let actual = SubscriptionStore(api: api, accountToken: api.account)
        defer { actual.close() }
        await actual.start()
        XCTAssertFalse(actual.baseActive)
        XCTAssertFalse(actual.canPurchase(.base))
        XCTAssertGreaterThanOrEqual(api.submitted, 1)
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
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let old = UUID()
        _ = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(old)])
        let api = Service()
        api.historicalAccount = old
        let actual = SubscriptionStore(api: api, accountToken: api.account)
        defer { actual.close() }
        await actual.start()
        XCTAssertGreaterThanOrEqual(api.submitted, 1)
        XCTAssertTrue(actual.baseActive)
        var unfinished = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue {
                unfinished += 1
            }
        }
        XCTAssertEqual(unfinished, 0)
    }
    func testRestoredOldTokenCannotFinishOnWrongCurrentAccountReadback() async throws {
        let environment = try await environment()
        defer {
            environment.clearTransactions()
            environment.resetToDefaultState()
        }
        let old = UUID()
        _ = try await environment.buyProduct(identifier: VipiPlan.base.rawValue, options: [.appAccountToken(old)])
        let api = Service()
        api.historicalAccount = old
        api.responseAccount = UUID()
        let actual = SubscriptionStore(api: api, accountToken: api.account)
        defer { actual.close() }
        await actual.start()
        XCTAssertGreaterThanOrEqual(api.submitted, 1)
        XCTAssertFalse(actual.baseActive)
        var unfinished = 0
        for await result in Transaction.unfinished {
            if case .verified(let transaction) = result, transaction.productID == VipiPlan.base.rawValue {
                unfinished += 1
            }
        }
        XCTAssertEqual(unfinished, 1)
    }
}
