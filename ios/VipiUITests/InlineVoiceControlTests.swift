import XCTest

@MainActor final class InlineVoiceControlTests: XCTestCase {
    /// Exercise the actual composer with the existing local timeline fixture.
    /// A short tap exposes the accessible alternative without opening the microphone.
    func testShortTapOffersHandsFreeWithoutStartingOrSending() {
        let app = XCUIApplication()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa"
        ]
        app.launch()
        let mic = app.buttons["voice-composer-action"]
        XCTAssertTrue(mic.waitForExistence(timeout: 20))
        XCTAssertEqual(mic.label, "Record voice message")
        XCTAssertTrue(app.buttons["chat-attach"].exists)
        mic.tap()
        XCTAssertTrue(app.buttons["voice-hands-free"].waitForExistence(timeout: 4))
        XCTAssertFalse(app.buttons["voice-stop-review"].exists)
        XCTAssertFalse(app.buttons["voice-discard"].exists)
        XCTAssertTrue(app.textViews["message-input"].exists)
        XCTAssertEqual(mic.label, "Record voice message")
    }
}
