import XCTest

@MainActor final class ContinuousImmersionTests: XCTestCase {
    func testReadingSurfaceKeepsStableGeometryAndPracticeWords() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-source", "en", "-vipi-target", "es", "-readingPace", "balanced"]; app.launch()
        let thread = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
        XCTAssertTrue(thread.waitForExistence(timeout: 20)); thread.tap()
        let text = app.descendants(matching: .any)["immersionText"]
        XCTAssertTrue(text.waitForExistence(timeout: 15))
        let target = "agua, agua!"
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", target), object: text)], timeout: 10), .completed)
        let label = text.label, frame = text.frame
        Thread.sleep(forTimeInterval: 2)
        XCTAssertEqual(text.label, label, "Visual practice state must not shift on its own")
        XCTAssertEqual(text.frame.height, frame.height, accuracy: 0.5)
        XCTAssertEqual(text.frame.minY, frame.minY, accuracy: 0.5)
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "Stable native reading surface"; capture.lifetime = .keepAlways; add(capture)
        let word = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'immersion-word-' AND label == 'agua'")).firstMatch
        XCTAssertTrue(word.waitForExistence(timeout: 5)); word.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        let language = app.buttons["conversation-language"]
        XCTAssertTrue(language.waitForExistence(timeout: 5)); language.tap()
        XCTAssertTrue(app.buttons["language-choice-es"].waitForExistence(timeout: 3))
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

    /// UIKit context-menu items may share image-derived identifiers. Resolve
    /// the unique visible label/frame, then deliver one real coordinate tap.
    @MainActor @discardableResult func tapNativeMenuButton(_ title: String, in app: XCUIApplication,
        excluding frameToExclude: CGRect? = nil, file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let matches = app.buttons.matching(NSPredicate(format: "label == %@", title))
        var previousFrame: CGRect?
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            let visible = matches.allElementsBoundByIndex.filter {
                $0.isHittable && app.frame.contains($0.frame) && $0.frame != frameToExclude
            }
            guard visible.count == 1 else { return false }
            let frame = visible[0].frame
            defer { previousFrame = frame }
            return previousFrame == frame
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 5), .completed, file: file, line: line)
        let visible = matches.allElementsBoundByIndex.filter {
            $0.isHittable && app.frame.contains($0.frame) && $0.frame != frameToExclude
        }
        guard visible.count == 1 else {
            XCTFail("The native menu choice must be uniquely visible", file: file, line: line)
            return matches.firstMatch
        }
        let choice = visible[0]
        XCTAssertTrue(choice.exists && choice.isHittable, file: file, line: line)
        // Freeze the measured point before event delivery. Several native
        // rows share an image identifier; an element-relative coordinate may
        // rebind to a different row when XCTest synthesizes the actual tap.
        let screenPoint = choice.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).screenPoint
        let origin = app.frame.origin
        let point = app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: screenPoint.x - origin.x, dy: screenPoint.y - origin.y))
        let witness = XCTAttachment(string: "native menu choice=\(title); frame=\(choice.frame); fixed_screen_point=\(screenPoint)")
        witness.name = "native-menu-choice-coordinate"; witness.lifetime = .keepAlways; add(witness)
        point.tap()
        return choice
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
        // Capture before opening: firstMatch can rebind to the submenu after
        // the native menu appears, despite retaining the same label.
        let triggerFrame = app.buttons["Reading options"].firstMatch.frame
        openInlineMessageActions(in: app, file: file, line: line)
        tapNativeMenuButton("Reading options", in: app, excluding: triggerFrame, file: file, line: line)
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
        tapNativeMenuButton("Reading options", in: app, file: file, line: line)
        XCTAssertTrue(app.buttons["Word switching"].waitForExistence(timeout: 5), file: file, line: line)
    }

    @MainActor func selectReadingMode(_ title: String, in app: XCUIApplication,
        file: StaticString = #filePath, line: UInt = #line) {
        let choice = tapNativeMenuButton(title, in: app, file: file, line: line)
        let other = app.buttons[title == "Original message" ? "Word switching" : "Original message"]
        var selectionObserved = false
        let applied = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            if choice.exists && choice.isSelected { selectionObserved = true; return true }
            return !choice.exists && !other.exists
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [applied], timeout: 5), .completed, file: file, line: line)
        if other.exists {
            XCTAssertTrue(selectionObserved, file: file, line: line)
            app.navigationBars.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        XCTAssertTrue(other.waitForNonExistence(timeout: 5), file: file, line: line)
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
        // SwiftUI propagates the stack identifier to its header buttons and
        // scroll view. Scope content by native role, not any.firstMatch.
        let panel = app.scrollViews.matching(identifier: "manual-translation-panel").firstMatch
        XCTAssertTrue(panel.waitForExistence(timeout: 10), file: file, line: line)
        return panel
    }
    @MainActor func chooseMessageLanguage(_ language: String, in app: XCUIApplication, paragraph: XCUIElement,
        file: StaticString = #filePath, line: UInt = #line) {
        openMessageReadingOptions(in: app, paragraph: paragraph, file: file, line: line)
        tapNativeMenuButton("Message language", in: app, file: file, line: line)
        XCTAssertTrue(app.buttons["Detect automatically"].waitForExistence(timeout: 5), file: file, line: line)
        let choice = tapNativeMenuButton(language, in: app, file: file, line: line)
        let automatic = app.buttons["Detect automatically"]
        var selectionObserved = false
        let applied = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            if choice.exists && choice.isSelected { selectionObserved = true; return true }
            return !automatic.exists
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [applied], timeout: 5), .completed, file: file, line: line)
        if automatic.exists {
            XCTAssertTrue(selectionObserved, file: file, line: line)
            app.navigationBars.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        XCTAssertTrue(automatic.waitForNonExistence(timeout: 5), file: file, line: line)
    }

    @MainActor func closeTranslationPanel(_ panel: XCUIElement, in app: XCUIApplication,
        file: StaticString = #filePath, line: UInt = #line) {
        let close = app.buttons.matching(identifier: "manual-translation-panel")
            .matching(NSPredicate(format: "label == 'Close'")).firstMatch
        XCTAssertTrue(close.waitForExistence(timeout: 5), file: file, line: line)
        close.tap()
        XCTAssertTrue(panel.waitForNonExistence(timeout: 5), file: file, line: line)
    }
}
