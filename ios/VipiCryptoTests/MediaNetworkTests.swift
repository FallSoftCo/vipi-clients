import Foundation
import CryptoKit
@preconcurrency import AVFoundation
import CoreMedia
import CoreVideo
import AudioToolbox
import ImageIO
import XCTest
@testable import Vipi

/// Two native platforms and the normal relay protocol, explicitly synthetic
/// signed authentication. Never reads native/customer session or Keychain data.
@MainActor final class MediaNetworkTests: XCTestCase {
    private struct Identity: Decodable { let username: String; let subject: String; let access_token: String }
    private struct Configuration: Decodable { let run: String; let endpoint: URL; let android: Identity; let peer: Identity }
    private struct Profile: Codable { let id: UUID; let username: String; let display_name: String }
    private struct Status: Decodable { let state: String }
    private struct DeviceResult: Decodable { let id: UUID; let active: Bool }
    private struct Inventory: Decodable { let revision: UInt32; let remaining: Int }
    private struct Inbox: Decodable { let messages: [RoutedMessage.Received] }
    private struct State: Codable { let run: String; let account: UUID }
    private struct Expected: Decodable { let id: UUID; let kind: AttachmentKind; let original_sha256: String }
    private struct AndroidState: Decodable { let run: String; let sender: UUID; let recipient: UUID; let messages: [Expected] }
    private func file(_ name: String) -> URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(name) }
    private func config() throws -> Configuration {
        try XCTSkipUnless(KeychainStore.isMediaQualification, "Requires isolated mediaqa Keychain namespace")
        guard FileManager.default.fileExists(atPath: file("media-network-config.json").path) else { throw XCTSkip("Requires explicitly prepared isolated media fixture") }
        let value = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: file("media-network-config.json")))
        guard value.endpoint.scheme == "http", value.endpoint.host == "127.0.0.1", value.endpoint.port != nil,
              value.android.subject.hasPrefix("user_localmedia_"), value.peer.subject.hasPrefix("user_localmedia_"),
              value.android.username.hasPrefix("vqa_"), value.peer.username.hasPrefix("vqa_") else {
            throw ServiceFailure(status: 0, code: "synthetic_loopback_media_required")
        }
        return value
    }
    private func body(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    private func hash(_ url: URL) throws -> String {
        let source = try FileHandle(forReadingFrom: url); defer { try? source.close() }
        var digest = SHA256()
        while let data = try source.read(upToCount: 65536), !data.isEmpty { digest.update(data: data) }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }
    private func decodeFirstFrameOrPCM(_ url: URL, kind: AttachmentKind) async throws {
        let asset = AVURLAsset(url: url)
        let tracks = try await asset.loadTracks(withMediaType: kind == .video ? .video : .audio)
        let track = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: asset)
        let settings: [String: Any] = kind == .video
            ? [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
            : [AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false]
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: settings)
        XCTAssertTrue(reader.canAdd(output)); reader.add(output)
        XCTAssertTrue(reader.startReading()); defer { reader.cancelReading() }
        let sample = try XCTUnwrap(output.copyNextSampleBuffer())
        XCTAssertGreaterThan(CMSampleBufferGetNumSamples(sample), 0)
        if kind == .video { XCTAssertNotNil(CMSampleBufferGetImageBuffer(sample)) }
        else { XCTAssertGreaterThan(CMBlockBufferGetDataLength(try XCTUnwrap(CMSampleBufferGetDataBuffer(sample))), 0) }
    }
    func testPublishFreshAppleRecipientKeys() async throws {
        let config = try config(), api = try SignedLoopbackPairTransport(endpoint: config.endpoint, token: config.peer.access_token)
        let profile: Profile = try await api.request("PUT", "/v1/me", body: body(["username": config.peer.username, "display_name": "Synthetic Apple media QA"]))
        let core = try MessagingCore(vault: MessageVault(account: profile.id))
        let device: DeviceResult = try await api.request("POST", "/v1/devices", body: body(["device_id": core.device.id.uuidString.lowercased(), "secret": core.device.secret]))
        XCTAssertEqual(device.id, core.device.id); XCTAssertTrue(device.active)
        let publication = try core.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000))
        let inventory: Inventory = try await api.request("PUT", "/v1/keys", body: JSONEncoder().encode(publication), device: core.device)
        try core.keys.published(revision: inventory.revision)
        try JSONEncoder().encode(State(run: config.run, account: profile.id)).write(to: file("media-apple-state.json"), options: .atomic)
        try body(["run": config.run, "published": true, "process_id": ProcessInfo.processInfo.processIdentifier,
                  "proof": "fresh synthetic Apple keys, no production/native session read"]).write(to: file("media-apple-published-receipt.json"), options: .atomic)
    }
    func testReceiveAndroidPhotoVideoVoiceAndReplyWithApplePhoto() async throws {
        let config = try config(), state = try JSONDecoder().decode(State.self, from: Data(contentsOf: file("media-apple-state.json")))
        let expected = try JSONDecoder().decode(AndroidState.self, from: Data(contentsOf: file("media-native-state.json")))
        XCTAssertEqual(config.run, state.run); XCTAssertEqual(config.run, expected.run); XCTAssertEqual(state.account, expected.recipient)
        let api = try SignedLoopbackPairTransport(endpoint: config.endpoint, token: config.peer.access_token)
        let token = config.peer.access_token
        let bytes = try CiphertextTransport(endpoint: config.endpoint) { _ in token }
        let repository = try AttachmentRepository(account: state.account)
        let vault = try MessageVault(account: state.account)
        let core = try MessagingCore(vault: vault)
        let inbox: Inbox = try await api.request("GET", "/v1/messages/pending", device: core.device)
        XCTAssertLessThanOrEqual(inbox.messages.count, 3)
        for message in inbox.messages {
            let routed = try message.routed(account: state.account)
            XCTAssertNotNil(expected.messages.first { $0.id == routed.envelope.id })
            _ = try core.receive(routed, now: Int64(Date().timeIntervalSince1970 * 1000))
            let acknowledged: Status = try await api.request("POST", "/v1/messages/\(routed.envelope.id.uuidString.lowercased())/receipt", device: core.device)
            XCTAssertEqual(acknowledged.state, "delivered")
            try core.journal.receiptAccepted(routed.envelope.id)
        }
        // Resume authenticated originals from the durable journal after a
        // decoder failure/process exit; never ask a sender to re-encrypt/send.
        for match in expected.messages {
            let saved = try vault.transaction {
                try JSONDecoder().decode(StoredChat.self, from: XCTUnwrap(vault.get("incoming", match.id.uuidString.lowercased())))
            }
            let manifest = try XCTUnwrap(saved.attachments?.first)
            XCTAssertEqual(saved.envelope.sender, expected.sender)
            XCTAssertEqual(manifest.kind, match.kind)
            let original = try await repository.open(manifest, thumbnail: false, bytes: bytes, device: core.device)
            XCTAssertEqual(try hash(original), match.original_sha256)
            if manifest.thumbnail != nil { _ = try await repository.open(manifest, thumbnail: true, bytes: bytes, device: core.device) }
            if manifest.kind == .photo {
                let decoder = try XCTUnwrap(CGImageSourceCreateWithURL(original as CFURL, nil))
                XCTAssertNotNil(CGImageSourceCreateImageAtIndex(decoder, 0, nil))
            }
            else {
                let duration = try await AVURLAsset(url: original).load(.duration)
                XCTAssertGreaterThan(duration.seconds, 0)
                try await decodeFirstFrameOrPCM(original, kind: manifest.kind)
            }
        }
        let nativePhoto = file("media-native-photo.jpg")
        // This supplied deterministic JPEG is an input fixture, not customer data.
        let manifest = try await repository.prepare(source: nativePhoto, kind: .photo)
        let id = UUID(), now = Int64(Date().timeIntervalSince1970 * 1000)
        try core.journal.saveDraft(id: id, recipient: expected.sender, text: "Photo", createdAt: now, now: now, attachments: [manifest])
        try await repository.ensureUploaded(manifest, api: api, bytes: bytes, device: core.device)
        let routed = try core.queue(id: id, peer: expected.sender, text: "Photo", createdAt: now, now: now, attachments: [manifest])
        let sent: Status = try await api.request("POST", "/v1/messages", body: routed.sendData(), device: core.device)
        XCTAssertEqual(sent.state, "accepted")
        let retry = try core.queue(id: id, peer: expected.sender, text: "Photo", createdAt: now, now: now, attachments: [manifest])
        XCTAssertEqual(routed.envelope.ciphertext, retry.envelope.ciphertext)
        try body(["run": config.run, "id": id.uuidString.lowercased(), "original_sha256": hash(nativePhoto)])
            .write(to: file("media-apple-reply-state.json"), options: .atomic)
        try body(["run": config.run, "android_originals_decrypted": 3, "native_image_decode": true, "native_video_frame_decode": true, "native_audio_pcm_decode": true,
                  "apple_photo_uploaded_and_signal_sent": true, "after_envelope_ack": true,
                  "process_id": ProcessInfo.processInfo.processIdentifier,
                  "proof": "two native platforms and isolated PG/RS256, not production/provider authentication"])
            .write(to: file("media-apple-receive-reply-receipt.json"), options: .atomic)
    }
}
