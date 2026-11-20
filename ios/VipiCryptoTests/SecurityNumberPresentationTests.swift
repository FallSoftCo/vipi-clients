import LibSignalClient
import SwiftUI
import XCTest
@testable import Vipi

@MainActor final class SecurityNumberPresentationTests: XCTestCase {
    private enum OutputReceiptError:Error { case invalid }
    private final class Transport: ChatTransport {
        let owner = UUID(), peer = UUID()
        var revoked = false
        var needsRecentAuthentication = false
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            var value: [String: Any]
            switch path {
            case "/v1/me": value = ["id": owner.uuidString, "username": "security_ui_qa", "display_name": "UI QA"]
            case "/v1/people/alex": value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
            case "/v1/devices":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                if needsRecentAuthentication { throw ServiceFailure(status: 403, code: "recent_sign_in_required") }
                value = ["id": input["device_id"]!, "active": true]
            case "/v1/keys":
                if revoked { throw ServiceFailure(status: 401, code: "device_revoked") }
                value = ["revision": 1, "remaining": 20]
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
        guard run.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else { throw OutputReceiptError.invalid }
        let output = documents.appendingPathComponent("security-ui-" + run)
        guard !FileManager.default.fileExists(atPath: output.path) else { throw OutputReceiptError.invalid }
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
    func testDeviceAndPeerRecoveryPresentation() async throws {
        let api = Transport(), user = "recovery-ui-" + UUID().uuidString
        let chat = try ChatSession(api: api, userID: user)
        await chat.start(); let peer = try await chat.find("alex")
        let vault = try MessageVault(account: api.owner), core = try MessagingCore(vault: vault)
        let peerRoot = FileManager.default.temporaryDirectory.appendingPathComponent("recovery-peer-" + UUID().uuidString)
        let remoteVault = try MessageVault(account: api.peer, directory: peerRoot), remote = try MessagingCore(vault: remoteVault)
        defer {
            try? chat.close(); try? vault.close(); try? remoteVault.close()
            KeychainStore.delete(account: "profile-" + user)
            for id in [api.owner, api.peer] { KeychainStore.delete(account: "messages-" + id.uuidString.lowercased()) }
            try? FileManager.default.removeItem(at: vault.url.deletingLastPathComponent()); try? FileManager.default.removeItem(at: peerRoot)
        }
        try vault.transaction {
            try vault.put("identity", peer.id.uuidString.lowercased() + "/1", IdentityKeyPair.generate().identityKey.serialize())
            try vault.put("peer-device", peer.id.uuidString.lowercased(), Data(UUID().uuidString.lowercased().utf8))
        }
        let publication = try remote.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000), count: 1), request = UUID()
        let response = ClaimedKeys(request_id: request, user_id: api.peer, device_id: remote.device.id, signal_device_id: 1,
            registration_id: publication.registration_id, identity_key: publication.identity_key, signed: publication.signed, one_time: publication.one_time[0])
        let review = try core.keys.reviewReplacement(peer: api.peer, requestID: request, response: response)
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let folder = docs.appendingPathComponent("device-recovery-ui-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try Data(folder.lastPathComponent.utf8).write(to: docs.appendingPathComponent("device-recovery-ui-latest.txt"))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }, window = UIWindow(windowScene: scene)
        window.frame = scene.screen.bounds; let host = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.isHidden = true; window.rootViewController = nil; previous?.makeKeyAndVisible() }
        func capture(_ name: String, _ view: AnyView, dark: Bool) async throws {
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            host.rootView = AnyView(view.preferredColorScheme(dark ? .dark : .light).id(name))
            try await Task.sleep(for: .milliseconds(700)); host.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            try XCTUnwrap(image.pngData()).write(to: folder.appendingPathComponent(name + ".png"))
        }
        try await capture("peer-change-light", AnyView(SecurityNumberView(chat: chat, peer: peer.id, reviewing: review)), dark: false)
        try await capture("peer-change-dark", AnyView(SecurityNumberView(chat: chat, peer: peer.id, reviewing: review)), dark: true)
        api.revoked = true; await chat.start(); XCTAssertTrue(chat.needsDeviceReplacement)
        let own = try chat.deviceReplacementCandidate()
        try await capture("own-device-light", AnyView(OwnDeviceReplacementView(chat: chat, candidate: own).environment(AuthenticationManager())), dark: false)
        try await capture("own-device-dark", AnyView(OwnDeviceReplacementView(chat: chat, candidate: own).environment(AuthenticationManager())), dark: true)
        api.needsRecentAuthentication = true
        do { try await chat.confirmDeviceReplacement(own); XCTFail("Old sign-in must require reauthentication") } catch {}
        XCTAssertTrue(chat.needsRecentSignIn)
        try await capture("own-device-sign-in-light", AnyView(OwnDeviceReplacementView(chat: chat, candidate: own).environment(AuthenticationManager())), dark: false)
        try await capture("own-device-sign-in-dark", AnyView(OwnDeviceReplacementView(chat: chat, candidate: own).environment(AuthenticationManager())), dark: true)
        print("VIPI_RECOVERY_UI_DIRECTORY " + folder.lastPathComponent)
    }

}
