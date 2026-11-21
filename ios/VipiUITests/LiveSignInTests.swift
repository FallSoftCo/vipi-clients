import XCTest
import UIKit

/// The private fixture is installed only into this simulator test runner's
/// Documents directory. It is never an app resource or a launch argument.
@MainActor final class LiveSignInTests: XCTestCase {
    private struct Identity: Decodable { let email: String; let password: String; let client_id: String }
    func testHostedFreshReauthenticationKeepsOwnedDevice() throws {
        let fixture = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("private-staging-identity.json")
        guard FileManager.default.fileExists(atPath: fixture.path) else { throw XCTSkip("Explicit private staging identity required") }
        let identity = try JSONDecoder().decode(Identity.self, from: Data(contentsOf: fixture))
        guard identity.email.hasSuffix("@example.net"), identity.client_id == "client_01M5S2CDSQ8F7FEX26G3CY9VS1" else { throw XCTSkip("Only the reserved dedicated staging identity is allowed") }
        continueAfterFailure = false
        defer { UIPasteboard.general.items = []; try? FileManager.default.removeItem(at: fixture) }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-reauth-qa", "-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.staticTexts["Ready to sign in again"].waitForExistence(timeout: 30))
        app.buttons["Sign in again"].tap()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if springboard.alerts.buttons["Continue"].waitForExistence(timeout: 5) { springboard.alerts.buttons["Continue"].tap() }
        if app.webViews.textFields["One-time code"].waitForExistence(timeout: 5) {
            return XCTFail("Provider requested a one-time code; stop without input, resend, or bypass")
        }
        let email = app.webViews.textFields.matching(NSPredicate(format: "label CONTAINS[c] 'email' OR identifier == 'email' OR placeholderValue CONTAINS[c] 'email'")).firstMatch
        if email.waitForExistence(timeout: 10) {
            if email.value as? String != identity.email {
                email.tap(); email.typeKey("a", modifierFlags: .command)
                paste(identity.email, into: email, app: app)
            }
            let next = app.webViews.buttons.matching(NSPredicate(format: "label == 'Continue' OR label == 'Continue with email'")).firstMatch
            XCTAssertTrue(next.waitForExistence(timeout: 10)); next.tap()
        }
        let password = app.webViews.secureTextFields.firstMatch
        XCTAssertTrue(password.waitForExistence(timeout: 25))
        paste(identity.password, into: password, app: app)
        let signIn = app.webViews.buttons.matching(NSPredicate(format: "label == 'Sign in' OR label == 'Continue'")).firstMatch
        XCTAssertTrue(signIn.waitForExistence(timeout: 10)); signIn.tap()
        XCTAssertTrue(app.staticTexts["Fresh sign-in verified"].waitForExistence(timeout: 35))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "owned-staging-fresh-reauthentication"; attachment.lifetime = .keepAlways; add(attachment)
        app.terminate(); app.launchArguments = []; app.launch()
        XCTAssertTrue(app.navigationBars["Chats"].buttons["home-compose"].waitForExistence(timeout: 20))
    }
    func testHostedPKCESignInForOwnedStagingIdentity() throws {
        let fixture = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("private-staging-identity.json")
        guard FileManager.default.fileExists(atPath: fixture.path) else { throw XCTSkip("Explicit private staging identity required") }
        let identity = try JSONDecoder().decode(Identity.self, from: Data(contentsOf: fixture))
        guard identity.email.hasSuffix("@example.net"), identity.client_id == "client_01M5S2CDSQ8F7FEX26G3CY9VS1" else { throw XCTSkip("Only the reserved dedicated staging identity is allowed") }
        continueAfterFailure = false
        // The isolated simulator pasteboard belongs to this QA run. Reading
        // another app's clipboard here can block on the system paste prompt.
        defer { UIPasteboard.general.items = []; try? FileManager.default.removeItem(at: fixture) }
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es", "-vipi-appearance-light"]
        app.launch()
        if app.navigationBars["Chats"].buttons["home-compose"].waitForExistence(timeout: 3) { throw XCTSkip("Reconcile the existing signed-in identity before a fresh login") }
        XCTAssertTrue(app.buttons["Choose languages"].waitForExistence(timeout: 15))
        app.buttons["Choose languages"].tap()
        XCTAssertTrue(app.buttons["I’m learning"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons["I’m learning"].value as? String, "Spanish")
        app.buttons["Continue"].tap()
        XCTAssertFalse(app.switches.firstMatch.exists)
        let accountContinue = app.buttons["Continue to sign in"]
        XCTAssertTrue(accountContinue.waitForExistence(timeout: 10)); XCTAssertTrue(accountContinue.isEnabled)
        accountContinue.tap()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if springboard.alerts.buttons["Continue"].waitForExistence(timeout: 5) { springboard.alerts.buttons["Continue"].tap() }
        if app.webViews.textFields["One-time code"].waitForExistence(timeout: 5) {
            return XCTFail("Provider requested a one-time code; stop without input, resend, or bypass")
        }
        let email = app.webViews.textFields.matching(NSPredicate(format: "label CONTAINS[c] 'email' OR identifier == 'email' OR placeholderValue CONTAINS[c] 'email'")).firstMatch
        XCTAssertTrue(email.waitForExistence(timeout: 30))
        paste(identity.email, into: email, app: app)
        let next = app.webViews.buttons.matching(NSPredicate(format: "label == 'Continue' OR label == 'Continue with email'")).firstMatch
        XCTAssertTrue(next.waitForExistence(timeout: 10)); next.tap()
        let password = app.webViews.secureTextFields.firstMatch
        XCTAssertTrue(password.waitForExistence(timeout: 20))
        paste(identity.password, into: password, app: app)
        let signIn = app.webViews.buttons.matching(NSPredicate(format: "label == 'Sign in' OR label == 'Continue'")).firstMatch
        XCTAssertTrue(signIn.waitForExistence(timeout: 10)); signIn.tap()
        let profile = app.textFields["profile-name"]
        if profile.waitForExistence(timeout: 30) {
            profile.tap(); profile.typeText("Vipi iOS QA")
            let username = app.textFields["profile-username"]; username.tap(); username.typeText("vqa_1107_ios01")
            app.switches["profile-accept-terms"].tap()
            app.buttons["profile-submit"].tap()
        }
        let joined = app.navigationBars["Chats"].buttons["home-compose"].waitForExistence(timeout: 30)
            && app.images["inbox-wordmark"].exists
            && !app.staticTexts["Chatting is paused"].exists
        guard joined else {
            // Keep diagnostics to route metadata. A full hierarchy/screenshot
            // while the provider is still open could retain private fields.
            let route = XCTAttachment(string: """
                new_chat=\(app.navigationBars["Chats"].buttons["home-compose"].exists)
                chats=\(app.images["inbox-wordmark"].exists)
                profile_required=\(app.textFields["profile-name"].exists)
                profile_error=\(app.staticTexts["profile-error"].exists)
                retry=\(app.buttons["Try again"].exists)
                chatting_paused=\(app.staticTexts["Chatting is paused"].exists)
                provider_webview=\(app.webViews.firstMatch.exists)
                """)
            route.name = "hosted-sign-in-incomplete-route"; route.lifetime = .keepAlways; add(route)
            return XCTFail("Hosted sign-in must reach the joined Chats screen. A retry/reconnect screen does not prove profile creation or joining; inspect the route-only diagnostic.")
        }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "owned-staging-authenticated-app"; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func paste(_ text: String, into field: XCUIElement, app: XCUIApplication) {
        // typeText(password) may be retained in XCTest activity logs. Paste
        // through the native shortcut so neither the secret nor an auth token is
        // a test action's argument, command line, assertion or attachment.
        UIPasteboard.general.string = text
        field.tap(); field.typeKey("v", modifierFlags: .command)
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if springboard.alerts.buttons["Allow Paste"].waitForExistence(timeout: 2) { springboard.alerts.buttons["Allow Paste"].tap() }
        if app.alerts.buttons["Allow Paste"].exists { app.alerts.buttons["Allow Paste"].tap() }
        let observed = field.value as? String ?? ""
        let correct = observed == text || (field.elementType == .secureTextField && observed.count == text.count && observed.allSatisfy { "•*".contains($0) })
        XCTAssertTrue(correct, "Native paste did not populate the intended field")
        UIPasteboard.general.items = []
    }
}
