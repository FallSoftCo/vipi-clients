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
    func testReviewedPeerReplacementPreservesOldCiphertextAndRequiresExactKeys() throws {
        try recoveryFixture { vaults, cores, accounts, now in
            let old = try claim(cores[1], peer: accounts[1], now: now)
            _ = try cores[0].keys.establish(peer: accounts[1], requestID: old.request_id, response: old)
            let sent = try cores[0].queue(id: UUID(), peer: accounts[1], text: "Keep this old ciphertext", createdAt: now, now: now)
            _ = try cores[1].receive(sent, now: now)
            let oldIncoming = try cores[1].queue(id: UUID(), peer: accounts[0], text: "Already received from old device", createdAt: now, now: now)
            _ = try cores[0].receive(oldIncoming, now: now)
            let oldWaiting = try cores[1].queue(id: UUID(), peer: accounts[0], text: "Still waiting from old device", createdAt: now, now: now)
            let number = try XCTUnwrap(cores[0].securityNumber(peer: accounts[1]))
            try cores[0].setIdentityVerified(true, peer: accounts[1], compared: number)
            let draft = UUID(); try cores[0].journal.saveDraft(id: draft, recipient: accounts[1], text: "Do not silently resend", createdAt: now, now: now)
            let next = try claim(cores[2], peer: accounts[1], now: now)
            let review = try cores[0].keys.reviewReplacement(peer: accounts[1], requestID: next.request_id, response: next)
            XCTAssertTrue(try XCTUnwrap(cores[0].securityNumber(peer: accounts[1])).verified)
            let bad = ClaimedKeys(request_id: next.request_id, user_id: next.user_id, device_id: next.device_id, signal_device_id: 1,
                registration_id: next.registration_id, identity_key: next.identity_key,
                signed: SignedPublicKey(id: next.signed.id, key: next.signed.key, signature: Data(repeating: 0, count: 64)), one_time: next.one_time)
            XCTAssertThrowsError(try cores[0].keys.establish(peer: accounts[1], requestID: bad.request_id, response: bad, replacing: review))
            let wrongNumber = PeerIdentityChange(response: next, previousIdentity: review.previousIdentity, previousDevice: review.previousDevice,
                number: SecurityNumber(digits: String(repeating: "0", count: 60), binding: review.number.binding, verified: false))
            XCTAssertThrowsError(try cores[0].keys.establish(peer: accounts[1], requestID: next.request_id, response: next, replacing: wrongNumber))
            XCTAssertEqual(try cores[0].securityNumber(peer: accounts[1])?.digits, number.digits)
            XCTAssertEqual(try cores[0].journal.draft(draft)?.state, "queued")
            _ = try cores[0].keys.establish(peer: accounts[1], requestID: next.request_id, response: next, replacing: review)
            XCTAssertFalse(try XCTUnwrap(cores[0].securityNumber(peer: accounts[1])).verified)
            XCTAssertEqual(try cores[0].journal.draft(draft)?.state, "cancelled")
            let retained = try XCTUnwrap(cores[0].journal.outgoing(sent.envelope.id))
            XCTAssertEqual(retained.envelope.ciphertext, sent.envelope.ciphertext); XCTAssertEqual(retained.state, "failed")
            XCTAssertEqual(try vaults[0].transaction { try vaults[0].get("outgoing-route", sent.envelope.id.uuidString.lowercased()) }, Data(sent.recipientDevice.uuidString.lowercased().utf8))
            XCTAssertTrue(try cores[0].journal.pending(now: now).isEmpty)
            XCTAssertThrowsError(try cores[0].queue(id: sent.envelope.id, peer: accounts[1], text: "Keep this old ciphertext", createdAt: now, now: now))
            XCTAssertNotNil(try vaults[0].transaction { try vaults[0].get("key-claim", old.request_id.uuidString.lowercased()) })
            let fresh = try cores[0].queue(id: UUID(), peer: accounts[1], text: "Explicit new keys", createdAt: now, now: now)
            XCTAssertEqual(fresh.recipientDevice, cores[2].device.id)
            XCTAssertEqual(try cores[2].receive(fresh, now: now).text, "Explicit new keys")
            XCTAssertEqual(try cores[0].receive(oldIncoming, now: now).text, "Already received from old device")
            XCTAssertThrowsError(try cores[0].receive(oldWaiting, now: now)) { error in
                guard case DurableSignalStore.Failure.retiredDevice = error else { return XCTFail("Old device was not classified as retired") }
            }
            let forgedRoute = RoutedMessage(envelope: oldIncoming.envelope, senderDevice: cores[2].device.id, recipientDevice: oldIncoming.recipientDevice)
            XCTAssertThrowsError(try cores[0].receive(forgedRoute, now: now))
            XCTAssertThrowsError(try cores[0].keys.establish(peer: accounts[1], requestID: next.request_id, response: next, replacing: review))
        }
    }
    func testOwnReplacementRotatesOnlyLocalProtocolStateAndTerminatesOldSends() throws {
        try recoveryFixture { vaults, cores, accounts, now in
            let old = try claim(cores[1], peer: accounts[1], now: now)
            _ = try cores[0].keys.establish(peer: accounts[1], requestID: old.request_id, response: old)
            let sent = try cores[0].queue(id: UUID(), peer: accounts[1], text: "Keep saved history", createdAt: now, now: now)
            let number = try XCTUnwrap(cores[0].securityNumber(peer: accounts[1]))
            try cores[0].setIdentityVerified(true, peer: accounts[1], compared: number)
            let draft = UUID(); try cores[0].journal.saveDraft(id: draft, recipient: accounts[1], text: "Old pending draft", createdAt: now, now: now)
            let candidate = try cores[0].replacementCandidate()
            try cores[0].confirmDeviceReplacement(candidate)
            let reopened = try MessagingCore(vault: vaults[0])
            XCTAssertEqual(reopened.device.id, candidate.device.id); XCTAssertNotEqual(reopened.device.id, cores[0].device.id)
            XCTAssertFalse(try reopened.hasSession(peer: accounts[1]))
            XCTAssertEqual(try reopened.journal.outgoing(sent.envelope.id)?.text, "Keep saved history")
            XCTAssertEqual(try reopened.journal.outgoing(sent.envelope.id)?.state, "failed")
            XCTAssertEqual(try reopened.journal.draft(draft)?.state, "cancelled")
            XCTAssertTrue(try reopened.journal.pending(now: now).isEmpty)
            XCTAssertFalse(try XCTUnwrap(reopened.securityNumber(peer: accounts[1])).verified)
            XCTAssertNotEqual(try reopened.securityNumber(peer: accounts[1])?.digits, number.digits)
            try vaults[0].transaction {
                XCTAssertEqual(try vaults[0].get("identity", accounts[1].uuidString.lowercased() + "/1"), old.identity_key)
                XCTAssertEqual(try vaults[0].get("outgoing-route", sent.envelope.id.uuidString.lowercased()), Data(sent.recipientDevice.uuidString.lowercased().utf8))
                XCTAssertEqual(try vaults[0].get("local", "replacement-consent"), Data(candidate.device.id.uuidString.lowercased().utf8))
                XCTAssertNotNil(try vaults[0].get("key-claim", old.request_id.uuidString.lowercased()))
            }
            let changedPeer = try claim(cores[2], peer: accounts[1], now: now)
            XCTAssertThrowsError(try reopened.keys.establish(peer: accounts[1], requestID: changedPeer.request_id, response: changedPeer)) { error in
                guard case DurableSignalStore.Failure.identityChanged = error else { return XCTFail("Own rotation must retain peer trust") }
            }
            XCTAssertThrowsError(try cores[0].confirmDeviceReplacement(candidate))
        }
    }
    private func claim(_ core: MessagingCore, peer: UUID, now: Int64) throws -> ClaimedKeys {
        let p = try core.keys.publication(now: now, count: 2)
        return ClaimedKeys(request_id: UUID(), user_id: peer, device_id: core.device.id, signal_device_id: 1,
            registration_id: p.registration_id, identity_key: p.identity_key, signed: p.signed, one_time: p.one_time[0])
    }
    private func recoveryFixture(_ body: ([MessageVault], [MessagingCore], [UUID], Int64) throws -> Void) throws {
        let alice = UUID(), bob = UUID(), accounts = [alice, bob, bob]
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("identity-recovery-" + UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: root)
            for id in [alice, bob] { KeychainStore.delete(account: "messages-" + id.uuidString.lowercased()) }
        }
        let vaults = try accounts.enumerated().map { try MessageVault(account: $0.element, directory: root.appendingPathComponent(String($0.offset))) }
        defer { for vault in vaults { try? vault.close() } }
        try body(vaults, vaults.map { try MessagingCore(vault: $0) }, accounts, Int64(Date().timeIntervalSince1970 * 1000))
    }

}
