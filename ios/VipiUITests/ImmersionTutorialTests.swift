import XCTest

/// Running production local adapters in a distinct simulator QA identity.
/// Availability is recorded honestly: unavailable model output is never replaced.
final class ImmersionTutorialTests: XCTestCase {
    @MainActor func testOptionalTutorialUsesRealControlsAndCarriesModeBeforeSignIn() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-language","-vipi-source","en","-vipi-target","es","-vipi-appearance-light"]
        app.launch(); defer { app.terminate() }
        let next = app.buttons["onboarding-continue"]
        XCTAssertTrue(next.waitForExistence(timeout:20)); XCTAssertTrue(next.isEnabled); next.tap()
        XCTAssertTrue(app.staticTexts["tutorial-title"].waitForExistence(timeout:15))
        let shallow = app.buttons["tutorial-mode-incremental"], deep = app.buttons["tutorial-mode-fullMessages"]
        XCTAssertTrue(shallow.exists); XCTAssertTrue(deep.exists)
        shallow.tap(); XCTAssertTrue(shallow.isSelected)
        let finish = app.buttons["tutorial-continue"]
        XCTAssertTrue(finish.isEnabled)
        capture("ios-tutorial-shallow-real-provider",app:app)
        deep.tap(); XCTAssertTrue(deep.isSelected)
        XCTAssertTrue(app.staticTexts["The whole message"].exists)
        capture("ios-tutorial-deep-real-provider",app:app)
        // Do not require any gesture, model download or working voice to leave.
        XCTAssertTrue(finish.isEnabled); finish.tap()
        XCTAssertTrue(app.staticTexts["Sign in to Vipi"].waitForExistence(timeout:10))
        capture("ios-tutorial-continued-before-signin",app:app)
        app.terminate(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.staticTexts["Sign in to Vipi"].waitForExistence(timeout:15))
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.staticTexts["tutorial-title"].waitForExistence(timeout:10))
        XCTAssertTrue(app.buttons["tutorial-mode-fullMessages"].isSelected)
        capture("ios-tutorial-persisted-deep",app:app)
    }
    @MainActor func testLargestArabicTutorialKeepsOptionalContinueAndKnownSource() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-tutorial","-vipi-source","ar","-vipi-target","en","-vipi-appearance-dark",
            "-AppleLanguages","(ar)","-AppleLocale","ar","-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.staticTexts["tutorial-title"].waitForExistence(timeout:20))
        capture("ios-tutorial-arabic-largest-top",app:app)
        let next = app.buttons["tutorial-continue"]
        for _ in 0..<8 where !next.isHittable { app.swipeUp() }
        XCTAssertTrue(next.isHittable); XCTAssertTrue(next.isEnabled)
        capture("ios-tutorial-arabic-largest-continue",app:app)
        next.tap()
        XCTAssertFalse(app.staticTexts["tutorial-title"].exists)
    }
    @MainActor private func capture(_ name:String,app:XCUIApplication) {
        let picture = XCTAttachment(screenshot:app.screenshot()); picture.name = name; picture.lifetime = .keepAlways; add(picture)
        let tree = XCTAttachment(string:app.debugDescription); tree.name = name+"-native-tree"; tree.lifetime = .keepAlways; add(tree)
    }
}
