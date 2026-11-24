import XCTest

/// The signed-out wizard is the first-run experience. Each page owns one idea,
/// and every page after the introduction must offer a visible forward action.
final class ImmersionTutorialTests: XCTestCase {
    @MainActor func testSevenPageWizardUsesRealSurfacesAndReachesGuestInbox() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es", "-vipi-appearance-light",
            "-vipi-onboarding-screenshot-fixture"]
        app.launch(); defer { app.terminate() }

        XCTAssertTrue(app.staticTexts["mambo-name-title"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["mambo-name-title"].label, "Mambo Vipi")
        XCTAssertTrue(element(app, "mambo-background").exists)
        XCTAssertFalse(app.staticTexts["tutorial-title"].exists)
        capture("ios-mambo-01-name", app: app)

        tapContinue(app)
        XCTAssertTrue(app.staticTexts["mambo-languages-title"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["mambo-known-language"].exists)
        XCTAssertTrue(app.buttons["mambo-target-language"].exists)
        capture("ios-mambo-02-languages", app: app)

        tapContinue(app)
        XCTAssertTrue(app.staticTexts["mambo-shallow-title"].waitForExistence(timeout: 10))
        let input = element(app, "mambo-message-input")
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap(); input.typeText("Coffee tomorrow?")
        let send = app.buttons["mambo-send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5)); send.tap()
        XCTAssertTrue(element(app, "mambo-message-bubble").waitForExistence(timeout: 20))
        let translated = app.descendants(matching: .any).matching(
            NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@", "Café", "mañana")).firstMatch
        XCTAssertTrue(translated.waitForExistence(timeout: 20), "The production bubble must render translated text")
        XCTAssertFalse(app.descendants(matching: .any).matching(
            NSPredicate(format: "label CONTAINS %@", "Translation isn’t supported")).firstMatch.exists)
        capture("ios-mambo-03-shallow", app: app)

        tapContinue(app)
        XCTAssertTrue(app.staticTexts["mambo-deep-title"].waitForExistence(timeout: 10))
        XCTAssertTrue(element(app, "mambo-message-bubble").waitForExistence(timeout: 20))
        capture("ios-mambo-04-deep", app: app)

        tapContinue(app)
        XCTAssertTrue(app.staticTexts["mambo-listen-title"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["mambo-continue"].waitForExistence(timeout: 10), "Hear-it page must not dead-end")
        capture("ios-mambo-05-listen", app: app)

        tapContinue(app)
        XCTAssertTrue(app.staticTexts["mambo-invite-title"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["mambo-share"].exists)
        XCTAssertTrue(app.buttons["mambo-invite-continue"].exists)
        capture("ios-mambo-06-invite", app: app)

        app.buttons["mambo-invite-continue"].tap()
        XCTAssertTrue(app.staticTexts["mambo-privacy-title"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["mambo-privacy-title"].label.contains("Private"))
        capture("ios-mambo-07-privacy", app: app)

        app.buttons["mambo-start"].tap()
        XCTAssertTrue(app.buttons["mambo-not-now"].waitForExistence(timeout: 10))
        app.buttons["mambo-not-now"].tap()
        XCTAssertTrue(app.staticTexts["Sign in to start chatting with friends."].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["guest-sign-in"].exists)
        capture("ios-mambo-guest-inbox", app: app)
    }

    @MainActor func testLargestArabicWizardKeepsForwardActionsReachable() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-welcome", "-vipi-source", "ar", "-vipi-target", "en", "-vipi-appearance-dark",
            "-AppleLanguages", "(ar)", "-AppleLocale", "ar", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.staticTexts["mambo-name-title"].waitForExistence(timeout: 20))
        let next = app.buttons["mambo-continue"]
        for _ in 0..<8 where !next.isHittable { app.swipeUp() }
        XCTAssertTrue(next.isHittable)
        capture("ios-mambo-arabic-largest", app: app)
    }

    @MainActor private func tapContinue(_ app: XCUIApplication) {
        let next = app.buttons["mambo-continue"]
        XCTAssertTrue(next.waitForExistence(timeout: 10))
        for _ in 0..<8 where !next.isHittable { app.swipeUp() }
        XCTAssertTrue(next.isHittable); next.tap()
    }

    @MainActor private func element(_ app: XCUIApplication, _ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    @MainActor private func capture(_ name: String, app: XCUIApplication) {
        let picture = XCTAttachment(screenshot: app.screenshot()); picture.name = name; picture.lifetime = .keepAlways; add(picture)
        let tree = XCTAttachment(string: app.debugDescription); tree.name = name + "-native-tree"; tree.lifetime = .keepAlways; add(tree)
    }
}
