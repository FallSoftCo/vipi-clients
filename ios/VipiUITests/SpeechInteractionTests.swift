import XCTest

@MainActor final class SpeechInteractionTests: XCTestCase {
    func testListenFollowsReadingStateAndNavigation() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-welcome", "-readingPace", "balanced"]
        app.launch()
        let text = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(text.waitForExistence(timeout: 10))
        let target = "Café mañana? I know a little place by the río."
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", target), object: text)], timeout: 10), .completed)
        app.buttons["immersionPause"].tap()
        let listen = app.buttons["messageListen"]
        XCTAssertTrue(listen.waitForExistence(timeout: 10))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND label == 'Listen'"), object: listen)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        let before = XCTAttachment(screenshot: app.screenshot()); before.name = "Welcome — voices ready"; before.lifetime = .keepAlways; add(before)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        let playing = XCTAttachment(screenshot: app.screenshot()); playing.name = "Mixed message — playing"; playing.lifetime = .keepAlways; add(playing)
        openInlineReadingOptions(in: app)
        app.buttons["Show original words now"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen'"), object: listen)], timeout: 2), .completed)
        XCTAssertEqual(text.label, "Coffee tomorrow? I know a little place by the river.")
        // Resume the real clock, then hold the mixed face for a native word tap.
        app.buttons["immersionPause"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", target), object: text)], timeout: 8), .completed)
        app.buttons["immersionPause"].tap()
        print("VIPI_ACCESSIBILITY_TREE\n\(app.debugDescription)")
        // Use the native attachment’s stable identifier and visible word face.
        let word = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'immersion-word-' AND label == 'mañana'")).firstMatch
        XCTAssertTrue(word.exists)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        word.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen'"), object: listen)], timeout: 2), .completed)
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'immersion-word-' AND label == 'tomorrow'")).firstMatch.exists)
        let revealed = XCTAttachment(screenshot: app.screenshot()); revealed.name = "Word revealed — message audio stopped"; revealed.lifetime = .keepAlways; add(revealed)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        app.buttons["Choose languages"].tap()
        XCTAssertTrue(app.buttons["I speak"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["Try a little Spanish"].exists)
    }
}
