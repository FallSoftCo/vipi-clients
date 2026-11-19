import XCTest
import StoreKit
@testable import Vipi

@MainActor final class SubscriptionCatalogTests: XCTestCase {
    private final class Service: ChatTransport {
        let account = UUID()
        var unexpectedRequests = 0
        var entitlementReads = 0
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            if method == "GET", path == "/v1/bot/allowance" {
                throw ServiceFailure(status: 503, code: "bot_not_available")
            }
            guard method == "GET", path == "/v1/entitlements" else {
                unexpectedRequests += 1
                throw ServiceFailure(status: 503, code: "unexpected_catalog_test_request")
            }
            entitlementReads += 1
            let clock = ISO8601DateFormatter(), now = Date()
            let end = clock.string(from: now.addingTimeInterval(30 * 86400))
            let value: [String: Any] = [
                "server_time": clock.string(from: now),
                "base": ["active": true, "access_source": "cardless_trial", "expires_at": end,
                         "cardless_trial": ["active": true, "started_at": clock.string(from: now), "ends_at": end]],
                "bot_mini": ["active": false, "available": false],
                "billing_account_id": "catalog-test-only", "app_account_token": account.uuidString,
                "purchases_ready": ["apple": true, "google": false]
            ]
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }

    func testPriceOutageKeepsFreeAccessAndPurchaseNoticeWithoutEnrolling() async {
        let api = Service()
        var fetches = 0
        let store = SubscriptionStore(api: api, accountToken: api.account, loadProducts: {
            fetches += 1
            if fetches == 1 { throw URLError(.notConnectedToInternet) }
            return [] // A reachable but empty catalog also supplies no valid offer.
        })
        defer { store.close() }
        let unresolvedPurchase = "Check an existing purchase before buying again."
        store.notice = unresolvedPurchase
        for attempt in 1...2 {
            await store.refresh()
            XCTAssertEqual(fetches, attempt)
            XCTAssertEqual(api.entitlementReads, attempt)
            XCTAssertTrue(store.baseActive, "Price availability must not take away the user's free month")
            XCTAssertFalse(store.botAvailable)
            XCTAssertTrue(store.catalogUnavailable)
            XCTAssertTrue(store.products.isEmpty)
            XCTAssertEqual(store.notice, unresolvedPurchase, "Catalog failure must not hide a transaction reconciliation message")
            XCTAssertFalse(store.canPurchase(.base)); XCTAssertFalse(store.canPurchase(.botMini))
            XCTAssertEqual(api.unexpectedRequests, 0, "Refreshing prices never submits a purchase or enrolls a user")
        }
    }
}
