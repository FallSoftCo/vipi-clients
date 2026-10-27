import XCTest

final class LanguageSettingsTests: XCTestCase {
    @MainActor func testLanguageChoiceListsRemainAccessible() throws {
        let app = XCUIApplication()
        for appearance in ["light", "dark", "large"] {
            app.launchArguments = ["-vipi-preview-home", "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-" + (appearance == "light" ? "light" : "dark")]
            if appearance == "large" { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
            app.launch()
            XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 10)); app.buttons["Your profile and settings"].tap()
            XCTAssertTrue(app.buttons["language-settings-link"].waitForExistence(timeout: 5)); app.buttons["language-settings-link"].tap()
            for (identifier,title,last) in [("language-source-picker","I already speak","Swahili"),
                                             ("language-target-picker","I’m picking up","Swahili · Kiswahili")] {
                XCTAssertTrue(app.buttons[identifier].waitForExistence(timeout: 5)); app.buttons[identifier].tap()
                XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 5))
                try app.performAccessibilityAudit { issue in
                    let detail = XCTAttachment(string: "\(issue.compactDescription)\n\(issue.detailedDescription)\n\(issue.element?.debugDescription ?? "no element")")
                    detail.name = "choice-audit-" + identifier + "-" + appearance; detail.lifetime = .keepAlways; self.add(detail)
                    return false
                }
                let choice = app.buttons[last]
                for _ in 0..<6 {
                    if choice.exists && choice.isHittable { break }
                    app.swipeUp()
                }
                XCTAssertTrue(choice.exists && choice.isHittable)
                try app.performAccessibilityAudit { issue in
                    let detail = XCTAttachment(string: "\(issue.compactDescription)\n\(issue.detailedDescription)\n\(issue.element?.debugDescription ?? "no element")")
                    detail.name = "choice-audit-" + identifier + "-" + appearance; detail.lifetime = .keepAlways; self.add(detail)
                    return false
                }
                let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                capture.name = "ipad-language-choices-" + identifier + "-" + appearance
                capture.lifetime = .keepAlways; add(capture)
                app.navigationBars[title].buttons.element(boundBy: 0).tap()
                XCTAssertTrue(app.buttons[identifier].waitForExistence(timeout: 5))
            }
            app.terminate()
        }
    }
    @MainActor func testLanguageSettingsNavigationAndSelectionLightAndDark() throws {
        let app = XCUIApplication()
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-vipi-preview-home", "-vipi-source", "en", "-vipi-target", "ja", "-vipi-appearance-" + appearance]
            app.launch()
            let settings = app.buttons["Your profile and settings"]
            XCTAssertTrue(settings.waitForExistence(timeout: 10)); settings.tap()
            let link = app.buttons["language-settings-link"]
            XCTAssertTrue(link.waitForExistence(timeout: 5)); link.tap()
            let status = app.staticTexts["language-download-status"]
            XCTAssertTrue(status.waitForExistence(timeout: 10))
            let picker = app.buttons["language-target-picker"]
            XCTAssertTrue(picker.exists); picker.tap()
            let spanish = app.buttons["Spanish · Español"]
            XCTAssertTrue(spanish.waitForExistence(timeout: 5)); spanish.tap()
            let settled = NSPredicate(format: "NOT (label ENDSWITH %@)", "Checking this device…")
            expectation(for: settled, evaluatedWith: status)
            waitForExpectations(timeout: 10)
            XCTAssertFalse(status.label.contains("Japanese"))
            XCTAssertFalse(app.staticTexts["language-download-message"].exists)
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "ios-language-settings-" + appearance; attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
    }
    @MainActor func testSwahiliReadyStateAndPairSelectionOnPhysicalDevice() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("The Swahili model runtime requires a physical device")
        #else
        continueAfterFailure = false
        let app = XCUIApplication()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-preview-home", "-vipi-source", "en", "-vipi-target", "sw"]; app.launch()
        }
        for appearance in ["light", "dark", "large"] {
            app.launchArguments = ["-vipi-preview-home", "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-" + (appearance == "light" ? "light" : "dark")]
            if appearance == "large" { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
            app.launch()
            let settings = app.buttons["Your profile and settings"]
            XCTAssertTrue(settings.waitForExistence(timeout: 10)); settings.tap()
            let link = app.buttons["language-settings-link"]
            XCTAssertTrue(link.waitForExistence(timeout: 5)); link.tap()
            let status = app.staticTexts["language-download-status"]
            XCTAssertTrue(status.waitForExistence(timeout: 10))
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label ENDSWITH %@", "English and Swahili are ready for offline translation."), object: status)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed)
            XCTAssertFalse(app.buttons["language-download-start"].exists)
            if appearance != "large" {
                app.buttons["language-source-picker"].tap()
                XCTAssertTrue(app.buttons["Spanish"].waitForExistence(timeout: 5)); app.buttons["Spanish"].tap()
                let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label ENDSWITH %@", "Spanish and Swahili are ready for offline translation."), object: status)
                XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 10), .completed)
            }
            if appearance == "light" {
                app.buttons["Remove these translation downloads"].tap()
                XCTAssertTrue(app.alerts["Remove downloads?"].waitForExistence(timeout: 5))
                app.buttons["Keep downloads"].tap()
                XCTAssertTrue(status.label.hasSuffix("Spanish and Swahili are ready for offline translation."))
            }
            if appearance != "large" {
                // Verify persisted pair and its accessibility after a real app
                // relaunch, including native menu/alert presentation teardown.
                app.terminate()
                app.launchArguments = ["-vipi-preview-home", "-vipi-appearance-" + appearance]
                app.launch()
                XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 10))
                app.buttons["Your profile and settings"].tap()
                XCTAssertTrue(app.buttons["language-settings-link"].waitForExistence(timeout: 5))
                app.buttons["language-settings-link"].tap()
                XCTAssertTrue(status.waitForExistence(timeout: 10))
                let persisted = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label ENDSWITH %@", "Spanish and Swahili are ready for offline translation."), object: status)
                XCTAssertEqual(XCTWaiter.wait(for: [persisted], timeout: 10), .completed)
            }
            XCTAssertFalse(app.alerts["Remove downloads?"].exists)
            Thread.sleep(forTimeInterval: 0.5) // Native modal dismissal is outside the app's layout clock.
            let beforeAudit = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            beforeAudit.name = "ipad-language-before-audit-" + appearance; beforeAudit.lifetime = .keepAlways; add(beforeAudit)
            continueAfterFailure = true
            do { try app.performAccessibilityAudit { issue in
                let detail = XCTAttachment(string: "issue: \(issue.compactDescription)\ndetail: \(issue.detailedDescription)\nidentifier: \(issue.element?.identifier ?? "nil")\nlabel: \(issue.element?.label ?? "nil")\nframe: \(issue.element.map { String(describing: $0.frame) } ?? "nil")\n\n" + app.debugDescription)
                detail.name = "language-settings-audit-detail-" + appearance; detail.lifetime = .keepAlways; self.add(detail)
                return false
            } } catch { XCTFail("Language accessibility audit failed: \(error)") }
            continueAfterFailure = false
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "ipad-language-settings-swahili-" + appearance; attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
        #endif
    }

}
