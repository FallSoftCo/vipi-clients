import XCTest

@MainActor final class ContinuousImmersionTests: XCTestCase {
    func testRepeatsWithoutTapsPreservesGeometryAndResumesAfterPause() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-welcome", "-readingPace", "balanced"]; app.launch()
        let text = app.descendants(matching: .any)["immersionText"]
        XCTAssertTrue(text.waitForExistence(timeout: 15))
        let target = "Café mañana? I know a little place by the río."
        let original = "Coffee tomorrow? I know a little place by the river."
        let first = text.frame
        for index in 0..<6 {
            let expected = index.isMultiple(of: 2) ? original : target
            let change = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", expected), object: text)
            XCTAssertEqual(XCTWaiter.wait(for: [change], timeout: 8), .completed)
            XCTAssertEqual(text.frame.height, first.height, accuracy: 0.5)
            XCTAssertEqual(text.frame.minY, first.minY, accuracy: 0.5)
            let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "Continuous phase \(index)"; capture.lifetime = .keepAlways; add(capture)
        }
        app.buttons["immersionPause"].tap()
        let held = text.label
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", held), object: text)
        changed.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 8), .completed)
        app.buttons["immersionPause"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", held), object: text)], timeout: 8), .completed)
        app.buttons["immersionPause"].tap()
        openInlineReadingOptions(in: app)
        app.buttons["Show original words now"].tap()
        XCTAssertEqual(text.label, original)
        XCTAssertEqual(app.buttons["immersionPause"].label, "Resume word switching")
        app.buttons["immersionPause"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", target), object: text)], timeout: 8), .completed)
        app.buttons["Choose languages"].tap()
        XCTAssertTrue(app.buttons["I speak"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["Try a little Spanish"].exists)
    }
}


extension XCTestCase {
    /// Each UI case owns its orientation, including when a preceding case
    /// intentionally exercised landscape. XCTest teardown also runs on failure.
    @MainActor func launchPortraitApp(_ app: XCUIApplication,
        file: StaticString = #filePath, line: UInt = #line) {
        let initial = XCUIDevice.shared.orientation
        addTeardownBlock { @MainActor in XCUIDevice.shared.orientation = initial }
        XCUIDevice.shared.orientation = .portrait
        app.launch()
        let portrait = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            app.frame.height > app.frame.width
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [portrait], timeout: 5), .completed, file: file, line: line)
    }

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
        XCTAssertTrue(app.buttons["Copy original message"].waitForNonExistence(timeout: 5), file: file, line: line)
        // The production UITextView has an explicit native whitespace action.
        // Tap its trailing blank area, rather than the outer SwiftUI padding.
        let point = paragraph.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.98))
        let before = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        before.name = "native-message-whitespace-before-tap"; before.lifetime = .keepAlways; add(before)
        let bounds = paragraph.frame
        let evidence = XCTAttachment(string: "paragraph=\(bounds); label=\(paragraph.label); nativeWhitespacePoint=\(point.screenPoint)")
        evidence.name = "native-message-whitespace-gesture"; evidence.lifetime = .keepAlways; add(evidence)
        point.tap()
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
        XCTAssertTrue(app.buttons["Detect automatically"].waitForNonExistence(timeout: 5), file: file, line: line)
        XCTAssertTrue(app.buttons["Copy original message"].waitForNonExistence(timeout: 5), file: file, line: line)
    }

    @MainActor func closeTranslationPanel(_ panel: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        let close = panel.buttons["Close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5), file: file, line: line)
        close.tap()
        XCTAssertTrue(panel.waitForNonExistence(timeout: 5), file: file, line: line)
    }
}
