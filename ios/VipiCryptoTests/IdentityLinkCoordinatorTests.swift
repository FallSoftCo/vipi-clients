import XCTest
@testable import Vipi

@MainActor final class IdentityLinkCoordinatorTests: XCTestCase {
    private let keys = ["session", "pending-sign-in", "pending-identity-link", "profile-user_shared_fixture", "profile-user_original_fixture"]
    private func fixture() throws -> IdentityLinkJournal {
        let intent = IdentityLinkIntent(accountID: UUID(), requestID: UUID(), oldUserID: "user_original_fixture", deviceID: UUID(), deviceSecret: String(repeating: "a", count: 43))
        return try IdentityLinkJournal(intent: intent, candidate: VipiSession(userID: "user_shared_fixture", accessToken: "synthetic-new-access", refreshToken: "synthetic-new-refresh", authority: .fallsoftVipiProduction))
    }
    private func oldSession() -> VipiSession { VipiSession(userID: "user_original_fixture", accessToken: "synthetic-old-access", refreshToken: "synthetic-old-refresh", authority: .vipiProduction) }
    private func receipt(_ journal: IdentityLinkJournal) throws -> Data {
        try JSONSerialization.data(withJSONObject: ["request_id": journal.intent.requestID.uuidString, "account_id": journal.intent.accountID.uuidString,
            "authority_id": IdentityAuthority.fallsoftVipiProduction.rawValue, "authentication_subject": journal.candidate.userID, "binding_revision": 1])
    }
    private func restore(_ saved: [(String, Data?)]) {
        for (key, data) in saved { if let data { try? KeychainStore.save(data, account: key) } else { KeychainStore.delete(account: key) } }
    }
    func testWrongUUIDReadbackKeepsOldSessionThenExactRetryActivatesOriginalAccount() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }; defer { restore(saved) }
        let journal = try fixture(); let original = try JSONEncoder().encode(oldSession())
        try KeychainStore.save(original, account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        let auth = AuthenticationManager(); var wrongProfile = true; var posts = 0
        auth.qualificationLinkRequest = { method, _, body, token, intent in
            XCTAssertEqual(intent.accountID, journal.intent.accountID)
            if method == "POST" {
                posts += 1; XCTAssertEqual(token, "synthetic-old-access")
                let fields = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                XCTAssertEqual(fields["request_id"] as? String, journal.intent.requestID.uuidString.lowercased())
                XCTAssertEqual(fields["fallsoft_access_token"] as? String, "synthetic-new-access")
                return try self.receipt(journal)
            }
            XCTAssertEqual(token, "synthetic-new-access")
            return try JSONEncoder().encode(IdentityLinkProfile(id: wrongProfile ? UUID() : journal.intent.accountID, username: "original_profile", display_name: "Synthetic"))
        }
        await auth.resumeFallsoftLink()
        XCTAssertNotNil(auth.errorMessage); XCTAssertEqual(auth.session?.userID, "user_original_fixture")
        XCTAssertEqual(try KeychainStore.read(account: "session"), original)
        XCTAssertNotNil(try KeychainStore.read(account: "pending-identity-link"))
        wrongProfile = false; await auth.resumeFallsoftLink()
        XCTAssertNil(auth.errorMessage); XCTAssertEqual(posts, 2)
        XCTAssertEqual(auth.session?.userID, "user_shared_fixture")
        XCTAssertEqual(auth.session?.authority, .fallsoftVipiProduction)
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
        let profile = try JSONDecoder().decode(IdentityLinkProfile.self, from: XCTUnwrap(KeychainStore.read(account: "profile-user_shared_fixture")))
        XCTAssertEqual(profile.id, journal.intent.accountID)
    }
    func testDurableActivationRecoveryDoesNotReplayOAuthOrServerRequest() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }; defer { restore(saved) }
        let initial = try fixture()
        let profile = IdentityLinkProfile(id: initial.intent.accountID, username: "original_profile", display_name: "Synthetic")
        let journal = try IdentityLinkJournal(intent: initial.intent, candidate: initial.candidate, verifiedProfile: profile)
        try KeychainStore.save(JSONEncoder().encode(journal.candidate), account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        try KeychainStore.save(JSONEncoder().encode(profile), account: "profile-user_shared_fixture")
        let auth = AuthenticationManager()
        auth.qualificationLinkRequest = { _, _, _, _, _ in XCTFail("Verified activation must not replay a request"); throw URLError(.unknown) }
        await auth.resumeFallsoftLink()
        XCTAssertNil(auth.errorMessage); XCTAssertEqual(auth.session?.userID, journal.candidate.userID)
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
    }
    func testSignOutDuringUncertainServerSuccessCannotRestoreAnySession() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }; defer { restore(saved) }
        let journal = try fixture()
        try KeychainStore.save(JSONEncoder().encode(oldSession()), account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        let auth = AuthenticationManager()
        auth.qualificationLinkRequest = { method, _, _, _, _ in
            if method == "POST" { return try self.receipt(journal) }
            auth.signOutLocally()
            return try JSONEncoder().encode(IdentityLinkProfile(id: journal.intent.accountID, username: "original_profile", display_name: "Synthetic"))
        }
        await auth.resumeFallsoftLink()
        XCTAssertNil(auth.session); XCTAssertNil(try KeychainStore.read(account: "session"))
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
    }
}
