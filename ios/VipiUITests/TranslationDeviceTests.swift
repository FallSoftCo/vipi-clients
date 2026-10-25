import XCTest

final class TranslationDeviceTests: XCTestCase {
    @MainActor func testPrepareAndRunAppleTranslation() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Apple translation requires a physical device")
        #else
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-translation-matrix"]
        app.launch()
        XCTAssertTrue(app.buttons["Prepare language models"].waitForExistence(timeout: 15))
        let monitor = addUIInterruptionMonitor(withDescription: "Apple local translation model download") { alert in
            if alert.buttons["Download"].exists { alert.buttons["Download"].tap(); return true }
            return false
        }
        defer { removeUIInterruptionMonitor(monitor) }
        app.buttons["Prepare language models"].tap()
        let status = app.staticTexts["translationStatus"]
        let prepared = NSPredicate(format: "label BEGINSWITH %@", "Finished 9 directions.")
        let deadline = Date().addingTimeInterval(900)
        while Date() < deadline && !prepared.evaluate(with: status) {
            // iPadOS 18 exposes per-language download icons rather than a
            // single Download action. Use Apple's accessibility identifier,
            // observed on the attached iPad, without coordinate guessing.
            let arrow = app.buttons.matching(identifier: "arrow.down.circle").firstMatch
            if arrow.exists && arrow.isHittable { arrow.tap() }
            else if app.buttons["Download"].exists { app.buttons["Download"].tap() }
            else if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons["Download"].exists {
                XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons["Download"].tap()
            }
            // Bounded UI observation; no model-generated polling is needed.
            _ = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: prepared, object: status)], timeout: 2)
        }
        XCTAssertTrue(prepared.evaluate(with: status), "Preparation did not finish; inspect device receipt")
        app.buttons["Run 90 directions"].tap()
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label BEGINSWITH %@", "Finished 90 directions."), object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 900), .completed)
        // The separate JSON receipt determines actual successes/meaning quality.
        #endif
    }
}
