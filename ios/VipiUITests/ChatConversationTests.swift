import XCTest

final class ChatConversationTests: XCTestCase {
    func testReportSelectedOriginalMessage() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-dark"]; app.launch()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let original = "Coffee tomorrow? Sent from the Android conversation screen."
        let message = app.staticTexts[original]
        for _ in 0..<5 { if message.exists && message.isHittable { break }; app.swipeDown() }
        XCTAssertTrue(message.waitForExistence(timeout: 10)); message.press(forDuration: 1.2)
        XCTAssertTrue(app.buttons["Report message"].waitForExistence(timeout: 10)); app.buttons["Report message"].tap()
        XCTAssertTrue(app.staticTexts["human-report-original"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["human-report-original"].label, original)
        capture("ios-report-selected-original-dark")
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Reason'")).firstMatch.tap()
        app.buttons["Something else"].tap()
        app.swipeUp(); app.buttons["human-report-submit"].tap()
        XCTAssertTrue(app.staticTexts["Report received"].waitForExistence(timeout: 20))
        capture("ios-report-received-dark")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["message-send"].exists)
    }
    func testBundledLicenseTextIsAvailableOffline() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        app.swipeUp()
        XCTAssertTrue(app.buttons["Licenses and notices"].waitForExistence(timeout: 10)); app.buttons["Licenses and notices"].tap()
        app.buttons["Vipi — GNU Affero General Public License v3"].tap()
        XCTAssertTrue(app.textViews.firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue((app.textViews.firstMatch.value as? String ?? "").contains("GNU AFFERO GENERAL PUBLIC LICENSE"))
        capture("ios-complete-license-text")
    }
    func testBackupNativeFilePicker() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "vqa_1107_ios01")).firstMatch.waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.buttons["Chat backup"].waitForExistence(timeout: 10)); app.buttons["Chat backup"].tap()
        let password = app.secureTextFields["history-password"]
        XCTAssertTrue(password.waitForExistence(timeout: 10)); password.tap(); password.typeText("Vipi public UI backup passphrase 2026")
        app.secureTextFields["history-password-confirm"].tap(); app.secureTextFields["history-password-confirm"].typeText("Vipi public UI backup passphrase 2026")
        app.swipeUp()
        app.buttons["history-begin"].tap()
        XCTAssertTrue(app.navigationBars["Save to Files"].waitForExistence(timeout: 15) || app.buttons["Save"].exists || app.buttons["Move"].exists)
        capture("ios-backup-native-file-picker")
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "backup-picker-accessibility"; tree.lifetime = .keepAlways; add(tree)
        XCTAssertTrue(app.buttons["Save"].isEnabled); app.buttons["Save"].tap()
        XCTAssertTrue(app.staticTexts["history-notice"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["history-notice"].label.contains("was saved"))
        capture("ios-backup-saved")
        try restoreBackup(app)
    }
    func testReviewChatList() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["New chat"].waitForExistence(timeout: 30))
        capture("ios-chat-list-light")
    }
    func testFindFriendComposeAndSend() throws {
        guard let peer = ProcessInfo.processInfo.environment["VIPI_QA_PEER"], peer.hasPrefix("vqa_") else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
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
        XCTAssertTrue(sentMetadata(app).waitForExistence(timeout: 15))
        capture("ios-conversation-light")
    }
    func testReopenExistingSentConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the iOS conversation screen."].waitForExistence(timeout: 15))
        capture("ios-existing-conversation-light")
        XCTAssertTrue(sentMetadata(app).waitForExistence(timeout: 15))
    }
    func testReceiveAndroidAndDarkConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the Android conversation screen."].waitForExistence(timeout: 20))
        capture("ios-conversation-dark")
    }
    func testRestoreExistingSavedBackup() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "vqa_1107_ios01")).firstMatch.waitForExistence(timeout: 10))
        app.swipeUp(); app.buttons["Chat backup"].tap()
        try restoreBackup(app)
    }
    private func restoreBackup(_ app: XCUIApplication) throws {
        app.buttons["Restore backup"].tap()
        app.buttons["history-choose-file"].tap()
        let file = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH 'Vipi chat backup '")).firstMatch
        if !file.waitForExistence(timeout: 2) {
            app.tabBars.buttons["Browse"].tap()
            let local = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'On My iPhone'")).firstMatch
            if local.waitForExistence(timeout: 5) { local.tap() }
        }
        XCTAssertTrue(file.waitForExistence(timeout: 15)); file.tap()
        XCTAssertTrue(app.secureTextFields["history-password"].waitForExistence(timeout: 10))
        app.secureTextFields["history-password"].tap(); app.secureTextFields["history-password"].typeText("Vipi public UI backup passphrase 2026")
        app.swipeUp(); app.buttons["history-begin"].tap()
        XCTAssertTrue(app.buttons["history-confirm-restore"].waitForExistence(timeout: 15))
        capture("ios-backup-restore-preview")
        app.buttons["history-confirm-restore"].tap()
        XCTAssertTrue(app.staticTexts["history-notice"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["history-notice"].label.contains("already saved. Nothing was duplicated."))
        capture("ios-backup-restored-no-duplicates")
        app.terminate(); app.launch()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the Android conversation screen."].waitForExistence(timeout: 15))
        capture("ios-backup-restored-chat-reopen")
    }
    private func dismissOptionalOffer(_ app: XCUIApplication) {
        if app.buttons["Not now"].waitForExistence(timeout: 3) { app.buttons["Not now"].tap() }
    }
    private func sentMetadata(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-' AND (label CONTAINS ' · Sent' OR label CONTAINS ' · Delivered')")).firstMatch
    }
    private func capture(_ name: String) { let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment) }
}
