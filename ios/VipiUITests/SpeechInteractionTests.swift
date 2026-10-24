import XCTest

@MainActor final class SpeechInteractionTests: XCTestCase {
    func testListenFollowsReadingStateAndNavigation() {
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-welcome"]
        app.launch()
        app.buttons["immersionPause"].tap()
        let listen = app.buttons["messageListen"]
        XCTAssertTrue(listen.waitForExistence(timeout: 10))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND label == 'Listen'"), object: listen)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        let before = XCTAttachment(screenshot: app.screenshot()); before.name = "Welcome — voices ready"; before.lifetime = .keepAlways; add(before)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        let playing = XCTAttachment(screenshot: app.screenshot()); playing.name = "Mixed message — playing"; playing.lifetime = .keepAlways; add(playing)
        app.buttons["See the whole thought in Spanish"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen'"), object: listen)], timeout: 2), .completed)
        XCTAssertTrue(app.staticTexts["¿Café mañana? Conozco un pequeño lugar junto al río."].exists)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        app.buttons["Back to a little Spanish"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen'"), object: listen)], timeout: 2), .completed)
        print("VIPI_ACCESSIBILITY_TREE\n\(app.debugDescription)")
        // The link changes the word in place; verify its native accessible action.
        let word = app.links["mañana"]
        XCTAssertTrue(word.exists)
        if word.exists {
            listen.tap(); word.tap()
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen'"), object: listen)], timeout: 2), .completed)
            XCTAssertTrue(app.links["tomorrow"].exists)
            let revealed = XCTAttachment(screenshot: app.screenshot()); revealed.name = "Word revealed — audio stopped"; revealed.lifetime = .keepAlways; add(revealed)
        }
        app.buttons["Find your language"].tap()
        XCTAssertTrue(app.staticTexts["I already speak"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["TRY A LITTLE SPANISH"].exists)
    }
}
