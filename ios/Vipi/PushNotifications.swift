import Observation
import SwiftUI
import UIKit
import UserNotifications

@MainActor @Observable final class PushNotifications {
    static let shared = PushNotifications()
    private weak var chat: ChatSession?
    private var token: String?
    private var registered: String?
    private var publishing = false
    private(set) var authorization: UNAuthorizationStatus = .notDetermined
    private(set) var enabled = true
    private(set) var busy = false
    var notice: String?
    private var preferenceKey: String? { chat?.profile.map { "notifications-enabled-" + $0.id.uuidString.lowercased() } }

    func attach(_ chat: ChatSession) async {
        if self.chat !== chat { self.chat = chat; registered = nil }
        if let key = preferenceKey { enabled = UserDefaults.standard.object(forKey: key) as? Bool ?? true }
        await refresh()
    }
    func detach() { chat = nil; registered = nil }
    func refresh() async {
        authorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        guard enabled else {
            // Retry an offline opt-out on the next foreground refresh.
            if let chat { try? await chat.removePushRegistration() }
            return
        }
        guard authorization == .authorized || authorization == .provisional else { return }
        UIApplication.shared.registerForRemoteNotifications()
        await publish()
    }
    func enable() async {
        guard !busy else { return }
        busy = true; notice = nil
        defer { busy = false }
        do {
            let allowed = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
            authorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
            guard allowed else { notice = "Notifications are off. You can allow them in iPhone Settings."; return }
            enabled = true
            if let key = preferenceKey { UserDefaults.standard.set(true, forKey: key) }
            UIApplication.shared.registerForRemoteNotifications()
            await publish()
        } catch { notice = "Notifications couldn’t be enabled. Please try again." }
    }
    func disable() async {
        guard !busy, let chat else { return }
        busy = true; notice = nil
        defer { busy = false }
        // Persist the user's opt-out before the network operation, including
        // when a token publication is already suspended in flight.
        enabled = false; registered = nil
        if let key = preferenceKey { UserDefaults.standard.set(false, forKey: key) }
        UIApplication.shared.unregisterForRemoteNotifications()
        do {
            try await chat.removePushRegistration()
        } catch { notice = "Notifications are off on this device. Reconnect to finish updating your preference." }
    }
    func receivedToken(_ data: Data) {
        token = data.map { String(format: "%02x", $0) }.joined()
        Task { await publish() }
    }
    func registrationFailed() { notice = "Notifications couldn’t connect. Open Vipi to check for new messages." }
    private func publish() async {
        guard !publishing, enabled, authorization == .authorized || authorization == .provisional,
              let chat, let token, registered != token,
              let configured = Bundle.main.object(forInfoDictionaryKey: "VipiPushEnvironment") as? String,
              ["development", "production"].contains(configured) else { return }
        publishing = true
        defer {
            publishing = false
            if enabled && (self.token != token || self.chat !== chat) {
                Task { await publish() }
            }
        }
        do {
            try await chat.registerPush(token: token, environment: configured == "production" ? "production" : "sandbox")
            guard self.chat === chat, self.token == token, enabled else {
                // A PUT that finishes after opt-out must not undo the DELETE.
                if self.chat === chat && !enabled { try? await chat.removePushRegistration() }
                return
            }
            registered = token; notice = nil
        } catch { if self.chat === chat { notice = "Notifications couldn’t connect. Open Vipi to check for new messages." } }
    }
    func inboxChanged() async -> UIBackgroundFetchResult {
        guard let chat else { return .noData }
        let before = chat.revision
        await chat.synchronize()
        return chat.revision != before ? .newData : .noData
    }
}

@MainActor final class VipiAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) { PushNotifications.shared.receivedToken(deviceToken) }
    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) { PushNotifications.shared.registrationFailed() }
    func application(_ application: UIApplication, didReceiveRemoteNotification userInfo: [AnyHashable: Any]) async -> UIBackgroundFetchResult {
        guard userInfo["type"] as? String == "inbox_changed" else { return .noData }
        return await PushNotifications.shared.inboxChanged()
    }
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        _ = await PushNotifications.shared.inboxChanged()
        // The visible conversation updates in place. No duplicate alert over it.
        return []
    }
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async { _ = await PushNotifications.shared.inboxChanged() }
}

struct NotificationSettingsView: View {
    let notifications = PushNotifications.shared
    var body: some View {
        Form {
            Section {
                Text("Know when a friend replies. Notifications never include message text or a friend’s name.")
                if notifications.enabled && notifications.authorization == .authorized {
                    Button("Turn off Vipi notifications") { Task { await notifications.disable() } }.disabled(notifications.busy)
                } else {
                    Button("Enable notifications") { Task { await notifications.enable() } }.disabled(notifications.busy)
                }
                Link("Open iPhone notification settings", destination: URL(string: UIApplication.openNotificationSettingsURLString)!)
            }
            if let notice = notifications.notice { Section { Text(notice).foregroundStyle(VipiDesign.secondary) } }
        }.navigationTitle("Notifications").task { await notifications.refresh() }
    }
}
