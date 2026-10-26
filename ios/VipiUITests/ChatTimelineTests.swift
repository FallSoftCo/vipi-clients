import XCTest

final class ChatTimelineTests: XCTestCase {
    @MainActor func testEarlierPagePreservesVisibleMessage() throws {
        continueAfterFailure = true
        let app = XCUIApplication(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-appearance-dark"]; app.launch()
        defer { if app.buttons["timeline-qa-finish"].exists { app.buttons["timeline-qa-finish"].tap() } }
        XCTAssertTrue(app.staticTexts["History message 70. We are making plans for tomorrow."].waitForExistence(timeout: 20))
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
        XCTAssertTrue(anchor.isHittable); XCTAssertEqual(anchor.frame.minY, y, accuracy: 3)
        XCTAssertFalse(earlier.exists)
        capture("ios-older-page-anchor-dark")
        app.buttons["timeline-qa-finish"].tap()
        XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
    }
    @MainActor func testReadingPositionIncomingAppendKeyboardAndOwnSend() throws {
        continueAfterFailure = true
        let app = XCUIApplication(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-appearance-light"]; app.launch()
        defer {
            let finish = app.buttons["timeline-qa-finish"]
            if finish.exists { finish.tap() }
        }
        let last = app.staticTexts["History message 70. We are making plans for tomorrow."]
        XCTAssertTrue(last.waitForExistence(timeout: 20)); XCTAssertTrue(last.isHittable)
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        XCTAssertTrue(timeline.exists)
        timeline.swipeDown(); timeline.swipeDown()
        let jump = app.buttons["conversation-latest"]
        XCTAssertTrue(jump.waitForExistence(timeout: 5)); XCTAssertTrue(jump.isHittable)
        let messages = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "History message")).allElementsBoundByIndex
        let top = max(timeline.frame.minY, app.navigationBars.firstMatch.frame.maxY)
        let anchor = try XCTUnwrap(messages.filter { $0.isHittable && $0.frame.minY >= top + 10 && $0.frame.maxY <= timeline.frame.maxY - 10 }.min { $0.frame.minY < $1.frame.minY })
        let label = anchor.label; let y = anchor.frame.minY
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(jump.isHittable)
        XCTAssertEqual(app.staticTexts[label].frame.minY, y, accuracy: 3)
        capture("ios-reading-preserved-light")
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.typeText("A draft while reading")
        capture("ios-reading-with-keyboard-light")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts[label].isHittable); XCTAssertTrue(jump.isHittable)
        app.buttons["message-send"].tap()
        let sent = app.staticTexts["A draft while reading"]
        XCTAssertTrue(sent.waitForExistence(timeout: 5)); XCTAssertTrue(sent.isHittable)
        XCTAssertFalse(jump.exists)
        timeline.swipeDown()
        XCTAssertTrue(jump.waitForExistence(timeout: 5)); jump.tap()
        XCTAssertTrue(sent.isHittable); XCTAssertFalse(jump.exists)
        app.buttons["timeline-qa-append"].tap()
        XCTAssertTrue(app.staticTexts.matching(identifier: "Appended while reading earlier messages.").allElementsBoundByIndex.contains { $0.isHittable })
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
            XCTAssertTrue(app.staticTexts["History message 70. We are making plans for tomorrow."].waitForExistence(timeout: 20))
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
                return false // Retain every issue as a test failure.
            }
            let report = XCTAttachment(data: try JSONSerialization.data(withJSONObject: findings, options: [.prettyPrinted, .sortedKeys]), uniformTypeIdentifier: "public.json")
            report.name = "conversation-accessibility-" + appearance
            report.lifetime = .keepAlways; add(report)
        }
    }
    @MainActor func testConversationLargeTextLayout() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
            XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 5))
        }
        let label = "History message 70. We are making plans for tomorrow."
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        XCTAssertTrue(app.staticTexts[label].waitForExistence(timeout: 20))
        let normalHeight = app.staticTexts[label].frame.height
        let metadataQuery = NSPredicate(format: "identifier BEGINSWITH %@", "message-meta-")
        let normalTimeHeight = try XCTUnwrap(app.descendants(matching: .any).matching(metadataQuery).allElementsBoundByIndex.last).frame.height
        app.terminate()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-audit", "-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let message = app.staticTexts[label]
        XCTAssertTrue(message.waitForExistence(timeout: 20))
        XCTAssertGreaterThan(message.frame.height, normalHeight * 1.5)
        XCTAssertGreaterThanOrEqual(message.frame.minX, app.frame.minX)
        XCTAssertLessThanOrEqual(message.frame.maxX, app.frame.maxX)
        XCTAssertTrue(message.isHittable)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "message-input").firstMatch.isHittable)
        let metadata = try XCTUnwrap(app.descendants(matching: .any).matching(metadataQuery).allElementsBoundByIndex.last)
        XCTAssertGreaterThan(metadata.frame.height, normalTimeHeight * 1.5)
        XCTAssertTrue(metadata.label.contains("Waiting to send"))
        let notice = app.buttons["conversation-notice"]
        XCTAssertTrue(notice.isHittable)
        XCTAssertLessThan(notice.frame.height, app.frame.height * 0.12)
        capture("ios-conversation-largest-text-dark")
    }
    @MainActor private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
}
