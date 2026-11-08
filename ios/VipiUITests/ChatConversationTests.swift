import XCTest

@MainActor
final class ChatConversationTests: XCTestCase {
    func testObserveExistingImmersionThroughComposerAndSpeech() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned native session required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-vipi-live-immersion-state", "010"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I need ' AND label CONTAINS 'I like '")).firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        var observations: [[String: Any]] = []
        defer {
            if let data = try? JSONSerialization.data(withJSONObject: observations, options: [.sortedKeys]) {
                let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
                attachment.name = "live-state-visible-phases"; attachment.lifetime = .keepAlways; add(attachment)
            }
        }
        func observe(_ stage: String, seconds: Double) {
            print("VIPI_LIVE_STATE_STAGE " + stage)
            let deadline = Date().addingTimeInterval(seconds); var previous = ""
            while Date() < deadline {
                let text = paragraph.label, frame = paragraph.frame
                observations.append(["stage": stage, "at": Date().timeIntervalSince1970, "text": text,
                    "x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height)])
                if text != previous { capture("live-state-" + stage + "-" + String(observations.count)); previous = text }
                Thread.sleep(forTimeInterval: 0.7)
            }
        }
        observe("before-composer", seconds: 20)
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.exists); input.tap()
        observe("empty-composer-focused", seconds: 25)
        input.typeText("x")
        observe("draft-nonempty", seconds: 5)
        input.typeText(XCUIKeyboardKey.delete.rawValue)
        observe("draft-cleared-still-focused", seconds: 25)
        let frame = paragraph.frame
        let menu = app.buttons.matching(identifier: "Reading options").allElementsBoundByIndex
            .filter { $0.frame.minY >= frame.maxY - 1 && $0.frame.minY < frame.maxY + 85 }
            .min { $0.frame.minY < $1.frame.minY }
        let control = try XCTUnwrap(menu); control.tap()
        XCTAssertTrue(app.buttons["Listen"].waitForExistence(timeout: 10)); app.buttons["Listen"].tap()
        observe("after-listen", seconds: 25)
        for stage in ["before-composer", "empty-composer-focused", "draft-cleared-still-focused", "after-listen"] {
            let labels = observations.filter { $0["stage"] as? String == stage }.compactMap { $0["text"] as? String }
            let transitions = zip(labels, labels.dropFirst()).filter { $0 != $1 }.count
            XCTAssertGreaterThanOrEqual(transitions, 3, "Continuous switching must resume in " + stage)
        }
        let drafting = observations.filter { $0["stage"] as? String == "draft-nonempty" }.compactMap { $0["text"] as? String }
        XCTAssertLessThanOrEqual(Set(drafting).count, 1, "Active composition keeps words still")
    }
    func testLiveSwahiliImmersionConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              ProcessInfo.processInfo.environment["VIPI_QA_LIVE_SW"] == "4ccee4cd1b9e79a60e018902af278e85bc34377c75162eef066960b6aa4d0e6e" else {
            throw XCTSkip("Frozen eight-turn protocol and owned peer required")
        }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        app.buttons["language-settings-link"].tap()
        app.buttons["language-source-picker"].tap()
        XCTAssertTrue(app.buttons["English"].waitForExistence(timeout: 10)); app.buttons["English"].tap()
        app.buttons["language-target-picker"].tap()
        let swahili = app.buttons["Swahili · Kiswahili"]
        for _ in 0..<4 { if swahili.exists && swahili.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(swahili.exists); swahili.tap()
        capture("live-sw-selected-language-availability")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 15)); friend.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        let incoming = ["I need water.", "Can you meet me after work?", "Do you want to listen to some music?", "Let's have lunch tomorrow."]
        let outgoing = ["I am drinking coffee now.", "I will be home in twenty minutes.", "I like music.", "That sounds good. See you soon."]
        print("VIPI_LIVE_SW_RECEIVER_READY " + ISO8601DateFormatter().string(from: Date()))
        for index in 0..<incoming.count {
            let original = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", incoming[index])).firstMatch
            XCTAssertTrue(original.waitForExistence(timeout: 150), "Original source face must remain recoverable without a tap")
            print("VIPI_LIVE_SW_RECEIVED_\(index * 2 + 1) " + ISO8601DateFormatter().string(from: Date()))
            capture("live-sw-received-\(index * 2 + 1)")
            if index == 0 {
                let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I need '")).firstMatch
                XCTAssertTrue(paragraph.waitForExistence(timeout: 15))
                var samples: [[String: Any]] = [], previous = "", transitions = 0
                let deadline = Date().addingTimeInterval(29)
                while Date() < deadline {
                    let label = paragraph.label, frame = paragraph.frame
                    if label != previous {
                        if !previous.isEmpty { transitions += 1 }
                        capture("live-sw-water-phase-\(transitions)"); previous = label
                    }
                    samples.append(["at": Date().timeIntervalSince1970, "label": label,
                                    "x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height)])
                    Thread.sleep(forTimeInterval: 0.65)
                }
                let evidence = XCTAttachment(data: try JSONSerialization.data(withJSONObject: samples, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
                evidence.name = "live-sw-three-cycle-geometry"; evidence.lifetime = .keepAlways; add(evidence)
                XCTAssertGreaterThanOrEqual(transitions, 6)
                XCTAssertTrue(samples.contains { ($0["label"] as? String)?.contains("maji") == true })
                XCTAssertTrue(samples.contains { $0["label"] as? String == incoming[0] })
                let widths = samples.compactMap { $0["width"] as? Double }, heights = samples.compactMap { $0["height"] as? Double }
                XCTAssertLessThan((widths.max() ?? 0) - (widths.min() ?? 0), 0.5)
                XCTAssertLessThan((heights.max() ?? 0) - (heights.min() ?? 0), 0.5)
                // The latest incoming bubble owns the last reading menu. No word
                // taps occur; the action plays the faces currently on screen.
                let menus = app.buttons.matching(identifier: "Reading options")
                menus.element(boundBy: menus.count - 1).tap()
                XCTAssertTrue(app.buttons["Listen"].waitForExistence(timeout: 15)); app.buttons["Listen"].tap()
                capture("live-sw-water-native-listen")
                Thread.sleep(forTimeInterval: 5)
            }
            input.tap(); input.typeText(outgoing[index]); app.buttons["message-send"].tap()
            print("VIPI_LIVE_SW_SENT_\(index * 2 + 2) " + ISO8601DateFormatter().string(from: Date()))
            capture("live-sw-sent-\(index * 2 + 2)")
        }
        print("VIPI_LIVE_SW_EXCHANGE_COMPLETE " + ISO8601DateFormatter().string(from: Date()))
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "live-sw-final-accessibility"; tree.lifetime = .keepAlways; add(tree)
    }
    func testForegroundExchangeWithoutRefresh() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              let sent = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_SEND"],
              let expected = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_TEXT"],
              sent.hasPrefix("Foreground iOS to Android "), expected.hasPrefix("Foreground Android to iOS "),
              sent.count < 160, expected.count < 160 else { throw XCTSkip("Fresh owned-account exchange required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts[sent].exists); XCTAssertFalse(app.staticTexts[expected].exists)
        let metadata = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-'"))
        let previousIDs = metadata.allElementsBoundByIndex.map { $0.identifier }
        input.tap(); input.typeText(sent); app.buttons["message-send"].tap()
        print("VIPI_FOREGROUND_SENT " + ISO8601DateFormatter().string(from: Date()))
        XCTAssertTrue(app.staticTexts[sent].waitForExistence(timeout: 15))
        capture("foreground-new-outgoing-message")
        print("VIPI_FOREGROUND_RECEIVER_READY")
        // No refresh, lifecycle change, navigation or subsequent local send.
        XCTAssertTrue(app.staticTexts[expected].waitForExistence(timeout: 120))
        let delivered = metadata.matching(NSPredicate(format: "NOT (identifier IN %@) AND label CONTAINS ' · Delivered'", previousIDs)).firstMatch
        XCTAssertTrue(delivered.waitForExistence(timeout: 30))
        capture("foreground-bidirectional-delivered-without-refresh")
        print("VIPI_FOREGROUND_EXCHANGE_COMPLETE " + ISO8601DateFormatter().string(from: Date()))
    }
    func testReceiveForegroundWithoutRefresh() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              let expected = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_TEXT"],
              expected.hasPrefix("Foreground Android to iOS "), expected.count < 160 else {
            throw XCTSkip("A fresh explicit owned-account foreground exchange is required")
        }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.buttons["message-send"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts[expected].exists, "Use a new message for this delivery proof")
        capture("foreground-chat-awaiting-new-message")
        // The peer sends only after this ready marker is observed. No pull to
        // refresh, relaunch, scene activation or local send follows this point.
        print("VIPI_FOREGROUND_RECEIVER_READY")
        XCTAssertTrue(app.staticTexts[expected].waitForExistence(timeout: 120))
        capture("foreground-message-arrived-without-refresh")
    }
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
