import XCTest
import UIKit
import Vision
import ImageIO

/// Actual VipiApp deletion gate and ConnectedChatRoot ownership, with only
/// DEBUG dependency construction and synthetic service responses supplied.
@MainActor final class ConnectedDeletionRootTests: XCTestCase {
    func testActualSettingsCancelLostReceiptRelaunchScopedEraseAndLateBotDisposal() throws {
        guard ProcessInfo.processInfo.environment["VIPI_STARTER_ROUTE_UI"] == "true" else { throw XCTSkip("Owned isolated deletion-root qualification only") }
        continueAfterFailure = false
        let app = XCUIApplication()
        let arguments = ["-vipi-deletion-root-qa", "-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es", "-vipi-density", "0", "-vipi-appearance-light"]
        app.launchArguments = arguments
        launchPortraitApp(app)
        addTeardownBlock { @MainActor in
            app.terminate()
            app.launchArguments = arguments + ["-vipi-deletion-root-cleanup"]
            app.launch()
            XCTAssertTrue(app.buttons["Choose languages"].waitForExistence(timeout: 10), "Owned fixture cleanup must leave the actual signed-out onboarding route")
            app.terminate()
        }
        let metadata = app.staticTexts["deletion-root-qa-proof"]
        XCTAssertTrue(metadata.waitForExistence(timeout: 20))
        func read() -> [String: Any] {
            guard metadata.exists, let data = metadata.label.data(using: .utf8),
                  let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return [:] }
            return value
        }
        func observe(_ name: String, _ predicate: @escaping ([String: Any]) -> Bool) -> [String: Any] {
            let expected = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in predicate(read()) }, object: metadata)
            XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 12), .completed, name)
            let value = read()
            let data = (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data()
            let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
            attachment.name = "connected-deletion-" + name; attachment.lifetime = .keepAlways; add(attachment)
            XCTAssertEqual(value["unexpected_requests"] as? Int, 0)
            XCTAssertEqual(value["fixture_failure"] as? Bool, false)
            XCTAssertEqual(value["other_marker"] as? Bool, true)
            XCTAssertEqual(value["other_key_unchanged"] as? Bool, true)
            XCTAssertEqual(value["other_profile_unchanged"] as? Bool, true)
            XCTAssertEqual(value["late_disk_replies"] as? Int, 0)
            XCTAssertEqual(value["late_memory_replies"] as? Int, 0)
            return value
        }
        func capture(_ name: String) {
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "connected-deletion-" + name; attachment.lifetime = .keepAlways; add(attachment)
        }
        let initial = observe("actual-connected-root-ready") {
            ($0["chat_creations"] as? Int ?? 0) > 0 && ($0["store_creations"] as? Int ?? 0) > 0 &&
                ($0["seeded_bot_owners"] as? Int ?? 0) > 0 && $0["own_marker"] as? Bool == true && $0["session_key_present"] as? Bool == true
        }
        XCTAssertEqual(initial["starts"] as? Int, 1)
        XCTAssertEqual(initial["receipt_present"] as? Bool, false)
        XCTAssertEqual(initial["auth_signed_out"] as? Bool, false)
        XCTAssertTrue(app.staticTexts["Chats"].exists)
        let botEntry = app.buttons.matching(NSPredicate(format: "label CONTAINS 'vBot'"))
        XCTAssertEqual(botEntry.count, 1); XCTAssertTrue(botEntry.firstMatch.isHittable); botEntry.firstMatch.tap()
        let agree = app.buttons["Agree and start chatting"]
        XCTAssertTrue(agree.waitForExistence(timeout: 10)); agree.tap()
        let input = app.descendants(matching: .any).matching(identifier: "bot-message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 10)); input.tap()
        input.typeText("Hold this reply while I review deletion.")
        let send = app.buttons["bot-message-send"]
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: send)], timeout: 10), .completed)
        send.tap()
        let held = observe("actual-native-bot-post-held") { $0["bot_posts"] as? Int == 1 && $0["bot_pending"] as? Bool == true }
        let originalRows = try XCTUnwrap(held["bot_row_ids"] as? [String]); XCTAssertEqual(originalRows.count, 1)
        app.navigationBars["vBot"].buttons["Back"].tap()
        XCTAssertTrue(app.staticTexts["Chats"].waitForExistence(timeout: 5))
        app.buttons["Your profile and settings"].tap()
        let deletionLink = app.buttons["Delete Vipi account"]
        for _ in 0..<5 {
            if deletionLink.exists && deletionLink.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(deletionLink.exists && deletionLink.isHittable); deletionLink.tap()
        let delete = app.buttons["delete-account"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5)); delete.tap()
        let confirm = app.alerts["Delete your Vipi account?"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5)); confirm.buttons["Cancel"].tap()
        let cancelled = observe("settings-cancel-preserves-live-owners-and-data") {
            $0["submissions"] as? Int == 0 && $0["receipt_present"] as? Bool == false &&
                $0["session_key_present"] as? Bool == true && $0["own_marker"] as? Bool == true &&
                $0["bot_pending"] as? Bool == true && $0["all_bot_owners_closed"] as? Bool == false
        }
        XCTAssertEqual(cancelled["bot_row_ids"] as? [String], originalRows)
        XCTAssertEqual(cancelled["auth_signed_out"] as? Bool, false)
        XCTAssertGreaterThan(cancelled["open_chat_owners"] as? Int ?? 0, 0)
        capture("cancel-keeps-session-encrypted-data-and-pending-bot")
        delete.tap(); XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.buttons["Delete Vipi account"].tap()
        let uncertain = observe("accepted-lost-response-persists-real-receipt-and-disposes-owners") {
            $0["submissions"] as? Int == 1 && $0["server_accepted"] as? Bool == true &&
                $0["phase"] as? String == "prepared" && $0["receipt_matches_owner"] as? Bool == true &&
                $0["late_results"] as? Int == 1 && $0["busy_bot_sessions"] as? Int == 0 &&
                $0["all_bot_owners_closed"] as? Bool == true && $0["open_chat_owners"] as? Int == 0
        }
        XCTAssertEqual(uncertain["bot_row_ids"] as? [String], originalRows)
        XCTAssertEqual(uncertain["own_marker"] as? Bool, true, "Unconfirmed response must not erase local data")
        XCTAssertEqual(uncertain["session_key_present"] as? Bool, true)
        XCTAssertEqual(uncertain["local_erased"] as? Bool, false)
        XCTAssertTrue(app.buttons["Continue deletion"].exists)
        XCTAssertFalse(app.buttons["New chat"].exists)
        capture("lost-response-actual-deletion-root")

        // Real process relaunch: same keychain capability, vaults and fake
        // server disk ledger. The fixture never selects the recovery view.
        app.terminate(); app.launchArguments = arguments; app.launch()
        XCTAssertTrue(metadata.waitForExistence(timeout: 15))
        let recovered = observe("fresh-app-owner-enters-only-deletion-recovery-and-erases-scope") {
            $0["starts"] as? Int == 2 && $0["phase"] as? String == "requested" &&
                $0["local_erased"] as? Bool == true && $0["auth_signed_out"] as? Bool == true
        }
        XCTAssertEqual(recovered["chat_creations"] as? Int, initial["chat_creations"] as? Int)
        XCTAssertEqual(recovered["store_creations"] as? Int, initial["store_creations"] as? Int)
        XCTAssertEqual(recovered["seeded_bot_owners"] as? Int, initial["seeded_bot_owners"] as? Int)
        XCTAssertEqual(recovered["submissions"] as? Int, 1, "Recovery must check status without another DELETE")
        for key in ["own_key", "own_directory", "own_profile", "own_marker", "session_key_present"] { XCTAssertEqual(recovered[key] as? Bool, false, key) }
        XCTAssertTrue(app.staticTexts["Deletion requested"].exists)
        XCTAssertFalse(app.staticTexts["Chats"].exists); XCTAssertFalse(app.buttons["New chat"].exists)
        XCTAssertFalse(app.buttons["Your profile and settings"].exists)
        capture("fresh-process-deletion-only-other-account-preserved")
        app.buttons["Check status"].tap()
        _ = observe("status-confirmed-complete") { $0["phase"] as? String == "completed" && $0["local_erased"] as? Bool == true && $0["submissions"] as? Int == 1 }
        let done = app.buttons["Done"]
        XCTAssertTrue(done.waitForExistence(timeout: 5)); done.tap()
        XCTAssertTrue(app.buttons["Choose languages"].waitForExistence(timeout: 10))
        let finished = observe("done-actual-signed-out-onboarding") {
            $0["receipt_present"] as? Bool == false && $0["auth_signed_out"] as? Bool == true && $0["session_key_present"] as? Bool == false
        }
        for key in ["own_key", "own_directory", "own_profile", "own_marker"] { XCTAssertEqual(finished[key] as? Bool, false, key) }
        XCTAssertEqual(finished["submissions"] as? Int, 1); XCTAssertEqual(finished["bot_posts"] as? Int, 1)
        XCTAssertEqual(finished["late_results"] as? Int, 1)
        capture("done-signed-out-with-no-vault-resurrection")
    }
}

