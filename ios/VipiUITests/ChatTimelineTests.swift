import XCTest

final class ChatTimelineTests: XCTestCase {
    func testReadingPositionIncomingAppendKeyboardAndOwnSend() throws {
        continueAfterFailure = true
        let app = XCUIApplication(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-appearance-light"]; app.launch()
        defer {
            let finish = app.buttons["timeline-qa-finish"]
            if finish.exists { finish.tap() }
        }
        let last = app.staticTexts["History message 70. We are making plans for tomorrow."]
        XCTAssertTrue(last.waitForExistence(timeout: 20)); XCTAssertTrue(last.isHittable)
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        XCTAssertTrue(timeline.exists)
        timeline.swipeDown(); timeline.swipeDown()
        let jump = app.buttons["conversation-latest"]
        XCTAssertTrue(jump.waitForExistence(timeout: 5)); XCTAssertTrue(jump.isHittable)
        let messages = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "History message")).allElementsBoundByIndex
        let top = max(timeline.frame.minY, app.navigationBars.firstMatch.frame.maxY)
        let anchor = try XCTUnwrap(messages.filter { $0.isHittable && $0.frame.minY >= top + 10 && $0.frame.maxY <= timeline.frame.maxY - 10 }.min { $0.frame.minY < $1.frame.minY })
        let label = anchor.label; let y = anchor.frame.minY
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(jump.isHittable)
        XCTAssertEqual(app.staticTexts[label].frame.minY, y, accuracy: 3)
        capture("ios-reading-preserved-light")
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.typeText("A draft while reading")
        capture("ios-reading-with-keyboard-light")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts[label].isHittable); XCTAssertTrue(jump.isHittable)
        app.buttons["message-send"].tap()
        let sent = app.staticTexts["A draft while reading"]
        XCTAssertTrue(sent.waitForExistence(timeout: 5)); XCTAssertTrue(sent.isHittable)
        XCTAssertFalse(jump.exists)
        timeline.swipeDown()
        XCTAssertTrue(jump.waitForExistence(timeout: 5)); jump.tap()
        XCTAssertTrue(sent.isHittable); XCTAssertFalse(jump.exists)
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(app.staticTexts.matching(identifier: "Appended while reading earlier messages.").allElementsBoundByIndex.contains { $0.isHittable })
        capture("ios-following-latest-light")
        app.buttons["timeline-qa-finish"].tap()
        XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
}
