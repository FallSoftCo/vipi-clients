import XCTest

final class ChatConversationTests: XCTestCase {
    func testReviewChatList() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["New chat"].waitForExistence(timeout: 30))
        capture("ios-chat-list-light")
    }
    func testFindFriendComposeAndSend() throws {
        guard let peer = ProcessInfo.processInfo.environment["VIPI_QA_PEER"], peer.hasPrefix("vqa_") else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["New chat"].waitForExistence(timeout: 30))
        capture("ios-chat-list-light")
        app.buttons["New chat"].tap()
        let username = app.textFields["Friend’s username"]
        XCTAssertTrue(username.waitForExistence(timeout: 5)); username.tap(); username.typeText(peer)
        capture("ios-find-friend-light")
        app.buttons["Find friend"].tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15)); input.tap()
        input.typeText("Coffee tomorrow? Sent from the iOS conversation screen.")
        capture("ios-compose-light")
        app.buttons["message-send"].tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the iOS conversation screen."].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Sent"].firstMatch.waitForExistence(timeout: 15))
        capture("ios-conversation-light")
    }
    func testReceiveAndroidAndDarkConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-dark"]; app.launch()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the Android conversation screen."].waitForExistence(timeout: 20))
        capture("ios-conversation-dark")
    }
    private func capture(_ name: String) { let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment) }
}
