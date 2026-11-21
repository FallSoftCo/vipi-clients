import XCTest

final class ReceivedPhotoUITests: XCTestCase {
    @MainActor func testOpenVerifiedPhotoFromConversationAndReturn() throws {
        try XCTSkipUnless(Bundle(for: Self.self).bundleIdentifier == "co.fallsoft.vipi.mediaqa.vieweruitests", "Requires the isolated media UI test bundle")
        let app = XCUIApplication()
        app.launchArguments += ["-vipi-received-photo-qa", "-vipi-photo-damaged-cache"]
        app.launch()
        let open = app.buttons["Open photo"]
        XCTAssertTrue(open.waitForExistence(timeout: 30), app.debugDescription)
        for name in ["First open", "Offline reopen"] {
            open.tap()
            if name == "First open" {
                let retry = app.buttons["Try again"]
                XCTAssertTrue(retry.waitForExistence(timeout: 15), app.debugDescription)
                XCTAssertTrue(app.staticTexts["Couldn’t open this photo."].exists)
                XCTAssertFalse(app.images["verified-photo-image"].exists)
                let error = XCTAttachment(screenshot: app.screenshot())
                error.name = "Damaged photo"; error.lifetime = .keepAlways; add(error)
                retry.tap()
            }
            let image = app.images["verified-photo-image"]
            XCTAssertTrue(image.waitForExistence(timeout: 15), app.debugDescription)
            XCTAssertEqual(image.label, "Opened photo")
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = name; capture.lifetime = .keepAlways; add(capture)
            app.buttons["Close"].tap()
            XCTAssertTrue(open.waitForExistence(timeout: 5))
        }
    }
}
