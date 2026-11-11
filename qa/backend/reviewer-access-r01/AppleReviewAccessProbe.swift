import Foundation
enum VipiPlan: String, CaseIterable, Identifiable {
    case base = "vipi.base.annual"
    case botMini = "vipi.botmini.annual"
    var id: String { rawValue }
    var title: String { self == .base ? "Vipi" : "Bot mini" }
}

struct EntitlementSnapshot: Decodable, Sendable {
    struct PurchaseReadiness: Decodable, Sendable { let apple: Bool; let google: Bool }
    struct Access: Decodable, Sendable {
        let active: Bool
        let available: Bool?
        let expires_at: String?
        let trial_ends_at: String?
        let access_source: String?
        let review_access: Bool?
        var isReviewAccess: Bool {
            active && access_source == "review_complimentary" && review_access == true &&
                expires_at == nil && trial_ends_at == nil
        }
    }
    let base: Access
    let bot_mini: Access
    let billing_account_id: String
    let app_account_token: UUID
    let purchases_ready: PurchaseReadiness?
    func access(_ plan: VipiPlan) -> Access { plan == .base ? base : bot_mini }
}


func decode(_ access: [String: Any]) throws -> EntitlementSnapshot {
 var bot = access; bot["available"] = true
 let data = try JSONSerialization.data(withJSONObject: ["base": access, "bot_mini": bot,
 "billing_account_id": String(repeating: "a", count: 64),
 "app_account_token": "11111111-1111-4111-8111-111111111111",
 "purchases_ready": ["apple": false, "google": false]])
 return try JSONDecoder().decode(EntitlementSnapshot.self, from: data)
}
var grant: [String: Any] = ["active": true, "expires_at": NSNull(), "trial_ends_at": NSNull(),
 "access_source": "review_complimentary", "review_access": true]
let snapshot = try decode(grant)
precondition(snapshot.base.isReviewAccess && snapshot.bot_mini.isReviewAccess)
precondition(snapshot.base.expires_at == nil && snapshot.base.trial_ends_at == nil)
var ordinary: [String: Any] = ["active": true, "expires_at": "2027-01-01T00:00:00Z", "trial_ends_at": NSNull()]
let parsedOrdinary = try decode(ordinary); precondition(!parsedOrdinary.base.isReviewAccess)
for key in ["access_source", "review_access"] {
 var partial = grant; partial.removeValue(forKey: key)
 let parsed = try decode(partial); precondition(!parsed.base.isReviewAccess)
}
var unknown = grant; unknown["access_source"] = "unknown"
let parsedUnknown = try decode(unknown); precondition(!parsedUnknown.base.isReviewAccess)
var inactive = grant; inactive["active"] = false
let parsedInactive = try decode(inactive); precondition(!parsedInactive.base.isReviewAccess)
var dated = grant; dated["expires_at"] = "2027-01-01T00:00:00Z"
let parsedDated = try decode(dated); precondition(!parsedDated.base.isReviewAccess)
var malformed = grant; malformed["review_access"] = "true"
do { _ = try decode(malformed); fatalError("string flag accepted") } catch is DecodingError {}
print("PASS: 8 exact-model complimentary decoding/coherence checks; ordinary active behavior retained")
