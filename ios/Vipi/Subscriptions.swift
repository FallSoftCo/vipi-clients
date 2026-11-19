import Foundation
import Observation
import StoreKit

/// Store metadata describes the offer; only the service grants account access.
enum VipiPlan: String, CaseIterable, Identifiable {
    case base = "vipi.base.annual"
    case botMini = "vipi.botmini.annual"
    var id: String { rawValue }
    var title: String { self == .base ? "Vipi" : "Bot mini" }
}

struct EntitlementSnapshot: Decodable, Sendable {
    struct PurchaseReadiness: Decodable, Sendable { let apple: Bool; let google: Bool }
    struct CardlessTrial: Decodable, Sendable { let started_at: String; let ends_at: String; let active: Bool }
    struct Access: Decodable, Sendable {
        let active: Bool
        let available: Bool?
        let expires_at: String?
        let trial_ends_at: String?
        let access_source: String?
        let review_access: Bool?
        let cardless_trial: CardlessTrial?
        let verification_unavailable: Bool?
        var isReviewAccess: Bool {
            active && access_source == "review_complimentary" && review_access == true &&
                expires_at == nil && trial_ends_at == nil
        }
    }
    let server_time: String?
    let base: Access
    let bot_mini: Access
    let billing_account_id: String
    let app_account_token: UUID
    let purchases_ready: PurchaseReadiness?
    func access(_ plan: VipiPlan) -> Access { plan == .base ? base : bot_mini }
}

/// Uses only the service timestamps and monotonic elapsed time, never the device wall clock.
struct ServerTrialClock: Sendable {
    let deadline: ContinuousClock.Instant
    static func make(serverTime: String?, trialEnd: String?, now: ContinuousClock.Instant = .now) -> ServerTrialClock? {
        guard let serverTime, let trialEnd else { return nil }
        func parse(_ value: String) -> Date? {
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
        }
        guard let start = parse(serverTime), let end = parse(trialEnd) else { return nil }
        let remaining = end.timeIntervalSince(start)
        guard remaining.isFinite else { return nil }
        return ServerTrialClock(deadline: now.advanced(by: .seconds(max(0, remaining))))
    }
    func expired(at now: ContinuousClock.Instant = .now) -> Bool { now >= deadline }
}

struct BotAllowance: Decodable, Sendable {
    let available: Bool
    let service_ready: Bool
    let remaining_replies: Int
    let monthly_replies: Int
    let resets_at: String
    let max_context_bytes: Int
    func canSend(at now: Date) -> Bool {
        guard available, service_ready, monthly_replies > 0,
              remaining_replies > 0, remaining_replies <= monthly_replies,
              max_context_bytes > 0, max_context_bytes <= 8192 else { return false }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let reset = fractional.date(from: resets_at) ?? ISO8601DateFormatter().date(from: resets_at) else { return false }
        return reset > now
    }
}

@MainActor @Observable final class SubscriptionStore {
    private let api: any ChatTransport
    private let accountToken: UUID
    private let loadProducts: @MainActor () async throws -> [Product]
    private var listener: Task<Void, Never>?
    private var expiryTasks: [VipiPlan: Task<Void, Never>] = [:]
    private var expiryClocks: [VipiPlan: ServerTrialClock] = [:]
    private var serverClockValid = false
    private var expiredPlans = Set<VipiPlan>()
    private var closed = false
    private var entitlementRevision: UInt64 = 0
    private var synchronizing = Set<UInt64>()
    private var reconciling = false
    private(set) var awaitingConfirmation = Set<VipiPlan>()
    private(set) var accountConflicts = Set<VipiPlan>()
    private(set) var snapshot: EntitlementSnapshot?
    private(set) var botAllowance: BotAllowance?
    private(set) var products: [VipiPlan: Product] = [:]
    private(set) var introductoryEligible = Set<VipiPlan>()
    private(set) var loading = false
    private(set) var busy = false
    private(set) var pending = false
    private(set) var catalogUnavailable = false
    var notice: String?

