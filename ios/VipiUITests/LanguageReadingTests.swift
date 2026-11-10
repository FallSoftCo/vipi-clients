import XCTest

@MainActor final class LanguageReadingTests: XCTestCase {
    func testJapaneseReadingScriptAndGrammarStayInOneBubble() {
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-language", "-vipi-source", "en", "-vipi-target", "ja", "-readingPace", "balanced"]
        app.launch()
        let text = app.descendants(matching: .any)["immersionText"]
        XCTAssertTrue(text.waitForExistence(timeout: 10))
        app.swipeUp()
        let reading = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'koohii'"), object: text)
        XCTAssertEqual(XCTWaiter.wait(for: [reading], timeout: 10), .completed)
        app.buttons["immersionPause"].tap()
        let romanized = XCTAttachment(screenshot: app.screenshot()); romanized.name = "Japanese — readable immersion"; romanized.lifetime = .keepAlways; add(romanized)
        app.buttons["Reading options"].tap(); app.buttons["Show original script"].tap()
        XCTAssertTrue(text.label.contains("コーヒー"))
        XCTAssertTrue(app.buttons["Show original script"].waitForNonExistence(timeout: 3))
        // The selection is already verified. Let the native menu's dismissal
        // animation finish before retaining a visual review capture.
        Thread.sleep(forTimeInterval: 0.5)
        let native = XCTAttachment(screenshot: app.screenshot()); native.name = "Japanese — original script"; native.lifetime = .keepAlways; add(native)
        app.buttons["Reading options"].tap(); app.buttons["Show Latin letters"].tap()
        app.buttons["Show full translation in Japanese"].tap()
        XCTAssertTrue(app.staticTexts["Ashita, koohii demo dou? Kawa no soba ni chiisana omise o shitte iru yo."].exists)
        let grammar = XCTAttachment(screenshot: app.screenshot()); grammar.name = "Japanese — whole thought"; grammar.lifetime = .keepAlways; add(grammar)
        app.buttons["Reading options"].tap(); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["明日、コーヒーでもどう？川のそばに小さなお店を知っているよ。"].exists)
        app.buttons["Resume word switching"].tap()
        XCTAssertTrue(text.exists)
        app.buttons["Reading options"].tap(); app.buttons["Copy original message"].tap()
        XCTAssertTrue(text.exists)
    }
    func testSpeechFreezesContinuousReadingUntilPlaybackEnds() {
        let app = XCUIApplication(); app.launchArguments = ["-vipi-welcome", "-readingPace", "balanced"]; app.launch()
        let listen = app.buttons["messageListen"]
        XCTAssertTrue(listen.waitForExistence(timeout: 10))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND label == 'Listen'"), object: listen)], timeout: 15), .completed)
        listen.tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Stop'"), object: listen)], timeout: 3), .completed)
        let text = app.descendants(matching: .any)["immersionText"]
        let captured = text.label
        let deadline = Date().addingTimeInterval(15)
        var observations = 0
        while listen.label == "Stop" && Date() < deadline {
            XCTAssertEqual(text.label, captured)
            observations += 1
        }
        XCTAssertGreaterThan(observations, 0)
        XCTAssertEqual(listen.label, "Listen")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", captured), object: text)], timeout: 9), .completed)
    }
}
