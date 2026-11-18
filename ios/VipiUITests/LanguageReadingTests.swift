import XCTest

@MainActor final class LanguageReadingTests: XCTestCase {
    func testJapanesePreviewScriptAndOriginalWordsStayInOneBubble() {
        continueAfterFailure = false
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
        openInlineReadingOptions(in: app); app.buttons["Show original script"].tap()
        XCTAssertTrue(text.label.contains("コーヒー"))
        XCTAssertTrue(app.buttons["Show original script"].waitForNonExistence(timeout: 3))
        // The selection is already verified. Let the native menu's dismissal
        // animation finish before retaining a visual review capture.
        Thread.sleep(forTimeInterval: 0.5)
        let native = XCTAttachment(screenshot: app.screenshot()); native.name = "Japanese — original script"; native.lifetime = .keepAlways; add(native)
        openInlineReadingOptions(in: app); app.buttons["Show Latin letters"].tap()
        let restored = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'koohii'"), object: text)
        XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 5), .completed)
        openInlineReadingOptions(in: app)
        app.buttons["Show original words now"].tap()
        XCTAssertEqual(text.label, "Coffee tomorrow? I know a little place by the river.")
        openInlineMessageActions(in: app); app.buttons["Copy original message"].tap()
        XCTAssertTrue(text.exists)
        // Prepared full-target display is no longer an onboarding feature.
        // FullReadingQualification tests retain their separately named native
        // full-sentence grammar/reading assertions; no replacement pass here.

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
