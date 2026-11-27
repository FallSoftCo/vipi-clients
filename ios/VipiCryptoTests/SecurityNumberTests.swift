import Foundation
import LibSignalClient
import XCTest
@testable import Vipi

final class SecurityNumberTests: XCTestCase {
    // Public test keys from Signal's NumericFingerprintGeneratorTest, v0.105.0
    // (Signal Messenger, LLC; AGPL-3.0-only). No user keys or phone numbers.
    private func key(_ hex: String) throws -> IdentityKey {
        try IdentityKey(
            bytes: Data(
                stride(from: 0, to: hex.count, by: 2).map {
                    UInt8(hex.dropFirst($0).prefix(2), radix: 16)!
                }))
    }
    func testCrossPlatformVectorAndIdentifierBinding() throws {
        let alice = UUID(uuidString: "10000000-0000-4000-8000-000000000001")!
        let bob = UUID(uuidString: "10000000-0000-4000-8000-000000000002")!
        let a = try key("0506863bc66d02b40d27b8d49ca7c09e9239236f9d7d25d6fcca5ce13c7064d868")
        let b = try key("05f781b6fb32fed9ba1cf2de978d4d5da28dc34046ae814402b5c0dbd96fda907b")
        let start = Date()
        let first = try SecurityNumber.make(local: alice, localKey: a, peer: bob, peerKey: b, receipt: nil)
        let ms = Date().timeIntervalSince(start) * 1000
        let second = try SecurityNumber.make(local: bob, localKey: b, peer: alice, peerKey: a, receipt: nil)
        XCTAssertEqual(first.digits, second.digits)
        XCTAssertEqual(first.groups.count, 12)
        XCTAssertTrue(first.groups.allSatisfy { $0.count == 5 })
        XCTAssertFalse(first.verified)
        XCTAssertNotEqual(
            first.digits,
            try SecurityNumber.make(local: alice, localKey: a, peer: UUID(), peerKey: b, receipt: nil).digits)
        XCTAssertNotEqual(
            first.digits, try SecurityNumber.make(local: alice, localKey: a, peer: bob, peerKey: a, receipt: nil).digits
        )
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        try JSONSerialization.data(
            withJSONObject: [
                "purpose": "SYNTHETIC PUBLIC KEY VECTOR", "digits": first.digits,
                "binding_hex": first.binding.map { String(format: "%02x", $0) }.joined(), "generation_ms": ms,
                "iterations": 5200, "version": 2
            ], options: [.sortedKeys]
        )
        .write(to: root.appendingPathComponent("security-number-vector-ios.json"), options: .atomic)
    }
    func testVerificationPersistsAndNeverSurvivesDifferentKeys() throws {
        let account = UUID(), peer = UUID()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("security-number-" + UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        try exercisePersistence(account: account, peer: peer, root: root)
    }
    private func exercisePersistence(account: UUID, peer: UUID, root: URL) throws {
        let vault = try MessageVault(account: account, directory: root), core = try MessagingCore(vault: vault)
        XCTAssertNil(try core.securityNumber(peer: peer))
        let address = try ProtocolAddress(name: peer.uuidString.lowercased(), deviceId: 1)
        try vault.transaction {
            _ = try core.store.saveIdentity(
                IdentityKeyPair.generate().identityKey, for: address, context: NullContext())
        }
        let original = try XCTUnwrap(core.securityNumber(peer: peer))
        XCTAssertFalse(original.verified)
        try core.setIdentityVerified(true, peer: peer, compared: original)
        let reopened = try MessagingCore(vault: MessageVault(account: account, directory: root))
        XCTAssertTrue(try XCTUnwrap(reopened.securityNumber(peer: peer)).verified)
        try core.setIdentityVerified(false, peer: peer, compared: original)
        XCTAssertFalse(try XCTUnwrap(reopened.securityNumber(peer: peer)).verified)
        try core.setIdentityVerified(true, peer: peer, compared: original)
        // Simulate a future explicitly accepted replacement; production trust
        // callbacks still reject changed identities rather than performing this.
        try vault.transaction {
            try vault.put(
                "identity", peer.uuidString.lowercased() + "/1", IdentityKeyPair.generate().identityKey.serialize())
        }
        let changed = try XCTUnwrap(core.securityNumber(peer: peer))
        XCTAssertFalse(changed.verified)
        XCTAssertNotEqual(original.digits, changed.digits)
        XCTAssertThrowsError(try core.setIdentityVerified(true, peer: peer, compared: original))
        let forged = SecurityNumber(
            digits: String(repeating: "0", count: 60), binding: changed.binding, verified: false)
        XCTAssertThrowsError(try core.setIdentityVerified(true, peer: peer, compared: forged))
        try core.setIdentityVerified(true, peer: peer, compared: changed)
        try vault.transaction { try vault.put("local", "identity", IdentityKeyPair.generate().serialize()) }
        XCTAssertFalse(try XCTUnwrap(core.securityNumber(peer: peer)).verified)
        XCTAssertThrowsError(try core.setIdentityVerified(true, peer: peer, compared: changed))
    }
}
