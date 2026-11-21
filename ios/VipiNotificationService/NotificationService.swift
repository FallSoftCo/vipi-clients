import Foundation
import UserNotifications

private final class RefuseRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

final class NotificationService: UNNotificationServiceExtension, @unchecked Sendable {
    private struct Display: Sendable {
        let account: UUID, peer: UUID, message: UUID
        let sender: String, body: String
        let repeated: Bool
    }
    private let lock = NSLock()
    private var delivery: ((UNNotificationContent) -> Void)?
    private var original: UNNotificationContent?
    private var operation: Task<Void, Never>?

    override func didReceive(_ request: UNNotificationRequest, withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        guard request.content.userInfo["kind"] as? String == "inbox_changed",
              let ticket = request.content.userInfo["preview"] as? String, (80...1024).contains(ticket.utf8.count) else {
            contentHandler(request.content); return
        }
        lock.lock()
        original = request.content
        delivery = contentHandler
        operation = Task { [weak self] in
            guard let self else { return }
            do {
                guard let grant = try NotificationAccess.grant(), let root = NotificationAccess.root else { finish(); return }
                let vault = try MessageVault(account: grant.account, directory: root, previewKey: grant.key)
                let device = try DeviceCredential.registered(vault: vault)
                var lookup = URLRequest(url: URL(string: "https://api.mambovipi.app/v1/notifications/envelope")!)
                lookup.httpMethod = "POST"
                lookup.httpBody = try JSONEncoder().encode(["ticket": ticket])
                lookup.setValue("application/json", forHTTPHeaderField: "Content-Type")
                lookup.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
                lookup.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
                let config = URLSessionConfiguration.ephemeral
                config.httpShouldSetCookies = false
                config.urlCache = nil
                config.timeoutIntervalForRequest = 6
                config.timeoutIntervalForResource = 9
                let session = URLSession(configuration: config, delegate: RefuseRedirects(), delegateQueue: nil)
                defer { session.invalidateAndCancel() }
                let (data, response) = try await session.data(for: lookup)
                guard (response as? HTTPURLResponse)?.statusCode == 200, data.count < 800_000 else { finish(); return }
                let match = try JSONDecoder().decode(NotificationEnvelope.self, from: data)
                let card = try match.preview(grant: grant, vault: vault, device: device) {
                    try Task.checkCancellation()
                    return try NotificationAccess.grant()
                }
                guard try NotificationAccess.grant() == grant else { finish(); return }
                finish(Display(account: grant.account, peer: match.peer, message: match.id,
                               sender: card.sender, body: card.body, repeated: card.repeated))
            } catch { finish() }
        }
        lock.unlock()
    }
    private func finish(_ card: Display? = nil) {
        lock.lock()
        let callback = delivery
        var result = original
        if let card, let display = original?.mutableCopy() as? UNMutableNotificationContent {
            display.title = card.sender
            display.body = card.body
            if card.repeated { display.sound = nil }
            display.userInfo = ["kind": "inbox_changed", "local_account": card.account.uuidString,
                                "local_peer": card.peer.uuidString, "local_message": card.message.uuidString]
            result = display
        }
        delivery = nil; original = nil; operation = nil
        lock.unlock()
        if let result { callback?(result) }
    }
    override func serviceExtensionTimeWillExpire() {
        lock.lock()
        let task = operation
        lock.unlock()
        task?.cancel()
        finish()
    }
}
