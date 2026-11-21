import XCTest
import SwiftUI
@testable import Vipi

/// Native presentation captures with synthetic public profiles/transport.
/// These are simulator layout evidence, not physical interaction acceptance.
@MainActor final class ChatBlockingPresentationTests: XCTestCase {
    private enum OutputReceiptError:Error { case invalid }
    private final class Transport: ChatTransport {
        let owner = UUID(), peer = UUID()
        var blocked = false
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            let value: [String: Any]
            switch path {
            case "/v1/me": value = ["id": owner.uuidString, "username": "block_ui_qa", "display_name": "UI QA"]
            case "/v1/devices":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                value = ["id": input["device_id"]!, "active": true]
            case "/v1/keys": value = ["revision": 1, "remaining": 20]
            case "/v1/people/alex": value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
            case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
            default:
                guard path.hasPrefix("/v1/blocks/") else { throw ServiceFailure(status: 500, code: "unexpected_qa_path") }
                if method == "PUT" {
                    let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                    blocked = try XCTUnwrap(input["blocked"] as? Bool)
                }
                value = ["blocked": blocked]
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    func testBlockedConversationThemesAndLargeType() async throws {
        let transport = Transport(), userID = "block-presentation-" + UUID().uuidString
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let config = documents.appendingPathComponent("block-ui-run.txt")
        let run = FileManager.default.fileExists(atPath: config.path) ? try String(contentsOf: config, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) : "001"
        guard run.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else { throw OutputReceiptError.invalid }
        let output = documents.appendingPathComponent("block-ui-" + run)
        guard !FileManager.default.fileExists(atPath: output.path) else { XCTFail("Preserve existing visual receipts"); throw OutputReceiptError.invalid }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let ownerID = transport.owner.uuidString.lowercased()
        // Keep the tiny encrypted QA database until the test process exits.
        // SwiftUI tasks can outlive the test method; in-process unlink is unsafe.
        addTeardownBlock { @MainActor in
            KeychainStore.delete(account: "profile-" + userID)
            KeychainStore.delete(account: "messages-" + ownerID)
        }
        let chat = try ChatSession(api: transport, userID: userID)
        await chat.start(); XCTAssertTrue(chat.ready)
        let peer = try await chat.find("alex")
        try chat.send("Coffee tomorrow?", peer: peer.id)
        try await chat.setBlocked(true, peer: peer.id)
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene); window.frame = scene.screen.bounds
        let host = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        let state = AppState(defaults: try XCTUnwrap(UserDefaults(suiteName: userID)))
        let authentication = AuthenticationManager()
        for (name, dark, large, blocked) in [
            ("ios-blocked-light", false, false, true), ("ios-blocked-dark", true, false, true),
            ("ios-blocked-large-type", false, true, true), ("ios-unblocked-light", false, false, false)
        ] {
            try await chat.setBlocked(blocked, peer: peer.id)
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            host.rootView = AnyView(NavigationStack { FriendConversationView(chat: chat, peer: peer.id) }
                .environment(state).environment(authentication)
                .tint(VipiDesign.highlight).preferredColorScheme(dark ? .dark : .light).environment(\.dynamicTypeSize, large ? .accessibility3 : .large))
            try await Task.sleep(for: .milliseconds(700))
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            try XCTUnwrap(image.pngData()).write(to: output.appendingPathComponent(name + ".png"))
            XCTAssertEqual(chat.blockedPeers.contains(peer.id), blocked)
            XCTAssertEqual(try chat.messages(peer.id).first?.text, "Coffee tomorrow?")
        }
        try JSONSerialization.data(withJSONObject: ["synthetic_contact_and_transport": true, "qa_account_id": ownerID,
            "evidence": "native_simulator_layout_capture_not_physical_interaction",
            "themes": ["light", "dark"], "large_type": "accessibility3"]).write(to: output.appendingPathComponent("receipt.json"))
    }
}
