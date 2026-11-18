import XCTest

@MainActor final class BundledSourceFrameUITests: XCTestCase {
    struct Case: Decodable { let source, target, original, mixed, script: String }
    func testPromotedOrdinaryPairsFlipContinuouslyAndShowReadings() throws {
        guard ProcessInfo.processInfo.environment["VIPI_BUNDLED_SOURCE_UI"] == "true" else { throw XCTSkip("Only after explicit bundled promotion") }
        continueAfterFailure = false
        let cases = try JSONDecoder().decode([Case].self, from: Data(#"""
[
  {
    "source": "ja",
    "target": "ar",
    "original": "このことは後で話しましょう。朝食が必要",
    "mixed": "このことは後で話しましょう。fuṭūrが必要",
    "script": "このことは後で話しましょう。فطورが必要"
  },
  {
    "source": "ar",
    "target": "ja",
    "original": "يمكننا التحدث عن هذا لاحقًا. أود عنوان بريدي",
    "mixed": "يمكننا التحدث عن هذا لاحقًا. أود yūsōsaki no jūsho",
    "script": "يمكننا التحدث عن هذا لاحقًا. أود 郵送先の住所"
  },
  {
    "source": "ko",
    "target": "zh",
    "original": "이 이야기는 나중에 다시 해요. 우편 주소 주세요",
    "mixed": "이 이야기는 나중에 다시 해요. yóujì dìzhǐ 주세요",
    "script": "이 이야기는 나중에 다시 해요. 邮寄地址 주세요"
  },
  {
    "source": "zh",
    "target": "ko",
    "original": "我们可以稍后再谈这件事。要一个邮寄地址",
    "mixed": "我们可以稍后再谈这件事。要一个upyeon juso",
    "script": "我们可以稍后再谈这件事。要一个우편 주소"
  },
  {
    "source": "sw",
    "target": "fr",
    "original": "Tunaweza kuzungumza kuhusu hili baadaye. Alitaka kifungua kinywa",
    "mixed": "Tunaweza kuzungumza kuhusu hili baadaye. Alitaka petit-déjeuner",
    "script": "Tunaweza kuzungumza kuhusu hili baadaye. Alitaka petit-déjeuner"
  }
]
"""#.utf8))
        for row in cases {
            let app = XCUIApplication()
            app.launchArguments = ["-vipi-starter-route-qa", "-vipi-starter-auto", "-vipi-starter-source", row.source,
                "-vipi-starter-target", row.target, "-vipi-starter-original", row.original, "-readingPace", "balanced"]
            app.launch(); defer { app.terminate() }
            let proof = app.staticTexts["starter-route-proof"]
            XCTAssertTrue(proof.waitForExistence(timeout: 20))
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "sourceReferencePartial|1|0"), object: proof)], timeout: 20), .completed)
            let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
            XCTAssertTrue(paragraph.waitForExistence(timeout: 10))
            var previous = "", transitions = 0, observations: [[String: Any]] = []
            let deadline = Date().addingTimeInterval(40)
            while Date() < deadline && transitions < 6 {
                let label = paragraph.label, frame = paragraph.frame
                if label != previous && [row.original, row.mixed].contains(label) {
                    if !previous.isEmpty { transitions += 1 }; previous = label
                    observations.append(["text": label, "height": Double(frame.height), "width": Double(frame.width), "y": Double(frame.minY)])
                }
                Thread.sleep(forTimeInterval: 0.25)
            }
            XCTAssertGreaterThanOrEqual(transitions, 6)
            for key in ["height", "width", "y"] {
                let values = observations.compactMap { ($0[key] as? NSNumber)?.doubleValue }
                XCTAssertLessThan((values.max() ?? 0) - (values.min() ?? 0), 0.5)
            }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", row.mixed), object: paragraph)], timeout: 12), .completed)
            let reading = XCTAttachment(screenshot: app.screenshot()); reading.name = row.source + "-" + row.target + "-continuous-reading"; reading.lifetime = .keepAlways; add(reading)
            if row.mixed != row.script {
                openMessageReadingOptions(in: app, paragraph: paragraph)
                XCTAssertTrue(app.buttons["Show original script"].waitForExistence(timeout: 5)); app.buttons["Show original script"].tap()
                XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", row.script), object: paragraph)], timeout: 12), .completed)
                let script = XCTAttachment(screenshot: app.screenshot()); script.name = row.source + "-" + row.target + "-native-script"; script.lifetime = .keepAlways; add(script)
                openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Show Latin letters"].tap()
                XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", row.mixed), object: paragraph)], timeout: 12), .completed)
            }
            let record = XCTAttachment(data: try JSONSerialization.data(withJSONObject: observations, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
            record.name = row.source + "-" + row.target + "-six-flips"; record.lifetime = .keepAlways; add(record)
            app.terminate()
        }
    }
}
