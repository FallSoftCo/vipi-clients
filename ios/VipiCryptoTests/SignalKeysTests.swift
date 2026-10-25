import Foundation
import XCTest
import LibSignalClient
@testable import Vipi

final class SignalKeysTests: XCTestCase {
    func testDurablePublicationAndValidatedSession() throws {
        let now = Int64(Date().timeIntervalSince1970 * 1000), alice = UUID(), bob = UUID(), device = UUID(), request = UUID()
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("KeyDirectoryQA/\(UUID())")
        let bobRoot = root.appendingPathComponent("bob"), aliceRoot = root.appendingPathComponent("alice")
        let publication: KeyPublication
        do { let vault = try MessageVault(account: bob, directory: bobRoot); publication = try SignalKeys(store: DurableSignalStore(vault: vault)).publication(now: now, count: 3) }
        do {
            let vault = try MessageVault(account: bob, directory: bobRoot), keys = try SignalKeys(store: DurableSignalStore(vault: vault))
            let again = try keys.publication(now: now + 1)
            XCTAssertEqual(publication.one_time[0].key, again.one_time[0].key)
            XCTAssertEqual(publication.revision, again.revision)
            XCTAssertThrowsError(try keys.published(revision: 2))
            try keys.published(revision: 1); try keys.published(revision: 1)
            let next = try keys.publication(now: now + 1, count: 2)
            XCTAssertEqual(next.revision, 2); XCTAssertEqual(next.one_time[0].id, 4)
            XCTAssertEqual(next.signed.signature, publication.signed.signature)
        }
        let response = ClaimedKeys(request_id: request, user_id: bob, device_id: device, signal_device_id: 1,
            registration_id: publication.registration_id, identity_key: publication.identity_key, signed: publication.signed, one_time: publication.one_time[0])
        let aliceAddress = try ProtocolAddress(name: alice.uuidString.lowercased(), deviceId: 1), bobAddress = try ProtocolAddress(name: bob.uuidString.lowercased(), deviceId: 1)
        let context = NullContext(), envelope: ChatEnvelope
        do {
            let vault = try MessageVault(account: alice, directory: aliceRoot), store = try DurableSignalStore(vault: vault), keys = SignalKeys(store: store)
            for field in ["signed", "one_time"] {
                var broken = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(response)) as? [String: Any])
                var key = try XCTUnwrap(broken[field] as? [String: Any]); key["signature"] = Data(repeating: 0, count: 64).base64EncodedString(); broken[field] = key
                let value = try JSONDecoder().decode(ClaimedKeys.self, from: JSONSerialization.data(withJSONObject: broken))
                XCTAssertThrowsError(try keys.establish(peer: bob, requestID: request, response: value))
                XCTAssertNil(try vault.transaction { try store.loadSession(for: bobAddress, context: context) })
            }
            XCTAssertEqual(try keys.establish(peer: bob, requestID: request, response: response), device)
            envelope = try MessageJournal(vault: vault).queue(id: UUID(), recipient: bob, text: "Real keys, local voices — café ☕", createdAt: now, now: now) {
                let cipher = try signalEncrypt(message: $0, for: bobAddress, localAddress: aliceAddress, sessionStore: store, identityStore: store, context: context)
                return (Int(cipher.messageType.rawValue), cipher.serialize())
            }
            let ratchet = try vault.transaction { try XCTUnwrap(store.loadSession(for: bobAddress, context: context)).serialize() }
            XCTAssertEqual(try keys.establish(peer: bob, requestID: request, response: response), device)
            XCTAssertEqual(ratchet, try vault.transaction { try XCTUnwrap(store.loadSession(for: bobAddress, context: context)).serialize() })
            XCTAssertThrowsError(try keys.establish(peer: bob, requestID: UUID(), response: response))
        }
        do {
            let vault = try MessageVault(account: bob, directory: bobRoot), store = try DurableSignalStore(vault: vault)
            let received = try MessageJournal(vault: vault).receive(envelope, now: now) { type, bytes in
                XCTAssertEqual(type, 3)
                return try signalDecryptPreKey(message: PreKeySignalMessage(bytes: bytes), from: aliceAddress, localAddress: bobAddress, sessionStore: store, identityStore: store, preKeyStore: store, signedPreKeyStore: store, kyberPreKeyStore: store, context: context)
            }
            XCTAssertEqual(received.text, "Real keys, local voices — café ☕")
            try vault.transaction {
                XCTAssertThrowsError(try store.loadPreKey(id: 1, context: context))
                XCTAssertThrowsError(try store.loadKyberPreKey(id: 1, context: context))
            }
        }
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("public-key-publication.json")
        try JSONEncoder().encode(publication).write(to: file, options: .atomic)
    }
}
