import XCTest

final class ChatImmersionTests: XCTestCase {

    @MainActor func testGatedChineseFullReadingUsesNativeDisplayAndOriginalScript() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-full-reading-qa", "-vipi-chinese-reading-qa", "-vipi-appearance-dark",
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch(); defer { app.terminate() }
        let latin = app.staticTexts["yin hang hang zhang zheng zai zou lu。"]
        XCTAssertTrue(latin.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "localTransliteration")
        capture("ios-chinese-local-full-reading")
        app.buttons["Reading options"].tap(); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["银行行长正在走路。"].waitForExistence(timeout: 5))
        capture("ios-chinese-local-original-script")
        app.buttons["Reading options"].tap(); app.buttons["Show transliteration"].tap()
        XCTAssertTrue(latin.waitForExistence(timeout: 5))
        app.buttons["Authored"].tap()
        XCTAssertTrue(app.staticTexts["Wǒ xūyào shuǐ."].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "authored")
        app.buttons["Unknown"].tap()
        XCTAssertTrue(app.staticTexts["𠮷先生与𰻞字怎么读？"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["reading-qa-provenance"].label, "unavailable")
        capture("ios-chinese-unknown-reading-abstains")
        app.buttons["Reading options"].tap()
        XCTAssertFalse(app.buttons["Show original script"].exists)
        XCTAssertFalse(app.buttons["Show transliteration"].exists)
        XCTAssertTrue(app.buttons["Copy original message"].exists)
    }

    @MainActor func testPartialLookupKeepsSwitchingAfterUnavailableWholeTranslation() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-source-unit-routing-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "0.25", "-vipi-appearance-dark", "-vipi-live-immersion-state", "016"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        // The frozen protocol explicitly chooses English. ML Kit language ID
        // has no simulator binary, so use the real message-language action;
        // do not inject a classifier or infer direction from a lexical hit.
        let options = app.buttons["Reading options"].firstMatch
        XCTAssertTrue(options.waitForExistence(timeout: 20)); options.tap()
        app.buttons["Message language"].tap(); app.buttons["English"].tap()
        let paragraph = app.descendants(matching: .any).matching(identifier: "immersionText").firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        XCTAssertTrue(paragraph.label.contains("Did you finish the report?"))
        let slot = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'immersion-word-'")).firstMatch
        XCTAssertTrue(slot.exists)
        let bounds = slot.frame
        app.buttons["Reading options"].firstMatch.tap()
        let full = app.buttons["Swahili"]
        XCTAssertTrue(full.waitForExistence(timeout: 5)); full.tap()
        let error = app.descendants(matching: .any).matching(identifier: "full-translation-error").firstMatch
        XCTAssertTrue(error.waitForExistence(timeout: 10))
        XCTAssertFalse(error.buttons["Try again"].exists)
        XCTAssertFalse(error.buttons["Prepare languages"].exists)
        XCTAssertTrue(app.staticTexts["Full translation for this language pair isn’t supported on this device. Your message stays here."].exists)
        XCTAssertTrue(paragraph.label.contains("Did you finish the report?"))
        capture("ios-partial-whole-reference-unavailable")
        // Observe the native attachment throughout several real clock phases;
        // retained error text must not turn continuous immersion into tap-only UI.
        var samples: [[String: Any]] = [], transitions = 0
        var previous: String?
        let start = Date()
        while Date().timeIntervalSince(start) < 29 {
            let label = slot.label
            let frame = slot.frame
            // UIKit replaces the accessibility attachment on each face change.
            // A query racing that replacement may have no label/frame; retain
            // that observation without counting it as a language transition.
            let complete = ["I need water.", "Ninahitaji maji."].contains(label) && frame.height > 0
            if complete {
                if let previous, label != previous { transitions += 1 }
                previous = label
                XCTAssertEqual(frame.width, bounds.width, accuracy: 1)
                XCTAssertEqual(frame.height, bounds.height, accuracy: 1)
            }
            samples.append(["seconds": Date().timeIntervalSince(start), "label": label,
                "width": frame.width, "height": frame.height, "complete_accessibility_snapshot": complete])
            Thread.sleep(forTimeInterval: 0.3)
        }
        XCTAssertGreaterThanOrEqual(transitions, 6)
        XCTAssertTrue(paragraph.label.contains("Did you finish the report?"))
        app.buttons["Reading options"].firstMatch.tap()
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["I need water. Did you finish the report?"].waitForExistence(timeout: 5))
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
        func face(_ label: String) -> XCUIElement {
            app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == %@", label)).firstMatch
        }
        let target = face("Asante sana.")
        XCTAssertTrue(target.waitForExistence(timeout: 20))
        let bounds = target.frame
        XCTAssertGreaterThanOrEqual(bounds.minX, app.frame.minX)
        XCTAssertLessThanOrEqual(bounds.maxX, app.frame.maxX)
        capture("ios-greeting-largest-target")
        let original = face("Thank you very much.")
        XCTAssertTrue(original.waitForExistence(timeout: 10))
        XCTAssertEqual(original.frame.height, bounds.height, accuracy: 1)
        XCTAssertEqual(original.frame.minY, bounds.minY, accuracy: 1)
        capture("ios-greeting-largest-original")
        app.buttons["Reading options"].tap(); app.buttons["Swahili"].tap()
        XCTAssertTrue(app.staticTexts["Asante sana."].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap(); app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["Thank you very much."].waitForExistence(timeout: 5))
    }
    @MainActor func testZeroDensityKeepsLanguageViewsWithoutInactiveWordActions() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "sw", "-vipi-density", "0", "-vipi-appearance-light"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup", "-vipi-density", "0.25"]; app.launch() }
        let menu = app.buttons["Reading options"]
        XCTAssertTrue(menu.waitForExistence(timeout: 20)); menu.tap()
        for title in ["Pause word switching", "Switching pace", "Show meanings now"] {
            XCTAssertFalse(app.buttons[title].exists)
        }
        XCTAssertTrue(app.buttons["Copy original message"].exists)
        app.buttons["Swahili"].tap()
        XCTAssertTrue(app.staticTexts["Ninapenda muziki."].waitForExistence(timeout: 5))
        capture("ios-zero-vocabulary-whole-translation")
        menu.tap(); app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["I like music."].waitForExistence(timeout: 5))
    }
    @MainActor func testExpandedRequestReadingsInAllFourNonRomanLanguagesAtLargestText() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch() }
        let cases = [
            ("ar", "Arabic", "Aḥtāj ilā shāḥin hātif.", "أحتاج إلى شاحن هاتف."),
            ("zh", "Chinese", "Wǒ xūyào yí ge shǒujī chōngdiànqì.", "我需要一个手机充电器。"),
            ("ja", "Japanese", "Keitai denwa no jūdenki ga hitsuyō desu.", "携帯電話の充電器が必要です。"),
            ("ko", "Korean", "Hyudaepon chungjeongiga piryohaeyo.", "휴대폰 충전기가 필요해요.")
        ]
        for (code, name, latin, native) in cases {
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-request-qa", "-vipi-timeline-audit",
                "-vipi-source", "en", "-vipi-target", code, "-vipi-appearance-light",
                "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            let menu = app.buttons["Reading options"]
            XCTAssertTrue(menu.waitForExistence(timeout: 20)); menu.tap(); app.buttons[name].tap()
            let reading = app.staticTexts[latin]
            XCTAssertTrue(reading.waitForExistence(timeout: 10)); XCTAssertTrue(reading.isHittable)
            XCTAssertGreaterThanOrEqual(reading.frame.minX, app.frame.minX)
            XCTAssertLessThanOrEqual(reading.frame.maxX, app.frame.maxX)
            capture("ios-request-reading-largest-" + code)
            menu.tap()
            XCTAssertFalse(app.buttons["Pause word switching"].exists)
            XCTAssertFalse(app.buttons["Switching pace"].exists)
            app.buttons["Show original script"].tap()
            XCTAssertTrue(app.staticTexts[native].waitForExistence(timeout: 5))
            menu.tap(); app.buttons["English"].tap()
            XCTAssertTrue(app.staticTexts["I need a phone charger."].waitForExistence(timeout: 5))
            if code == "ar" {
                menu.tap(); app.buttons["Immersed"].tap()
                for label in ["Relaxed", "Balanced"] {
                    menu.tap()
                    let pace = app.buttons["Switching pace"]
                    XCTAssertTrue(pace.isHittable)
                    pace.tap()
                    XCTAssertTrue(app.buttons[label].waitForExistence(timeout: 5))
                    capture("ios-request-pace-largest-" + label.lowercased())
                    app.buttons[label].tap()
                }
            }
            app.terminate()
        }
    }
    @MainActor func testOnboardingSelectsSwahiliAndShowsWholeThoughtInBothDirections() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-language", "-vipi-source", "en", "-vipi-target", "es", "-vipi-appearance-light"]
        app.launch()
        defer { app.terminate(); app.launchArguments = ["-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es"]; app.launch() }
        let targetPicker = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'I want to pick up'")).firstMatch
        XCTAssertTrue(targetPicker.waitForExistence(timeout: 15)); targetPicker.tap()
        app.buttons["Swahili · Kiswahili"].tap()
        XCTAssertTrue(app.buttons["Continue with Swahili"].waitForExistence(timeout: 5))
        let whole = app.buttons["See the whole thought in Swahili"]
        for _ in 0..<3 {
            if whole.isHittable && whole.frame.maxY < app.buttons["Continue with Swahili"].frame.minY - 24 { break }
            app.scrollViews.firstMatch.swipeUp()
        }
        whole.tap()
        XCTAssertTrue(app.staticTexts["Kahawa kesho? Ninajua sehemu ndogo karibu na mto."].waitForExistence(timeout: 5))
        capture("ios-onboarding-swahili-whole-thought")
        app.buttons["Back to immersion"].tap()
        for _ in 0..<3 { if targetPicker.isHittable { break }; app.swipeDown() }
        let sourcePicker = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'I already speak'")).firstMatch
        sourcePicker.tap(); app.buttons["Swahili"].tap()
        targetPicker.tap(); app.buttons["English · English"].tap()
        XCTAssertTrue(app.buttons["Continue with English"].waitForExistence(timeout: 5))
        let reverseWhole = app.buttons["See the whole thought in English"]
        for _ in 0..<3 {
            if reverseWhole.isHittable && reverseWhole.frame.maxY < app.buttons["Continue with English"].frame.minY - 24 { break }
            app.scrollViews.firstMatch.swipeUp()
        }
        reverseWhole.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? I know a little place by the river."].waitForExistence(timeout: 5))
        capture("ios-onboarding-swahili-known-language")
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
    @MainActor func testJapaneseWholeReadingAndScriptUseTheSameChatBubble() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-immersion-single-qa", "-vipi-timeline-audit",
            "-vipi-source", "en", "-vipi-target", "ja", "-vipi-appearance-light"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == 'I like ongaku.'")).firstMatch.waitForExistence(timeout: 20))
        app.buttons["Reading options"].tap(); app.buttons["Japanese"].tap()
        XCTAssertTrue(app.staticTexts["Watashi wa ongaku ga suki desu."].waitForExistence(timeout: 5))
        capture("ios-japanese-whole-reading")
        app.buttons["Reading options"].tap(); app.buttons["Show original script"].tap()
        XCTAssertTrue(app.staticTexts["私は音楽が好きです。"].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap(); app.buttons["Show transliteration"].tap()
        XCTAssertTrue(app.staticTexts["Watashi wa ongaku ga suki desu."].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap(); app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["I like music."].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap()
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
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        let immersed = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == 'I like muziki.'")).firstMatch
        XCTAssertTrue(immersed.waitForExistence(timeout: 20))
        app.buttons["Reading options"].tap(); app.buttons["English"].tap()
        XCTAssertTrue(app.staticTexts["I like music."].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap(); app.buttons["Swahili"].tap()
        XCTAssertTrue(app.staticTexts["Ninapenda muziki."].waitForExistence(timeout: 5))
        app.buttons["Reading options"].tap(); app.buttons["Immersed"].tap()
        app.buttons["Reading options"].tap(); app.buttons["Message language"].tap()
        app.buttons["Swahili"].tap()
        XCTAssertTrue(immersed.waitForExistence(timeout: 10))
        app.buttons["Reading options"].tap(); app.buttons["Copy original message"].tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        input.tap(); input.press(forDuration: 1.2)
        let paste = app.buttons["Paste"].exists ? app.buttons["Paste"] : app.menuItems["Paste"]
        XCTAssertTrue(paste.waitForExistence(timeout: 5)); paste.tap()
        XCTAssertEqual(input.value as? String, "Ninapenda muziki.")
        capture("ios-swahili-original-copy")
    }
    // A single row and the preparation notice remain in the viewport at all
    // audited sizes. The separate full-history audit stays unfiltered too.
    // This distinguishes an actual font failure from nodes moving offscreen.
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
    @MainActor func testSwahiliImmersionAndFullTranslationInActualConversationRows() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-immersion-chat-qa", "-vipi-source", "en", "-vipi-target", "sw", "-vipi-appearance-light"]
        app.launch()
        defer {
            app.terminate(); app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]; app.launch()
        }
        let target = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label CONTAINS 'muziki'")).firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 30))
        // Stable semantic identity survives the first row leaving the viewport
        // when the keyboard appears; a positional index does not.
        let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I like '")).firstMatch
        let before = paragraph.frame
        let meaning = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == 'I like music.'")).firstMatch
        XCTAssertTrue(meaning.waitForExistence(timeout: 10))
        XCTAssertEqual(meaning.frame.height, before.height, accuracy: 1)
        capture("ios-swahili-conversation-light")
        let menu = app.buttons.matching(NSPredicate(format: "label == %@", "Reading options")).allElementsBoundByIndex.last!
        menu.tap()
        app.buttons["Swahili"].tap()
        XCTAssertTrue(app.staticTexts["Ninapenda muziki."].waitForExistence(timeout: 5))
        capture("ios-swahili-whole-translation-light")
        app.buttons.matching(NSPredicate(format: "label == %@", "Reading options")).allElementsBoundByIndex.last!.tap()
        app.buttons["Immersed"].tap()
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
