import XCTest

extension XCTestCase {
    /// Nonembedded previews retain a visible menu; reading settings now live in
    /// its nested submenu, alongside the separate Copy and Select actions.
    @MainActor func openInlineMessageActions(in app: XCUIApplication,
        file: StaticString = #filePath, line: UInt = #line) {
        let trigger = app.buttons["Reading options"].firstMatch
        XCTAssertTrue(trigger.waitForExistence(timeout: 5), file: file, line: line)
        trigger.tap()
        XCTAssertTrue(app.buttons["Copy original message"].waitForExistence(timeout: 5), file: file, line: line)
    }

    @MainActor func openInlineReadingOptions(in app: XCUIApplication,
        file: StaticString = #filePath, line: UInt = #line) {
        let triggerFrame = app.buttons["Reading options"].firstMatch.frame
        openInlineMessageActions(in: app, file: file, line: line)
        let submenu = app.buttons.matching(NSPredicate(format: "label == 'Reading options'"))
        let presented = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            submenu.allElementsBoundByIndex.contains { $0.isHittable && $0.frame != triggerFrame }
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [presented], timeout: 5), .completed, file: file, line: line)
        guard let control = submenu.allElementsBoundByIndex.first(where: { $0.isHittable && $0.frame != triggerFrame }) else {
            XCTFail("The native reading submenu must be presented", file: file, line: line); return
        }
        control.tap()
    }

    /// Embedded rows expose secondary reading actions through their native
    /// context menu. Press actual bubble padding, outside text-selection glyphs.
    @MainActor func openMessageActions(in app: XCUIApplication, paragraph: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(paragraph.exists && paragraph.isHittable, file: file, line: line)
        XCTAssertGreaterThan(paragraph.frame.minX, app.frame.minX + 8, file: file, line: line)
        paragraph.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.5))
            .withOffset(CGVector(dx: -7, dy: 0)).press(forDuration: 1)
        XCTAssertTrue(app.buttons["Copy original message"].waitForExistence(timeout: 5), file: file, line: line)
    }

    @MainActor func openMessageReadingOptions(in app: XCUIApplication, paragraph: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        openMessageActions(in: app, paragraph: paragraph, file: file, line: line)
        let submenu = app.buttons["Reading options"].firstMatch
        XCTAssertTrue(submenu.waitForExistence(timeout: 5), file: file, line: line)
        submenu.tap()
    }

    /// The current whole-message action opens a nonmodal translation panel;
    /// it does not replace the row with a full-target reading mode.
    @MainActor @discardableResult func translateMessage(in app: XCUIApplication, paragraph: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        XCTAssertTrue(paragraph.exists && paragraph.isHittable, file: file, line: line)
        paragraph.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.5))
            .withOffset(CGVector(dx: -7, dy: 0)).tap()
        let panel = app.descendants(matching: .any).matching(identifier: "manual-translation-panel").firstMatch
        XCTAssertTrue(panel.waitForExistence(timeout: 10), file: file, line: line)
        return panel
    }
    @MainActor func chooseMessageLanguage(_ language: String, in app: XCUIApplication, paragraph: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        openMessageReadingOptions(in: app, paragraph: paragraph, file: file, line: line)
        let choices = app.buttons["Message language"]
        XCTAssertTrue(choices.waitForExistence(timeout: 5), file: file, line: line)
        choices.tap()
        XCTAssertTrue(app.buttons[language].waitForExistence(timeout: 5), file: file, line: line)
        app.buttons[language].tap()
    }

    @MainActor func closeTranslationPanel(_ panel: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        let close = panel.buttons["Close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5), file: file, line: line)
        close.tap()
        XCTAssertTrue(panel.waitForNonExistence(timeout: 5), file: file, line: line)
    }
}
