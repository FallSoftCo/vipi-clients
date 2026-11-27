import XCTest

final class ChatTimelineTests: XCTestCase {
    @MainActor func testQuotedReplyActionsAndEmbeddedPreview() throws {
        let app = XCUIApplication()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-message-actions-qa", "-vipi-appearance-light"
        ]
        app.launch()
        let menus = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'message-actions-'"))
        XCTAssertTrue(menus.element(boundBy: 2).waitForExistence(timeout: 16), app.debugDescription)
        capture("ios-message-actions-thread")
        menus.element(boundBy: 2).tap()
        XCTAssertTrue(app.buttons["Reply"].waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(app.buttons["More reactions"].exists)
        capture("ios-message-actions-tray")
        app.buttons["Reply"].tap()
        XCTAssertTrue(app.buttons["Cancel reply"].waitForExistence(timeout: 5))
        if app.buttons["Continue"].waitForExistence(timeout: 1.5) { app.buttons["Continue"].tap() }
        XCTAssertFalse(app.buttons["Continue"].exists)
        capture("ios-message-actions-composer")
        app.buttons["Cancel reply"].tap()
        XCTAssertFalse(app.buttons["Cancel reply"].exists)
        let original = menus.element(boundBy: 2)
        let swipeFrom = original.coordinate(withNormalizedOffset: .init(dx: 0.7, dy: -0.35))
        swipeFrom.press(
            forDuration: 0.04, thenDragTo: swipeFrom.withOffset(.init(dx: 106, dy: 0)), withVelocity: .fast,
            thenHoldForDuration: 0)
        XCTAssertTrue(app.buttons["Cancel reply"].waitForExistence(timeout: 4), app.debugDescription)
        app.buttons["Cancel reply"].tap()
        app.terminate()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
        app.launch()
    }
    @MainActor func testVoicePlayerFitsIncomingAndOutgoingBubbles() throws {
        let app = XCUIApplication()
        for scenario in ["normal", "compact", "rtl"] {
            app.launchArguments = [
                "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-voice-layout-qa", "-vipi-appearance-light"
            ]
            if scenario != "normal" {
                app.launchArguments += [
                    "-vipi-voice-narrow-qa", "-UIPreferredContentSizeCategoryName",
                    "UICTContentSizeCategoryAccessibilityXXXL"
                ]
            }
            if scenario == "rtl" { app.launchArguments += ["-AppleLanguages", "(ar)", "-AppleLocale", "ar"] }
            app.launch()
            let controls = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'voice-note-control-'"))
            XCTAssertTrue(controls.element(boundBy: 1).waitForExistence(timeout: 15), app.debugDescription)
            let positions = app.staticTexts.matching(identifier: "voice-playback-position")
            XCTAssertEqual(positions.count, 2)
            let labels = positions.allElementsBoundByIndex.map(\.label)
            let durations = XCTAttachment(string: labels.joined(separator: "\n"))
            durations.name = "voice-times-" + scenario
            durations.lifetime = .keepAlways
            add(durations)
            let first = controls.element(boundBy: 0), second = controls.element(boundBy: 1)
            for button in [first, second] {
                XCTAssertGreaterThanOrEqual(button.frame.width + 0.001, 44)
                XCTAssertGreaterThanOrEqual(button.frame.height + 0.001, 44)
                XCTAssertTrue(app.frame.contains(button.frame), "Playback button outside the window")
            }
            for index in 0..<2 {
                let button = controls.element(boundBy: index).frame
                let timer = positions.element(boundBy: index).frame
                if scenario == "normal" {
                    XCTAssertGreaterThan(timer.minX, button.maxX)
                    XCTAssertLessThan(timer.minY, button.maxY)
                } else {
                    XCTAssertGreaterThan(
                        timer.minY, button.maxY, "Long elapsed and total should reflow below the control")
                }
            }
            func capture(_ name: String) throws {
                let shot = XCTAttachment(screenshot: app.screenshot())
                shot.name = "voice-bounds-" + scenario + "-" + name
                shot.lifetime = .keepAlways
                add(shot)
                let times = app.staticTexts.matching(NSPredicate(format: "identifier BEGINSWITH 'message-time-'"))
                let frames =
                    (controls.allElementsBoundByIndex + positions.allElementsBoundByIndex
                    + times.allElementsBoundByIndex)
                    .map { item in
                        [
                            "id": item.identifier, "label": item.label, "x": item.frame.minX, "y": item.frame.minY,
                            "width": item.frame.width, "height": item.frame.height
                        ] as [String: Any]
                    }
                let bounds = XCTAttachment(
                    data: try JSONSerialization.data(withJSONObject: frames), uniformTypeIdentifier: "public.json")
                bounds.name = "voice-frames-" + scenario + "-" + name
                bounds.lifetime = .keepAlways
                add(bounds)
            }
            try capture("idle")
            let play = second.label
            let incomingPosition = positions.element(boundBy: 1)
            let start = incomingPosition.label
            second.tap()
            let advanced = XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "label != %@", start), object: incomingPosition)
            XCTAssertEqual(XCTWaiter.wait(for: [advanced], timeout: 5), .completed)
            try capture("playing")
            second.tap()
            XCTAssertEqual(second.label, play)
            try capture("paused")
            if scenario == "normal" {
                second.tap()
                let finished = XCTNSPredicateExpectation(
                    predicate: NSPredicate(format: "label == %@", play), object: second)
                XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 12), .completed)
                try capture("completed")
            }
            XCTAssertFalse(app.sheets.firstMatch.exists)
            app.terminate()
        }
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
        app.launch()
    }

    @MainActor func testConversationRespondsToLiveSystemTextSize() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_LIVE_TEXT_SIZE"] == "restore-system-setting-r01" else {
            throw XCTSkip("Requires coordinated system text-size change and restoration")
        }
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-dark", "-vipi-live-immersion-state", "012"
        ]
        app.launch()
        defer {
            app.terminate()
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
            app.launch()
            XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
        }
        let message = app.staticTexts["History message 70. We are making plans for tomorrow."]
        XCTAssertTrue(message.waitForExistence(timeout: 20))
        XCTAssertTrue(message.isHittable)
        let metadataID = try XCTUnwrap(
            app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH %@", "message-meta-"))
                .allElementsBoundByIndex.last
        ).identifier
        let metadata = app.descendants(matching: .any).matching(identifier: metadataID).firstMatch
        let bodyHeight = message.frame.height, metadataHeight = metadata.frame.height
        capture("ios-live-system-text-size-before")
        print("VIPI_SYSTEM_TEXT_SIZE_READY")
        let expanded = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in
                guard message.exists && metadata.exists else { return false }
                return message.frame.height > bodyHeight * 1.5 && metadata.frame.height > metadataHeight * 1.5
            }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [expanded], timeout: 45), .completed)
        let largeBody = message.frame.height, largeMetadata = metadata.frame.height
        XCTAssertTrue(message.isHittable)
        capture("ios-live-system-text-size-expanded")
        print("VIPI_SYSTEM_TEXT_SIZE_RESTORE")
        let restored = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in
                guard message.exists && metadata.exists else { return false }
                return abs(message.frame.height - bodyHeight) < 1 && abs(metadata.frame.height - metadataHeight) < 1
            }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 45), .completed)
        capture("ios-live-system-text-size-restored")
        let report: [String: Any] = [
            "body_before": bodyHeight, "body_large": largeBody,
            "body_restored": message.frame.height, "metadata_before": metadataHeight,
            "metadata_large": largeMetadata, "metadata_restored": metadata.frame.height,
            "same_process": true, "relaunch_between_sizes": false
        ]
        let attachment = XCTAttachment(
            data: try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]),
            uniformTypeIdentifier: "public.json")
        attachment.name = "live-system-text-size"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    @MainActor func testEarlierPagePreservesVisibleMessage() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-appearance-dark"]
        app.launch()
        defer { if app.buttons["timeline-qa-finish"].exists { app.buttons["timeline-qa-finish"].tap() } }
        XCTAssertTrue(
            app.staticTexts["History message 70. We are making plans for tomorrow."].waitForExistence(timeout: 20))
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        let earlier = app.buttons["Earlier messages"]
        for _ in 0..<12 {
            if earlier.isHittable { break }
            timeline.swipeDown()
        }
        XCTAssertTrue(earlier.isHittable)
        let anchor = app.staticTexts["History message 21. We are making plans for tomorrow."]
        XCTAssertTrue(anchor.isHittable)
        let y = anchor.frame.minY
        earlier.tap()
        XCTAssertTrue(anchor.isHittable)
        XCTAssertEqual(anchor.frame.minY, y, accuracy: 3)
        XCTAssertFalse(earlier.exists)
        capture("ios-older-page-anchor-dark")
        app.buttons["timeline-qa-finish"].tap()
        XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
    }
    @MainActor func testReadingPositionIncomingAppendKeyboardAndOwnSend() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-appearance-light", "-vipi-live-immersion-state", "011"]
        app.launch()
        defer {
            let finish = app.buttons["timeline-qa-finish"]
            if finish.exists { finish.tap() }
        }
        let last = app.staticTexts["History message 70. We are making plans for tomorrow."]
        XCTAssertTrue(last.waitForExistence(timeout: 20))
        XCTAssertTrue(last.isHittable)
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        XCTAssertTrue(timeline.exists)
        timeline.swipeDown()
        timeline.swipeDown()
        let jump = app.buttons["conversation-latest"]
        XCTAssertTrue(jump.waitForExistence(timeout: 5))
        XCTAssertTrue(jump.isHittable)
        let messages = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "History message"))
            .allElementsBoundByIndex
        let top = max(timeline.frame.minY, app.navigationBars.firstMatch.frame.maxY)
        let anchor = try XCTUnwrap(
            messages.filter { $0.isHittable && $0.frame.minY >= top + 10 && $0.frame.maxY <= timeline.frame.maxY - 10 }
                .min { $0.frame.minY < $1.frame.minY })
        let label = anchor.label
        let y = anchor.frame.minY
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(jump.isHittable)
        XCTAssertEqual(app.staticTexts[label].frame.minY, y, accuracy: 3)
        capture("ios-reading-preserved-light")
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap()
        input.typeText("A draft while reading")
        capture("ios-reading-with-keyboard-light")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts[label].isHittable)
        XCTAssertTrue(jump.isHittable)
        app.buttons["message-send"].tap()
        let sent = app.staticTexts["A draft while reading"]
        XCTAssertTrue(sent.waitForExistence(timeout: 5))
        XCTAssertTrue(sent.isHittable)
        XCTAssertFalse(jump.exists)
        // The scroll view's accessibility frame extends behind the keyboard.
        // Keep this real drag within the visible messages, above the composer.
        let visibleTop = max(timeline.frame.minY, app.navigationBars.firstMatch.frame.maxY)
        let visibleBottom = min(timeline.frame.maxY, input.frame.minY - 20)
        XCTAssertGreaterThan(visibleBottom - visibleTop, 140)
        let origin = app.coordinate(withNormalizedOffset: .zero)
        origin.withOffset(CGVector(dx: timeline.frame.midX, dy: visibleTop + 40))
            .press(
                forDuration: 0.1,
                thenDragTo: origin.withOffset(CGVector(dx: timeline.frame.midX, dy: visibleBottom - 20)))
        XCTAssertTrue(jump.waitForExistence(timeout: 5))
        jump.tap()
        XCTAssertTrue(sent.isHittable)
        XCTAssertFalse(jump.exists)
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(
            app.staticTexts.matching(identifier: "Appended while reading earlier messages.").allElementsBoundByIndex
                .contains { $0.isHittable })
        capture("ios-following-latest-light")
        app.buttons["timeline-qa-finish"].tap()
        XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
    }
    @MainActor func testConversationAccessibilityAuditLightAndDark() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-" + appearance]
            app.launch()
            defer {
                app.terminate()
                app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
                app.launch()
                XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
            }
            XCTAssertTrue(
                app.staticTexts["History message 70. We are making plans for tomorrow."].waitForExistence(timeout: 20))
            app.scrollViews["conversation-timeline"].firstMatch.swipeDown()
            XCTAssertTrue(app.buttons["conversation-latest"].waitForExistence(timeout: 5))
            capture("ios-accessibility-before-" + appearance)
            var findings: [[String: String]] = []
            try app.performAccessibilityAudit { issue in
                let element = issue.element
                findings.append([
                    "appearance": appearance,
                    "issue": issue.compactDescription,
                    "detail": issue.detailedDescription,
                    "identifier": element?.identifier ?? "",
                    "label": element?.label ?? "",
                    "frame": element.map { String(describing: $0.frame) } ?? "",
                    "hittable": element.map { String($0.isHittable) } ?? ""
                ])
                return false  // Retain every issue as a test failure.
            }
            let report = XCTAttachment(
                data: try JSONSerialization.data(withJSONObject: findings, options: [.prettyPrinted, .sortedKeys]),
                uniformTypeIdentifier: "public.json")
            report.name = "conversation-accessibility-" + appearance
            report.lifetime = .keepAlways
            add(report)
        }
    }
    @MainActor func testConversationLargeTextLayout() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        defer {
            app.terminate()
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
            app.launch()
            XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
        }
        let label = "History message 70. We are making plans for tomorrow."
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName",
            "UICTContentSizeCategoryL"
        ]
        app.launch()
        XCTAssertTrue(app.staticTexts[label].waitForExistence(timeout: 20))
        let normalHeight = app.staticTexts[label].frame.height
        let metadataQuery = NSPredicate(format: "identifier BEGINSWITH %@", "message-meta-")
        let normalTimeHeight = try XCTUnwrap(
            app.descendants(matching: .any).matching(metadataQuery).allElementsBoundByIndex.last
        ).frame.height
        app.terminate()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName",
            "UICTContentSizeCategoryAccessibilityXXXL"
        ]
        app.launch()
        let message = app.staticTexts[label]
        XCTAssertTrue(message.waitForExistence(timeout: 20))
        XCTAssertGreaterThan(message.frame.height, normalHeight * 1.5)
        XCTAssertGreaterThanOrEqual(message.frame.minX, app.frame.minX)
        XCTAssertLessThanOrEqual(message.frame.maxX, app.frame.maxX)
        XCTAssertTrue(message.isHittable)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "message-input").firstMatch.isHittable)
        let metadata = try XCTUnwrap(
            app.descendants(matching: .any).matching(metadataQuery).allElementsBoundByIndex.last)
        XCTAssertGreaterThan(metadata.frame.height, normalTimeHeight * 1.5)
        XCTAssertTrue(metadata.label.contains("Waiting to send"))
        let notice = app.buttons["conversation-notice"]
        XCTAssertTrue(notice.isHittable)
        XCTAssertLessThan(notice.frame.height, app.frame.height * 0.12)
        capture("ios-conversation-largest-text-dark")
    }
    @MainActor private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        image.name = name
        image.lifetime = .keepAlways
        add(image)
    }
}
