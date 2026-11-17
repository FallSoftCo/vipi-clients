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

struct BotAllowance: Decodable, Sendable {
    let available: Bool
    let service_ready: Bool
    let remaining_replies: Int
    let monthly_replies: Int
    let resets_at: String
    let max_context_bytes: Int
}

@MainActor @Observable final class SubscriptionStore {
    private let api: any ChatTransport
    private let accountToken: UUID
    private var listener: Task<Void, Never>?
    private var closed = false
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
    var notice: String?

    init(api: any ChatTransport, accountToken: UUID) {
        self.api = api; self.accountToken = accountToken
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
    func close() { closed = true; listener?.cancel(); listener = nil; snapshot = nil; botAllowance = nil }
    func refresh() async {
        guard !loading, !closed else { return }
        loading = true
        // Fail closed on a failed refresh rather than reuse a stale readiness
        // signal for a new charge. Existing account access is kept separately.
        purchaseReady = false; botAllowance = nil
        defer { loading = false }
        do {
            let value: EntitlementSnapshot = try await api.request("GET", "/v1/entitlements")
            try accept(value)
            purchaseReady = value.purchases_ready?.apple == true
        } catch { if !closed { notice = Self.explanation(error) } }
        do {
            let value: BotAllowance = try await api.request("GET", "/v1/bot/allowance")
            if !closed { botAllowance = value }
        } catch { /* Bot availability never prevents using a base subscription. */ }
        do {
            let values = try await Product.products(for: VipiPlan.allCases.map(\.rawValue))
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
        } catch {
            if !closed {
                // Never initiate a charge from stale offer or price information.
                products = [:]; introductoryEligible = []
                notice = String(localized: "The App Store couldn’t load prices. Please try again.")
            }
        }
    }
    var baseActive: Bool { snapshot?.base.active == true }
    private(set) var purchaseReady = false
    var botServiceReady: Bool { botAllowance?.service_ready == true }
    var botAvailable: Bool { snapshot?.bot_mini.available == true && baseActive && botAllowance?.available == true }
    // A cardless Base trial must not be followed by a second store trial.
    // Block eligible Base checkout until the old introductory offer is removed.
    var baseStoreTrialStillOffered: Bool { introductoryEligible.contains(.base) }
    func canPurchase(_ plan: VipiPlan) -> Bool {
        !closed && !busy && !loading && !reconciling && !pending && !awaitingConfirmation.contains(plan) && !accountConflicts.contains(plan) && purchaseReady && snapshot != nil && products[plan] != nil &&
        snapshot?.access(plan).active == false &&
        snapshot?.access(plan).verification_unavailable != true &&
        !(plan == .base && baseStoreTrialStillOffered) &&
        (plan == .base || (baseActive && botServiceReady))
    }
    func purchase(_ plan: VipiPlan) async {
        guard canPurchase(plan), let product = products[plan] else { return }
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
    private func accept(_ value: EntitlementSnapshot) throws {
        guard !closed, value.app_account_token == accountToken else {
            throw ServiceFailure(status: 0, code: "purchase_account_mismatch")
        }
        snapshot = value
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
        guard transaction.appAccountToken == accountToken else {
            accountConflicts.insert(plan)
            throw ServiceFailure(status: 0, code: "purchase_account_mismatch")
        }
        guard synchronizing.insert(transaction.id).inserted else { return }
        defer { synchronizing.remove(transaction.id) }
        awaitingConfirmation.insert(plan)
        let body = try JSONEncoder().encode(PurchaseBody(signed_transaction_info: result.jwsRepresentation))
        let value: EntitlementSnapshot = try await api.request("POST", "/v1/purchases/apple", body: body)
        try accept(value)
        // Preserve unfinished delivery when validation/network failed. A local
        // success flag never substitutes for the account-bound service result.
        await transaction.finish()
        awaitingConfirmation.remove(plan)
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
