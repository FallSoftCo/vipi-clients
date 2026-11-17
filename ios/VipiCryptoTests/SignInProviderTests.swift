import XCTest
@testable import Vipi

final class SignInProviderTests: XCTestCase {
    private let start = URL(string: "https://api.workos.com/user_management/authorize?client_id=client_fixture&redirect_uri=co.fallsoft.vipi%3A%2F%2Fauth%2Fcallback&response_type=code&state=state%2Bfixture&code_challenge=challenge_fixture&code_challenge_method=S256&provider=old&provider=other&max_age=90&screen_hint=sign-up")!

    func testProviderSelectionPreservesOriginalPKCEStateAndExactCallback() throws {
        for provider in SignInProvider.allCases {
            let url = try signInAuthorizationURL(start, provider: provider, reauthenticate: false)
            let original = try XCTUnwrap(URLComponents(url: start, resolvingAgainstBaseURL: false))
            let result = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
            func values(_ parts: URLComponents, _ name: String) -> [String?] { (parts.queryItems ?? []).filter { $0.name == name }.map(\.value) }
            XCTAssertEqual(values(result, "provider"), [provider.rawValue])
            for name in ["client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method"] {
                XCTAssertEqual(values(result, name), values(original, name))
            }
            XCTAssertTrue(values(result, "max_age").isEmpty)
            XCTAssertTrue(values(result, "screen_hint").isEmpty)
            XCTAssertTrue(values(result, "client_secret").isEmpty)
            XCTAssertEqual(url.scheme, start.scheme)
            XCTAssertEqual(url.host, start.host)
            XCTAssertEqual(url.path, start.path)
        }
    }

    func testSameAccountReauthenticationAlwaysUsesAuthKitFreshFactorSelection() throws {
        for provider in SignInProvider.allCases {
            let url = try signInAuthorizationURL(start, provider: provider, reauthenticate: true)
            let parts = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
            func values(_ name: String) -> [String?] { (parts.queryItems ?? []).filter { $0.name == name }.map(\.value) }
            XCTAssertEqual(values("provider"), ["authkit"])
            XCTAssertEqual(values("max_age"), ["0"])
            XCTAssertEqual(values("screen_hint"), ["sign-in"])
            XCTAssertEqual(values("state"), ["state+fixture"])
            XCTAssertEqual(values("code_challenge"), ["challenge_fixture"])
        }
    }
}

final class IdentityAuthorityTests: XCTestCase {
    private let oldSession: [String: Any] = ["userID": "user_original_fixture", "accessToken": "synthetic-access", "refreshToken": "synthetic-refresh"]
    private let oldPending: [String: Any] = ["state": "synthetic-state", "verifier": "synthetic-verifier", "createdAt": 123, "expectedUser": "user_original_fixture"]
    private func data(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value) }

    func testLegacySessionAndTransactionRemainOnLegacyAuthority() throws {
        let session = try JSONDecoder().decode(VipiSession.self, from: data(oldSession))
        let pending = try JSONDecoder().decode(PendingSignIn.self, from: data(oldPending))
        XCTAssertEqual(session.authority, .legacy)
        XCTAssertEqual(pending.authority, .legacy)
        XCTAssertEqual(session.userID, "user_original_fixture")
        XCTAssertEqual(pending.expectedUser, session.userID)
        XCTAssertEqual(pending.verifier, "synthetic-verifier")
        XCTAssertEqual(pending.createdAt, Date(timeIntervalSinceReferenceDate: 123))
    }

    func testAuthoritySurvivesSessionAndPendingRoundTripsWithoutChangingAccountBinding() throws {
        for authority in IdentityAuthority.allCases {
            let session = VipiSession(userID: "user_original_fixture", accessToken: "synthetic-access", refreshToken: "synthetic-refresh", authority: authority)
            let pending = PendingSignIn(state: "synthetic-state", verifier: "synthetic-verifier", createdAt: Date(timeIntervalSinceReferenceDate: 123), expectedUser: session.userID, authority: authority)
            let saved = try JSONEncoder().encode(session)
            let restored = try JSONDecoder().decode(VipiSession.self, from: saved)
            let transaction = try JSONDecoder().decode(PendingSignIn.self, from: JSONEncoder().encode(pending))
            XCTAssertEqual(restored.authority, authority)
            XCTAssertEqual(transaction.authority, authority)
            XCTAssertEqual(restored.userID, session.userID)
            XCTAssertEqual(restored.refreshToken, session.refreshToken)
            XCTAssertEqual(transaction.expectedUser, session.userID)
            let fields = try XCTUnwrap(JSONSerialization.jsonObject(with: saved) as? [String: Any])
            XCTAssertEqual(fields["formatVersion"] as? Int, 2)
            XCTAssertEqual(fields["clientID"] as? String, authority.clientID)
            XCTAssertNil(fields["client_secret"])
        }
    }

    func testUnknownMismatchedPartialAndFutureAuthorityMetadataFailClosed() throws {
        let invalid: [[String: Any]] = [
            ["formatVersion": 2, "authority": "unknown", "clientID": IdentityAuthority.vipiProduction.clientID],
            ["formatVersion": 2, "authority": IdentityAuthority.vipiProduction.rawValue, "clientID": IdentityAuthority.vipiStaging.clientID],
            ["formatVersion": 3, "authority": IdentityAuthority.vipiProduction.rawValue, "clientID": IdentityAuthority.vipiProduction.clientID],
            ["authority": IdentityAuthority.vipiProduction.rawValue], ["clientID": IdentityAuthority.vipiProduction.clientID], ["formatVersion": 2]
        ]
        for metadata in invalid {
            XCTAssertThrowsError(try JSONDecoder().decode(VipiSession.self, from: data(oldSession.merging(metadata) { _, new in new })))
            XCTAssertThrowsError(try JSONDecoder().decode(PendingSignIn.self, from: data(oldPending.merging(metadata) { _, new in new })))
        }
    }

    func testSavedAuthorityControlsReauthenticationEvenWhenBuildConfigurationChanges() throws {
        for authority in IdentityAuthority.allCases {
            XCTAssertEqual(try IdentityAuthority.forSignIn(saved: authority, hasExpectedUser: true, configuredClientID: "client_unknown_future"), authority)
            XCTAssertEqual(try IdentityAuthority.forSignIn(saved: authority, hasExpectedUser: false, configuredClientID: ""), authority)
            XCTAssertEqual(try IdentityAuthority.forSignIn(saved: nil, hasExpectedUser: false, configuredClientID: authority.clientID), authority)
        }
        XCTAssertEqual(try IdentityAuthority.forSignIn(saved: nil, hasExpectedUser: true, configuredClientID: "client_unknown_future"), .legacy)
        XCTAssertThrowsError(try IdentityAuthority.forSignIn(saved: nil, hasExpectedUser: false, configuredClientID: "client_unknown_future"))
    }
    func testEqualSubjectFromAnotherAuthorityCannotReplaceExistingAccount() {
        let session = VipiSession(userID: "user_original_fixture", accessToken: "synthetic-access", refreshToken: "synthetic-refresh", authority: .vipiProduction)
        XCTAssertTrue(session.isBound(to: .vipiProduction, subject: session.userID))
        XCTAssertFalse(session.isBound(to: .vipiStaging, subject: session.userID))
        XCTAssertFalse(session.isBound(to: .vipiProduction, subject: "user_other_fixture"))
    }
}
