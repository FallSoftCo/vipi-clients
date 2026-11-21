import XCTest

final class ChatFeedbackUITests: XCTestCase {
    @MainActor func testHintDismissAndHoldInBothReadingModes() throws {
        continueAfterFailure = false
        for mode in ["incremental", "fullMessages"] {
            let app = XCUIApplication()
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-appearance-light", "-vipi-source", "en", "-vipi-target", "es", "-immersionMode", mode, "-full-message-gestures-v1-seen", "YES"]
            app.launch()
            let thread = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
            XCTAssertTrue(thread.waitForExistence(timeout: 20)); thread.tap()
            let hint = app.staticTexts["chat-gesture-hint"]
            XCTAssertTrue(hint.waitForExistence(timeout: 12))
            let target = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label CONTAINS[c] 'agua'")).firstMatch
            XCTAssertTrue(target.exists)
            let rect = target.frame
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "ios-hold-hint-" + mode; image.lifetime = .keepAlways; add(image)
            if mode == "incremental" { app.buttons["Dismiss hint"].tap() }
            else { target.press(forDuration: 0.7) }
            XCTAssertTrue(hint.waitForNonExistence(timeout: 3)); XCTAssertFalse(app.buttons["Dismiss hint"].exists)
            XCTAssertTrue(target.exists); XCTAssertLessThanOrEqual(target.frame.minY, rect.minY + 1)
            app.navigationBars.buttons.element(boundBy: 0).tap()
            XCTAssertTrue(thread.waitForExistence(timeout: 5))
            thread.tap()
            XCTAssertFalse(hint.exists)
            app.terminate()
        }
    }

    @MainActor func testOptionalSettingsGuideDemonstratesHoldOnceThenSupportsActualInput() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-source", "en", "-vipi-target", "es", "-immersionMode", "fullMessages"]
        app.launch(); defer { app.terminate() }
        let settings = app.buttons["Your profile and settings"]
        XCTAssertTrue(settings.waitForExistence(timeout: 20)); settings.tap()
        let help = app.buttons["settings-help"]
        for _ in 0..<10 where !help.isHittable { app.swipeUp() }
        XCTAssertTrue(help.isHittable); help.tap()
        let guide = app.buttons["tutorial-reentry"]
        for _ in 0..<12 where !guide.isHittable { app.swipeUp() }
        XCTAssertTrue(guide.isHittable); guide.tap()
        let rows = app.descendants(matching: .any).matching(identifier: "immersionText")
        let source = rows.matching(NSPredicate(format: "label == %@", "Coffee tomorrow?")).firstMatch
        let practice = rows.matching(NSPredicate(format: "label == %@", "¿Café mañana?")).firstMatch
        XCTAssertTrue(source.waitForExistence(timeout: 15))
        let held = XCTAttachment(screenshot: app.screenshot())
        held.name = "ios-guide-hold-demonstration"; held.lifetime = .keepAlways; add(held)
        XCTAssertTrue(practice.waitForExistence(timeout: 6))
        practice.press(forDuration: 0.65)
        XCTAssertTrue(practice.waitForExistence(timeout: 4))
        XCTAssertFalse(app.staticTexts["chat-gesture-hint"].exists)
        app.buttons["tutorial-continue"].tap()
        XCTAssertTrue(guide.waitForExistence(timeout: 5))
    }

    @MainActor func testSettingsHelpOpensVisualGuidesAndReturnsToSettings() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-source", "en", "-vipi-target", "es"]
        app.launch(); defer { app.terminate() }
        let settings = app.buttons["Your profile and settings"]
        XCTAssertTrue(settings.waitForExistence(timeout: 20)); settings.tap()
        let help = app.buttons["settings-help"]
        for _ in 0..<8 where !help.isHittable { app.swipeUp() }
        XCTAssertTrue(help.isHittable); help.tap()
        XCTAssertTrue(app.buttons["tutorial-reentry"].waitForExistence(timeout: 5))
        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = name; shot.lifetime = .keepAlways; add(shot)
        }
        capture("ios-native-help")
        for (key, prefix) in [("friends", "Open Chats"), ("groups", "Open New chat"), ("reading", "Tap a practice"), ("voice", "In a friend’s chat"), ("status", "One check"), ("languages", "Tap the language"),
                              ("notifications", "Open Notifications"), ("safety", "In a friend"),
                              ("backup", "Open Chat backup"), ("account", "If Vipi asks")] {
            let row = app.buttons["help-topic-" + key]
            for _ in 0..<8 where !row.isHittable { app.swipeUp() }
            XCTAssertTrue(row.isHittable, key); row.tap()
            let step = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", prefix)).firstMatch
            // SwiftUI materializes expanded List content as it enters the viewport.
            for _ in 0..<4 where !step.exists { app.swipeUp() }
            XCTAssertTrue(step.waitForExistence(timeout: 3), key)
            if key == "friends" {
                capture("ios-native-help-friends")
            }
            for _ in 0..<4 where !row.isHittable { app.swipeDown() }
            XCTAssertTrue(row.isHittable); row.tap()
        }
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.navigationBars["Settings"].waitForExistence(timeout: 5))
    }

    @MainActor func testEligibleReturnToChatsShowsOptionalFundingSurvey() throws {
        try qualifySurvey(appearance: "light")
    }
    @MainActor func testDarkSurvey() throws {
        try qualifySurvey(appearance: "dark")
    }
    @MainActor private func qualifySurvey(appearance: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-appearance-" + appearance, "-vipi-source", "en", "-vipi-target", "es"]
        app.launch()
        defer { app.terminate() }
        let thread = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
        XCTAssertTrue(thread.waitForExistence(timeout: 25))
        XCTAssertFalse(app.buttons["funding-yes"].exists)
        thread.tap()
        XCTAssertTrue(app.textViews["message-input"].waitForExistence(timeout: 8) || app.textFields["message-input"].exists)
        XCTAssertFalse(app.buttons["funding-yes"].exists)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.buttons["funding-yes"].waitForExistence(timeout: 7))
        for id in ["yes", "maybe", "no", "skip"] { XCTAssertTrue(app.buttons["funding-" + id].isHittable) }
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = "ios-funding-survey-chats-" + appearance; image.lifetime = .keepAlways; add(image)
        app.buttons["funding-maybe"].tap()
        XCTAssertFalse(app.buttons["funding-yes"].exists)
        thread.tap(); app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(thread.waitForExistence(timeout: 6)); XCTAssertFalse(app.buttons["funding-yes"].exists)
    }
}
