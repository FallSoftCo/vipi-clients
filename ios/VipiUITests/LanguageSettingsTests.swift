import XCTest

final class LanguageSettingsTests: XCTestCase {
    @MainActor func testLanguageSettingsNavigationAndSelectionLightAndDark() throws {
        let app = XCUIApplication()
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-vipi-preview-home", "-vipi-source", "en", "-vipi-target", "ja", "-vipi-appearance-" + appearance]
            app.launch()
            let settings = app.buttons["Your profile and settings"]
            XCTAssertTrue(settings.waitForExistence(timeout: 10)); settings.tap()
            let link = app.buttons["language-settings-link"]
            XCTAssertTrue(link.waitForExistence(timeout: 5)); link.tap()
            let status = app.staticTexts["language-download-status"]
            XCTAssertTrue(status.waitForExistence(timeout: 10))
            let picker = app.buttons["language-target-picker"]
            XCTAssertTrue(picker.exists); picker.tap()
            let spanish = app.buttons["Spanish · Español"]
            XCTAssertTrue(spanish.waitForExistence(timeout: 5)); spanish.tap()
            let settled = NSPredicate(format: "label != %@", "Checking this device…")
            expectation(for: settled, evaluatedWith: status)
            waitForExpectations(timeout: 10)
            XCTAssertFalse(status.label.contains("Japanese"))
            XCTAssertFalse(app.staticTexts["language-download-message"].exists)
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "ios-language-settings-" + appearance; attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
    }
}