@MainActor
final class ChatConversationTests: XCTestCase {
    /// The existing preview route renders the actual NewChatView with no chat
    /// session. Find therefore returns a local error without any API/account.
    func testPreviewFriendLookupKeepsControlsAboveKeyboardAndCancelReturnsHome() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-preview-home", "-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch(); defer { app.terminate() }
        let newChat = app.buttons["New chat"]
        XCTAssertTrue(newChat.waitForExistence(timeout: 15)); newChat.tap()
        let username = app.textFields["Friend’s username"]
        XCTAssertTrue(username.waitForExistence(timeout: 5)); username.tap(); username.typeText("vqa_keyboard_probe")
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5), "A hardware-keyboard-only run cannot prove software keyboard clearance")
        let find = app.buttons["Find friend"], cancel = app.buttons["Cancel"]
        let navigation = app.navigationBars["New conversation"]
        XCTAssertTrue(navigation.exists); XCTAssertGreaterThan(navigation.frame.height, 0)
        func requireVisible(_ control: XCUIElement, belowNavigation: Bool = true) {
            XCTAssertTrue(control.exists); XCTAssertTrue(control.isHittable)
            XCTAssertGreaterThan(control.frame.width, 0); XCTAssertGreaterThan(control.frame.height, 0)
            XCTAssertTrue(app.frame.contains(control.frame), "Control must fit entirely on screen: \(control.label)")
            XCTAssertLessThanOrEqual(control.frame.maxY, keyboard.frame.minY + 1, "Keyboard must not cover \(control.label)")
            if belowNavigation { XCTAssertGreaterThanOrEqual(control.frame.minY, navigation.frame.maxY - 1) }
        }
        requireVisible(username); requireVisible(find); requireVisible(cancel, belowNavigation: false)
        capture("ios-preview-friend-lookup-keyboard")
        find.tap()
        let error = app.staticTexts["Sign in to find your friends."]
        XCTAssertTrue(error.waitForExistence(timeout: 5)); XCTAssertTrue(keyboard.exists)
        capture("ios-preview-friend-lookup-local-error-keyboard")
        requireVisible(username); requireVisible(find); requireVisible(error); requireVisible(cancel, belowNavigation: false)
        let geometry: [String: Any] = Dictionary(uniqueKeysWithValues: [("screen", app), ("keyboard", keyboard), ("username", username), ("find", find), ("error", error), ("cancel", cancel)].map { name, element in
            let frame = element.frame
            return (name, ["x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height), "hittable": element.isHittable] as [String: Any])
        })
        let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
        attachment.name = "friend-lookup-keyboard-geometry"; attachment.lifetime = .keepAlways; add(attachment)
        cancel.tap()
        XCTAssertTrue(newChat.waitForExistence(timeout: 5)); XCTAssertTrue(newChat.isHittable)
        XCTAssertTrue(app.staticTexts["Chats"].exists)
        XCTAssertFalse(username.exists); XCTAssertFalse(error.exists)
        capture("ios-preview-friend-lookup-cancel-restores-home")
    }
    /// Production HomeView owns every navigation step. The existing guarded
    /// timeline fixture supplies only synthetic service/Signal/account state.
    /// This does not qualify hosted auth or the outer ConnectedChatRoot router.
    func testExpiredBaseUsesActualSettingsPlansAndKeepsQueuedMessageAndDraft() throws {
        guard ProcessInfo.processInfo.environment["VIPI_STARTER_ROUTE_UI"] == "true" else { throw XCTSkip("Owned isolated client expiry qualification only") }
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-timeline-qa", "-vipi-base-expiry-qa", "-vipi-appearance-light", "-vipi-source", "en", "-vipi-target", "es", "-vipi-density", "0"]
        launchPortraitApp(app)
        addTeardownBlock { @MainActor in
            app.terminate()
            app.launchArguments = ["-vipi-timeline-qa", "-vipi-timeline-cleanup"]
            app.launch()
            XCTAssertTrue(app.staticTexts["Synthetic conversation removed"].waitForExistence(timeout: 10), "Remove only this fixture's recorded synthetic account/peer resources")
            app.terminate()
        }
        let evidence = app.staticTexts["base-expiry-qa-proof"]
        XCTAssertTrue(evidence.waitForExistence(timeout: 20))
        func proof() -> [String: Any] {
            guard evidence.exists, let bytes = evidence.label.data(using: .utf8),
                  let result = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { return [:] }
            return result
        }
        func observe(_ phase: String, _ predicate: @escaping ([String: Any]) -> Bool) -> [String: Any] {
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in predicate(proof()) }, object: evidence)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed, phase)
            let result = proof()
            let bytes = (try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])) ?? Data()
            let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: "public.json")
            attachment.name = "base-expiry-" + phase; attachment.lifetime = .keepAlways; add(attachment)
            XCTAssertEqual(result["unexpected_requests"] as? Int, 0)
            XCTAssertEqual(result["purchase_ready"] as? Bool, false)
            XCTAssertEqual(result["bot_active"] as? Bool, false)
            return result
        }
        _ = observe("initial-cardless-access") {
            $0["base_active"] as? Bool == true && $0["setup_decryptions"] as? Int == 1 && $0["rows"] as? Int == 1
        }
        let friend = app.staticTexts["Alex"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 10)); friend.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 10)); input.tap()
        let attempted = "Keep this message when my free access ends."
        let nextDraft = "Keep my next unsent draft too."
        input.typeText(attempted)
        let send = app.buttons["message-send"]
        XCTAssertTrue(send.isEnabled); send.tap()
        let refused = observe("server-refuses-expired-send") {
            ($0["expired_posts"] as? Int ?? 0) >= 1 && $0["queued_count"] as? Int == 1 && $0["queued_text"] as? String == attempted
        }
        let originalID = try XCTUnwrap(refused["queued_id"] as? String)
        XCTAssertNotNil(UUID(uuidString: originalID))
        XCTAssertEqual(refused["expired_ids"] as? [String], [originalID])
        XCTAssertEqual(input.value as? String, "")
        input.typeText(nextDraft)
        XCTAssertEqual(input.value as? String, nextDraft)
        _ = observe("draft-committed-after-refusal") { $0["draft"] as? String == nextDraft }
        let notice = app.buttons["conversation-notice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 10)); notice.tap()
        let explanation = app.staticTexts["conversation-notice-detail"]
        XCTAssertTrue(explanation.waitForExistence(timeout: 5))
        XCTAssertEqual(explanation.label, "Start or restore your Vipi plan in Settings → Subscriptions to send messages. Your saved chats and drafts remain available.")
        capture("ios-expired-base-real-message-status")
        app.navigationBars["Message status"].buttons["Done"].tap()
        app.navigationBars["Alex"].buttons["Back"].tap()
        XCTAssertTrue(app.staticTexts["Chats"].waitForExistence(timeout: 5))
        app.buttons["Your profile and settings"].tap()
        let subscriptions = app.buttons["Subscriptions"]
        for _ in 0..<4 where !subscriptions.isHittable { app.swipeUp() }
        XCTAssertTrue(subscriptions.exists && subscriptions.isHittable); subscriptions.tap()
        let base = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Vipi' AND label CONTAINS 'See plan'")).firstMatch
        XCTAssertTrue(base.waitForExistence(timeout: 15))
        let bot = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Bot mini' AND label CONTAINS 'See plan'")).firstMatch
        XCTAssertTrue(bot.exists, "Bot mini stays separate from the expired Base period")
        base.tap()
        let ended = app.staticTexts["Your free Vipi access has ended. Subscribe to continue chatting."]
        XCTAssertTrue(ended.waitForExistence(timeout: 15))
        _ = observe("actual-base-plan-after-expiry") { $0["base_active"] as? Bool == false && $0["rows"] as? Int == 2 && $0["draft"] as? String == nextDraft }
        let checkout = app.buttons["subscription-purchase-vipi.base.annual"]
        if checkout.exists { XCTAssertFalse(checkout.isEnabled, "Unready service cannot authorize checkout") }
        capture("ios-expired-base-real-plan-no-enrollment")
        app.navigationBars["Vipi"].buttons["Subscriptions"].tap()
        app.navigationBars["Subscriptions"].buttons["Settings"].tap()
        app.navigationBars["Settings"].buttons["Back"].tap()
        XCTAssertTrue(friend.waitForExistence(timeout: 5)); friend.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, nextDraft)
        let final = observe("returned-durable-queued-text-and-next-draft") {
            $0["queued_id"] as? String == originalID && $0["queued_text"] as? String == attempted &&
                $0["draft"] as? String == nextDraft && $0["queued_count"] as? Int == 1 && $0["rows"] as? Int == 2
        }
        XCTAssertEqual(final["expired_ids"] as? [String], [originalID], "Foreground retries must retain the original message identity")
        XCTAssertEqual(final["setup_decryptions"] as? Int, 1, "No expired message was delivered to the synthetic peer")
        let queued = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label == %@", attempted)).firstMatch
        XCTAssertTrue(queued.exists && queued.isHittable, "Queued plaintext remains readable in the actual conversation")
        capture("ios-expired-base-returned-original-row-and-next-draft")
    }

    func testObserveExistingImmersionThroughComposerAndSpeech() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned native session required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-vipi-live-immersion-state", "010"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I need ' AND label CONTAINS 'I like '")).firstMatch
        XCTAssertTrue(paragraph.waitForExistence(timeout: 20))
        var observations: [[String: Any]] = []
        defer {
            if let data = try? JSONSerialization.data(withJSONObject: observations, options: [.sortedKeys]) {
                let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
                attachment.name = "live-state-visible-phases"; attachment.lifetime = .keepAlways; add(attachment)
            }
        }
        func observe(_ stage: String, seconds: Double) {
            print("VIPI_LIVE_STATE_STAGE " + stage)
            let deadline = Date().addingTimeInterval(seconds); var previous = ""
            while Date() < deadline {
                let text = paragraph.label, frame = paragraph.frame
                observations.append(["stage": stage, "at": Date().timeIntervalSince1970, "text": text,
                    "x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height)])
                if text != previous { capture("live-state-" + stage + "-" + String(observations.count)); previous = text }
                Thread.sleep(forTimeInterval: 0.7)
            }
        }
        observe("before-composer", seconds: 20)
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.exists); input.tap()
        observe("empty-composer-focused", seconds: 25)
        input.typeText("x")
        observe("draft-nonempty", seconds: 5)
        input.typeText(XCUIKeyboardKey.delete.rawValue)
        observe("draft-cleared-still-focused", seconds: 25)
        let frame = paragraph.frame
        let actions = app.buttons.matching(identifier: "messageListen").allElementsBoundByIndex
            .filter { $0.frame.minY >= frame.maxY - 1 && $0.frame.minY < frame.maxY + 85 }
            .min { $0.frame.minY < $1.frame.minY }
        let control = try XCTUnwrap(actions)
        XCTAssertEqual(control.label, "Play message")
        XCTAssertTrue(control.isEnabled && control.isHittable)
        control.tap()
        observe("after-listen", seconds: 25)
        for stage in ["before-composer", "empty-composer-focused", "draft-cleared-still-focused", "after-listen"] {
            let labels = observations.filter { $0["stage"] as? String == stage }.compactMap { $0["text"] as? String }
            let transitions = zip(labels, labels.dropFirst()).filter { $0 != $1 }.count
            XCTAssertGreaterThanOrEqual(transitions, 3, "Continuous switching must resume in " + stage)
        }
        let drafting = observations.filter { $0["stage"] as? String == "draft-nonempty" }.compactMap { $0["text"] as? String }
        XCTAssertLessThanOrEqual(Set(drafting).count, 1, "Active composition keeps words still")
    }
    func testLiveSwahiliImmersionConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              ProcessInfo.processInfo.environment["VIPI_QA_LIVE_SW"] == "4ccee4cd1b9e79a60e018902af278e85bc34377c75162eef066960b6aa4d0e6e" else {
            throw XCTSkip("Frozen eight-turn protocol and owned peer required")
        }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        app.buttons["language-settings-link"].tap()
        app.buttons["language-source-picker"].tap()
        XCTAssertTrue(app.buttons["English"].waitForExistence(timeout: 10)); app.buttons["English"].tap()
        app.buttons["language-target-picker"].tap()
        let swahili = app.buttons["Swahili · Kiswahili"]
        for _ in 0..<4 { if swahili.exists && swahili.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(swahili.exists); swahili.tap()
        capture("live-sw-selected-language-availability")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 15)); friend.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        let incoming = ["I need water.", "Can you meet me after work?", "Do you want to listen to some music?", "Let's have lunch tomorrow."]
        let outgoing = ["I am drinking coffee now.", "I will be home in twenty minutes.", "I like music.", "That sounds good. See you soon."]
        print("VIPI_LIVE_SW_RECEIVER_READY " + ISO8601DateFormatter().string(from: Date()))
        for index in 0..<incoming.count {
            let original = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", incoming[index])).firstMatch
            XCTAssertTrue(original.waitForExistence(timeout: 150), "Original source face must remain recoverable without a tap")
            print("VIPI_LIVE_SW_RECEIVED_\(index * 2 + 1) " + ISO8601DateFormatter().string(from: Date()))
            capture("live-sw-received-\(index * 2 + 1)")
            if index == 0 {
                let paragraph = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'immersionText' AND label BEGINSWITH 'I need '")).firstMatch
                XCTAssertTrue(paragraph.waitForExistence(timeout: 15))
                var samples: [[String: Any]] = [], previous = "", transitions = 0
                let deadline = Date().addingTimeInterval(29)
                while Date() < deadline {
                    let label = paragraph.label, frame = paragraph.frame
                    if label != previous {
                        if !previous.isEmpty { transitions += 1 }
                        capture("live-sw-water-phase-\(transitions)"); previous = label
                    }
                    samples.append(["at": Date().timeIntervalSince1970, "label": label,
                                    "x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width), "height": Double(frame.height)])
                    Thread.sleep(forTimeInterval: 0.65)
                }
                let evidence = XCTAttachment(data: try JSONSerialization.data(withJSONObject: samples, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
                evidence.name = "live-sw-three-cycle-geometry"; evidence.lifetime = .keepAlways; add(evidence)
                XCTAssertGreaterThanOrEqual(transitions, 6)
                XCTAssertTrue(samples.contains { ($0["label"] as? String)?.contains("maji") == true })
                XCTAssertTrue(samples.contains { $0["label"] as? String == incoming[0] })
                let widths = samples.compactMap { $0["width"] as? Double }, heights = samples.compactMap { $0["height"] as? Double }
                XCTAssertLessThan((widths.max() ?? 0) - (widths.min() ?? 0), 0.5)
                XCTAssertLessThan((heights.max() ?? 0) - (heights.min() ?? 0), 0.5)
                // Use the direct speaker belonging to this incoming paragraph.
                // No word tap changes the currently visible speech faces.
                let frame = paragraph.frame
                let action = try XCTUnwrap(app.buttons.matching(identifier: "messageListen").allElementsBoundByIndex
                    .filter { $0.frame.minY >= frame.maxY - 1 && $0.frame.minY < frame.maxY + 85 }
                    .min { $0.frame.minY < $1.frame.minY })
                XCTAssertEqual(action.label, "Play message")
                XCTAssertTrue(action.isEnabled && action.isHittable)
                action.tap()
                capture("live-sw-water-native-listen")
                Thread.sleep(forTimeInterval: 5)
            }
            input.tap(); input.typeText(outgoing[index]); app.buttons["message-send"].tap()
            print("VIPI_LIVE_SW_SENT_\(index * 2 + 2) " + ISO8601DateFormatter().string(from: Date()))
            capture("live-sw-sent-\(index * 2 + 2)")
        }
        print("VIPI_LIVE_SW_EXCHANGE_COMPLETE " + ISO8601DateFormatter().string(from: Date()))
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "live-sw-final-accessibility"; tree.lifetime = .keepAlways; add(tree)
    }
    func testForegroundExchangeWithoutRefresh() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              let sent = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_SEND"],
              let expected = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_TEXT"],
              sent.hasPrefix("Foreground iOS to Android "), expected.hasPrefix("Foreground Android to iOS "),
              sent.count < 160, expected.count < 160 else { throw XCTSkip("Fresh owned-account exchange required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts[sent].exists); XCTAssertFalse(app.staticTexts[expected].exists)
        let metadata = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-'"))
        let previousIDs = metadata.allElementsBoundByIndex.map { $0.identifier }
        input.tap(); input.typeText(sent); app.buttons["message-send"].tap()
        print("VIPI_FOREGROUND_SENT " + ISO8601DateFormatter().string(from: Date()))
        XCTAssertTrue(app.staticTexts[sent].waitForExistence(timeout: 15))
        capture("foreground-new-outgoing-message")
        print("VIPI_FOREGROUND_RECEIVER_READY")
        // No refresh, lifecycle change, navigation or subsequent local send.
        XCTAssertTrue(app.staticTexts[expected].waitForExistence(timeout: 120))
        let delivered = metadata.matching(NSPredicate(format: "NOT (identifier IN %@) AND label CONTAINS ' · Delivered'", previousIDs)).firstMatch
        XCTAssertTrue(delivered.waitForExistence(timeout: 30))
        capture("foreground-bidirectional-delivered-without-refresh")
        print("VIPI_FOREGROUND_EXCHANGE_COMPLETE " + ISO8601DateFormatter().string(from: Date()))
    }
    func testReceiveForegroundWithoutRefresh() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01",
              let expected = ProcessInfo.processInfo.environment["VIPI_QA_FOREGROUND_TEXT"],
              expected.hasPrefix("Foreground Android to iOS "), expected.count < 160 else {
            throw XCTSkip("A fresh explicit owned-account foreground exchange is required")
        }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.buttons["message-send"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts[expected].exists, "Use a new message for this delivery proof")
        capture("foreground-chat-awaiting-new-message")
        // The peer sends only after this ready marker is observed. No pull to
        // refresh, relaunch, scene activation or local send follows this point.
        print("VIPI_FOREGROUND_RECEIVER_READY")
        XCTAssertTrue(app.staticTexts[expected].waitForExistence(timeout: 120))
        capture("foreground-message-arrived-without-refresh")
    }
    func testReportSelectedOriginalMessage() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-dark"]; app.launch()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        let original = "Coffee tomorrow? Sent from the Android conversation screen."
        let message = app.staticTexts[original]
        for _ in 0..<5 { if message.exists && message.isHittable { break }; app.swipeDown() }
        XCTAssertTrue(message.waitForExistence(timeout: 10)); message.press(forDuration: 1.2)
        XCTAssertTrue(app.buttons["Report message"].waitForExistence(timeout: 10)); app.buttons["Report message"].tap()
        XCTAssertTrue(app.staticTexts["human-report-original"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["human-report-original"].label, original)
        capture("ios-report-selected-original-dark")
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Reason'")).firstMatch.tap()
        app.buttons["Something else"].tap()
        app.swipeUp(); app.buttons["human-report-submit"].tap()
        XCTAssertTrue(app.staticTexts["Report received"].waitForExistence(timeout: 20))
        capture("ios-report-received-dark")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["message-send"].exists)
    }
    func testBundledLicenseTextIsAvailableOffline() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        app.swipeUp()
        XCTAssertTrue(app.buttons["Licenses and notices"].waitForExistence(timeout: 10)); app.buttons["Licenses and notices"].tap()
        app.buttons["Vipi — GNU Affero General Public License v3"].tap()
        XCTAssertTrue(app.textViews.firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue((app.textViews.firstMatch.value as? String ?? "").contains("GNU AFFERO GENERAL PUBLIC LICENSE"))
        capture("ios-complete-license-text")
    }
    func testBackupNativeFilePicker() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "vqa_1107_ios01")).firstMatch.waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.buttons["Chat backup"].waitForExistence(timeout: 10)); app.buttons["Chat backup"].tap()
        let password = app.secureTextFields["history-password"]
        XCTAssertTrue(password.waitForExistence(timeout: 10)); password.tap(); password.typeText("Vipi public UI backup passphrase 2026")
        app.secureTextFields["history-password-confirm"].tap(); app.secureTextFields["history-password-confirm"].typeText("Vipi public UI backup passphrase 2026")
        app.swipeUp()
        app.buttons["history-begin"].tap()
        XCTAssertTrue(app.navigationBars["Save to Files"].waitForExistence(timeout: 15) || app.buttons["Save"].exists || app.buttons["Move"].exists)
        capture("ios-backup-native-file-picker")
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "backup-picker-accessibility"; tree.lifetime = .keepAlways; add(tree)
        XCTAssertTrue(app.buttons["Save"].isEnabled); app.buttons["Save"].tap()
        XCTAssertTrue(app.staticTexts["history-notice"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["history-notice"].label.contains("was saved"))
        capture("ios-backup-saved")
        try restoreBackup(app)
    }
    func testReviewChatList() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["New chat"].waitForExistence(timeout: 30))
        capture("ios-chat-list-light")
    }
    func testFindFriendComposeAndSend() throws {
        guard let peer = ProcessInfo.processInfo.environment["VIPI_QA_PEER"], peer.hasPrefix("vqa_") else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        XCTAssertTrue(app.buttons["New chat"].waitForExistence(timeout: 30))
        capture("ios-chat-list-light")
        app.buttons["New chat"].tap()
        let username = app.textFields["Friend’s username"]
        XCTAssertTrue(username.waitForExistence(timeout: 5)); username.tap(); username.typeText(peer)
        capture("ios-find-friend-light")
        app.buttons["Find friend"].tap()
        let input = app.descendants(matching: .any).matching(identifier: "message-input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 15)); input.tap()
        input.typeText("Coffee tomorrow? Sent from the iOS conversation screen.")
        capture("ios-compose-light")
        app.buttons["message-send"].tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the iOS conversation screen."].waitForExistence(timeout: 10))
        XCTAssertTrue(sentMetadata(app).waitForExistence(timeout: 15))
        capture("ios-conversation-light")
    }
    func testReopenExistingSentConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the iOS conversation screen."].waitForExistence(timeout: 15))
        capture("ios-existing-conversation-light")
        XCTAssertTrue(sentMetadata(app).waitForExistence(timeout: 15))
    }
    func testReceiveAndroidAndDarkConversation() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"]?.hasPrefix("vqa_") == true else { throw XCTSkip("Controlled staging accounts must be explicitly prepared") }
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]; app.launch()
        dismissOptionalOffer(app)
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the Android conversation screen."].waitForExistence(timeout: 20))
        capture("ios-conversation-dark")
    }
    func testRestoreExistingSavedBackup() throws {
        guard ProcessInfo.processInfo.environment["VIPI_QA_PEER"] == "vqa_1107_android01" else { throw XCTSkip("Owned staging identity required") }
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-vipi-appearance-light"]; app.launch()
        XCTAssertTrue(app.buttons["Your profile and settings"].waitForExistence(timeout: 30)); app.buttons["Your profile and settings"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "vqa_1107_ios01")).firstMatch.waitForExistence(timeout: 10))
        app.swipeUp(); app.buttons["Chat backup"].tap()
        try restoreBackup(app)
    }
    private func restoreBackup(_ app: XCUIApplication) throws {
        app.buttons["Restore backup"].tap()
        app.buttons["history-choose-file"].tap()
        let file = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH 'Vipi chat backup '")).firstMatch
        if !file.waitForExistence(timeout: 2) {
            app.tabBars.buttons["Browse"].tap()
            let local = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'On My iPhone'")).firstMatch
            if local.waitForExistence(timeout: 5) { local.tap() }
        }
        XCTAssertTrue(file.waitForExistence(timeout: 15)); file.tap()
        XCTAssertTrue(app.secureTextFields["history-password"].waitForExistence(timeout: 10))
        app.secureTextFields["history-password"].tap(); app.secureTextFields["history-password"].typeText("Vipi public UI backup passphrase 2026")
        app.swipeUp(); app.buttons["history-begin"].tap()
        XCTAssertTrue(app.buttons["history-confirm-restore"].waitForExistence(timeout: 15))
        capture("ios-backup-restore-preview")
        app.buttons["history-confirm-restore"].tap()
        XCTAssertTrue(app.staticTexts["history-notice"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["history-notice"].label.contains("already saved. Nothing was duplicated."))
        capture("ios-backup-restored-no-duplicates")
        app.terminate(); app.launch()
        let friend = app.staticTexts["Vipi Android QA"].firstMatch
        XCTAssertTrue(friend.waitForExistence(timeout: 30)); friend.tap()
        XCTAssertTrue(app.staticTexts["Coffee tomorrow? Sent from the Android conversation screen."].waitForExistence(timeout: 15))
        capture("ios-backup-restored-chat-reopen")
    }
    private func dismissOptionalOffer(_ app: XCUIApplication) {
        if app.buttons["Not now"].waitForExistence(timeout: 3) { app.buttons["Not now"].tap() }
    }
    private func sentMetadata(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'message-meta-' AND (label CONTAINS ' · Sent' OR label CONTAINS ' · Delivered')")).firstMatch
    }
    private func capture(_ name: String) { let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment) }
}

