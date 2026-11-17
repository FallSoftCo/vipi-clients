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
