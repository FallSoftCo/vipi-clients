import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import Vipi

/// Native journal/Signal lifecycle with controlled JSON responses. HTTP byte
/// transfer/server admission are qualified by the separate two-platform run.
@MainActor final class MediaOutboxTests: XCTestCase {
    private final class Transport: ChatTransport {
        let profile: ChatProfile
        var uploadsReady = false, loseAdmission = true
        var reservations = 0
        var sent: [[String: Any]] = []
        init(_ profile: ChatProfile) { self.profile = profile }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            let input = try body.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) } ?? [:]
            let output: Data
            switch path {
            case "/v1/me": output = try JSONEncoder().encode(profile)
            case "/v1/devices": output = try JSONSerialization.data(withJSONObject: ["id": try XCTUnwrap(input["device_id"]), "active": true])
            case "/v1/keys": output = try JSONSerialization.data(withJSONObject: ["revision": 1, "remaining": 20])
            case "/v1/messages/pending": output = Data("{\"messages\":[],\"next_cursor\":null}".utf8)
            case "/v1/media/uploads":
                reservations += 1
                guard uploadsReady else { throw ServiceFailure(status: 503, code: "synthetic_upload_offline") }
                var ready = input; ready["state"] = "ready"
                output = try JSONSerialization.data(withJSONObject: ready)
            case "/v1/messages":
                XCTAssertTrue(uploadsReady); sent.append(input)
                if loseAdmission { loseAdmission = false; throw URLError(.networkConnectionLost) }
                output = Data("{\"state\":\"accepted\"}".utf8)
            default:
                throw ServiceFailure(status: 404, code: "controlled_route_unavailable")
            }
            return try JSONDecoder().decode(type, from: output)
        }
    }
    func testUploadFailureAndLostAdmissionKeepDurableManifestAndCiphertext() async throws {
        #if !targetEnvironment(simulator)
        try XCTSkipUnless(KeychainStore.isMediaQualification, "Requires a simulator or explicit media QA namespace")
        #endif
        let manager = FileManager.default, alice = UUID(), bob = UUID(), user = "user_localmedia_outbox_\(UUID())"
        let root = manager.temporaryDirectory.appendingPathComponent("VipiMediaOutbox-\(UUID())", isDirectory: true)
        try manager.createDirectory(at: root, withIntermediateDirectories: true)
        let aliceVault = try MessageVault(account: alice), bobVault = try MessageVault(account: bob)
        var chat: ChatSession?
        defer {
            try? chat?.close(); try? aliceVault.close(); try? bobVault.close()
            for account in [alice,bob] {
                KeychainStore.delete(account: "messages-\(account.uuidString.lowercased())")
                for location in [FileManager.SearchPathDirectory.applicationSupportDirectory,.cachesDirectory] {
                    if let base = manager.urls(for: location, in: .userDomainMask).first {
                        try? manager.removeItem(at: base.appendingPathComponent("Attachments/\(account.uuidString.lowercased())"))
                        if location == .applicationSupportDirectory { try? manager.removeItem(at: base.appendingPathComponent("Messages/\(account.uuidString.lowercased())")) }
                    }
                }
            }
            KeychainStore.delete(account: "profile-"+user)
            try? manager.removeItem(at: root)
        }
        let sender = try MessagingCore(vault: aliceVault), receiver = try MessagingCore(vault: bobVault)
        let now = Int64(Date().timeIntervalSince1970 * 1000), claim = UUID()
        let publication = try receiver.keys.publication(now: now, count: 1)
        _ = try sender.keys.establish(peer: bob, requestID: claim, response: ClaimedKeys(request_id: claim,
            user_id: bob, device_id: receiver.device.id, signal_device_id: 1, registration_id: publication.registration_id,
            identity_key: publication.identity_key, signed: publication.signed, one_time: try XCTUnwrap(publication.one_time.first)))
        let pixels = Data(repeating: 127, count: 48 * 32 * 4)
        let provider = try XCTUnwrap(CGDataProvider(data: pixels as CFData))
        let image = try XCTUnwrap(CGImage(width: 48, height: 32, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 48 * 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent))
        let source = root.appendingPathComponent("native.jpg")
        let output = try XCTUnwrap(CGImageDestinationCreateWithURL(source as CFURL, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(output, image, nil); XCTAssertTrue(CGImageDestinationFinalize(output))
        let manifest = try await AttachmentRepository(account: alice).prepare(source: source, kind: .photo)
        let api = Transport(ChatProfile(id: alice, username: "media_outbox_qa", display_name: "Media outbox QA"))
        let bytes = try CiphertextTransport(endpoint: URL(string: "http://127.0.0.1:1")!) { _ in "unused-explicit-fixture-token" }
        chat = try ChatSession(api: api, userID: user, media: bytes); await chat!.start()
        XCTAssertTrue(chat!.ready)
        let id = try chat!.sendAttachments("Photo", peer: bob, attachments: [manifest])
        await chat!.synchronize()
        XCTAssertTrue(api.sent.isEmpty); XCTAssertNil(try sender.journal.outgoing(id))
        XCTAssertEqual(try sender.journal.draft(id)?.attachments, [manifest])
        try chat!.close(); chat = nil; api.uploadsReady = true
        chat = try ChatSession(api: api, userID: user, media: bytes); await chat!.start()
        XCTAssertEqual(api.sent.count, 1); XCTAssertEqual(try sender.journal.outgoing(id)?.state, "queued")
        let sealed = try XCTUnwrap(sender.journal.outgoing(id)).envelope.ciphertext
        try chat!.close(); chat = nil
        chat = try ChatSession(api: api, userID: user, media: bytes); await chat!.start()
        XCTAssertEqual(api.sent.count, 2)
        XCTAssertTrue(NSDictionary(dictionary: api.sent[0]).isEqual(to: api.sent[1]))
        let saved = try XCTUnwrap(sender.journal.outgoing(id))
        XCTAssertEqual(saved.envelope.ciphertext, sealed); XCTAssertEqual(saved.state, "accepted")
        let routed = RoutedMessage(envelope: saved.envelope, senderDevice: sender.device.id, recipientDevice: receiver.device.id)
        XCTAssertEqual(try receiver.receive(routed, now: now).attachments, [manifest])
        let beforeText = api.reservations
        try chat!.send("Text keeps its existing outbox", peer: bob); await chat!.synchronize()
        XCTAssertEqual(api.reservations, beforeText)
        XCTAssertEqual(Set(api.sent.compactMap { $0["id"] as? String }).count, 2)
        let text = try XCTUnwrap(api.sent.first { ($0["id"] as? String) != id.uuidString.lowercased() })
        XCTAssertNil(text["attachment_ids"])
    }
}
