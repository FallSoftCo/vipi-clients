import XCTest

final class ConversationStreakUITests: XCTestCase {
    @MainActor func testDirectAndGroupRowsHeadersAndExplanations() throws {
        let app = XCUIApplication()
        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "ios-streak-" + name; shot.lifetime = .keepAlways; add(shot)
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
            capture(scenario + "-direct")
            badge.tap()
            XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 4))
            capture(scenario + "-meaning")
            app.alerts.buttons.firstMatch.tap()
            if scenario == "normal" {
                app.navigationBars.buttons.element(boundBy: 0).tap()
                app.buttons["home-compose"].tap()
                app.buttons["open-groups"].tap()
                let group = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Book club'")).firstMatch
                XCTAssertTrue(group.waitForExistence(timeout: 8))
                capture("groups")
                group.tap()
                XCTAssertTrue(badge.waitForExistence(timeout: 10)); XCTAssertTrue((badge.value as? String)?.contains("7") == true)
                capture("group-header")
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
