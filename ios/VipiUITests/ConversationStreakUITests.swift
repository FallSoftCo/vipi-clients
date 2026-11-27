import XCTest

final class ConversationStreakUITests: XCTestCase {
    @MainActor func testDirectAndGroupRowsHeadersAndExplanations() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "ios-streak-" + name; shot.lifetime = .keepAlways; add(shot)
        }
        func checkHeader() {
            let language = app.buttons["conversation-language"]
            let immersion = app.buttons["chat-immersion-picker"]
            let autoplay = app.buttons["chat-autoplay-toggle"]
            let identity = app.buttons["streak-explanation"]
            let options = app.buttons["conversation-options"].exists ? app.buttons["conversation-options"] : app.buttons["conversation-group-info"]
            let back = app.navigationBars.buttons["BackButton"].firstMatch
            let controls = [back, identity, language, immersion, autoplay, options]
            for control in controls {
                print("VIPI_HEADER_FRAME", control.identifier, control.frame, control.value ?? "")
                XCTAssertTrue(control.isHittable)
                XCTAssertTrue(app.frame.contains(control.frame))
                XCTAssertGreaterThanOrEqual(control.frame.width, 44 - 0.001)
                // The system Menu exposes 36pt within its 44pt toolbar slot.
                let minimumHeight: CGFloat = control.identifier == "conversation-options" ? 36 : 44
                XCTAssertGreaterThanOrEqual(control.frame.height, minimumHeight - 0.001)
                XCTAssertEqual(control.frame.midY, language.frame.midY, accuracy: 3)
            }
            let ordered = controls.map(\.frame).sorted { $0.minX < $1.minX }
            for (lhs, rhs) in zip(ordered, ordered.dropFirst()) {
                XCTAssertLessThanOrEqual(lhs.maxX, rhs.minX + 1)
            }
            XCTAssertFalse((language.value as? String ?? "").isEmpty)
        }
        for scenario in ["normal", "dark", "compact-rtl"] {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-streaks-qa"]
            if scenario == "dark" { app.launchArguments.append("-vipi-appearance-dark") }
            else { app.launchArguments.append("-vipi-appearance-light") }
            if scenario == "compact-rtl" {
                app.launchArguments += ["-vipi-streaks-compact-qa", "-AppleLanguages", "(ar)", "-AppleLocale", "ar_SA"]
            }
            app.launch()
            let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 35))
            let expected = scenario == "compact-rtl" ? "١٠٥" : "105"
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", expected), object: row)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 12), .completed)
            capture(scenario + "-inbox")
            if scenario == "dark" { app.terminate(); continue }
            row.tap()
            let badge = app.buttons["streak-explanation"]
            XCTAssertTrue(badge.waitForExistence(timeout: 8)); XCTAssertTrue((badge.value as? String)?.contains(expected) == true)
            XCTAssertGreaterThanOrEqual(badge.frame.width, 44)
            XCTAssertTrue(app.frame.contains(badge.frame))
            checkHeader()
            if scenario == "normal" {
                let language = app.buttons["conversation-language"]
                language.tap()
                let search = app.searchFields.firstMatch
                XCTAssertTrue(search.waitForExistence(timeout: 5))
                search.tap()
                search.typeText("fran")
                let french = app.buttons["language-choice-fr"]
                XCTAssertTrue(french.waitForExistence(timeout: 4))
                capture("search-language")
                french.tap()
                XCTAssertEqual(language.value as? String, "French")
                XCTAssertGreaterThan(language.frame.width, 54, "Show the full language on a standard-width phone")
                XCTAssertGreaterThanOrEqual(language.frame.minX - badge.frame.maxX, 8)
            }
            capture(scenario + "-direct")
            if scenario == "normal" {
                let menu = app.buttons["conversation-options"]
                menu.tap()
                let languages = app.buttons["conversation-languages"]
                XCTAssertTrue(languages.waitForExistence(timeout: 4))
                languages.tap()
                XCTAssertTrue(app.navigationBars["Your languages"].waitForExistence(timeout: 5))
                app.navigationBars.buttons["BackButton"].tap()
            }
            badge.tap()
            XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 4))
            capture(scenario + "-meaning")
            app.alerts.buttons.firstMatch.tap()
            if scenario == "normal" {
                app.navigationBars.buttons.element(boundBy: 0).tap()
                let group = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'group-thread-' AND label CONTAINS 'Book club'")).firstMatch
                XCTAssertTrue(group.waitForExistence(timeout: 8))
                capture("groups-in-inbox")
                group.tap()
                XCTAssertTrue(badge.waitForExistence(timeout: 10)); XCTAssertTrue((badge.value as? String)?.contains("7") == true)
                checkHeader()
                let language = app.buttons["conversation-language"]
                XCTAssertNotEqual(language.value as? String, "French")
                language.tap()
                let german = app.buttons["language-choice-de"]
                XCTAssertTrue(german.waitForExistence(timeout: 4))
                german.tap()
                XCTAssertEqual(language.value as? String, "German")
                XCTAssertGreaterThan(language.frame.width, 54, "Show the full language on a standard-width phone")
                XCTAssertGreaterThanOrEqual(language.frame.minX - badge.frame.maxX, 8)
                capture("group-header")
                language.tap()
                let reset = app.buttons["conversation-language-default"]
                XCTAssertTrue(reset.waitForExistence(timeout: 4))
                reset.tap()
                XCTAssertNotEqual(language.value as? String, "German")
                badge.tap()
                XCTAssertTrue(app.alerts.staticTexts["A day counts when at least two different group members send a message. Days start at midnight UTC."].exists)
                capture("group-meaning")
            }
            app.terminate()
        }
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
        app.launch()
    }
}
