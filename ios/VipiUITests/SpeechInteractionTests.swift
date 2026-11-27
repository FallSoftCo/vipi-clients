import XCTest

@MainActor final class SpeechInteractionTests: XCTestCase {
    func testMessageTapAndWordTapUseTheCurrentReadingSurface() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-funding-qa", "-vipi-source", "en", "-vipi-target", "es", "-readingPace",
            "balanced"
        ]
        app.launch()
        let thread = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
        XCTAssertTrue(thread.waitForExistence(timeout: 20))
        thread.tap()
        let text = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(text.waitForExistence(timeout: 10))
        let target = "agua, agua!"
        XCTAssertEqual(
            XCTWaiter.wait(
                for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", target), object: text)],
                timeout: 10), .completed)
        text.tap()
        let word = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier BEGINSWITH 'immersion-word-' AND label == 'agua'")
        ).firstMatch
        XCTAssertTrue(word.waitForExistence(timeout: 5))
        word.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        let revealed = XCTAttachment(screenshot: app.screenshot())
        revealed.name = "Practice word on the native reading surface"
        revealed.lifetime = .keepAlways
        add(revealed)
        let language = app.buttons["conversation-language"]
        XCTAssertTrue(language.waitForExistence(timeout: 5))
        language.tap()
        XCTAssertTrue(app.buttons["language-choice-es"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["Try a little Spanish"].exists)
    }
}
