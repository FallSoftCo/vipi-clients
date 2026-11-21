import Foundation
import CryptoKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import Vipi

@MainActor final class MediaAttachmentTests: XCTestCase {
    private func jpeg(_ file: URL) throws {
        let pixels = Data(repeating: 127, count: 96 * 72 * 4)
        let provider = try XCTUnwrap(CGDataProvider(data: pixels as CFData))
        let image = try XCTUnwrap(CGImage(width: 96, height: 72, bitsPerComponent: 8, bitsPerPixel: 32,
            bytesPerRow: 96 * 4, space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue), provider: provider,
            decode: nil, shouldInterpolate: false, intent: .defaultIntent))
        let output = try XCTUnwrap(CGImageDestinationCreateWithURL(file as CFURL, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(output, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(output))
    }
    func testPhotoManifestKeyInsideSignalAndOfflineJournalRetry() async throws {
        #if !targetEnvironment(simulator)
        try XCTSkipUnless(KeychainStore.isMediaQualification, "Requires a simulator or explicit media QA namespace")
        #endif
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("VipiMediaQA-\(UUID())", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let alice = UUID(), bob = UUID(), now = Int64(Date().timeIntervalSince1970 * 1000), messageID = UUID()
        let source = root.appendingPathComponent("native-photo.jpg"); try jpeg(source)
        let repository = try AttachmentRepository(account: alice, directory: root)
        let manifest = try await repository.prepare(source: source, kind: .photo)
        XCTAssertEqual(manifest.width, 96); XCTAssertEqual(manifest.height, 72); XCTAssertEqual(manifest.contentType, "image/jpeg")
        let senderRoot = root.appendingPathComponent("sender"), recipientRoot = root.appendingPathComponent("recipient")
        let routed: RoutedMessage
        do {
            let recipient = try MessagingCore(vault: MessageVault(account: bob, directory: recipientRoot))
            let publication = try recipient.keys.publication(now: now, count: 1), request = UUID()
            let claimed = ClaimedKeys(request_id: request, user_id: bob, device_id: recipient.device.id, signal_device_id: 1,
                registration_id: publication.registration_id, identity_key: publication.identity_key,
                signed: publication.signed, one_time: try XCTUnwrap(publication.one_time.first))
            do {
                let sender = try MessagingCore(vault: MessageVault(account: alice, directory: senderRoot))
                _ = try sender.keys.establish(peer: bob, requestID: request, response: claimed)
                try sender.journal.saveDraft(id: messageID, recipient: bob, text: "Photo", createdAt: now, now: now, attachments: [manifest])
            }
            let reopened = try MessagingCore(vault: MessageVault(account: alice, directory: senderRoot))
            let draft = try XCTUnwrap(reopened.journal.draft(messageID))
            routed = try reopened.queue(id: messageID, peer: bob, text: draft.text, createdAt: draft.createdAt, now: now, attachments: draft.attachments ?? [])
        }
        let outer = try XCTUnwrap(JSONSerialization.jsonObject(with: routed.sendData()) as? [String: Any])
        XCTAssertNil(outer["key"]); XCTAssertNil(outer["filename"]); XCTAssertNil(outer["content_type"])
        XCTAssertEqual(outer["attachment_ids"] as? [String], manifest.blobIDs)
        do {
            let sender = try MessagingCore(vault: MessageVault(account: alice, directory: senderRoot))
            let saved = try XCTUnwrap(sender.journal.outgoing(messageID))
            let retry = try sender.queue(id: messageID, peer: bob, text: "Photo", createdAt: now, now: now, attachments: saved.attachments ?? [])
            XCTAssertEqual(retry.envelope.ciphertext, routed.envelope.ciphertext)
            XCTAssertThrowsError(try sender.queue(id: messageID, peer: bob, text: "Photo", createdAt: now, now: now))
        }
        do {
            let recipient = try MessagingCore(vault: MessageVault(account: bob, directory: recipientRoot))
            let received = try recipient.receive(routed, now: now)
            XCTAssertEqual(received.attachments, [manifest])
            let history = try ConversationHistory(vault: MessageVault(account: bob, directory: recipientRoot))
            let receivedManifest = try XCTUnwrap(history.messages(peer: alice).first?.attachments.first)
            let receivingFiles = try AttachmentRepository(account: bob, directory: recipientRoot)
            try FileManager.default.copyItem(at: repository.ciphertext(manifest.original), to: receivingFiles.ciphertext(manifest.original))
            let offline = try CiphertextTransport(endpoint: URL(string: "http://127.0.0.1:1")!) { _ in
                XCTFail("A cached received photo must open offline")
                return "unused"
            }
            let viewed = try await receivingFiles.viewPhoto(receivedManifest, bytes: offline, device: recipient.device)
            XCTAssertEqual(viewed.width, 96); XCTAssertEqual(viewed.height, 72)
            XCTAssertEqual(try recipient.receive(routed, now: now).attachments, [manifest])
            let clear = root.appendingPathComponent("verified.jpg")
            _ = try await MediaCryptography.shared.open(source: repository.ciphertext(manifest.original), destination: clear,
                key: manifest.key, attachment: manifest.id, part: manifest.original)
            XCTAssertEqual(try Data(contentsOf: clear), try Data(contentsOf: source))
            let thumbnail = try XCTUnwrap(manifest.thumbnail)
            let thumb = root.appendingPathComponent("thumbnail-verified.jpg")
            _ = try await MediaCryptography.shared.open(source: repository.ciphertext(thumbnail), destination: thumb,
                key: manifest.key, attachment: manifest.id, part: thumbnail)
            XCTAssertNotNil(CGImageSourceCreateWithURL(thumb as CFURL, nil))
        }
        // Only keys generated by this isolated test, never an existing account.
        KeychainStore.delete(account: "messages-\(alice.uuidString.lowercased())")
        KeychainStore.delete(account: "messages-\(bob.uuidString.lowercased())")
    }
    func testCorruptWrongContextAndMistakenPhotoNeverPublishPlaintext() async throws {
        #if !targetEnvironment(simulator)
        try XCTSkipUnless(KeychainStore.isMediaQualification, "Requires a simulator or explicit media QA namespace")
        #endif
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("VipiMediaCorrupt-\(UUID())", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("native-photo.jpg"); try jpeg(source)
        let repository = try AttachmentRepository(account: UUID(), directory: root)
        let manifest = try await repository.prepare(source: source, kind: .photo)
        let encrypted = repository.ciphertext(manifest.original), clear = root.appendingPathComponent("must-not-publish.jpg")
        do {
            _ = try await MediaCryptography.shared.open(source: encrypted, destination: clear, key: manifest.key,
                attachment: UUID().uuidString.lowercased(), part: manifest.original)
            XCTFail("Wrong attachment context authenticated")
        } catch { XCTAssertFalse(FileManager.default.fileExists(atPath: clear.path)) }
        var bytes = try Data(contentsOf: encrypted); bytes[bytes.count - 1] ^= 1; try bytes.write(to: encrypted)
        do {
            _ = try await MediaCryptography.shared.open(source: encrypted, destination: clear,
                key: manifest.key, attachment: manifest.id, part: manifest.original)
            XCTFail("Corrupt ciphertext authenticated")
        } catch { XCTAssertFalse(FileManager.default.fileExists(atPath: clear.path)) }
        let mistaken = root.appendingPathComponent("not-a-photo.jpg")
        try Data("synthetic text, not a photo".utf8).write(to: mistaken)
        do { _ = try await repository.prepare(source: mistaken, kind: .photo); XCTFail("Mistaken file accepted") }
        catch { /* expected native decoder rejection */ }
    }
}
