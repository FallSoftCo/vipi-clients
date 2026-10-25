import LibSignalClient
import SwiftUI
import XCTest
@testable import Vipi

@MainActor final class SecurityNumberPresentationTests: XCTestCase {
    private final class Transport: ChatTransport {
        let owner = UUID(), peer = UUID()
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            var value: [String: Any]
            switch path {
            case "/v1/me": value = ["id": owner.uuidString, "username": "security_ui_qa", "display_name": "UI QA"]
            case "/v1/people/alex": value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
            case "/v1/devices":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                value = ["id": input["device_id"]!, "active": true]
            case "/v1/keys": value = ["revision": 1, "remaining": 20]
            case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
            default: throw ServiceFailure(status: 500, code: "unexpected_synthetic_path")
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    func testEncryptionDetailsThemesAndLargeType() async throws {
        let transport = Transport(), userID = "security-presentation-" + UUID().uuidString
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let config = documents.appendingPathComponent("security-ui-run.txt")
        let run = FileManager.default.fileExists(atPath: config.path) ? try String(contentsOf: config, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) : "001"
        guard run.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else { throw VocabularyPackError.invalid }
        let output = documents.appendingPathComponent("security-ui-" + run)
        guard !FileManager.default.fileExists(atPath: output.path) else { throw VocabularyPackError.invalid }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let ownerID = transport.owner.uuidString.lowercased()
        addTeardownBlock { @MainActor in
            KeychainStore.delete(account: "profile-" + userID)
            KeychainStore.delete(account: "messages-" + ownerID)
        }
        let chat = try ChatSession(api: transport, userID: userID)
        await chat.start(); XCTAssertTrue(chat.ready)
        let peer = try await chat.find("alex")
        let vault = try MessageVault(account: transport.owner)
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene); window.frame = scene.screen.bounds
        let host = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        for (name, established, verified, dark, large) in [
            ("ios-security-not-established-light", false, false, false, false),
            ("ios-security-unverified-light", true, false, false, false),
            ("ios-security-verified-dark", true, true, true, false),
            ("ios-security-large-type", true, false, false, true)
        ] {
            if established {
                if try chat.securityNumber(peer.id) == nil {
                    try vault.transaction { try vault.put("identity", peer.id.uuidString.lowercased() + "/1", IdentityKeyPair.generate().identityKey.serialize()) }
                }
                try chat.setIdentityVerified(verified, peer: peer.id, compared: XCTUnwrap(chat.securityNumber(peer.id)))
            }
            // New hosting view identity forces the actual load task on each scene.
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            host.rootView = AnyView(SecurityNumberView(chat: chat, peer: peer.id).id(name)
                .preferredColorScheme(dark ? .dark : .light).environment(\.dynamicTypeSize, large ? .accessibility3 : .large))
            try await Task.sleep(for: .milliseconds(700))
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            try XCTUnwrap(image.pngData()).write(to: output.appendingPathComponent(name + ".png"))
        }
        try JSONSerialization.data(withJSONObject: ["synthetic_contact_and_transport": true, "qa_account_id": ownerID,
            "evidence": "native_simulator_presentation_not_tap_or_physical_device_verification",
            "themes": ["light", "dark"], "large_type": "accessibility3"]).write(to: output.appendingPathComponent("receipt.json"))
    }
}
