import XCTest

final class ShortReplyImmersionTests: XCTestCase {
    @MainActor func testShortReplyAutomaticallySwitchesWithSwahiliInBothLanguageRoles() throws {
        continueAfterFailure=false
        let app=XCUIApplication()
        defer { app.terminate();app.launchArguments=["-vipi-timeline-qa","-vipi-timeline-cleanup"];app.launch() }
        for (source,target,learning,familiar,appearance) in [("en","sw","Ndiyo","yes","light"),("sw","en","yes.","Ndiyo.","dark")] {
            app.launchArguments=["-vipi-timeline-qa","-vipi-immersion-chat-qa","-vipi-immersion-response-qa","-vipi-timeline-audit",
                "-vipi-source",source,"-vipi-target",target,"-vipi-density","0.25","-vipi-appearance-"+appearance,
                "-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            func face(_ text:String)->XCUIElement {
                app.descendants(matching:.any).matching(NSPredicate(format:"identifier == 'immersionText' AND label == %@",text)).firstMatch
            }
            let learned=face(learning);XCTAssertTrue(learned.waitForExistence(timeout:20));let bounds=learned.frame
            let a=XCTAttachment(screenshot:XCUIScreen.main.screenshot());a.name="ios-short-reply-\(source)-\(target)-learning";a.lifetime = .keepAlways;add(a)
            let meaning=face(familiar);XCTAssertTrue(meaning.waitForExistence(timeout:10))
            XCTAssertEqual(meaning.frame.height,bounds.height,accuracy:1);XCTAssertEqual(meaning.frame.minY,bounds.minY,accuracy:1)
            let b=XCTAttachment(screenshot:XCUIScreen.main.screenshot());b.name="ios-short-reply-\(source)-\(target)-meaning";b.lifetime = .keepAlways;add(b)
            XCTAssertTrue(learned.waitForExistence(timeout:10),"Switch continuously, without a word tap")
            app.buttons["Reading options"].tap();app.buttons["Swahili"].tap()
            XCTAssertTrue(app.staticTexts["Ndiyo."].waitForExistence(timeout:5))
            app.buttons["Reading options"].tap();app.buttons["English"].tap()
            XCTAssertTrue(app.staticTexts["yes"].waitForExistence(timeout:5))
            app.terminate()
        }
    }
}
