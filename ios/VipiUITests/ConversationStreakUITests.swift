import XCTest

final class ConversationStreakUITests: XCTestCase {
    @MainActor func testDirectAndGroupRowsHeadersAndExplanations() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "ios-streak-" + name; shot.lifetime = .keepAlways; add(shot)
        }
        func checkHeader() {
            let language = app.buttons["conversation-language"]
            let immersion = app.buttons["chat-immersion-picker"]
            let autoplay = app.buttons["chat-autoplay-toggle"]
            let identity = app.buttons["streak-explanation"]
            let options = app.buttons["conversation-options"].exists ? app.buttons["conversation-options"] : app.buttons["conversation-group-info"]
            let back = app.navigationBars.buttons["BackButton"].firstMatch
            let controls = [back, identity, language, immersion, autoplay, options]
            for control in controls {
                print("VIPI_HEADER_FRAME", control.identifier, control.frame, control.value ?? "")
                XCTAssertTrue(control.isHittable)
                XCTAssertTrue(app.frame.contains(control.frame))
                XCTAssertGreaterThanOrEqual(control.frame.width, 44 - 0.001)
                // The system Menu exposes 36pt within its 44pt toolbar slot.
                let minimumHeight: CGFloat = control.identifier == "conversation-options" ? 36 : 44
                XCTAssertGreaterThanOrEqual(control.frame.height, minimumHeight - 0.001)
                XCTAssertEqual(control.frame.midY, language.frame.midY, accuracy: 3)
            }
            let ordered = controls.map(\.frame).sorted { $0.minX < $1.minX }
            for (lhs, rhs) in zip(ordered, ordered.dropFirst()) {
                XCTAssertLessThanOrEqual(lhs.maxX, rhs.minX + 1)
            }
            XCTAssertFalse((language.value as? String ?? "").isEmpty)
        }
        for scenario in ["normal", "dark", "compact-rtl"] {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-streaks-qa"]
            if scenario == "dark" { app.launchArguments.append("-vipi-appearance-dark") }
            else { app.launchArguments.append("-vipi-appearance-light") }
            if scenario == "compact-rtl" {
                app.launchArguments += ["-vipi-streaks-compact-qa", "-AppleLanguages", "(ar)", "-AppleLocale", "ar_SA"]
            }
            app.launch()
            let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 35))
            let expected = scenario == "compact-rtl" ? "١٠٥" : "105"
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", expected), object: row)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 12), .completed)
            capture(scenario + "-inbox")
            if scenario == "dark" { app.terminate(); continue }
            row.tap()
            let badge = app.buttons["streak-explanation"]
            XCTAssertTrue(badge.waitForExistence(timeout: 8)); XCTAssertTrue((badge.value as? String)?.contains(expected) == true)
            XCTAssertGreaterThanOrEqual(badge.frame.width, 44)
            XCTAssertTrue(app.frame.contains(badge.frame))
            checkHeader()
            if scenario == "normal" {
                let language = app.buttons["conversation-language"]
                language.tap()
                let search = app.searchFields.firstMatch
                XCTAssertTrue(search.waitForExistence(timeout: 5))
                search.tap()
                search.typeText("fran")
                let french = app.buttons["language-choice-fr"]
                XCTAssertTrue(french.waitForExistence(timeout: 4))
                capture("search-language")
                french.tap()
                XCTAssertEqual(language.value as? String, "French")
                XCTAssertGreaterThan(language.frame.width, 54, "Show the full language on a standard-width phone")
                XCTAssertGreaterThanOrEqual(language.frame.minX - badge.frame.maxX, 8)
            }
            capture(scenario + "-direct")
            if scenario == "normal" {
                let menu = app.buttons["conversation-options"]
                menu.tap()
                let languages = app.buttons["conversation-languages"]
                XCTAssertTrue(languages.waitForExistence(timeout: 4))
                languages.tap()
                XCTAssertTrue(app.navigationBars["Your languages"].waitForExistence(timeout: 5))
                app.navigationBars.buttons["BackButton"].tap()
            }
            badge.tap()
            XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 4))
            capture(scenario + "-meaning")
            app.alerts.buttons.firstMatch.tap()
            if scenario == "normal" {
                app.navigationBars.buttons.element(boundBy: 0).tap()
                let group = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'group-thread-' AND label CONTAINS 'Book club'")).firstMatch
                XCTAssertTrue(group.waitForExistence(timeout: 8))
                capture("groups-in-inbox")
                group.tap()
                XCTAssertTrue(badge.waitForExistence(timeout: 10)); XCTAssertTrue((badge.value as? String)?.contains("7") == true)
                checkHeader()
                let language = app.buttons["conversation-language"]
                XCTAssertNotEqual(language.value as? String, "French")
                language.tap()
                let german = app.buttons["language-choice-de"]
                XCTAssertTrue(german.waitForExistence(timeout: 4))
                german.tap()
                XCTAssertEqual(language.value as? String, "German")
                XCTAssertGreaterThan(language.frame.width, 54, "Show the full language on a standard-width phone")
                XCTAssertGreaterThanOrEqual(language.frame.minX - badge.frame.maxX, 8)
                capture("group-header")
                language.tap()
                let reset = app.buttons["conversation-language-default"]
                XCTAssertTrue(reset.waitForExistence(timeout: 4))
                reset.tap()
                XCTAssertNotEqual(language.value as? String, "German")
                badge.tap()
                XCTAssertTrue(app.alerts.staticTexts["A day counts when at least two different group members send a message. Days start at midnight UTC."].exists)
                capture("group-meaning")
            }
            app.terminate()
        }
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
        app.launch()
    }

    @MainActor func testLandscapeComposingKeepsDraftAndSendAboveKeyboard() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        let device = XCUIDevice.shared
        device.orientation = .portrait
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-streaks-qa"]
        app.launch()
        defer {
            app.terminate()
            device.orientation = .portrait
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
            app.launch()
            app.terminate()
        }
        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            shot.name = name
            shot.lifetime = .keepAlways
            add(shot)
        }
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 35))
        row.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 8))
        device.orientation = .landscapeLeft
        input.tap()
        let draft = "Meeting at six"
        input.typeText(draft)
        let send = app.buttons["message-send"]
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertTrue(send.isHittable)
        XCTAssertTrue(app.frame.contains(send.frame))
        XCTAssertLessThanOrEqual(send.frame.maxY, keyboard.frame.minY + 1)
        if app.frame.width > 1000 {
            XCTAssertLessThanOrEqual(input.frame.width, 644)
            XCTAssertLessThan(abs(input.frame.midX - app.frame.midX), 100)
        }
        capture("ios-landscape-compose")
        let mode = app.buttons["chat-immersion-picker"]
        if mode.isHittable { mode.tap() }
        XCTAssertTrue((input.value as? String)?.contains(draft) == true)
        XCTAssertTrue(keyboard.exists)
        XCTAssertTrue(send.isHittable)
        let language = app.buttons["conversation-language"]
        XCTAssertTrue(language.isHittable)
        language.tap()
        let french = app.buttons["language-choice-fr"]
        XCTAssertTrue(french.waitForExistence(timeout: 5))
        french.tap()
        XCTAssertEqual(language.value as? String, "French")
        XCTAssertTrue((input.value as? String)?.contains(draft) == true)
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertTrue(send.isHittable)
        print("VIPI_LANDSCAPE_GEOMETRY", app.frame, keyboard.frame, input.frame, send.frame)
    }

    @MainActor func testJoinedConversationInAResizedIPadWindow() throws {
        let simulator = ProcessInfo.processInfo.environment["SIMULATOR_DEVICE_NAME"] ?? ""
        try XCTSkipUnless(simulator.hasPrefix("Vipi Window Audit"), "Dedicated windowing simulator required")
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .landscapeLeft
        defer { XCUIDevice.shared.orientation = .portrait }
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        func named(_ app: XCUIApplication, _ label: String) -> XCUIElement {
            app.descendants(matching: .any).matching(NSPredicate(format: "label ==[c] %@", label)).firstMatch
        }
        let multitasking = named(settings, "Multitasking & Gestures")
        let sidebar = settings.coordinate(withNormalizedOffset: CGVector(dx: 0.18, dy: 0.8))
        for _ in 0..<4 where !multitasking.isHittable {
            sidebar.press(forDuration: 0.05, thenDragTo: settings.coordinate(withNormalizedOffset: CGVector(dx: 0.18, dy: 0.27)))
        }
        XCTAssertTrue(multitasking.isHittable, settings.debugDescription)
        multitasking.tap()
        let windowed = named(settings, "Windowed Apps")
        XCTAssertTrue(windowed.waitForExistence(timeout: 5), settings.debugDescription)
        windowed.tap()
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-streaks-qa"]
        app.launch()
        defer { app.terminate() }
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'group-thread-' AND label CONTAINS 'Book club'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 35))
        let nav = app.navigationBars.firstMatch
        let initial = nav.frame
        print("VIPI_IPAD_INITIAL_WINDOW", app.frame, initial)
        for ratio in [0.48, 0.36] where nav.frame.width >= 750 {
            let window = app.windows.firstMatch
            let handle = window.coordinate(withNormalizedOffset: CGVector(dx: 0.995, dy: 0.995))
            let target = window.coordinate(withNormalizedOffset: CGVector(dx: ratio, dy: 0.90))
            handle.press(forDuration: 0.35, thenDragTo: target, withVelocity: .slow, thenHoldForDuration: 0.25)
        }
        print("VIPI_IPAD_RESIZED_WINDOW", app.frame, nav.frame)
        let narrow = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        narrow.name = "ios-ipad-narrow-inbox"; narrow.lifetime = .keepAlways; add(narrow)
        XCTAssertGreaterThanOrEqual(nav.frame.width, 320)
        XCTAssertLessThan(nav.frame.width, 750)
        if initial.width >= 750 { XCTAssertLessThan(nav.frame.width, initial.width - 100) }
        let language = app.buttons["inbox-practice-language"]
        let newChat = app.buttons["home-compose"]
        XCTAssertEqual(language.frame.midY, newChat.frame.midY, accuracy: 3)
        XCTAssertGreaterThanOrEqual(newChat.frame.minX - language.frame.maxX, 7)
        print("VIPI_IPAD_INBOX_GUTTER", newChat.frame.minX - language.frame.maxX)
        let settingsButton = app.buttons["Your profile and settings"]
        XCTAssertLessThanOrEqual(settingsButton.frame.maxX, nav.frame.maxX + 1)
        row.tap()
        XCTAssertTrue(app.buttons["conversation-group-info"].waitForExistence(timeout: 5))
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        shot.name = "ios-ipad-narrow-group"; shot.lifetime = .keepAlways; add(shot)
        let controls = [nav.buttons["BackButton"].firstMatch,
                        app.buttons["streak-explanation"], app.buttons["conversation-language"],
                        app.buttons["chat-immersion-picker"], app.buttons["chat-autoplay-toggle"],
                        app.buttons["conversation-group-info"]]
        for control in controls {
            print("VIPI_IPAD_CONTROL", control.identifier, control.frame, nav.frame)
            XCTAssertTrue(control.isHittable)
            XCTAssertGreaterThanOrEqual(control.frame.minX, nav.frame.minX - 1)
            XCTAssertLessThanOrEqual(control.frame.maxX, nav.frame.maxX + 1)
        }
        for (left, right) in zip(controls, controls.dropFirst()) {
            XCTAssertLessThanOrEqual(left.frame.maxX, right.frame.minX + 1)
        }
    }

    @MainActor func testDiscoverySafetyAndAttachmentControlsCanBeReviewedBeforeActing() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        func launchChats() {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-streaks-qa"]
            app.launch()
        }
        func capture(_ name: String) {
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "ios-readiness-" + name
            image.lifetime = .keepAlways
            add(image)
        }
        XCUIDevice.shared.orientation = .portrait
        launchChats()
        defer {
            app.terminate()
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
            app.launch()
            app.terminate()
        }
        let newChat = app.buttons["home-compose"]
        XCTAssertTrue(newChat.waitForExistence(timeout: 35))
        let joined = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'group-thread-' AND label CONTAINS 'Book club'")).firstMatch
        XCTAssertTrue(joined.waitForExistence(timeout: 8))
        capture("inbox")
        joined.tap()
        XCTAssertTrue(app.buttons["conversation-group-info"].waitForExistence(timeout: 8))
        capture("joined-group")
        app.navigationBars.buttons["BackButton"].tap()
        newChat.tap()
        let newGroup = app.buttons["new-chat-new-group"]
        XCTAssertTrue(newGroup.waitForExistence(timeout: 8))
        capture("new-chat")
        newGroup.tap()
        XCTAssertTrue(app.textFields["group-name"].waitForExistence(timeout: 8))
        capture("new-group")

        launchChats()
        XCTAssertTrue(newChat.waitForExistence(timeout: 35))
        newChat.tap()
        let invite = app.buttons["new-chat-invite-friend"]
        for _ in 0..<5 where !invite.isHittable { app.swipeUp() }
        XCTAssertTrue(invite.isHittable)
        invite.tap()
        let contacts = app.buttons["invite-use-phone-contacts"]
        XCTAssertTrue(contacts.waitForExistence(timeout: 8))
        capture("invitation-options")
        contacts.tap()
        capture("contacts-choice")

        launchChats()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chat-thread-'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 35))
        row.tap()
        let options = app.buttons["conversation-options"]
        XCTAssertTrue(options.waitForExistence(timeout: 8))
        capture("direct")
        let viewport = app.frame.insetBy(dx: 0, dy: 100)
        func visibleAction(_ snapshot: XCUIElementSnapshot) -> String? {
            if snapshot.identifier.hasPrefix("message-actions-"), viewport.contains(snapshot.frame) {
                return snapshot.identifier
            }
            for child in snapshot.children.reversed() {
                if let id = visibleAction(child) { return id }
            }
            return nil
        }
        let messageAction = try XCTUnwrap(visibleAction(try app.snapshot()))
        app.buttons[messageAction].tap()
        let reply = app.buttons["Reply"]
        XCTAssertTrue(reply.waitForExistence(timeout: 5))
        capture("message-actions")
        reply.tap()
        capture("reply-compose")
        options.tap()
        app.buttons["Block"].tap()
        let alert = app.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 5))
        capture("block-confirmation")
        alert.buttons["Cancel"].tap()
        options.tap()
        app.buttons["Report person"].tap()
        XCTAssertTrue(app.navigationBars["Report person"].waitForExistence(timeout: 5))
        capture("report-disclosure")
        app.buttons["Cancel"].tap()
        let attachment = app.buttons["chat-attach"]
        if attachment.isEnabled {
            attachment.tap()
            XCTAssertTrue(app.buttons["Choose photo or video"].waitForExistence(timeout: 5))
            capture("attachment-options")
        }

        launchChats()
        let settings = app.buttons["Your profile and settings"]
        XCTAssertTrue(settings.waitForExistence(timeout: 35))
        settings.tap()
        XCTAssertTrue(app.navigationBars["Settings"].waitForExistence(timeout: 5))
        capture("settings")
        let deletion = app.buttons["Delete Vipi account"]
        for _ in 0..<14 where !deletion.isHittable { app.swipeUp() }
        XCTAssertTrue(deletion.isHittable)
        deletion.tap()
        let confirm = app.buttons["delete-account"]
        for _ in 0..<4 where !confirm.isHittable { app.swipeUp() }
        XCTAssertTrue(confirm.isHittable)
        capture("delete-scope")
        confirm.tap()
        XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 5))
        capture("delete-confirmation")
        app.alerts.firstMatch.buttons["Cancel"].tap()
        XCTAssertTrue(confirm.exists)
    }
}
