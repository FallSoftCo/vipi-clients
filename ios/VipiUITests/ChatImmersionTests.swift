import XCTest
import UIKit

final class ChatImmersionTests: XCTestCase {

    @MainActor func testJapaneseDefaultReadingUsesOriginalScriptAndAuthoredPriority() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-full-reading-qa", "-vipi-japanese-reading-fixture", "-vipi-appearance-dark",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch(); defer { app.terminate() }
        let latin = app.staticTexts["Zoë to José ni messēji wo okutta。"]
        XCTAssertTrue(latin.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "localTransliteration")
        capture("ios-japanese-local-full-reading")
        openInlineReadingOptions(in: app); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["ZoëとJoséにメッセージを送った。"].waitForExistence(timeout: 5))
        capture("ios-japanese-local-original-script")
        openInlineReadingOptions(in: app); app.buttons["Show Latin letters"].tap()
        XCTAssertTrue(latin.waitForExistence(timeout: 5))
        app.buttons["Authored"].tap()
        XCTAssertTrue(app.staticTexts["Mizu ga hitsuyō desu."].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "authored")
        app.buttons["Unknown"].tap()
        XCTAssertTrue(app.staticTexts["𠮷先生に会う。"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "unavailable")
        capture("ios-japanese-unknown-reading-abstains")
        openInlineMessageActions(in: app)
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.navigationBars.firstMatch.tap()
        openInlineReadingOptions(in: app)
        XCTAssertFalse(app.buttons["Show original script"].exists)
        XCTAssertFalse(app.buttons["Show Latin letters"].exists)
    }

    @MainActor func testKoreanDefaultReadingUsesOriginalScriptAndAuthoredPriority() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-full-reading-qa", "-vipi-korean-reading-fixture", "-vipi-appearance-dark",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch(); defer { app.terminate() }
        let latin = app.staticTexts["gat-i haggyoe gabnida."]
        XCTAssertTrue(latin.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "localTransliteration")
        capture("ios-korean-local-full-reading")
        openInlineReadingOptions(in: app); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["같이 학교에 갑니다."].waitForExistence(timeout: 5))
        capture("ios-korean-local-original-script")
        openInlineReadingOptions(in: app); app.buttons["Show Latin letters"].tap()
        XCTAssertTrue(latin.waitForExistence(timeout: 5))
        app.buttons["Authored"].tap()
        XCTAssertTrue(app.staticTexts["Muri piryohaeyo."].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "authored")
        app.buttons["Unknown"].tap()
        XCTAssertTrue(app.staticTexts["𠮷에게 메시지를 보내요."].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "unavailable")
        capture("ios-korean-unknown-reading-abstains")
        openInlineMessageActions(in: app)
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.navigationBars.firstMatch.tap()
        openInlineReadingOptions(in: app)
        XCTAssertFalse(app.buttons["Show original script"].exists)
        XCTAssertFalse(app.buttons["Show Latin letters"].exists)
    }

    @MainActor func testDelayedManualReadingPreservesProductionHistoryAnchor() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-history-qa",
            "-vipi-immersion-single-qa", "-vipi-delayed-reading-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "ja", "-vipi-appearance-dark",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
            XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 10))
            app.terminate()
        }
        let timeline = app.scrollViews["conversation-timeline"]
        let paragraphs = app.descendants(matching: .any).matching(identifier: "immersionText")
        XCTAssertTrue(paragraphs.firstMatch.waitForExistence(timeout: 30))
        timeline.swipeDown(); timeline.swipeDown()
        let jump = app.buttons["conversation-latest"]
        XCTAssertTrue(jump.waitForExistence(timeout: 5))
        let viewport = timeline.frame
        let paragraph = try XCTUnwrap(paragraphs.allElementsBoundByIndex
            .filter { $0.isHittable && $0.frame.minY > viewport.minY + 40 && $0.frame.maxY < viewport.maxY - 40 }
            .min { abs($0.frame.midY - viewport.midY) < abs($1.frame.midY - viewport.midY) })
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "I like music.")
        let before = paragraph.frame
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Translating on this device…"].waitForExistence(timeout: 5))
        XCTAssertFalse(panel.staticTexts["Watashi wa ongaku ga suki desu."].exists)
        XCTAssertEqual(paragraph.frame.minY, before.minY, accuracy: 3)
        XCTAssertTrue(jump.exists)
        capture("ios-delayed-direct-reading-pending")
        app.buttons["timeline-qa-release-reading"].tap()
        let reading = panel.staticTexts["Watashi wa ongaku ga suki desu."]
        XCTAssertTrue(reading.waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["私は音楽が好きです。"].exists)
        XCTAssertTrue(panel.staticTexts["I like music."].exists)
        capture("ios-delayed-direct-reading-ready")
        closeTranslationPanel(panel, in: app)
        let after = paragraph.frame
        func box(_ rect: CGRect) -> [String: Double] { ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height] }
        let data = try JSONSerialization.data(withJSONObject: ["before": box(before), "after": box(after),
            "timeline_before": box(viewport), "timeline_after": box(timeline.frame),
            "history_mode_retained": jump.exists, "actual_direct_panel": true,
            "supplied_authored_reference": true, "fresh_translation_provider": false,
            "retired_expectation": "Full-target mode used to grow the chat row; current lookup publishes target+reading in its separate panel."], options: [.prettyPrinted, .sortedKeys])
        let receipt = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        receipt.name = "delayed-direct-reading-history-geometry"; receipt.lifetime = .keepAlways; add(receipt)
        XCTAssertEqual(paragraph.label, "I like music.")
        XCTAssertEqual(after.minY, before.minY, accuracy: 3)
        XCTAssertEqual(after.height, before.height, accuracy: 1)
        XCTAssertEqual(timeline.frame.minY, viewport.minY, accuracy: 1)
        XCTAssertEqual(timeline.frame.height, viewport.height, accuracy: 1)
        XCTAssertTrue(jump.exists, "Reading arrival must preserve older-reading intent")
    }

    @MainActor func testChineseFullReadingUsesBundledReaderAndOriginalScript() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-full-reading-qa", "-vipi-appearance-dark",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        launchPortraitApp(app); defer { app.terminate() }
        let latin = app.staticTexts["yínháng hángzhǎng zhèng zài zǒu lù。"]
        XCTAssertTrue(latin.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "localTransliteration")
        capture("ios-chinese-local-full-reading")
        openInlineReadingOptions(in: app); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["银行行长正在走路。"].waitForExistence(timeout: 5))
        capture("ios-chinese-local-original-script")
        openInlineReadingOptions(in: app); app.buttons["Show Latin letters"].tap()
        XCTAssertTrue(latin.waitForExistence(timeout: 5))
        app.buttons["Authored"].tap()
        XCTAssertTrue(app.staticTexts["Wǒ xūyào shuǐ."].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "authored")
        app.buttons["Unknown"].tap()
        XCTAssertTrue(app.staticTexts["𠮷先生与𰻞字怎么读？"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "unavailable")
        capture("ios-chinese-unknown-reading-abstains")
        openInlineMessageActions(in: app)
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.navigationBars.firstMatch.tap()
        openInlineReadingOptions(in: app)
        XCTAssertFalse(app.buttons["Show original script"].exists)
        XCTAssertFalse(app.buttons["Show Latin letters"].exists)
    }

    @MainActor func testPartialLookupKeepsSwitchingAfterUnavailableWholeTranslation() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-source-unit-routing-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "0.25", "-vipi-appearance-dark", "-vipi-live-immersion-state", "016"]
        app.launchArguments += ["-readingPace", "balanced"]
        launchPortraitApp(app)
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        // The simulator has no ML Kit classifier. Choose the real message
        // language rather than injecting inferred direction or target text.
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        XCTAssertTrue(paragraph.label.contains("Did you finish the report?"))
        // An explicit English choice resolves the current provider's two
        // native units. Wait for that binding, not the cached sentence face
        // which may still exist while the source override is being applied.
        let words: [(id: String, faces: [String])] = [
            ("immersion-word-0", ["I need", "ninahitaji"]),
            ("immersion-word-7", ["water", "maji"])
        ]
        let slots = words.map { app.descendants(matching: .any).matching(identifier: $0.id).firstMatch }
        for slot in slots { XCTAssertTrue(slot.waitForExistence(timeout: 5)) }
        let bounds = slots.map(\.frame)
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Translation isn’t supported for this language pair on this device."].waitForExistence(timeout: 10))
        XCTAssertFalse(panel.buttons["Try again"].exists)
        XCTAssertFalse(panel.buttons["Download languages"].exists)
        XCTAssertTrue(paragraph.label.contains("Did you finish the report?"))
        capture("ios-partial-direct-translation-unavailable")
        var samples: [[String: Any]] = []
        var transitions = [0, 0], previous: [String?] = [nil, nil]
        let start = Date()
        while Date().timeIntervalSince(start) < 29 {
            for index in words.indices {
                let label = slots[index].label, frame = slots[index].frame
                let complete = words[index].faces.contains(label) && frame.height > 0
                if complete {
                    if let old = previous[index], label != old { transitions[index] += 1 }
                    previous[index] = label
                    XCTAssertEqual(frame.width, bounds[index].width, accuracy: 1)
                    XCTAssertEqual(frame.height, bounds[index].height, accuracy: 1)
                }
                samples.append(["seconds": Date().timeIntervalSince(start), "id": words[index].id, "label": label,
                    "width": frame.width, "height": frame.height, "complete_accessibility_snapshot": complete])
            }
            Thread.sleep(forTimeInterval: 0.3)
        }
        for count in transitions { XCTAssertGreaterThanOrEqual(count, 6) }
        closeTranslationPanel(panel, in: app)
        openMessageReadingOptions(in: app, paragraph: paragraph)
        app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "I need water. Did you finish the report?")
        capture("ios-partial-original-message-preserved")
        let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: ["samples": samples,
            "transitions": transitions, "real_provider": "simulator unsupported; no injected inference"], options: [.sortedKeys]),
            uniformTypeIdentifier: "public.json")
        attachment.name = "source-unit-partial-switching"; attachment.lifetime = .keepAlways; add(attachment)
    }

    @MainActor func testWholeGreetingKeepsItsBlockStableAtLargestText() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-opener-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "0.25", "-vipi-appearance-light",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        let target = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Asante sana."), object: paragraph)
        XCTAssertEqual(XCTWaiter.wait(for: [target], timeout: 10), .completed)
        let bounds = paragraph.frame
        XCTAssertGreaterThanOrEqual(bounds.minX, app.frame.minX)
        XCTAssertLessThanOrEqual(bounds.maxX, app.frame.maxX)
        capture("ios-greeting-largest-target")
        let meaning = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Thank you very much."), object: paragraph)
        XCTAssertEqual(XCTWaiter.wait(for: [meaning], timeout: 10), .completed)
        XCTAssertEqual(paragraph.frame.height, bounds.height, accuracy: 1)
        XCTAssertEqual(paragraph.frame.minY, bounds.minY, accuracy: 1)
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Asante sana."].waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["Thank you very much."].exists)
        capture("ios-greeting-largest-direct-translation")
        closeTranslationPanel(panel, in: app)
        openMessageReadingOptions(in: app, paragraph: paragraph)
        app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "Thank you very much.")
        XCTAssertEqual(paragraph.frame.height, bounds.height, accuracy: 1)
        XCTAssertEqual(paragraph.frame.minY, bounds.minY, accuracy: 1)
    }

    @MainActor func testZeroDensityKeepsDirectTranslationWithoutInactiveWordActions() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "0", "-vipi-appearance-light"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup", "-vipi-density", "0.25"]; app.launch() }
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        openMessageActions(in: app, paragraph: paragraph)
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.buttons["Reading options"].tap()
        for title in ["Pause word switching", "Word switching speed", "Show original words now"] {
            XCTAssertFalse(app.buttons[title].exists)
        }
        app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "I like music.")
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Ninapenda muziki."].waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["I like music."].exists)
        capture("ios-zero-vocabulary-direct-translation")
        closeTranslationPanel(panel, in: app)
        XCTAssertEqual(paragraph.label, "I like music.")
    }

    @MainActor func testExpandedRequestReadingsInAllFourNonRomanLanguagesAtLargestText() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let cases = [
            ("ar", "Aḥtāj ilā shāḥin hātif.", "أحتاج إلى شاحن هاتف."),
            ("zh", "Wǒ xūyào yí ge shǒujī chōngdiànqì.", "我需要一个手机充电器。"),
            ("ja", "Keitai denwa no jūdenki ga hitsuyō desu.", "携帯電話の充電器が必要です。"),
            ("ko", "Hyudaepon chungjeongiga piryohaeyo.", "휴대폰 충전기가 필요해요.")
        ]
        for (code, latin, native) in cases {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-request-qa", "-vipi-timeline-audit",
                "-vipi-source", "en", "-vipi-target", code, "-vipi-appearance-light",
                "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
            XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
            chooseMessageLanguage("English", in: app, paragraph: paragraph)
            let panel = translateMessage(in: app, paragraph: paragraph)
            // Direct lookup shows native target and its reading together; it
            // does not replace the row or require toggling a full-target mode.
            let reading = panel.staticTexts[latin]
            XCTAssertTrue(reading.waitForExistence(timeout: 10))
            XCTAssertTrue(panel.staticTexts[native].exists)
            for (face, content) in [("native", panel.staticTexts[native]), ("latin", reading)] {
                for _ in 0..<4 {
                    if content.isHittable && content.frame.minY >= panel.frame.minY && content.frame.maxY <= panel.frame.maxY { break }
                    panel.swipeUp()
                }
                XCTAssertTrue(content.isHittable)
                XCTAssertGreaterThanOrEqual(content.frame.minX, app.frame.minX)
                XCTAssertLessThanOrEqual(content.frame.maxX, app.frame.maxX)
                XCTAssertGreaterThanOrEqual(content.frame.minY, panel.frame.minY)
                XCTAssertLessThanOrEqual(content.frame.maxY, panel.frame.maxY)
                capture("ios-request-direct-reading-largest-" + code + "-" + face)
            }
            closeTranslationPanel(panel, in: app)
            openMessageReadingOptions(in: app, paragraph: paragraph)
            app.buttons["Original message"].tap()
            XCTAssertEqual(paragraph.label, "I need a phone charger.")
            if code == "ar" {
                openMessageReadingOptions(in: app, paragraph: paragraph)
                app.buttons["Word switching"].tap()
                for label in ["Slower", "Standard"] {
                    openMessageReadingOptions(in: app, paragraph: paragraph)
                    let pace = app.buttons["Word switching speed"]
                    XCTAssertTrue(pace.isHittable); pace.tap()
                    XCTAssertTrue(app.buttons[label].waitForExistence(timeout: 5))
                    capture("ios-request-pace-largest-" + label.lowercased())
                    app.buttons[label].tap()
                }
            }
            app.terminate()
        }
    }

    @MainActor func testOnboardingSelectsSwahiliAndKeepsPreparedWordFacesInBothDirections() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-language", "-vipi-source", "en", "-vipi-target", "es", "-vipi-appearance-light"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es"]; app.launch() }
        let targetPicker = app.buttons["I’m learning"]
        XCTAssertTrue(targetPicker.waitForExistence(timeout: 15)); targetPicker.tap()
        app.buttons["Swahili · Kiswahili"].tap()
        XCTAssertEqual(targetPicker.value as? String, "Swahili")
        XCTAssertTrue(app.buttons["Continue"].exists)
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 5))
        for _ in 0..<3 { if paragraph.isHittable { break }; app.swipeUp() }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'Kahawa' AND label CONTAINS 'mto'"), object: paragraph)], timeout: 10), .completed)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Coffee tomorrow? I know a little place by the river."), object: paragraph)], timeout: 10), .completed)
        capture("ios-onboarding-swahili-prepared-faces")
        for _ in 0..<3 { if targetPicker.isHittable { break }; app.swipeDown() }
        let sourcePicker = app.buttons["I speak"]
        sourcePicker.tap(); app.buttons["Swahili"].tap()
        targetPicker.tap(); app.buttons["English · English"].tap()
        XCTAssertEqual(sourcePicker.value as? String, "Swahili")
        XCTAssertEqual(targetPicker.value as? String, "English")
        for _ in 0..<3 { if paragraph.isHittable { break }; app.swipeUp() }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'Coffee' AND label CONTAINS 'river'"), object: paragraph)], timeout: 10), .completed)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Kahawa kesho? Ninajua sehemu ndogo karibu na mto."), object: paragraph)], timeout: 10), .completed)
        capture("ios-onboarding-swahili-known-language-faces")
        // The former prepared full-target display button was removed. This
        // test now names the actual preview outcome, not full-text translation.
    }

    @MainActor func testOldestAndNewestMetadataActuallyGrowAndRemainReadable() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        let base = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-dark"]
        app.launchArguments = base + ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        let metadata = app.staticTexts.matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-'"))
        XCTAssertTrue(metadata.firstMatch.waitForExistence(timeout: 20))
        let normal = metadata.firstMatch.frame.height
        XCTAssertGreaterThan(normal, 0)
        app.terminate()
        app.launchArguments = base + ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(metadata.firstMatch.waitForExistence(timeout: 20))
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        XCTAssertGreaterThan(timeline.frame.height, app.frame.height * 0.5)
        let notice = app.buttons["conversation-notice"]
        XCTAssertTrue(notice.isHittable)
        notice.tap()
        let detail = app.staticTexts["conversation-notice-detail"]
        XCTAssertTrue(detail.waitForExistence(timeout: 5))
        XCTAssertTrue(detail.label.contains("Messages are saved here"))
        app.buttons["Done"].tap()
        let oldestBody = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I am reading a '")).firstMatch
        for _ in 0..<8 {
            if oldestBody.exists && oldestBody.isHittable && metadata.firstMatch.isHittable { break }
            timeline.swipeDown()
        }
        XCTAssertTrue(oldestBody.isHittable); XCTAssertTrue(metadata.firstMatch.isHittable)
        XCTAssertGreaterThan(metadata.firstMatch.frame.height, normal * 1.5)
        XCTAssertTrue(metadata.firstMatch.label.contains("Waiting to send"))
        XCTAssertGreaterThanOrEqual(metadata.firstMatch.frame.minX, timeline.frame.minX)
        XCTAssertLessThanOrEqual(metadata.firstMatch.frame.maxX, timeline.frame.maxX)
        capture("ios-largest-text-oldest-message")
        if app.buttons["conversation-latest"].exists { app.buttons["conversation-latest"].tap() }
        let newest = try XCTUnwrap(metadata.allElementsBoundByIndex.last)
        XCTAssertTrue(newest.isHittable); XCTAssertGreaterThan(newest.frame.height, normal * 1.5)
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.isHittable)
        capture("ios-largest-text-latest-message")
    }
    @MainActor func testJapaneseDirectLookupKeepsReadingBesideOriginalChatBubble() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "ja", "-vipi-appearance-light"]
        app.launchArguments += ["-vipi-density", "0.25", "-readingPace", "balanced", "-vipi-live-immersion-state", "044"]
        launchPortraitApp(app)
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        let music = app.descendants(matching: .any).matching(identifier: "immersion-word-7").firstMatch
        XCTAssertTrue(music.waitForExistence(timeout: 5))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "ongaku"), object: music)], timeout: 10), .completed)
        let before = paragraph.frame, wordBefore = music.frame
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Show original script"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "音楽"), object: music)], timeout: 10), .completed)
        XCTAssertEqual(music.frame.width, wordBefore.width, accuracy: 1)
        XCTAssertEqual(music.frame.height, wordBefore.height, accuracy: 1)
        XCTAssertEqual(music.frame.minX, wordBefore.minX, accuracy: 1)
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Show Latin letters"].tap()
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Watashi wa ongaku ga suki desu."].waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["私は音楽が好きです。"].exists)
        XCTAssertTrue(panel.staticTexts["I like music."].exists)
        capture("ios-japanese-direct-reading-and-script")
        closeTranslationPanel(panel, in: app)
        XCTAssertEqual(paragraph.frame.height, before.height, accuracy: 1)
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "I like music.")
        openMessageReadingOptions(in: app, paragraph: paragraph)
        XCTAssertFalse(app.buttons["Show original script"].exists)
    }

    @MainActor func testLongImmersedHistoryPreservesReadingAcrossAppendAndEarlierPage() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-history-qa",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-dark"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch.waitForExistence(timeout: 30))
        let timeline = app.scrollViews["conversation-timeline"].firstMatch
        let metadata = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-'"))
        func anchor() throws -> XCUIElement {
            let top = max(timeline.frame.minY, app.navigationBars.firstMatch.frame.maxY)
            return try XCTUnwrap(metadata.allElementsBoundByIndex.filter {
                $0.isHittable && $0.frame.minY >= top + 10 && $0.frame.maxY <= timeline.frame.maxY - 10
            }.min { $0.frame.minY < $1.frame.minY })
        }
        timeline.swipeDown(); timeline.swipeDown()
        XCTAssertTrue(app.buttons["conversation-latest"].waitForExistence(timeout: 5))
        let before = try anchor(), identifier = before.identifier, y = before.frame.minY
        app.buttons["timeline-qa-append"].tap()
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: identifier).firstMatch.frame.minY, y, accuracy: 3)
        let earlier = app.buttons["Earlier messages"]
        for _ in 0..<18 {
            if earlier.isHittable { break }
            timeline.swipeDown()
        }
        XCTAssertTrue(earlier.isHittable)
        let page = try anchor(), pageID = page.identifier, pageY = page.frame.minY
        earlier.tap()
        XCTAssertFalse(earlier.exists)
        let retained = app.descendants(matching: .any).matching(identifier: pageID).firstMatch
        XCTAssertTrue(retained.isHittable)
        XCTAssertEqual(retained.frame.minY, pageY, accuracy: 3)
        capture("ios-immersed-older-page-anchor")
        app.buttons["conversation-latest"].tap()
        let appended = app.staticTexts["Appended while reading earlier messages."]
        // The lazily realized row can briefly have a zero accessibility frame
        // after a long jump. Require it inside the viewport before hit testing.
        let visible = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            guard appended.exists else { return false }
            let frame = appended.frame
            return frame.height > 0 && frame.minY >= timeline.frame.minY && frame.maxY <= timeline.frame.maxY
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [visible], timeout: 3), .completed)
        XCTAssertTrue(appended.isHittable)
        XCTAssertFalse(app.buttons["conversation-latest"].exists)
        capture("ios-immersed-jump-to-latest")
    }
    @MainActor func testSwahiliOriginalCanBeReadInEnglishAndCopiedWithoutRewriting() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-learning-language-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-light"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        chooseMessageLanguage("Swahili", in: app, paragraph: paragraph)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "I like muziki."), object: paragraph)], timeout: 10), .completed)
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["I like music."].waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["Ninapenda muziki."].exists)
        closeTranslationPanel(panel, in: app)
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Original message"].tap()
        XCTAssertEqual(paragraph.label, "Ninapenda muziki.")
        openMessageReadingOptions(in: app, paragraph: paragraph); app.buttons["Word switching"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "I like muziki."), object: paragraph)], timeout: 10), .completed)
        openMessageActions(in: app, paragraph: paragraph); app.buttons["Copy original message"].tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.press(forDuration: 1.2)
        let paste = app.buttons["Paste"].exists ? app.buttons["Paste"] : app.menuItems["Paste"]
        XCTAssertTrue(paste.waitForExistence(timeout: 5)); paste.tap()
        XCTAssertEqual(input.value as? String, "Ninapenda muziki.")
        capture("ios-swahili-original-copy")
    }

    @MainActor func testVisibleImmersedRowAndPreparationNoticeAccessibility() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
                "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-" + appearance]
            app.launch()
            XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch.waitForExistence(timeout: 20))
            try app.performAccessibilityAudit()
            capture("ios-swahili-visible-row-accessibility-" + appearance)
            app.terminate()
        }
    }

    @MainActor func testLanguagePreparationReturnResumesImmersionWithoutLosingDraft() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-light"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        let options = app.buttons["conversation-options"]
        XCTAssertTrue(options.waitForExistence(timeout: 20))
        options.tap()
        app.buttons["conversation-languages"].tap()
        XCTAssertTrue(app.buttons["language-target-picker"].waitForExistence(timeout: 5))
        app.buttons["language-target-picker"].tap()
        app.buttons["Spanish · Español"].tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let spanish = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label CONTAINS 'música'")).firstMatch
        XCTAssertTrue(spanish.waitForExistence(timeout: 20))
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.typeText("Tomorrow works for me")
        // Backgrounding must stop playback/alternation and retain the draft.
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertEqual(input.value as? String, "Tomorrow works for me")
        XCTAssertTrue(app.buttons["message-send"].isEnabled)
        capture("ios-language-return-draft")
    }

    @MainActor func testImmersedConversationAccessibilityAndLargestType() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-timeline-audit",
                "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-" + appearance]
            app.launch()
            let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I like '")).firstMatch
            XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
            let composer = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
            let composerHeight = composer.frame.height
            var findings: [[String: String]] = []
            try app.performAccessibilityAudit { issue in
                findings.append(["issue":issue.compactDescription, "detail":issue.detailedDescription,
                    "identifier":issue.element?.identifier ?? "", "label":issue.element?.label ?? "",
                    "frame":issue.element.map { String(describing: $0.frame) } ?? "",
                    "hittable":issue.element.map { String($0.isHittable) } ?? ""])
                return false
            }
            XCTAssertEqual(composer.frame.height, composerHeight, accuracy: 2,
                "Returning from accessibility sizes must not leave an expanded empty composer")
            let report = XCTAttachment(data: try JSONSerialization.data(withJSONObject: findings, options: [.prettyPrinted, .sortedKeys]), uniformTypeIdentifier: "public.json")
            report.name = "chat-immersion-accessibility-" + appearance; report.lifetime = .keepAlways; add(report)
            capture("ios-swahili-accessibility-" + appearance)
            app.terminate()
        }
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let last = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I like '")).firstMatch
        XCTAssertTrue(last.waitForExistence(timeout: 20)); XCTAssertTrue(last.isHittable)
        XCTAssertGreaterThanOrEqual(last.frame.minX, app.frame.minX)
        XCTAssertLessThanOrEqual(last.frame.maxX, app.frame.maxX)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "message-input").firstMatch.isHittable)
        capture("ios-swahili-largest-text-dark")
    }
    @MainActor func testSwahiliImmersionAndDirectTranslationInActualConversationRows() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-light"]
        app.launchArguments += ["-vipi-density", "0.25", "-readingPace", "balanced", "-vipi-timeline-audit", "-vipi-live-immersion-state", "045"]
        launchPortraitApp(app)
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        let target = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label CONTAINS 'muziki'")).firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 30))
        // Match both real word faces: explicit English also permits I→mimi.
        // This identifies the same music row after earlier rows leave view.
        let musicRows = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND (label CONTAINS 'music' OR label CONTAINS 'muziki')"))
        XCTAssertEqual(musicRows.count, 1)
        let paragraph = musicRows.firstMatch
        let before = paragraph.frame
        let meaning = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == 'I like music.'")).firstMatch
        XCTAssertTrue(meaning.waitForExistence(timeout: 10))
        XCTAssertEqual(meaning.frame.height, before.height, accuracy: 1)
        capture("ios-swahili-conversation-light")
        chooseMessageLanguage("English", in: app, paragraph: paragraph)
        let panel = translateMessage(in: app, paragraph: paragraph)
        XCTAssertTrue(panel.staticTexts["Ninapenda muziki."].waitForExistence(timeout: 10))
        XCTAssertTrue(panel.staticTexts["I like music."].exists)
        capture("ios-swahili-direct-translation-light")
        closeTranslationPanel(panel, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.typeText("I am eating bread now.")
        let visible = paragraph.label
        let stable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != %@", visible), object: paragraph)
        stable.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [stable], timeout: 8), .completed)
        app.buttons["message-send"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label CONTAINS 'mkate'")).firstMatch.waitForExistence(timeout: 15))
        capture("ios-swahili-sent-immersion-light")
    }
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
