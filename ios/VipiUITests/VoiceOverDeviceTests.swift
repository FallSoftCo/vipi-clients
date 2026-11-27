import XCTest
import UIKit

/// Explicit physical-device qualification. No mocked accessibility environment.
/// The user's initial VoiceOver setting is restored by teardown on failure too.
final class VoiceOverDeviceTests: XCTestCase {
    override func setUpWithError() throws {
        guard ProcessInfo.processInfo.environment["VIPI_PHYSICAL_VOICEOVER"] == "1" else {
            throw XCTSkip("Explicit physical VoiceOver diagnostic only; XCTest can interrupt the service")
        }
    }
    @MainActor func testActualVoiceOverHoldsWordsAndAllowsManualSwitching() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("VoiceOver requires a physical iPad")
        #else
        continueAfterFailure = false
        let notificationMonitor = addUIInterruptionMonitor(
            withDescription: "Do not grant VoiceOver notifications during qualification"
        ) { alert in
            guard alert.label.contains("VoiceOver") else { return false }
            for title in ["Don’t Allow", "Don't Allow"] where alert.buttons[title].exists {
                alert.buttons[title].tap()
                return true
            }
            return false
        }
        defer { removeUIInterruptionMonitor(notificationMonitor) }
        let app = XCUIApplication()
        app.launchArguments = [
            "-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "1", "-vipi-appearance-light"
        ]
        let revision = ProcessInfo.processInfo.environment["VIPI_VOICEOVER_REVISION"] ?? "unknown"
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else {
            throw XCTSkip("A unique three-digit diagnostic receipt is required")
        }
        app.launchArguments += ["-vipi-voiceover-qa", revision]
        app.launch()
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        let control = try voiceControl(in: settings)
        guard let initial = control.value as? String, ["0", "1"].contains(initial) else {
            throw NSError(
                domain: "VipiQualification", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Unknown VoiceOver state; no change made"])
        }
        addTeardownBlock { @MainActor in
            defer {
                app.terminate()
                app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup", "-vipi-density", "0.25"]
                app.launch()
            }
            settings.activate()
            let restored = try self.voiceControl(in: settings)
            try self.setVoiceOver(initial, control: restored)
            XCTAssertEqual(restored.value as? String, initial)
            let receipt = XCTAttachment(
                string: "{\"initial\":\"\(initial)\",\"restored\":\"\(restored.value as? String ?? "unknown")\"}")
            receipt.name = "voiceover-setting-restoration"
            receipt.lifetime = .keepAlways
            self.add(receipt)
        }
        try setVoiceOver("1", control: control)
        app.activate()
        XCTAssertTrue(paragraph.waitForExistence(timeout: 10))
        XCTAssertTrue(
            UIAccessibility.isVoiceOverRunning,
            "XCTest interrupted the actual VoiceOver service; this is not a pause pass")
        let held = paragraph.label
        XCTAssertTrue(["I like music.", "I like muziki."].contains(held))
        let changes = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", held), object: paragraph)
        changes.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [changes], timeout: 8), .completed, "VoiceOver must hold the current words")
        XCTAssertTrue(UIAccessibility.isVoiceOverRunning)
        let word = app.links.matching(NSPredicate(format: "identifier BEGINSWITH 'immersion-word-'")).firstMatch
        XCTAssertTrue(word.exists)
        XCTAssertTrue(word.isHittable)
        try activate(word, until: { paragraph.label != held })
        XCTAssertTrue(["I like music.", "I like muziki."].contains(paragraph.label))
        capture("ipad-voiceover-manual-word")
        try openVoiceOverReadingOptions(in: app, paragraph: paragraph)
        for title in ["Pause word switching", "Resume word switching", "Word switching speed"] {
            XCTAssertFalse(app.buttons[title].exists)
        }
        XCTAssertTrue(app.buttons["Original message"].exists)
        try activate(app.buttons["Original message"], until: { paragraph.label == "I like music." })
        try openVoiceOverReadingOptions(in: app, paragraph: paragraph)
        try activate(app.buttons["Word switching"], until: { !app.buttons["Word switching"].exists })
        let restoredFace = paragraph.label
        let heldAgain = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label != %@", restoredFace), object: paragraph)
        heldAgain.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [heldAgain], timeout: 8), .completed)
        if initial == "0" {
            settings.activate()
            try setVoiceOver("0", control: try voiceControl(in: settings))
            app.activate()
            XCTAssertEqual(
                XCTWaiter.wait(
                    for: [
                        XCTNSPredicateExpectation(
                            predicate: NSPredicate(format: "label != %@", restoredFace), object: paragraph)
                    ], timeout: 12), .completed)
            openMessageReadingOptions(in: app, paragraph: paragraph)
            XCTAssertTrue(app.buttons["Pause word switching"].waitForExistence(timeout: 5))
            XCTAssertTrue(app.buttons["Word switching speed"].exists)
        }
        let receipt = XCTAttachment(
            string:
                "{\"physical_voiceover_setting_verified\":true,\"eight_second_pause\":true,\"native_word_activation\":true,\"inactive_controls_hidden\":true,\"automatic_resume_checked\":\(initial == "0"),\"speech_listening_acceptance\":false}"
        )
        receipt.name = "voiceover-immersion-result"
        receipt.lifetime = .keepAlways
        add(receipt)
        #endif
    }
    /// With VoiceOver running, use the actual focus then hold gesture to open
    /// the bubble context menu. Require its observed actions before continuing.
    @MainActor private func openVoiceOverReadingOptions(in app: XCUIApplication, paragraph: XCUIElement) throws {
        XCTAssertTrue(UIAccessibility.isVoiceOverRunning)
        let point = paragraph.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.5))
            .withOffset(CGVector(dx: -7, dy: 0))
        point.tap()
        point.press(forDuration: 1)
        XCTAssertTrue(app.buttons["Copy original message"].waitForExistence(timeout: 5))
        try activate(app.buttons["Reading options"], until: { app.buttons["Original message"].exists })
        XCTAssertTrue(UIAccessibility.isVoiceOverRunning)
    }
    @MainActor private func voiceControl(in settings: XCUIApplication) throws -> XCUIElement {
        let control = settings.switches["VoiceOver"]
        if control.exists { return control }
        let row = settings.buttons["com.apple.settings.accessibility"]
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        try activate(row, until: { settings.cells["VoiceOver"].exists })
        try activate(settings.cells["VoiceOver"], until: { control.exists })
        return control
    }
    @MainActor private func setVoiceOver(_ value: String, control: XCUIElement) throws {
        if control.value as? String == value { return }
        try activate(control, until: { control.value as? String == value })
        XCTAssertEqual(control.value as? String, value)
    }
    @MainActor private func activate(_ element: XCUIElement, until changed: @escaping () -> Bool) throws {
        XCTAssertTrue(element.exists)
        XCTAssertTrue(element.isHittable)
        let point = element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        point.tap()
        // A VoiceOver touch selects the item; double tap activates it. Some
        // XCTest routes already invoke it on tap, so observe before repeating.
        if !changed() { point.doubleTap() }
        let done = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in changed() }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [done], timeout: 10), .completed)
    }
    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    @MainActor func testInspectVoiceOverControls() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("VoiceOver requires a physical iPad")
        #else
        continueAfterFailure = false
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        let tree = XCTAttachment(string: settings.debugDescription)
        tree.name = "private-voiceover-settings-root"
        tree.lifetime = .keepAlways
        add(tree)
        let row = settings.buttons.matching(
            NSPredicate(format: "label == 'Accessibility' OR identifier == 'com.apple.Accessibility'")
        ).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        if !row.isHittable { settings.swipeUp() }
        XCTAssertTrue(row.isHittable)
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let detail = XCTAttachment(string: settings.debugDescription)
        detail.name = "private-voiceover-settings-accessibility"
        detail.lifetime = .keepAlways
        add(detail)
        let voice = settings.cells["VoiceOver"]
        XCTAssertTrue(voice.waitForExistence(timeout: 10))
        voice.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let controls = XCTAttachment(string: settings.debugDescription)
        controls.name = "private-voiceover-settings-controls"
        controls.lifetime = .keepAlways
        add(controls)
        XCTAssertTrue(settings.switches["VoiceOver"].waitForExistence(timeout: 10))
        #endif
    }
}
