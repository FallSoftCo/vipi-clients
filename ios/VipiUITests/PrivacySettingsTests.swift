import XCTest

final class PrivacySettingsTests: XCTestCase {
    @MainActor func testPrivacyStickerInLightAndDark() throws {
        for appearance in ["light", "dark"] {
            try checkSticker(appearance: appearance, category: "UICTContentSizeCategoryL", name: appearance)
        }
    }

    @MainActor func testPrivacyStickerAtLargestType() throws {
        try checkSticker(appearance: "dark", category: "UICTContentSizeCategoryAccessibilityXXXL", name: "largest")
    }

    @MainActor private func checkSticker(appearance: String, category: String, name: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }

        func capture(_ name: String) {
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = name; image.lifetime = .keepAlways; add(image)
        }

        app.launchArguments = ["-vipi-preview-home", "-vipi-appearance-" + appearance,
                               "-UIPreferredContentSizeCategoryName", category]
        app.launch()
        let settings = app.buttons["Your profile and settings"]
        XCTAssertTrue(settings.waitForExistence(timeout: 12)); settings.tap()
        let card = app.buttons["settings-privacy-promise"]
        let form = app.collectionViews.firstMatch
        let top = app.navigationBars["Settings"].frame.maxY + 35
        let bottom = app.frame.maxY - 34
        for _ in 0..<20 {
            let frame = card.exists ? card.frame : .zero
            if !frame.isEmpty, card.isHittable, frame.minY >= top, frame.maxY <= bottom { break }
            let shift = frame.isEmpty ? -210 : min(210, max(-210, (top + bottom) / 2 - frame.midY))
            let start = form.coordinate(withNormalizedOffset: .init(dx: 0.5, dy: 0.5))
            start.press(forDuration: 0.08, thenDragTo: start.withOffset(.init(dx: 0, dy: shift)),
                        withVelocity: .slow, thenHoldForDuration: 0.25)
        }
        XCTAssertTrue(card.isHittable)
        XCTAssertGreaterThanOrEqual(card.frame.minY, top)
        XCTAssertLessThanOrEqual(card.frame.maxY, bottom)
        XCTAssertTrue(card.label.contains("FallSoft’s privacy promise"))
        XCTAssertEqual(card.value as? String, "Certified Zucker Free, FallSoft’s privacy mark")
        XCTAssertEqual(card.frame.midX, app.frame.midX, accuracy: 3)
        capture("settings-privacy-" + name)
        card.tap()
        let sticker = app.images["Certified Zucker Free, FallSoft’s privacy mark"]
        XCTAssertTrue(sticker.waitForExistence(timeout: 5))
        XCTAssertEqual(sticker.frame.midX, app.frame.midX, accuracy: 3)
        XCTAssertGreaterThan(sticker.frame.width, min(app.frame.width * 0.8, 380))
        XCTAssertTrue(app.staticTexts["FallSoft’s privacy promise"].exists)
        XCTAssertTrue(app.staticTexts["We don’t sell your chat content."].exists)
        capture("privacy-promise-" + name)
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "privacy-layout-" + name; tree.lifetime = .keepAlways; add(tree)
        let policy = app.buttons["Privacy Policy"]
        let policyLink = policy.exists ? policy : app.links["Privacy Policy"]
        for _ in 0..<4 where !policyLink.isHittable { app.swipeUp() }
        XCTAssertTrue(policyLink.isHittable)
        app.navigationBars["Privacy"].buttons.element(boundBy: 0).tap()
        XCTAssertTrue(card.waitForExistence(timeout: 5))
    }
}