    init(api: any ChatTransport, accountToken: UUID,
         loadProducts: @escaping @MainActor () async throws -> [Product] = {
             try await Product.products(for: [VipiPlan.base.rawValue])
         }) {
        self.api = api; self.accountToken = accountToken; self.loadProducts = loadProducts
    }
    func start() async {
        guard !closed else { return }
        reconciling = true
        defer { reconciling = false }
        if listener == nil {
            listener = Task { [weak self] in
                for await update in Transaction.updates {
                    guard !Task.isCancelled, let self, !self.closed else { return }
                    do { try await self.synchronize(update) }
                    catch { self.notice = Self.explanation(error) }
                }
            }
        }
        await refresh()
        await reconcile()
    }
    func close() { closed = true; listener?.cancel(); listener = nil; expiryTasks.values.forEach { $0.cancel() }; expiryTasks = [:]; expiryClocks = [:]; serverClockValid = false; expiredPlans = []; snapshot = nil; botAllowance = nil }
    func refresh() async {
        guard !loading, !closed else { return }
        loading = true
        botAllowance = nil
        defer { loading = false }
        await refreshEntitlements()
        // Local vBot readiness is device-owned; subscription refresh sends no bot request.
        do {
            let values = try await loadProducts()
            guard !closed else { return }
            var found: [VipiPlan: Product] = [:], eligible = Set<VipiPlan>()
            for value in values {
                guard let plan = VipiPlan(rawValue: value.id), value.type == .autoRenewable,
                      let subscription = value.subscription,
                      subscription.subscriptionPeriod.unit == .year,
                      subscription.subscriptionPeriod.value == 1 else { continue }
                found[plan] = value
                if await subscription.isEligibleForIntroOffer,
                   let offer = subscription.introductoryOffer,
                   offer.paymentMode == .freeTrial, offer.period.unit == .month,
                   offer.period.value == 1, offer.periodCount == 1 { eligible.insert(plan) }
            }
            guard !closed else { return }
            products = found; introductoryEligible = eligible
            catalogUnavailable = found[.base] == nil
        } catch {
            if !closed {
                // Never initiate a charge from stale offer or price information.
                products = [:]; introductoryEligible = []
                // Catalog availability does not invalidate current account
                // access or replace a purchase/restore reconciliation notice.
                catalogUnavailable = true
            }
        }
    }
    /// Service access reconciliation is independent of StoreKit offer loading.
    func refreshEntitlements() async {
        guard !closed else { return }
        // Fail closed on a failed refresh rather than reuse a stale readiness
        // signal for a new charge. Existing account access is kept separately.
        purchaseReady = false
        let revision = entitlementRevision
        do {
            let startedAt = ContinuousClock.now
            let value: EntitlementSnapshot = try await api.request("GET", "/v1/entitlements")
            // A StoreKit confirmation can accept newer access while this GET
            // is in flight. Its response must not undo that confirmation.
            if revision == entitlementRevision { try accept(value, capturedAt: startedAt) }
        } catch { if !closed && revision == entitlementRevision { notice = Self.explanation(error) } }
    }
    func accessVerificationPending(_ plan: VipiPlan) -> Bool {
        guard serverClockValid, let access = snapshot?.access(plan) else { return true }
        if access.verification_unavailable == true { return true }
        if access.active && !access.isReviewAccess {
            return expiryClocks[plan] == nil || expiredPlans.contains(plan) || expiryClocks[plan]?.expired() == true
        }
        return false
    }
    func accessActive(_ plan: VipiPlan) -> Bool {
        snapshot?.access(plan).active == true && !accessVerificationPending(plan)
    }
    var baseActive: Bool { accessActive(.base) }
    private(set) var purchaseReady = false
    var botServiceReady: Bool { botAllowance?.service_ready == true }
    var botAvailable: Bool { snapshot?.bot_mini.available == true && accessActive(.botMini) && baseActive && botAllowance?.available == true }
    // A cardless Base trial must not be followed by a second store trial.
    // Block eligible Base checkout until the old introductory offer is removed.
    var baseStoreTrialStillOffered: Bool { introductoryEligible.contains(.base) }
    func canPurchase(_ plan: VipiPlan) -> Bool {
        plan == .base && !closed && !busy && !loading && !reconciling && !pending && !awaitingConfirmation.contains(plan) && !accountConflicts.contains(plan) && purchaseReady && snapshot != nil && products[plan] != nil &&
        snapshot?.access(plan).active == false &&
        !accessVerificationPending(plan) &&
        !(plan == .base && baseStoreTrialStillOffered) &&
        (plan == .base || (baseActive && botServiceReady))
    }
    func purchase(_ plan: VipiPlan) async {
        guard plan == .base, canPurchase(plan), let product = products[plan] else { return }
        busy = true; notice = nil
        defer { busy = false }
        do {
            switch try await product.purchase(options: [.appAccountToken(accountToken)]) {
            case .success(let result):
                awaitingConfirmation.insert(plan)
                try await synchronize(result)
                if !closed { await refresh() }
            case .pending:
                pending = true
                notice = String(localized: "Your purchase is waiting for App Store approval. It will appear here when it’s confirmed.")
            case .userCancelled: break
            @unknown default: notice = String(localized: "The purchase couldn’t finish. Check your App Store subscriptions before trying again.")
            }
        } catch { if !closed { notice = Self.explanation(error) } }
    }
    /// Explicit user action; never prompts for store authentication on launch.
    func restore() async {
        guard !busy, !closed else { return }
        busy = true; notice = nil
        defer { busy = false }
        do {
            try await AppStore.sync()
            await reconcile()
            await refresh()
            if !closed && notice == nil { notice = String(localized: "Your App Store purchases are up to date.") }
        } catch { if !closed { notice = Self.explanation(error) } }
    }
    /// Accept only an account-bound service response, including purchase verification.
    func accept(_ value: EntitlementSnapshot, capturedAt: ContinuousClock.Instant) throws {
        guard !closed, value.app_account_token == accountToken else {
            throw ServiceFailure(status: 0, code: "purchase_account_mismatch")
        }
        entitlementRevision &+= 1
        snapshot = value
        purchaseReady = value.purchases_ready?.apple == true
        serverClockValid = ServerTrialClock.make(serverTime: value.server_time, trialEnd: value.server_time, now: capturedAt) != nil
        expiryTasks.values.forEach { $0.cancel() }; expiryTasks = [:]; expiryClocks = [:]; expiredPlans = []
        for plan in VipiPlan.allCases {
            let access = value.access(plan)
            guard access.active && !access.isReviewAccess else { continue }
            if plan == .base && access.access_source == "cardless_trial" && access.cardless_trial?.active == false { continue }
            let end = plan == .base && access.access_source == "cardless_trial"
                ? (access.cardless_trial?.ends_at ?? access.trial_ends_at ?? access.expires_at)
                : access.expires_at
            // Request-start anchoring makes network delay conservative.
            guard let clock = ServerTrialClock.make(serverTime: value.server_time, trialEnd: end, now: capturedAt) else { continue }
            expiryClocks[plan] = clock
            expiryTasks[plan] = Task { [weak self] in
                do { try await ContinuousClock().sleep(until: clock.deadline) } catch { return }
                guard !Task.isCancelled, let self, !self.closed else { return }
                self.expiredPlans.insert(plan)
                await self.refresh()
            }
        }
    }
    private func reconcile() async {
        guard !closed else { return }
        for await result in Transaction.unfinished {
            do { try await synchronize(result) }
            catch { if !closed { notice = Self.explanation(error) } }
        }
        for await result in Transaction.currentEntitlements {
            do { try await synchronize(result) }
            catch { if !closed { notice = Self.explanation(error) } }
        }
    }
    private func synchronize(_ result: VerificationResult<Transaction>) async throws {
        guard !closed else { throw CancellationError() }
        guard case .verified(let transaction) = result else {
            throw ServiceFailure(status: 0, code: "purchase_unverified")
        }
        guard let plan = VipiPlan(rawValue: transaction.productID) else { return }
        // A verified transaction may retain the token of a deleted Vipi profile.
        // The authenticated service checks its retained hashed ownership against
        // this exact Fallsoft identity; a local UUID mismatch cannot decide it.
        guard synchronizing.insert(transaction.id).inserted else { return }
        defer { synchronizing.remove(transaction.id) }
        awaitingConfirmation.insert(plan)
        let body = try JSONEncoder().encode(PurchaseBody(signed_transaction_info: result.jwsRepresentation))
        let startedAt = ContinuousClock.now
        let value: EntitlementSnapshot
        do { value = try await api.request("POST", "/v1/purchases/apple", body: body) }
        catch let error as ServiceFailure where error.code == "purchase_account_mismatch" {
            accountConflicts.insert(plan)
            awaitingConfirmation.remove(plan)
            throw error
        }
        try accept(value, capturedAt: startedAt)
        // Preserve unfinished delivery when validation/network failed. A local
        // success flag never substitutes for the account-bound service result.
        await transaction.finish()
        awaitingConfirmation.remove(plan)
        accountConflicts.remove(plan)
        pending = false
    }
    private struct PurchaseBody: Encodable { let signed_transaction_info: String }
    private static func explanation(_ error: Error) -> String {
        if let failure = error as? ServiceFailure {
            if failure.code == "purchase_account_mismatch" { return String(localized: "This purchase belongs to another Vipi account. Sign in to that account to restore it.") }
            if failure.code == "purchase_unverified" { return String(localized: "The App Store purchase couldn’t be verified. No access has been changed.") }
            if failure.code == "billing_unavailable" { return String(localized: "Subscriptions aren’t available yet. Your saved conversations are still here.") }
        }
        return String(localized: "We couldn’t confirm your subscription. If you completed a purchase, use Restore purchases to check it before buying again.")
    }
}
