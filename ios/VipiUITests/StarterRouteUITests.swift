import XCTest

@MainActor final class StarterRouteUITests: XCTestCase {
    func testDefaultPairMessagesReachContinuousBubble() throws {
        try checkPairMessages(packed:false)
    }
    func testPackedPairMessagesReachContinuousBubble() throws {
        try checkPairMessages(packed:true)
    }
    func testExpandedPairMessagesReachContinuousBubble() throws {
        try checkPairMessages(packed:true,expanded:true)
    }
    private func checkPairMessages(packed:Bool,expanded:Bool = false) throws {
        guard ProcessInfo.processInfo.environment["VIPI_STARTER_ROUTE_UI"] == "true" else { throw XCTSkip("Owned isolated starter UI qualification only") }
        continueAfterFailure=false
        for target in ["ja","sw"] {
            let app=XCUIApplication();app.launchArguments=["-vipi-starter-route-qa"]+(target == "sw" ? ["-vipi-starter-sw"] : [])+(packed ? ["-vipi-starter-packed"] : [])+(expanded ? ["-vipi-starter-expanded"] : [])
            app.launch();defer { app.terminate() }
            let proof=app.staticTexts["starter-route-proof"]
            let expectedProof="sourceReferencePartial|"+String(packed ? (target == "sw" ? 4 : 3) : 1)+"|0"
            XCTAssertTrue(proof.waitForExistence(timeout:20));XCTAssertTrue(NSPredicate(format:"label == %@",expectedProof).evaluate(with:proof) || XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == %@",expectedProof),object:proof)],timeout:20) == .completed)
            let paragraph=app.descendants(matching:.any).matching(identifier:"immersionText").firstMatch
            XCTAssertTrue(paragraph.waitForExistence(timeout:20))
            let original=expanded ? "The coffee and bread are for lunch." : packed ? "My family and my family enjoy pizza." : "Country music is fun!"
            let mixed=expanded ? (target == "sw" ? "The kahawa na mkate are for chakula cha mchana." : "The kōhī and pan are for chuushoku.") : packed ? (target == "sw" ? "My familia na my familia enjoy piza." : "My kazoku and my kazoku enjoy piza.") : (target == "sw" ? "Country muziki is fun!" : "Country ongaku is fun!")
            var observations:[[String:Any]]=[];var previous="";var transitions=0
            let deadline=Date().addingTimeInterval(40)
            while Date()<deadline && transitions<6 {
                let label=paragraph.label,frame=paragraph.frame
                if label != previous && [original,mixed].contains(label) {
                    if !previous.isEmpty { transitions += 1 };previous=label
                    observations.append(["label":label,"at":Date().timeIntervalSince1970,"x":Double(frame.minX),"y":Double(frame.minY),"width":Double(frame.width),"height":Double(frame.height)])
                }
                Thread.sleep(forTimeInterval:0.25)
            }
            XCTAssertGreaterThanOrEqual(transitions,6)
            let widths=observations.compactMap{$0["width"] as? Double},heights=observations.compactMap{$0["height"] as? Double}
            XCTAssertLessThan((widths.max() ?? 0)-(widths.min() ?? 0),0.5);XCTAssertLessThan((heights.max() ?? 0)-(heights.min() ?? 0),0.5)
            let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="starter-ui-"+target+"-continuous";screenshot.lifetime = .keepAlways;add(screenshot)
            app.buttons["Reading options"].tap()
            if target == "ja" {
                XCTAssertTrue(app.buttons["Show original script"].waitForExistence(timeout:5));app.buttons["Show original script"].tap()
                let expected=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == %@",expanded ? "The コーヒー and パン are for 昼食." : packed ? "My 家族 and my 家族 enjoy ピザ." : "Country 音楽 is fun!"),object:paragraph)
                XCTAssertEqual(XCTWaiter.wait(for:[expected],timeout:12),.completed)
                let script=XCTAttachment(screenshot:app.screenshot());script.name="starter-ui-ja-native-script";script.lifetime = .keepAlways;add(script)
                app.buttons["Reading options"].tap();XCTAssertTrue(app.buttons["Show Latin letters"].exists);app.buttons["Show Latin letters"].tap()
            } else {
                XCTAssertFalse(app.buttons["Show original script"].exists);app.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.1)).tap()
            }
            let targetVisible=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == %@",mixed),object:paragraph)
            XCTAssertEqual(XCTWaiter.wait(for:[targetVisible],timeout:12),.completed)
            app.buttons["Reading options"].tap();XCTAssertTrue(app.buttons["Listen"].waitForExistence(timeout:20));app.buttons["Listen"].tap()
            let state=app.staticTexts["starter-route-speech-events"]
            let started=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@","playing"),object:state)
            XCTAssertEqual(XCTWaiter.wait(for:[started],timeout:10),.completed)
            observations.append(["observed_speech_states":state.label,"acoustic_correctness_claim":false])
            let data=try JSONSerialization.data(withJSONObject:observations,options:.sortedKeys);let record=XCTAttachment(data:data,uniformTypeIdentifier:"public.json");record.name="starter-ui-"+target+"-observations";record.lifetime = .keepAlways;add(record)
            app.terminate()
        }
    }
}
