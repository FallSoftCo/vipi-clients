import XCTest
import SwiftUI
import WorkOS
@testable import Vipi

@MainActor final class ChatReauthenticationTests: XCTestCase {
    private final class ExpiredTransport: ChatTransport {
        var error: Error
        var calls = 0
        init(_ error: Error) { self.error = error }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            calls += 1
            throw error
        }
    }
    func testExpiredRequestsExposeRecoveryWithoutDeviceReplacement() async throws {
        for error: Error in [ServiceFailure(status: 401, code: "sign_in_required"), ServiceFailure(status: 401, code: "recent_sign_in_required"), AuthenticationManager.SessionFailure.signInRequired] {
            let transport = ExpiredTransport(error)
            let chat = ChatSession(qualificationAPI: transport, userID: "same-account-qualification", ready: true)
            await chat.start()
            XCTAssertTrue(chat.needsReauthentication)
            XCTAssertTrue(chat.ready)
            XCTAssertFalse(chat.needsDeviceReplacement)
            XCTAssertFalse(chat.hasPendingDeviceReplacement)
            XCTAssertEqual(chat.userID, "same-account-qualification")
            XCTAssertNotNil(chat.notice)
            await chat.synchronize()
            XCTAssertEqual(transport.calls, 1)
            try chat.close()
        }
    }
    func testRefreshRejectionDoesNotMislabelOfflineOrServerErrors() {
        XCTAssertTrue(AuthenticationManager.refreshRequiresSignIn(WorkOSError.badRequest(APIError(statusCode: 400, message: "expired", code: "invalid_grant"))))
        XCTAssertTrue(AuthenticationManager.refreshRequiresSignIn(WorkOSError.badRequest(APIError(statusCode: 400, message: "expired", raw: .object(["error": .string("invalid_grant")])))))
        XCTAssertFalse(AuthenticationManager.refreshRequiresSignIn(WorkOSError.badRequest(APIError(statusCode: 400, message: "invalid_grant"))))
        XCTAssertTrue(AuthenticationManager.refreshRequiresSignIn(WorkOSError.authentication(APIError(statusCode: 401, message: "rejected"))))
        XCTAssertFalse(AuthenticationManager.refreshRequiresSignIn(WorkOSError.network(URLError(.notConnectedToInternet))))
        XCTAssertFalse(AuthenticationManager.refreshRequiresSignIn(WorkOSError.server(APIError(statusCode: 503, message: "unavailable"))))
        XCTAssertFalse(AuthenticationManager.refreshRequiresSignIn(CancellationError()))
    }
    func testDeviceRevocationRemainsSeparate() async throws {
        let chat = ChatSession(qualificationAPI: ExpiredTransport(ServiceFailure(status: 401, code: "device_revoked")), userID: "same-account-qualification")
        await chat.start()
        XCTAssertTrue(chat.needsDeviceReplacement)
        XCTAssertFalse(chat.needsReauthentication)
        try chat.close()
    }
    func testRecoverySurvivesNetworkFailureUntilAuthenticated() {
        var state = ChatAuthenticationRecovery()
        state.failed(ServiceFailure(status: 401, code: "sign_in_required"), deviceRecovery: false)
        state.failed(URLError(.notConnectedToInternet), deviceRecovery: false)
        XCTAssertTrue(state.required)
        state.authenticated()
        XCTAssertFalse(state.required)
        state.failed(ServiceFailure(status: 401, code: "recent_sign_in_required"), deviceRecovery: true)
        XCTAssertFalse(state.required)
        state.failed(AuthenticationManager.SessionFailure.accountChanged, deviceRecovery: false)
        XCTAssertFalse(state.required)
    }
    func testRecoveryComponentDisplaysActionAndSavedHistoryExplanation() throws {
        let renderer = ImageRenderer(content: ReauthenticationNotice(busy: false, error: "Sign in to the same account to continue.", signIn: {}).frame(width: 358).padding(16))
        let image = try XCTUnwrap(renderer.uiImage)
        let attachment = XCTAttachment(image: image); attachment.name = "same-account-reauthentication-component"; attachment.lifetime = .keepAlways
        add(attachment)
        XCTAssertGreaterThan(image.size.height, 80)
    }
}
