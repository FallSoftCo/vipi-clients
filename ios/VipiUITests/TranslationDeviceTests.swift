import XCTest

final class TranslationDeviceTests: XCTestCase {
    @MainActor func testRunAppleTranslationWithoutNetwork() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Apple translation requires a physical device")
        #else
        // Development signing checks trust when the newly installed app first
        // launches. Start it online, then qualify translation after the radios
        // are disconnected; this is not a cold-launch offline qualification.
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-translation-matrix", "-vipi-translation-offline"]
        app.launch()
        XCTAssertTrue(app.staticTexts["translationNetwork"].waitForExistence(timeout: 15))
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        let airplane = settings.switches["com.apple.settings.airplaneMode"]
        guard airplane.waitForExistence(timeout: 10), airplane.value as? String == "1" else {
            throw NSError(domain: "VipiQualification", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Expected the observed airplane-on state; no radio changed."])
        }
        let wifi = try wifiControl(in: settings)
        guard let initial = wifi.value as? String, ["0", "1"].contains(initial) else {
            throw NSError(domain: "VipiQualification", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "Unrecognized Wi-Fi state; no radio changed."])
        }
        addTeardownBlock { @MainActor in
            settings.activate()
            let restored = try self.wifiControl(in: settings)
            if restored.value as? String != initial {
                restored.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            }
            let matches = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", initial), object: restored)
            XCTAssertEqual(XCTWaiter.wait(for: [matches], timeout: 15), .completed, "Restore initial Wi-Fi state")
            XCTAssertEqual(airplane.value as? String, "1", "Airplane mode must remain unchanged")
            let receipt = XCTAttachment(string: "{\"wifi_initial\":\"\(initial)\",\"wifi_restored\":\"\(restored.value as? String ?? "unknown")\",\"airplane_initial\":\"1\",\"airplane_restored\":\"\(airplane.value as? String ?? "unknown")\"}")
            receipt.name = "ipad-offline-network-restoration"; receipt.lifetime = .keepAlways; self.add(receipt)
        }
        if initial == "1" { wifi.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '0'"), object: wifi)], timeout: 10), .completed)
        app.activate()
        let network = app.staticTexts["translationNetwork"]
        let offline = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Network path: unavailable'"), object: network)
        guard XCTWaiter.wait(for: [offline], timeout: 30) == .completed else {
            throw NSError(domain: "VipiQualification", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "No confirmed offline path; matrix not started."])
        }
        try tapReady(app.buttons["translation-run"], in: app)
        let status = app.staticTexts["translationStatus"]
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label BEGINSWITH 'Finished 90 directions.'"), object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 900), .completed)
        XCTAssertEqual(status.label, "Finished 90 directions. 0 failed.")
        XCTAssertEqual(network.label, "Network path: unavailable")
        capture("ipad-translation-offline-matrix-completed")
        #endif
    }
    @MainActor private func wifiControl(in settings: XCUIApplication) throws -> XCUIElement {
        let row = settings.buttons["com.apple.settings.wifi"]
        XCTAssertTrue(row.waitForExistence(timeout: 10)); try tapReady(row, in: settings)
        XCTAssertTrue(settings.navigationBars["Wi-Fi"].waitForExistence(timeout: 10))
        // This is the exact label observed in the physical Settings hierarchy.
        let control = settings.switches["Wi‑Fi"]
        guard control.waitForExistence(timeout: 10) else {
            throw NSError(domain: "VipiQualification", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "Physical Wi-Fi switch missing."])
        }
        return control
    }
    @MainActor func testInspectNetworkControls() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPad network controls")
        #else
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        let wifi = settings.buttons["com.apple.settings.wifi"]
        XCTAssertTrue(wifi.waitForExistence(timeout: 10))
        try tapReady(wifi, in: settings)
        XCTAssertTrue(settings.navigationBars["Wi-Fi"].waitForExistence(timeout: 10))
        let tree = XCTAttachment(string: settings.debugDescription)
        tree.name = "private-ipad-network-settings-hierarchy"; tree.lifetime = .keepAlways; add(tree)
        #endif
    }
    @MainActor func testPrepareAndRunAppleTranslation() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Apple translation requires a physical device")
        #else
        continueAfterFailure = false
        let app = XCUIApplication()
        let monitor = addUIInterruptionMonitor(withDescription: "Apple local translation model download") { alert in
            if alert.buttons["Download"].exists { alert.buttons["Download"].tap(); return true }
            return false
        }
        defer { removeUIInterruptionMonitor(monitor) }
        let deadline = Date().addingTimeInterval(900)
        for target in ["es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko"] {
            // iPadOS 18 can leave the download sheet's dimming layer behind
            // when a batch replaces its presenter. Qualify each model with a
            // fresh app presenter, then run all installed directions together.
            app.terminate()
            app.launchArguments = ["-vipi-translation-matrix", "-vipi-translation-prepare-target", target]
            app.launch()
            let prepare = app.buttons["translation-prepare"]
            XCTAssertTrue(prepare.waitForExistence(timeout: 15)); try tapReady(prepare, in: app)
            let status = app.staticTexts["translationStatus"]
            let prepared = NSPredicate(format: "label BEGINSWITH %@", "Finished 1 directions.")
            while Date() < deadline && !prepared.evaluate(with: status) {
                let arrow = app.buttons.matching(identifier: "arrow.down.circle").firstMatch
                if arrow.exists && arrow.isHittable { arrow.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
                else if app.buttons["Download"].exists { app.buttons["Download"].tap() }
                else if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons["Download"].exists {
                    XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons["Download"].tap()
                }
                _ = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: prepared, object: status)], timeout: 2)
            }
            XCTAssertTrue(prepared.evaluate(with: status), "Preparation did not finish: " + target)
            XCTAssertEqual(status.label, "Finished 1 directions. 0 failed.")
            capture("ipad-language-prepared-" + target)
        }
        app.terminate(); app.launchArguments = ["-vipi-translation-matrix"]; app.launch()
        let run = app.buttons["translation-run"]
        XCTAssertTrue(run.waitForExistence(timeout: 15)); try tapReady(run, in: app)
        let started = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label BEGINSWITH %@ OR label BEGINSWITH %@", "Translating", "Finished 90 directions."), object: app.staticTexts["translationStatus"])
        XCTAssertEqual(XCTWaiter.wait(for: [started], timeout: 15), .completed, "The run button did not start a new matrix")
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label BEGINSWITH %@", "Finished 90 directions."), object: app.staticTexts["translationStatus"])
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 900), .completed)
        XCTAssertEqual(app.staticTexts["translationStatus"].label, "Finished 90 directions. 0 failed.")
        capture("ipad-translation-matrix-completed")
        // The separate JSON receipt determines actual successes/meaning quality.
        #endif
    }
    @MainActor private func tapReady(_ button: XCUIElement, in app: XCUIApplication) throws {
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        let frame = button.frame
        XCTAssertGreaterThan(frame.width, 44); XCTAssertGreaterThanOrEqual(frame.height, 44)
        XCTAssertTrue(app.frame.contains(CGPoint(x: frame.midX, y: frame.midY)))
        // Xcode 26 against iPadOS 18 returned a (-1,-1) hit point without
        // failing tap(). Use the freshly observed element's center instead.
        button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
    }
    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