/// Actual BotConversationView and BotSession in the exact guarded QA bundle.
@MainActor final class BotJourneyTests: XCTestCase {
    func testKeyboardConsentConfirmedReplyAndReopenWhileReplyIsPending() throws {
        continueAfterFailure = false
        let originalOrientation = XCUIDevice.shared.orientation
        XCUIDevice.shared.orientation = .portrait
        defer { XCUIDevice.shared.orientation = originalOrientation }
        let app = XCUIApplication()
        app.launchArguments = ["-vipi-bot-ui-qa", "-vipi-appearance-light", "-vipi-source", "en", "-vipi-target", "es", "-vipi-density", "0"]
        app.launch(); defer { app.terminate() }
        let open = app.buttons["Open vBot"], proof = app.staticTexts["bot-qa-proof"]
        XCTAssertTrue(open.waitForExistence(timeout: 15)); open.tap()
        let input = app.descendants(matching: .any).matching(identifier: "bot-message-input").firstMatch
        let send = app.buttons["bot-message-send"]
        XCTAssertTrue(input.waitForExistence(timeout: 10)); input.tap(); input.typeText("Local draft before consent.")
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        let navigation = app.navigationBars["vBot"], back = navigation.buttons.element(boundBy: 0)
        let title = navigation.staticTexts["vBot"]
        for control in [input, send, title, back] {
            XCTAssertTrue(control.exists)
            if control.isEnabled { XCTAssertTrue(control.isHittable) }
            XCTAssertGreaterThan(control.frame.height, 0); XCTAssertTrue(app.frame.contains(control.frame))
            XCTAssertLessThanOrEqual(control.frame.maxY, keyboard.frame.minY + 1)
        }
        XCTAssertEqual(input.value as? String, "Local draft before consent.")
        XCTAssertFalse(send.isEnabled)
        capture(app, "bot-preconsent-draft-keyboard-title-back-send")
        // Both orientations are declared by the app. Keep real multiline input,
        // its action, and the focused field above the actual software IME.
        let extra = "\nLandscape line two.\nLandscape line three.\nLandscape line four.\nLandscape line five.\nFinal landscape line."
        input.typeText(extra)
        var landscapeDraft = "Local draft before consent." + extra
        XCTAssertEqual(input.value as? String, landscapeDraft)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            app.frame.width > app.frame.height
        }, object: app)], timeout: 5), .completed)
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        let layout = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            input.frame.maxY <= keyboard.frame.minY + 1 && input.frame.minY >= navigation.frame.maxY - 1
        }, object: app)
        let settled = XCTWaiter.wait(for: [layout], timeout: 5)
        // Appending after rotation proves real typing remains at the document
        // end and restarts the native caret blink for retained visual evidence.
        input.typeText(" End."); landscapeDraft += " End."
        XCTAssertEqual(input.value as? String, landscapeDraft)
        capture(app, "bot-landscape-multiline-draft-native-keyboard")
        let geometry = XCTAttachment(data: try JSONSerialization.data(withJSONObject:
            Dictionary(uniqueKeysWithValues: [("screen", app), ("keyboard", keyboard), ("input", input), ("send", send), ("navigation", navigation)].map { name, element in
                let frame = element.frame
                return (name, ["x": frame.minX, "y": frame.minY, "width": frame.width, "height": frame.height, "hittable": element.isHittable] as [String: Any])
            }), options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
        geometry.name = "bot-landscape-native-input-geometry"; geometry.lifetime = .keepAlways; add(geometry)
        try assertRenderedEndLine("Final landscape line. End.", in: input, app: app, keyboard: keyboard)
        XCTAssertEqual(settled, .completed, "Focused multiline composer must fit between native navigation and software keyboard")
        XCTAssertEqual(input.value as? String, landscapeDraft)
        for control in [input, send] {
            XCTAssertTrue(app.frame.contains(control.frame))
            XCTAssertGreaterThanOrEqual(control.frame.minY, navigation.frame.maxY - 1)
            XCTAssertLessThanOrEqual(control.frame.maxY, keyboard.frame.minY + 1)
        }
        XCTAssertTrue(input.isHittable); XCTAssertFalse(send.isEnabled)
        XCUIDevice.shared.orientation = .portrait
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            app.frame.height > app.frame.width
        }, object: app)], timeout: 5), .completed)
        input.tap(); input.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: extra.count + " End.".count))
        XCTAssertEqual(input.value as? String, "Local draft before consent.")
        back.tap(); XCTAssertTrue(open.waitForExistence(timeout: 5))
        XCTAssertTrue(proof.label.contains("posts=0")); open.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5)); XCTAssertEqual(input.value as? String, "Local draft before consent.")
        let agree = app.buttons["Agree and start chatting"]
        XCTAssertTrue(agree.waitForExistence(timeout: 5)); XCTAssertTrue(agree.isHittable); agree.tap()
        XCTAssertTrue(send.isEnabled)
        capture(app, "bot-explicit-consent-draft-send-enabled")
        send.tap()
        let confirmed = message("Confirmed QA reply.", in: app)
        XCTAssertTrue(confirmed.waitForExistence(timeout: 8)); XCTAssertTrue(confirmed.isHittable)
        capture(app, "bot-explicit-consent-single-confirmed-reply")
        input.tap(); input.typeText("Draft survives ordinary Back.")
        XCTAssertEqual(input.value as? String, "Draft survives ordinary Back.")
        back.tap(); XCTAssertTrue(open.waitForExistence(timeout: 5))
        XCTAssertTrue(proof.label.contains("posts=1;completed=1"))
        app.buttons["Hold next reply"].tap(); XCTAssertTrue(proof.label.contains("hold=true")); open.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5)); XCTAssertEqual(input.value as? String, "Draft survives ordinary Back.")
        XCTAssertTrue(send.isEnabled); send.tap()
        XCTAssertTrue(message("Waiting for vBot", in: app).waitForExistence(timeout: 5))
        back.tap(); XCTAssertTrue(open.waitForExistence(timeout: 5))
        XCTAssertTrue(proof.label.contains("posts=2;completed=1;pending=true"))
        capture(app, "bot-left-pending-request-without-account-disposal")
        open.tap(); XCTAssertTrue(input.waitForExistence(timeout: 5))
        let pendingReply = message("Pending QA reply completed.", in: app)
        let lateReplyVisible = pendingReply.waitForExistence(timeout: 8)
        capture(app, "bot-returned-before-pending-reply-completed")
        back.tap(); XCTAssertTrue(open.waitForExistence(timeout: 5))
        XCTAssertTrue(proof.label.contains("posts=2;completed=2;pending=false"))
        XCTAssertTrue(proof.label.contains("durableComplete=4"), "Both actual encrypted request/reply pairs must be complete")
        capture(app, "bot-durable-pairs-after-ordinary-navigation")
        XCTAssertTrue(lateReplyVisible, "The reopened conversation must display a reply that completed after ordinary Back and return")
        app.buttons["Finish Bot QA"].tap()
        XCTAssertTrue(app.staticTexts["Synthetic Bot conversation removed"].waitForExistence(timeout: 5))
    }
    /// Public XCUITest does not expose UITextInput's caret rect. Measure the
    /// actually rendered last line in the native screenshot instead; retain
    /// that same frame for independent caret/blink inspection.
    private func assertRenderedEndLine(_ endLine: String, in input: XCUIElement,
        app: XCUIApplication, keyboard: XCUIElement) throws {
        let screenshot = XCUIScreen.main.screenshot()
        let frame = XCTAttachment(screenshot: screenshot)
        frame.name = "bot-landscape-final-line-and-native-caret"; frame.lifetime = .keepAlways; add(frame)
        let nativeImage = screenshot.image
        let image = try XCTUnwrap(nativeImage.cgImage)
        let orientation: CGImagePropertyOrientation
        switch nativeImage.imageOrientation {
        case .up: orientation = .up
        case .down: orientation = .down
        case .left: orientation = .left
        case .right: orientation = .right
        case .upMirrored: orientation = .upMirrored
        case .downMirrored: orientation = .downMirrored
        case .leftMirrored: orientation = .leftMirrored
        case .rightMirrored: orientation = .rightMirrored
        @unknown default: throw NSError(domain: "VipiScreenshot", code: 1,
            userInfo: [NSLocalizedDescriptionKey: "Unknown native screenshot orientation; glyph coordinates cannot be qualified"])
        }
        let swapsAxes = [UIImage.Orientation.left, .right, .leftMirrored, .rightMirrored].contains(nativeImage.imageOrientation)
        let rasterWidth = CGFloat(swapsAxes ? image.height : image.width)
        let rasterHeight = CGFloat(swapsAxes ? image.width : image.height)
        let captureGeometry: [String: Any] = ["capture": "XCUIScreen.main.screenshot", "cg_width": image.width,
            "cg_height": image.height, "ui_image_orientation": nativeImage.imageOrientation.rawValue,
            "vision_orientation": orientation.rawValue, "ui_image_width": nativeImage.size.width,
            "ui_image_height": nativeImage.size.height, "oriented_raster_width": rasterWidth,
            "oriented_raster_height": rasterHeight, "native_window_width": app.frame.width,
            "native_window_height": app.frame.height]
        let captureReceipt = XCTAttachment(data: try JSONSerialization.data(withJSONObject: captureGeometry, options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
        captureReceipt.name = "bot-landscape-whole-screen-capture-geometry"; captureReceipt.lifetime = .keepAlways; add(captureReceipt)
        XCTAssertEqual(rasterWidth / rasterHeight, app.frame.width / app.frame.height, accuracy: 0.01,
            "Validate the complete orientation-aware native raster before mapping any glyph coordinates")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate; request.usesLanguageCorrection = false; request.recognitionLanguages = ["en-US"]
        try VNImageRequestHandler(cgImage: image, orientation: orientation, options: [:]).perform([request])
        let observed = try XCTUnwrap(request.results?.compactMap { observation -> CGRect? in
            guard let candidate = observation.topCandidates(1).first, candidate.confidence >= 0.8,
                  let range = candidate.string.range(of: endLine),
                  let glyphs = try? candidate.boundingBox(for: range) else { return nil }
            let box = glyphs.boundingBox
            return CGRect(x: app.frame.minX + box.minX * app.frame.width,
                y: app.frame.minY + (1 - box.maxY) * app.frame.height,
                width: box.width * app.frame.width, height: box.height * app.frame.height)
        }.first, "The full final typed visual line must actually render; field existence alone is insufficient")
        let measured = XCTAttachment(data: try JSONSerialization.data(withJSONObject: [
            "method": "Orientation-aware Vision OCR on validated whole-screen XCUIScreenshot; normalized glyph box mapped to native app coordinates",
            "line": endLine, "x": observed.minX, "y": observed.minY, "width": observed.width, "height": observed.height,
            "keyboard_top": keyboard.frame.minY, "native_full_draft_verified": true,
            "caret_rect_exposed_by_public_xcuitest": false, "caret_evidence": "same retained native screenshot after actual append"
        ], options: [.sortedKeys]), uniformTypeIdentifier: "public.json")
        measured.name = "bot-landscape-rendered-final-line-geometry"; measured.lifetime = .keepAlways; add(measured)
        XCTAssertGreaterThanOrEqual(observed.height, UIFont.preferredFont(forTextStyle: .body).capHeight * 0.85,
            "A clipped fragment of the final line cannot qualify as fully rendered")
        XCTAssertTrue(input.frame.insetBy(dx: -1, dy: -1).contains(observed))
        XCTAssertLessThanOrEqual(observed.maxY, keyboard.frame.minY - 1)
    }
    private func message(_ text: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", text)).firstMatch
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screenshot.name = name; screenshot.lifetime = .keepAlways; add(screenshot)
        let hierarchy = XCTAttachment(string: app.debugDescription); hierarchy.name = name + "-hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
    }
}
