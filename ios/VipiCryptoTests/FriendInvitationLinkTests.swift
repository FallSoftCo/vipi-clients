import XCTest
@testable import Vipi

@MainActor final class FriendInvitationLinkTests: XCTestCase {
    func testInvitationsSurviveOnboardingRelaunchAndCanBeDismissed() throws {
        let key = "vipi-invitation-test-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: key))
        defer { defaults.removePersistentDomain(forName: key) }
        let state = AppState(defaults: defaults)
        XCTAssertTrue(state.acceptInvitation(try XCTUnwrap(URL(string: "https://api.mambovipi.app/invite/Alice_123"))))
        XCTAssertFalse(state.isAuthenticated)
        XCTAssertEqual(state.onboarding, .welcome)
        XCTAssertEqual(AppState(defaults: defaults).invitationUsername, "alice_123")
        XCTAssertFalse(
            state.acceptInvitation(try XCTUnwrap(URL(string: "co.fallsoft.vipi://auth/callback?code=unused"))))
        XCTAssertEqual(state.invitationUsername, "alice_123", "Authentication must not consume the pending friend")
        state.invitationUsername = nil
        XCTAssertNil(AppState(defaults: defaults).invitationUsername)
    }

    func testStrictLinkBoundaryAndBothEntryPoints() throws {
        for raw in ["https://api.mambovipi.app/invite/Alice_123", "co.fallsoft.vipi://invite/Alice_123"] {
            XCTAssertEqual(FriendInvitationLink.username(in: try XCTUnwrap(URL(string: raw))), "alice_123")
        }
        for raw in [
            "https://evil.example/invite/alice", "http://api.mambovipi.app/invite/alice",
            "https://api.mambovipi.app.evil.example/invite/alice", "https://alice@api.mambovipi.app/invite/bob",
            "https://api.mambovipi.app:443/invite/alice", "https://api.mambovipi.app/invite/alice?next=evil",
            "https://api.mambovipi.app/invite/alice#fragment", "https://api.mambovipi.app/invite/alice/extra",
            "https://api.mambovipi.app/invite/alice/", "https://api.mambovipi.app/invite/%61lice",
            "https://api.mambovipi.app/invite/%2falice", "https://api.mambovipi.app/invite/аlice",
            "https://api.mambovipi.app/invite/1alice", "https://api.mambovipi.app/invite/a",
            "https://api.mambovipi.app/invite/" + String(repeating: "a", count: 25),
            "https://api.mambovipi.app/invite/admin", "https://api.mambovipi.app/invite/vBot",
            "co.fallsoft.vipi://auth/callback?code=untouched&state=untouched"
        ] {
            XCTAssertNil(FriendInvitationLink.username(in: try XCTUnwrap(URL(string: raw))), raw)
        }
    }
}
