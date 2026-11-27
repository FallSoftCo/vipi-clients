import SwiftUI
import XCTest
@testable import Vipi

@MainActor final class AccountDeletionPresentationTests: XCTestCase {
    private enum OutputReceiptError: Error { case invalid }
    private final class Store: DeletionStore {
        var record: DeletionRecord?
        func load() -> DeletionRecord? { record }
        func save(_ record: DeletionRecord) { self.record = record }
        func remove() { record = nil }
    }
    private final class Transport: ChatTransport, DeletionTransport {
        let account = UUID()
        var offline = true
        var finished = false
        func request<T: Decodable>(
            _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
            as type: T.Type
        ) async throws -> T {
            let value: [String: Any]
            switch path {
            case "/v1/me": value = ["id": account.uuidString, "username": "delete_ui_qa", "display_name": "UI QA"]
            case "/v1/devices":
                let input = try JSONSerialization.jsonObject(with: body!) as! [String: Any]
                value = ["id": input["device_id"]!, "active": true]
            case "/v1/keys": value = ["revision": 1, "remaining": 20]
            case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
            default: throw ServiceFailure(status: 500, code: "unexpected_synthetic_path")
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
        func submit(_ record: DeletionRecord) async throws -> DeletionReply {
            XCTFail("Presentation must not submit deletion")
            throw URLError(.unsupportedURL)
        }
        func status(_ record: DeletionRecord) async throws -> DeletionReply {
            if offline { throw URLError(.notConnectedToInternet) }
            return DeletionReply(account_id: record.account, status: finished ? "deleted" : "deletion_requested")
        }
    }
    func testDeletionStatesThemesAndLargeType() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let config = documents.appendingPathComponent("deletion-ui-run.txt")
        let run: String
        if FileManager.default.fileExists(atPath: config.path) {
            run = try String(contentsOf: config, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            guard run.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else {
                throw OutputReceiptError.invalid
            }
        } else {
            let existing = Set(try FileManager.default.contentsOfDirectory(atPath: documents.path))
            run = try XCTUnwrap(
                (1...999).lazy.map { String(format: "%03d", $0) }.first { !existing.contains("deletion-ui-" + $0) },
                "No unused numbered capture directory in this simulator")
        }
        let output = documents.appendingPathComponent("deletion-ui-" + run)
        guard !FileManager.default.fileExists(atPath: output.path) else { throw OutputReceiptError.invalid }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: false)
        let api = Transport(), store = Store(), user = "delete-ui-" + UUID().uuidString
        let authentication = AuthenticationManager()
        let chat = try ChatSession(api: api, userID: user)
        await chat.start()
        XCTAssertTrue(chat.ready)
        let manager = AccountDeletion(store: store, service: api, erase: { _ in }, signOut: { _ in })
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene)
        window.frame = scene.screen.bounds
        let host = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.rootViewController = nil
            window.isHidden = true
            previous?.makeKeyAndVisible()
            try? chat.close()
            KeychainStore.delete(account: "profile-" + user)
            let suffix = api.account.uuidString.lowercased()
            for root in [NotificationAccess.legacyRoot, NotificationAccess.root].compactMap({ $0 }) {
                try? FileManager.default.removeItem(at: root.appendingPathComponent(suffix))
            }
            if (try? NotificationAccess.grant())?.account == api.account { try? NotificationAccess.revoke() }
            for prefix in ["messages-", "messages-initializing-", "notification-store-location-"] {
                KeychainStore.delete(account: prefix + suffix)
            }
        }
        for (index, name, dark, large) in [
            (0, "ios-deletion-explanation-light", false, false),
            (1, "ios-deletion-interrupted-dark", true, false),
            (2, "ios-deletion-requested-large-type", false, true),
            (3, "ios-deletion-complete-light", false, false)
        ] {
            if index == 1 { try manager.begin(account: api.account, userID: user) { try chat.close() } }
            if index == 2 { api.offline = false }
            if index == 3 { api.finished = true }
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            let view =
                index == 0
                ? AnyView(NavigationStack { DeleteAccountView(chat: chat) }) : AnyView(AccountDeletionProgressView())
            host.rootView = AnyView(
                view.id(name).environment(manager).environment(authentication)
                    .tint(VipiDesign.highlight).preferredColorScheme(dark ? .dark : .light).environment(
                        \.dynamicTypeSize, large ? .accessibility3 : .large))
            try await Task.sleep(for: .milliseconds(650))
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            try XCTUnwrap(image.pngData()).write(to: output.appendingPathComponent(name + ".png"))
        }
        XCTAssertEqual(manager.pending?.phase, .completed)
        try JSONSerialization.data(withJSONObject: [
            "synthetic_account_and_transport": true, "live_account_deleted": false,
            "evidence": "native_simulator_static_presentation_not_taps_or_physical_device",
            "large_type": "accessibility3"
        ])
        .write(to: output.appendingPathComponent("receipt.json"))
    }
}
