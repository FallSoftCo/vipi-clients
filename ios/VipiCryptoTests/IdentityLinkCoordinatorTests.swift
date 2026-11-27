import XCTest
import SwiftUI
import UIKit
@testable import Vipi

@MainActor final class IdentityLinkCoordinatorTests: XCTestCase {
    private let keys = [
        "session", "pending-sign-in", "pending-identity-link", "profile-user_shared_fixture",
        "profile-user_original_fixture"
    ]
    private func fixture() throws -> IdentityLinkJournal {
        let intent = IdentityLinkIntent(
            accountID: UUID(), requestID: UUID(), oldUserID: "user_original_fixture", deviceID: UUID(),
            deviceSecret: String(repeating: "a", count: 43))
        return try IdentityLinkJournal(
            intent: intent,
            candidate: VipiSession(
                userID: "user_shared_fixture", accessToken: "synthetic-new-access",
                refreshToken: "synthetic-new-refresh", authority: .fallsoftVipiProduction))
    }
    private func seedLegacyProfile(_ intent: IdentityLinkIntent) throws -> Data {
        let data = try JSONEncoder().encode(
            IdentityLinkProfile(id: intent.accountID, username: "original_profile", display_name: "Synthetic"))
        try KeychainStore.save(data, account: "profile-" + intent.oldUserID)
        return data
    }
    private func oldSession() -> VipiSession {
        VipiSession(
            userID: "user_original_fixture", accessToken: "synthetic-old-access", refreshToken: "synthetic-old-refresh",
            authority: .vipiProduction)
    }
    private func receipt(_ journal: IdentityLinkJournal) throws -> Data {
        try JSONSerialization.data(withJSONObject: [
            "request_id": journal.intent.requestID.uuidString, "account_id": journal.intent.accountID.uuidString,
            "authority_id": IdentityAuthority.fallsoftVipiProduction.rawValue,
            "authentication_subject": journal.candidate.userID, "binding_revision": 1
        ])
    }
    private func restore(_ saved: [(String, Data?)]) {
        for (key, data) in saved {
            if let data { try? KeychainStore.save(data, account: key) } else { KeychainStore.delete(account: key) }
        }
    }
    func testWrongUUIDReadbackKeepsOldSessionThenExactRetryActivatesOriginalAccount() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let journal = try fixture()
        let original = try JSONEncoder().encode(oldSession())
        let originalProfile = try seedLegacyProfile(journal.intent)
        try KeychainStore.save(original, account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        let auth = AuthenticationManager()
        var wrongProfile = true
        var posts = 0
        auth.qualificationLinkRequest = { method, _, body, token, intent in
            XCTAssertEqual(intent.accountID, journal.intent.accountID)
            if method == "POST" {
                posts += 1
                XCTAssertEqual(token, "synthetic-old-access")
                let fields = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                XCTAssertEqual(fields["request_id"] as? String, journal.intent.requestID.uuidString.lowercased())
                XCTAssertEqual(fields["fallsoft_access_token"] as? String, "synthetic-new-access")
                return try self.receipt(journal)
            }
            XCTAssertEqual(token, "synthetic-new-access")
            return try JSONEncoder().encode(
                IdentityLinkProfile(
                    id: wrongProfile ? UUID() : journal.intent.accountID, username: "original_profile",
                    display_name: "Synthetic"))
        }
        await auth.resumeFallsoftLink()
        XCTAssertNotNil(auth.errorMessage)
        XCTAssertEqual(auth.session?.userID, "user_original_fixture")
        XCTAssertEqual(try KeychainStore.read(account: "session"), original)
        XCTAssertNotNil(try KeychainStore.read(account: "pending-identity-link"))
        XCTAssertEqual(try KeychainStore.read(account: "profile-user_original_fixture"), originalProfile)
        wrongProfile = false
        await auth.resumeFallsoftLink()
        XCTAssertNil(try KeychainStore.read(account: "profile-user_original_fixture"))
        XCTAssertNil(auth.errorMessage)
        XCTAssertEqual(posts, 2)
        XCTAssertEqual(auth.session?.userID, "user_shared_fixture")
        XCTAssertEqual(auth.session?.authority, .fallsoftVipiProduction)
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
        let profile = try JSONDecoder().decode(
            IdentityLinkProfile.self, from: XCTUnwrap(KeychainStore.read(account: "profile-user_shared_fixture")))
        XCTAssertEqual(profile.id, journal.intent.accountID)
    }
    func testDurableActivationRecoveryDoesNotReplayOAuthOrServerRequest() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let initial = try fixture()
        _ = try seedLegacyProfile(initial.intent)
        let profile = IdentityLinkProfile(
            id: initial.intent.accountID, username: "original_profile", display_name: "Synthetic")
        let journal = try IdentityLinkJournal(
            intent: initial.intent, candidate: initial.candidate, verifiedProfile: profile)
        try KeychainStore.save(JSONEncoder().encode(journal.candidate), account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        try KeychainStore.save(JSONEncoder().encode(profile), account: "profile-user_shared_fixture")
        let auth = AuthenticationManager()
        auth.qualificationLinkRequest = { _, _, _, _, _ in
            XCTFail("Verified activation must not replay a request")
            throw URLError(.unknown)
        }
        await auth.resumeFallsoftLink()
        XCTAssertNil(try KeychainStore.read(account: "profile-user_original_fixture"))
        XCTAssertNil(auth.errorMessage)
        XCTAssertEqual(auth.session?.userID, journal.candidate.userID)
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
    }
    func testSignOutDuringUncertainServerSuccessCannotRestoreAnySession() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let journal = try fixture()
        try KeychainStore.save(JSONEncoder().encode(oldSession()), account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        let auth = AuthenticationManager()
        auth.qualificationLinkRequest = { method, _, _, _, _ in
            if method == "POST" { return try self.receipt(journal) }
            auth.signOutLocally()
            return try JSONEncoder().encode(
                IdentityLinkProfile(
                    id: journal.intent.accountID, username: "original_profile", display_name: "Synthetic"))
        }
        await auth.resumeFallsoftLink()
        XCTAssertNil(auth.session)
        XCTAssertNil(try KeychainStore.read(account: "session"))
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
    }
    private func pending() throws -> PendingSignIn {
        try JSONDecoder().decode(PendingSignIn.self, from: XCTUnwrap(KeychainStore.read(account: "pending-sign-in")))
    }
    private func callback(_ pending: PendingSignIn, cancelled: Bool = false) throws -> URL {
        var parts = URLComponents(string: "co.fallsoft.vipi://auth/callback")!
        parts.queryItems = [
            URLQueryItem(name: "state", value: pending.state),
            URLQueryItem(name: cancelled ? "error" : "code", value: cancelled ? "access_denied" : "synthetic-code")
        ]
        return try XCTUnwrap(parts.url)
    }
    private func installLegacyFlow() throws -> AuthenticationManager {
        try KeychainStore.save(JSONEncoder().encode(oldSession()), account: "session")
        KeychainStore.delete(account: "pending-sign-in")
        KeychainStore.delete(account: "pending-identity-link")
        let auth = AuthenticationManager()
        auth.qualificationCodeExchange = { _, _, _ in
            XCTFail("Unexpected external exchange")
            throw URLError(.unsupportedURL)
        }
        auth.qualificationLinkRequest = { _, _, _, _, _ in
            XCTFail("Unexpected backend call")
            throw URLError(.unsupportedURL)
        }
        return auth
    }
    func testSettingsFlowAlwaysReauthenticatesSameLegacyUserBeforeSharedReceiptActivation() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let fixture = try fixture()
        let auth = try installLegacyFlow()
        var launches: [URL] = []
        var posts = 0
        let originalProfile = try seedLegacyProfile(fixture.intent)
        auth.qualificationSignInLaunch = { launches.append($0) }
        auth.qualificationCodeExchange = { _, _, authority in
            VipiSession(
                userID: authority == .vipiProduction ? fixture.intent.oldUserID : fixture.candidate.userID,
                accessToken: authority == .vipiProduction
                    ? "synthetic-fresh-legacy-access" : fixture.candidate.accessToken,
                refreshToken: "synthetic-fresh-refresh", authority: authority)
        }
        XCTAssertTrue(auth.canLinkFallsoft)
        auth.beginFallsoftLink(
            accountID: fixture.intent.accountID,
            device: DeviceCredential(id: fixture.intent.deviceID, secret: fixture.intent.deviceSecret))
        let source = try pending()
        let intent = try XCTUnwrap(source.sourceLink)
        XCTAssertEqual(source.authority, .vipiProduction)
        XCTAssertEqual(source.expectedUser, fixture.intent.oldUserID)
        XCTAssertEqual(intent.accountID, fixture.intent.accountID)
        XCTAssertEqual(intent.deviceID, fixture.intent.deviceID)
        XCTAssertEqual(intent.deviceSecret, fixture.intent.deviceSecret)
        XCTAssertNil(source.link)
        XCTAssertEqual(auth.session?.accessToken, "synthetic-old-access")
        XCTAssertEqual(
            URLComponents(url: launches[0], resolvingAgainstBaseURL: false)?.queryItems?.first(where: {
                $0.name == "max_age"
            })?.value, "0")
        await auth.complete(try callback(source))
        let target = try pending()
        XCTAssertEqual(launches.count, 2)
        XCTAssertEqual(try KeychainStore.read(account: "profile-user_original_fixture"), originalProfile)
        XCTAssertEqual(target.authority, .fallsoftVipiProduction)
        XCTAssertNil(target.sourceLink)
        XCTAssertEqual(target.link?.requestID, intent.requestID)
        XCTAssertEqual(target.link?.accountID, intent.accountID)
        XCTAssertEqual(target.link?.deviceID, intent.deviceID)
        XCTAssertEqual(target.link?.deviceSecret, intent.deviceSecret)
        XCTAssertEqual(auth.session?.userID, intent.oldUserID)
        XCTAssertTrue(auth.canLinkFallsoft)
        let journal = try IdentityLinkJournal(intent: intent, candidate: fixture.candidate)
        auth.qualificationLinkRequest = { method, _, _, token, bound in
            XCTAssertEqual(bound.requestID, intent.requestID)
            XCTAssertEqual(bound.deviceID, intent.deviceID)
            if method == "POST" {
                posts += 1
                XCTAssertEqual(token, "synthetic-fresh-legacy-access")
                XCTAssertEqual(auth.session?.authority, .vipiProduction)
                return try self.receipt(journal)
            }
            XCTAssertEqual(token, fixture.candidate.accessToken)
            return try JSONEncoder().encode(
                IdentityLinkProfile(id: intent.accountID, username: "original_profile", display_name: "Synthetic"))
        }
        await auth.complete(try callback(target))
        XCTAssertEqual(posts, 1)
        XCTAssertNil(auth.errorMessage)
        XCTAssertNil(try KeychainStore.read(account: "profile-user_original_fixture"))
        XCTAssertEqual(auth.session?.userID, fixture.candidate.userID)
        XCTAssertFalse(auth.canLinkFallsoft)
        let profile = try JSONDecoder().decode(
            IdentityLinkProfile.self, from: XCTUnwrap(KeychainStore.read(account: "profile-user_shared_fixture")))
        XCTAssertEqual(profile.id, intent.accountID)
    }
    func testWrongLegacyUserCannotContinueToSharedAuthentication() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let fixture = try fixture()
        let auth = try installLegacyFlow()
        var launches = 0
        let originalProfile = try seedLegacyProfile(fixture.intent)
        let original = try KeychainStore.read(account: "session")
        auth.qualificationSignInLaunch = { _ in launches += 1 }
        auth.qualificationCodeExchange = { _, _, authority in
            VipiSession(
                userID: "user_wrong_fixture", accessToken: "synthetic-access", refreshToken: "synthetic-refresh",
                authority: authority)
        }
        auth.beginFallsoftLink(
            accountID: fixture.intent.accountID,
            device: DeviceCredential(id: fixture.intent.deviceID, secret: fixture.intent.deviceSecret))
        await auth.complete(try callback(pending()))
        XCTAssertEqual(launches, 1)
        XCTAssertNotNil(auth.errorMessage)
        XCTAssertEqual(try KeychainStore.read(account: "session"), original)
        XCTAssertEqual(try KeychainStore.read(account: "profile-user_original_fixture"), originalProfile)
        XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
    }
    func testCancellationAtEitherSignInStageKeepsLegacyIdentityAndNeverLinks() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        for cancelTarget in [false, true] {
            let fixture = try fixture()
            let auth = try installLegacyFlow()
            var launches = 0
            let originalProfile = try seedLegacyProfile(fixture.intent)
            auth.qualificationSignInLaunch = { _ in launches += 1 }
            auth.qualificationCodeExchange = { _, _, authority in
                VipiSession(
                    userID: fixture.intent.oldUserID, accessToken: "synthetic-fresh-access",
                    refreshToken: "synthetic-fresh-refresh", authority: authority)
            }
            auth.beginFallsoftLink(
                accountID: fixture.intent.accountID,
                device: DeviceCredential(id: fixture.intent.deviceID, secret: fixture.intent.deviceSecret))
            if cancelTarget { await auth.complete(try callback(pending())) }
            auth.qualificationCancelSignIn()
            XCTAssertEqual(launches, cancelTarget ? 2 : 1)
            XCTAssertEqual(auth.session?.userID, fixture.intent.oldUserID)
            XCTAssertTrue(auth.canLinkFallsoft)
            XCTAssertEqual(try KeychainStore.read(account: "profile-user_original_fixture"), originalProfile)
            XCTAssertFalse(auth.busy)
            XCTAssertNil(try KeychainStore.read(account: "pending-sign-in"))
            XCTAssertNil(try KeychainStore.read(account: "pending-identity-link"))
        }
    }
    func testRecoveredJournalKeepsItsRequestAndRejectsAnotherSharedTarget() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let fixture = try fixture()
        let auth = try installLegacyFlow()
        try KeychainStore.save(JSONEncoder().encode(fixture), account: "pending-identity-link")
        auth.qualificationSignInLaunch = { _ in }
        auth.qualificationCodeExchange = { _, _, authority in
            VipiSession(
                userID: authority == .vipiProduction ? fixture.intent.oldUserID : "user_wrong_fixture",
                accessToken: "synthetic-access", refreshToken: "synthetic-refresh", authority: authority)
        }
        auth.beginFallsoftLink(
            accountID: fixture.intent.accountID,
            device: DeviceCredential(id: fixture.intent.deviceID, secret: fixture.intent.deviceSecret))
        XCTAssertEqual(try pending().sourceLink?.requestID, fixture.intent.requestID)
        await auth.complete(try callback(pending()))
        XCTAssertEqual(try pending().link?.expectedSharedUser, fixture.candidate.userID)
        await auth.complete(try callback(pending()))
        XCTAssertEqual(auth.session?.userID, fixture.intent.oldUserID)
        XCTAssertNotNil(auth.errorMessage)
        let retained = try JSONDecoder().decode(
            IdentityLinkJournal.self, from: XCTUnwrap(KeychainStore.read(account: "pending-identity-link")))
        XCTAssertEqual(retained.intent.requestID, fixture.intent.requestID)
        XCTAssertEqual(retained.candidate.userID, fixture.candidate.userID)
    }
    func testSharedAndStagingSessionsDoNotOfferOrStartLegacyMigration() throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let fixture = try fixture()
        for authority in [IdentityAuthority.fallsoftVipiProduction, .vipiStaging] {
            try KeychainStore.save(
                JSONEncoder().encode(
                    VipiSession(
                        userID: "user_shared_fixture", accessToken: "synthetic-access",
                        refreshToken: "synthetic-refresh", authority: authority)), account: "session")
            let auth = AuthenticationManager()
            auth.qualificationSignInLaunch = { _ in XCTFail("Only legacy accounts may start migration") }
            XCTAssertFalse(auth.canLinkFallsoft)
            auth.beginFallsoftLink(
                accountID: fixture.intent.accountID,
                device: DeviceCredential(id: fixture.intent.deviceID, secret: fixture.intent.deviceSecret))
            XCTAssertNotNil(auth.errorMessage)
            XCTAssertFalse(auth.busy)
        }
    }

    private final class OfflineSettingsTransport: ChatTransport {
        var requests = 0
        func request<T: Decodable>(
            _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
            as type: T.Type
        ) async throws -> T {
            requests += 1
            XCTFail("Settings qualification must not call a backend")
            throw URLError(.unsupportedURL)
        }
    }
    func testNativeSettingsPresentationForLegacyAndSharedIdentityWithoutBackend() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else {
            XCTFail("Native hosted app scene required")
            return
        }
        let previous = scene.windows.first(where: \.isKeyWindow)
        let transport = OfflineSettingsTransport()
        let profile = ChatProfile(id: UUID(), username: "synthetic_profile", display_name: "Synthetic")
        for authority in [IdentityAuthority.vipiProduction, .fallsoftVipiProduction] {
            let user = authority == .vipiProduction ? "user_original_fixture" : "user_shared_fixture"
            try KeychainStore.save(
                JSONEncoder().encode(
                    VipiSession(
                        userID: user, accessToken: "synthetic-access", refreshToken: "synthetic-refresh",
                        authority: authority)), account: "session")
            let auth = AuthenticationManager()
            let chat = ChatSession(qualificationAPI: transport, userID: user, ready: true, profile: profile)
            XCTAssertEqual(auth.canLinkFallsoft, authority == .vipiProduction)
            // This fixture deliberately has no protocol core/device. The real
            // Settings caller must not create an identity or device to link it.
            XCTAssertThrowsError(try chat.identityLinkTarget(expectedUser: user))
            XCTAssertThrowsError(try chat.identityLinkTarget(expectedUser: "user_wrong_fixture"))
            let controller = UIHostingController(
                rootView: NavigationStack { SettingsView(chat: chat) }
                    .environment(AppState()).environment(auth))
            let window = UIWindow(windowScene: scene)
            window.frame = scene.coordinateSpace.bounds
            window.rootViewController = controller
            window.makeKeyAndVisible()
            controller.view.layoutIfNeeded()
            try await Task.sleep(for: .milliseconds(200))
            controller.view.layoutIfNeeded()
            var views = [controller.view!]
            while !views.isEmpty {
                let view = views.removeFirst()
                views.append(contentsOf: view.subviews)
                if let scroll = view as? UIScrollView, scroll.contentSize.height > scroll.bounds.height {
                    scroll.setContentOffset(
                        CGPoint(
                            x: 0,
                            y: max(
                                -scroll.adjustedContentInset.top,
                                scroll.contentSize.height - scroll.bounds.height + scroll.adjustedContentInset.bottom)),
                        animated: false)
                    break
                }
            }
            controller.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: controller.view.bounds).image { _ in
                controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = authority == .vipiProduction ? "legacy-settings-explicit-link" : "shared-settings-no-link"
            attachment.lifetime = .keepAlways
            add(attachment)
            window.isHidden = true
            window.rootViewController = nil
            try chat.close()
        }
        previous?.makeKeyAndVisible()
        XCTAssertEqual(transport.requests, 0)
    }

    func testEqualRawSubjectsAcrossRealmsKeepCurrentSharedProfileCache() async throws {
        let saved = try keys.map { ($0, try KeychainStore.read(account: $0)) }
        defer { restore(saved) }
        let fixture = try fixture()
        let profileData = try seedLegacyProfile(fixture.intent)
        let profile = try JSONDecoder().decode(IdentityLinkProfile.self, from: profileData)
        let candidate = VipiSession(
            userID: fixture.intent.oldUserID, accessToken: "synthetic-shared-access", refreshToken: "synthetic-refresh",
            authority: .fallsoftVipiProduction)
        let journal = try IdentityLinkJournal(intent: fixture.intent, candidate: candidate, verifiedProfile: profile)
        try KeychainStore.save(JSONEncoder().encode(candidate), account: "session")
        try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
        let auth = AuthenticationManager()
        auth.qualificationLinkRequest = { _, _, _, _, _ in
            XCTFail("Verified recovery must remain local")
            throw URLError(.unsupportedURL)
        }
        await auth.resumeFallsoftLink()
        XCTAssertNil(auth.errorMessage)
        XCTAssertEqual(try KeychainStore.read(account: "profile-user_original_fixture"), profileData)
    }

}
