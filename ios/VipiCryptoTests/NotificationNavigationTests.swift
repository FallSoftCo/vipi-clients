import XCTest
import UserNotifications
@testable import Vipi

@MainActor final class NotificationNavigationTests: XCTestCase {
    func testValidTapWaitsForReadyUIAndNewerTapCannotBeConsumedByOlderUI() async throws {
        let notifications = PushNotifications()
        await notifications.notificationOpened(
            kind: "inbox_changed", actionIdentifier: UNNotificationDefaultActionIdentifier)
        let first = try XCTUnwrap(notifications.inboxPresentation)
        await notifications.notificationOpened(
            kind: "inbox_changed", actionIdentifier: UNNotificationDefaultActionIdentifier)
        let second = try XCTUnwrap(notifications.inboxPresentation)
        XCTAssertNotEqual(first, second)
        notifications.consumeInboxPresentation(first)
        XCTAssertEqual(notifications.inboxPresentation, second)
        notifications.consumeInboxPresentation(second)
        XCTAssertNil(notifications.inboxPresentation)
    }

    func testUnrelatedPushOrDismissalDoesNotNavigateAndNewerInvitationCanClearTap() async throws {
        let notifications = PushNotifications()
        for kind in [nil, "another_event"] as [String?] {
            await notifications.notificationOpened(kind: kind, actionIdentifier: UNNotificationDefaultActionIdentifier)
        }
        await notifications.notificationOpened(
            kind: "inbox_changed", actionIdentifier: UNNotificationDismissActionIdentifier)
        XCTAssertNil(notifications.inboxPresentation)
        await notifications.notificationOpened(
            kind: "inbox_changed", actionIdentifier: UNNotificationDefaultActionIdentifier)
        XCTAssertNotNil(notifications.inboxPresentation)
        notifications.clearInboxPresentation()
        XCTAssertNil(notifications.inboxPresentation)
    }
}
