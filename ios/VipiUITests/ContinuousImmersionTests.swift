import XCTest

@MainActor final class ContinuousImmersionTests: XCTestCase {
    func testRepeatsWithoutTapsPreservesGeometryAndResumesAfterPause() throws {
        let app = XCUIApplication(); app.launchArguments = ["-vipi-welcome"]; app.launch()
        let text = app.textViews["immersionText"]
        XCTAssertTrue(text.waitForExistence(timeout: 15))
        let target = "Café mañana? I know a little place by the río."
        let original = "Coffee tomorrow? I know a little place by the river."
        let first = text.frame
        for index in 0..<6 {
            let expected = index.isMultiple(of: 2) ? original : target
            let change = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", expected), object: text)
            XCTAssertEqual(XCTWaiter.wait(for: [change], timeout: 8), .completed)
            XCTAssertEqual(text.frame.height, first.height, accuracy: 0.5)
            XCTAssertEqual(text.frame.minY, first.minY, accuracy: 0.5)
            let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "Continuous phase \(index)"; capture.lifetime = .keepAlways; add(capture)
        }
        app.buttons["immersionPause"].tap()
        let held = text.label
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", held), object: text)
        changed.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 8), .completed)
        app.buttons["immersionPause"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", held), object: text)], timeout: 8), .completed)
        app.buttons["See the whole thought in Spanish"].tap()
        XCTAssertTrue(app.staticTexts["¿Café mañana? Conozco un pequeño lugar junto al río."].exists)
        app.buttons["Back to a little Spanish"].tap()
        XCTAssertTrue(text.waitForExistence(timeout: 3))
        app.buttons["Find your language"].tap()
        XCTAssertTrue(app.staticTexts["I already speak"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["TRY A LITTLE SPANISH"].exists)
    }
}
