import Foundation
import LibSignalClient
import XCTest

/// Cross-platform library qualification; deliberately separate from production key storage.
final class SignalInteropTests: XCTestCase {
    func testAndroidHandshakeAndExportSwiftReplies() throws {
        let resource = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "android-handshake", withExtension: "json"))
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: resource)) as? [String: Any])
        func bytes(_ name: String) throws -> Data {
            try XCTUnwrap(Data(base64Encoded: try XCTUnwrap(fixture[name] as? String)))
        }
        let alice = try ProtocolAddress(name: XCTUnwrap(fixture["aliceAddress"] as? String), deviceId: 1)
        let bob = try ProtocolAddress(name: XCTUnwrap(fixture["bobAddress"] as? String), deviceId: 1)
        let store = InMemorySignalProtocolStore(
            identity: try IdentityKeyPair(bytes: bytes("bobIdentity")), registrationId: 202)
        let context = NullContext()
        try store.storePreKey(PreKeyRecord(bytes: bytes("bobPreKey")), id: 1, context: context)
        try store.storeSignedPreKey(SignedPreKeyRecord(bytes: bytes("bobSignedPreKey")), id: 2, context: context)
        try store.storeKyberPreKey(KyberPreKeyRecord(bytes: bytes("bobKyberPreKey")), id: 3, context: context)
        let incoming = try PreKeySignalMessage(bytes: bytes("ciphertext"))
        let plaintext = try signalDecryptPreKey(
            message: incoming, from: alice, localAddress: bob, sessionStore: store, identityStore: store,
            preKeyStore: store, signedPreKeyStore: store, kyberPreKeyStore: store, context: context)
        XCTAssertEqual(String(decoding: plaintext, as: UTF8.self), "Coffee by the river? ☕ مرحباً")
        XCTAssertThrowsError(
            try signalDecryptPreKey(
                message: incoming, from: alice, localAddress: bob, sessionStore: store, identityStore: store,
                preKeyStore: store, signedPreKeyStore: store, kyberPreKeyStore: store, context: context))
        let replies = try (0..<3).map { index in
            let message = try signalEncrypt(
                message: Data("Swift reply \(index) — río ☕".utf8), for: alice, localAddress: bob, sessionStore: store,
                identityStore: store, context: context)
            XCTAssertEqual(message.messageType, .whisper)
            return message.serialize().base64EncodedString()
        }
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(
            "swift-replies.json")
        try JSONSerialization.data(withJSONObject: ["messages": replies], options: [.sortedKeys]).write(
            to: output, options: .atomic)
    }
}
