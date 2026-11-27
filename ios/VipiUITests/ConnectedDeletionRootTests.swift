import XCTest

/// Actual VipiApp deletion gate and ConnectedChatRoot ownership, with only
/// DEBUG dependency construction and synthetic service responses supplied.
@MainActor final class ConnectedDeletionRootTests: XCTestCase {
    func testFreeAccountCancelLostResponseRelaunchAndScopedErase() throws {
        guard ProcessInfo.processInfo.environment["VIPI_STARTER_ROUTE_UI"] == "true" else {
            throw XCTSkip("Owned isolated deletion-root qualification only")
        }
        continueAfterFailure = false
        let app = XCUIApplication()
        let arguments = [
            "-vipi-deletion-root-qa", "-vipi-welcome", "-vipi-source", "en", "-vipi-target", "es", "-vipi-density", "0",
            "-vipi-appearance-light"
        ]
        app.launchArguments = arguments
        launchPortraitApp(app)
        addTeardownBlock { @MainActor in
            app.terminate()
            app.launchArguments = arguments + ["-vipi-deletion-root-cleanup"]
            app.launch()
            XCTAssertTrue(
                app.staticTexts["mambo-name-title"].waitForExistence(timeout: 10),
                "Owned fixture cleanup must leave the actual signed-out onboarding route")
            app.terminate()
        }
        let metadata = app.staticTexts["deletion-root-qa-proof"]
        XCTAssertTrue(metadata.waitForExistence(timeout: 20))
        func read() -> [String: Any] {
            guard metadata.exists, let data = metadata.label.data(using: .utf8),
                let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return [:] }
            return value
        }
        func observe(_ name: String, _ predicate: @escaping ([String: Any]) -> Bool) -> [String: Any] {
            let expected = XCTNSPredicateExpectation(
                predicate: NSPredicate { _, _ in predicate(read()) }, object: metadata)
            XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 12), .completed, "\(name): \(read())")
            let value = read()
            let data = (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data()
            let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
            attachment.name = "connected-deletion-" + name
            attachment.lifetime = .keepAlways
            add(attachment)
            XCTAssertEqual(value["unexpected_requests"] as? Int, 0)
            XCTAssertEqual(value["fixture_failure"] as? Bool, false)
            XCTAssertEqual(value["other_marker"] as? Bool, true)
            XCTAssertEqual(value["other_key_unchanged"] as? Bool, true)
            XCTAssertEqual(value["other_profile_unchanged"] as? Bool, true)
            return value
        }
        func capture(_ name: String) {
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "connected-deletion-" + name
            attachment.lifetime = .keepAlways
            add(attachment)
        }
        let initial = observe("actual-connected-root-ready") {
            ($0["chat_creations"] as? Int ?? 0) > 0 && ($0["ready_chats"] as? Int ?? 0) > 0
                && $0["own_marker"] as? Bool == true && $0["session_key_present"] as? Bool == true
        }
        XCTAssertEqual(initial["starts"] as? Int, 1)
        XCTAssertEqual(initial["receipt_present"] as? Bool, false)
        XCTAssertEqual(initial["auth_signed_out"] as? Bool, false)
        XCTAssertTrue(app.images["inbox-wordmark"].exists)
        app.buttons["Your profile and settings"].tap()
        let deletionLink = app.buttons["Delete Vipi account"]
        for _ in 0..<5 {
            if deletionLink.exists && deletionLink.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(deletionLink.exists && deletionLink.isHittable)
        deletionLink.tap()
        let delete = app.buttons["delete-account"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        delete.tap()
        let confirm = app.alerts["Delete your Vipi account?"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.buttons["Cancel"].tap()
        let cancelled = observe("settings-cancel-preserves-live-owners-and-data") {
            $0["submissions"] as? Int == 0 && $0["receipt_present"] as? Bool == false
                && $0["session_key_present"] as? Bool == true && $0["own_marker"] as? Bool == true
                && ($0["ready_chats"] as? Int ?? 0) > 0
        }
        XCTAssertEqual(cancelled["own_key"] as? Bool, true)
        XCTAssertEqual(cancelled["own_profile"] as? Bool, true)
        XCTAssertEqual(cancelled["auth_signed_out"] as? Bool, false)
        XCTAssertGreaterThan(cancelled["open_chat_owners"] as? Int ?? 0, 0)
        capture("cancel-keeps-session-encrypted-data-and-chat")
        delete.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.buttons["Delete Vipi account"].tap()
        let uncertain = observe("accepted-lost-response-persists-real-receipt-and-disposes-owners") {
            $0["submissions"] as? Int == 1 && $0["server_accepted"] as? Bool == true
                && $0["phase"] as? String == "prepared" && $0["receipt_matches_owner"] as? Bool == true
                && $0["open_chat_owners"] as? Int == 0
        }
        XCTAssertEqual(uncertain["own_marker"] as? Bool, true, "Unconfirmed response must not erase local data")
        XCTAssertEqual(uncertain["session_key_present"] as? Bool, true)
        XCTAssertEqual(uncertain["local_erased"] as? Bool, false)
        XCTAssertTrue(app.buttons["deletion-retry"].exists)
        XCTAssertFalse(app.navigationBars["Chats"].buttons["home-compose"].exists)
        capture("lost-response-actual-deletion-root")

        // Real process relaunch: same keychain capability, vaults and fake
        // server disk ledger. The fixture never selects the recovery view.
        app.terminate()
        app.launchArguments = arguments
        app.launch()
        XCTAssertTrue(metadata.waitForExistence(timeout: 15))
        let recovered = observe("fresh-app-owner-enters-only-deletion-recovery-and-erases-scope") {
            $0["starts"] as? Int == 2 && ["requested", "completed"].contains($0["phase"] as? String ?? "")
                && $0["local_erased"] as? Bool == true && $0["auth_signed_out"] as? Bool == true
                && ($0["confirmations"] as? Int ?? 0) > 0
        }
        XCTAssertEqual(recovered["chat_creations"] as? Int, initial["chat_creations"] as? Int)
        XCTAssertGreaterThan(recovered["status_reads"] as? Int ?? 0, 0)
        XCTAssertEqual(recovered["submissions"] as? Int, 1, "Recovery must check status without another DELETE")
        for key in ["own_key", "own_directory", "own_profile", "own_marker", "session_key_present"] {
            XCTAssertEqual(recovered[key] as? Bool, false, key)
        }
        XCTAssertFalse(app.images["inbox-wordmark"].exists)
        XCTAssertFalse(app.navigationBars["Chats"].buttons["home-compose"].exists)
        XCTAssertFalse(app.buttons["Your profile and settings"].exists)
        capture("fresh-process-deletion-only-other-account-preserved")
        let completedTitle = app.staticTexts["Vipi account deleted"]
        let checkStatus = app.buttons["deletion-retry"]
        var manuallyChecked = false
        if read()["phase"] as? String == "requested" {
            let available = XCTNSPredicateExpectation(
                predicate: NSPredicate { _, _ in
                    completedTitle.exists || (checkStatus.exists && checkStatus.isHittable)
                }, object: app)
            XCTAssertEqual(XCTWaiter.wait(for: [available], timeout: 5), .completed)
            // A foreground/scene check may finish between observations. Do
            // not require a transient intermediate state to remain visible.
            if !completedTitle.exists && read()["phase"] as? String == "requested" && checkStatus.exists
                && checkStatus.isHittable
            {
                checkStatus.tap()
                manuallyChecked = true
            }
        }
        let complete = observe("status-confirmed-complete") {
            $0["phase"] as? String == "completed" && $0["local_erased"] as? Bool == true
                && $0["submissions"] as? Int == 1 && ($0["confirmations"] as? Int ?? 0) > 0
        }
        XCTAssertTrue(completedTitle.exists)
        let route = XCTAttachment(
            string:
                "status_route=\(manuallyChecked ? "manual Check status" : "automatic status completion"); confirmations=\(complete["confirmations"] as? Int ?? 0)"
        )
        route.name = "connected-deletion-confirmation-route"
        route.lifetime = .keepAlways
        add(route)
        let done = app.buttons["Done"]
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        done.tap()
        XCTAssertTrue(app.staticTexts["mambo-name-title"].waitForExistence(timeout: 10))
        let finished = observe("done-actual-signed-out-onboarding") {
            $0["receipt_present"] as? Bool == false && $0["auth_signed_out"] as? Bool == true
                && $0["session_key_present"] as? Bool == false
        }
        for key in ["own_key", "own_directory", "own_profile", "own_marker"] {
            XCTAssertEqual(finished[key] as? Bool, false, key)
        }
        XCTAssertEqual(finished["submissions"] as? Int, 1)
        capture("done-signed-out-with-no-vault-resurrection")
    }
}
