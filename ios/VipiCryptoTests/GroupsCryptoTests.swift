import Foundation
import XCTest
@testable import Vipi

final class GroupsCryptoTests: XCTestCase {
    private final class Fixture {
        let accounts: [UUID]
        let vaults: [MessageVault]
        let cores: [MessagingCore]
        let now: Int64
        let directory: URL
        init(_ count: Int) throws {
            let ids = (0..<count).map { _ in UUID() }, root = FileManager.default.temporaryDirectory.appendingPathComponent("groups-crypto-" + UUID().uuidString)
            var stores: [MessageVault] = []
            let engines: [MessagingCore]
            do {
                for (index, id) in ids.enumerated() { stores.append(try MessageVault(account: id, directory: root.appendingPathComponent(String(index)))) }
                engines = try stores.map { try MessagingCore(vault: $0) }
            } catch {
                for vault in stores { try? vault.close() }; try? FileManager.default.removeItem(at: root)
                for id in ids { KeychainStore.delete(account: "messages-" + id.uuidString.lowercased()) }; throw error
            }
            accounts = ids; directory = root; now = Int64(Date().timeIntervalSince1970 * 1000); vaults = stores; cores = engines
            for peer in 1..<count {
                let publication = try cores[peer].keys.publication(now: now, count: 1), request = UUID()
                let claim = ClaimedKeys(request_id: request, user_id: accounts[peer], device_id: cores[peer].device.id, signal_device_id: 1,
                    registration_id: publication.registration_id, identity_key: publication.identity_key, signed: publication.signed, one_time: publication.one_time[0])
                _ = try cores[0].keys.establish(peer: accounts[peer], requestID: request, response: claim)
                let hello = try cores[0].queue(id: UUID(), peer: accounts[peer], text: "Private conversation establishes the existing identity", createdAt: now, now: now)
                _ = try cores[peer].receive(hello, now: now)
                let reply = try cores[peer].queue(id: UUID(), peer: accounts[0], text: "Identity already known", createdAt: now, now: now)
                _ = try cores[0].receive(reply, now: now)
            }
        }
        deinit {
            for vault in vaults { try? vault.close() }
            try? FileManager.default.removeItem(at: directory)
            for account in accounts { KeychainStore.delete(account: "messages-" + account.uuidString.lowercased()) }
        }
        func person(_ index: Int, device: UUID? = nil) -> GroupMember {
            .init(user_id: accounts[index], display_name: "Person \(index)", username: "person_\(index)", role: index == 0 ? .owner : .member, joined_epoch: 1, device_id: device ?? cores[index].device.id)
        }
        func owner(_ group: UUID) -> GroupSnapshot { .init(id: group, title: "Friends", epoch: 1, state: "active", members: [person(0)], invitations: []) }
        func roster(_ group: UUID) -> GroupSnapshot { .init(id: group, title: "Friends", epoch: accounts.count * 2 - 1, state: "active", members: accounts.indices.map { person($0) }, invitations: []) }
        func add(_ group: UUID, _ index: Int) -> GroupRosterTransition {
            let previous = (0..<index).map { GroupApprovedPerson(user_id: accounts[$0], role: $0 == 0 ? .owner : .member) }
            return .init(actor_id: accounts[0], action: .add, target_id: accounts[index], from_revision: index, to_revision: index + 1, server_epoch: index * 2 + 1,
                previous_members: previous, members: previous + [.init(user_id: accounts[index], role: .member)])
        }
        func incoming(_ fanout: GroupFanout, recipient: Int, kind: String) throws -> GroupIncoming {
            let body = try JSONSerialization.jsonObject(with: fanout.body) as! [String: Any]
            let envelope = (body["envelopes"] as! [[String: Any]]).first { ($0["recipient_id"] as? String) == accounts[recipient].uuidString.lowercased() }!
            var wire = envelope
            wire["sender_id"] = accounts[0].uuidString.lowercased(); wire["sender_device_id"] = cores[0].device.id.uuidString.lowercased()
            wire["created_at"] = body["created_at"]; wire["group_id"] = fanout.groupID.uuidString.lowercased()
            wire["group_epoch"] = fanout.epoch; wire["group_message_id"] = fanout.messageID.uuidString.lowercased(); wire["group_kind"] = kind
            return try JSONDecoder().decode(GroupIncoming.self, from: JSONSerialization.data(withJSONObject: wire))
        }
        func admitted(_ fanout: GroupFanout) throws -> GroupFanout.Acceptance {
            // Synthetic HTTP admission fixture, not server/transport qualification.
            let body = try JSONSerialization.jsonObject(with: fanout.body) as! [String: Any]
            let deliveries = (body["envelopes"] as! [[String: Any]]).map { ["id": $0["id"]!, "state": "accepted", "expires_at": "2026-12-01T00:00:00Z"] }
            return try JSONDecoder().decode(GroupFanout.Acceptance.self, from: JSONSerialization.data(withJSONObject: ["id": fanout.messageID.uuidString.lowercased(), "group_id": fanout.groupID.uuidString.lowercased(), "epoch": fanout.epoch, "admitted": true, "deliveries": deliveries]))
        }
    }
    func testPairwiseControlBootstrapAndExactDataRetry() throws {
        let f = try Fixture(2), group = UUID()
        let membership = GroupsMembership(vault: f.vaults[0]); try membership.createdLocally(f.owner(group), expectedID: group)
        let aliceControl = GroupsControlCrypto(vault: f.vaults[0], core: f.cores[0]), bobControl = GroupsControlCrypto(vault: f.vaults[1], core: f.cores[1])
        let control = try aliceControl.prepare(id: UUID(), roster: f.roster(group), change: f.add(group, 1), now: f.now)
        try bobControl.receive(f.incoming(control, recipient: 1, kind: "control"), now: f.now)
        let bobMembership = GroupsMembership(vault: f.vaults[1]); XCTAssertNil(try bobMembership.current(group))
        let pending = try XCTUnwrap(bobControl.pending().first); try bobControl.confirmBootstrap(pending)
        XCTAssertEqual(try bobMembership.current(group)?.revision, 2)
        XCTAssertNotNil(try f.vaults[1].transaction { try bobMembership.historyInTransaction(group, revision: 1) })
        try aliceControl.accepted(f.admitted(control), fanout: control); try aliceControl.reconciled(control)
        let alice = GroupsCrypto(vault: f.vaults[0], core: f.cores[0], store: GroupsStore(vault: f.vaults[0]))
        let bob = GroupsCrypto(vault: f.vaults[1], core: f.cores[1], store: GroupsStore(vault: f.vaults[1]))
        let message = GroupMessage(id: UUID(), groupID: group, epoch: 3, membershipRevision: 2, sender: f.accounts[0], text: "Hello, こんにちは 🌍", createdAt: f.now, delivery: .queued)
        let first = try alice.prepare(message, roster: f.roster(group), now: f.now)
        XCTAssertEqual(try alice.prepare(message, roster: f.roster(group), now: f.now + 1_000).body, first.body)
        let incoming = try f.incoming(first, recipient: 1, kind: "message")
        let received = try XCTUnwrap(bob.receive(incoming, now: f.now)); XCTAssertEqual(received.text, message.text); XCTAssertEqual(received.delivery, .received)
        XCTAssertEqual(try bob.receive(incoming, now: f.now), received)
        XCTAssertEqual(try bob.receipts().filter { $0 == incoming.id }.count, 1)
        XCTAssertFalse(try f.cores[1].journal.pendingReceipts().contains(incoming.id))
        let altered = GroupMessage(id: message.id, groupID: group, epoch: 3, membershipRevision: 2, sender: message.sender, text: "Different original text", createdAt: f.now, delivery: .queued)
        XCTAssertThrowsError(try alice.prepare(altered, roster: f.roster(group), now: f.now))
    }
    func testRecipientFailureRollsBackEveryRatchetAndFanout() throws {
        let f = try Fixture(3), group = UUID(), membership = GroupsMembership(vault: f.vaults[0])
        try membership.createdLocally(f.owner(group), expectedID: group)
        try f.vaults[0].transaction { try membership.applyInTransaction(f.add(group, 1), group: group, authenticatedSender: f.accounts[0]); try membership.applyInTransaction(f.add(group, 2), group: group, authenticatedSender: f.accounts[0]) }
        let key = f.accounts[1].uuidString.lowercased() + "/1"
        let before = try f.vaults[0].transaction { try f.vaults[0].get("session", key) }
        let eve = f.person(2)
        let unavailable = GroupMember(user_id: eve.id, display_name: eve.display_name, username: eve.username, role: .member, joined_epoch: 1, device_id: nil)
        let roster = GroupSnapshot(id: group, title: "Friends", epoch: 5, state: "active", members: [f.person(0), f.person(1), unavailable], invitations: [])
        let message = GroupMessage(id: UUID(), groupID: group, epoch: 5, membershipRevision: 3, sender: f.accounts[0], text: "All recipients or none", createdAt: f.now, delivery: .queued)
        let crypto = GroupsCrypto(vault: f.vaults[0], core: f.cores[0], store: GroupsStore(vault: f.vaults[0]))
        XCTAssertThrowsError(try crypto.prepare(message, roster: roster, now: f.now))
        XCTAssertEqual(try f.vaults[0].transaction { try f.vaults[0].get("session", key) }, before)
        XCTAssertNil(try crypto.pending(group, message.id)); XCTAssertTrue(try GroupsStore(vault: f.vaults[0]).messages(group).isEmpty)
    }
    func testUnknownIdentityHoldSurvivesExpiryAndPromotionRequiresContinuity() throws {
        let f = try Fixture(2), group = UUID(), aliceMembership = GroupsMembership(vault: f.vaults[0])
        try aliceMembership.createdLocally(f.owner(group), expectedID: group)
        try f.vaults[0].transaction { try aliceMembership.applyInTransaction(f.add(group, 1), group: group, authenticatedSender: f.accounts[0]) }
        let sender = GroupsCrypto(vault: f.vaults[0], core: f.cores[0], store: GroupsStore(vault: f.vaults[0]))
        let store = GroupsStore(vault: f.vaults[1]), receiver = GroupsCrypto(vault: f.vaults[1], core: f.cores[1], store: GroupsStore(vault: f.vaults[1]))
        let message = GroupMessage(id: UUID(), groupID: group, epoch: 3, membershipRevision: 2, sender: f.accounts[0], text: "Saved safely until review", createdAt: f.now, delivery: .queued)
        let fanout = try sender.prepare(message, roster: f.roster(group), now: f.now), incoming = try f.incoming(fanout, recipient: 1, kind: "message")
        let peer = f.accounts[0].uuidString.lowercased(), identityID = peer + "/1"
        let pin = try XCTUnwrap(f.vaults[1].transaction { try f.vaults[1].get("identity", identityID) })
        let session = try f.vaults[1].transaction { try f.vaults[1].get("session", identityID) }
        try f.vaults[1].transaction { try f.vaults[1].remove("identity", identityID) }
        XCTAssertNil(try receiver.receive(incoming, now: f.now))
        XCTAssertNil(try receiver.receive(incoming, now: f.now + MessageJournal.ttl + 1))
        XCTAssertEqual(try f.vaults[1].transaction { try f.vaults[1].get("session", identityID) }, session)
        XCTAssertTrue(try receiver.receipts().isEmpty); XCTAssertEqual(try receiver.heldEnvelopes().count, 1)
        try f.vaults[1].transaction { try f.vaults[1].put("identity", identityID, pin) }
        let held = try XCTUnwrap(receiver.receive(incoming, now: f.now + MessageJournal.ttl + 1))
        XCTAssertEqual(held.delivery, .withheld); XCTAssertEqual(try store.unread(group, account: f.accounts[1]), 0)
        // The encrypted-control path is exercised above. This isolated trusted
        // policy call lets this test vary the later local continuity boundary.
        let approved = GroupsMembership(vault: f.vaults[1])
        try f.vaults[1].transaction { try approved.bootstrapInTransaction(f.add(group, 1), group: group, authenticatedSender: f.accounts[0], confirmedInviter: f.accounts[0]); try f.vaults[1].put("blocked", peer, Data([1])) }
        XCTAssertTrue(try receiver.releaseAuthorized(group).isEmpty)
        try f.vaults[1].transaction { try f.vaults[1].remove("blocked", peer); try f.vaults[1].put("identity-change", peer, Data([1])) }
        XCTAssertTrue(try receiver.releaseAuthorized(group).isEmpty)
        try f.vaults[1].transaction { try f.vaults[1].remove("identity-change", peer); try f.vaults[1].put("retired-peer-device", peer + "/" + f.cores[0].device.id.uuidString.lowercased(), Data([1])) }
        XCTAssertTrue(try receiver.releaseAuthorized(group).isEmpty)
        try f.vaults[1].transaction { try f.vaults[1].remove("retired-peer-device", peer + "/" + f.cores[0].device.id.uuidString.lowercased()) }
        XCTAssertEqual(try receiver.releaseAuthorized(group).map(\.id), [message.id])
        XCTAssertEqual(try store.unread(group, account: f.accounts[1]), 1)
        XCTAssertTrue(try f.vaults[1].transaction { try f.vaults[1].ids("group-hold-budget").isEmpty })
    }

    func testInactiveDeviceCanBeRemovedWithoutRelaxingDataOrBootstrap() throws {
        let f = try Fixture(3), group = UUID(), owner = GroupsMembership(vault: f.vaults[0])
        try owner.createdLocally(f.owner(group), expectedID: group)
        // Known authenticated history is the policy fixture. The new approval
        // and removal below use actual pinned Signal ciphertext and bootstrap.
        try f.vaults[0].transaction { try owner.applyInTransaction(f.add(group, 1), group: group, authenticatedSender: f.accounts[0]) }
        let sendControl = GroupsControlCrypto(vault: f.vaults[0], core: f.cores[0])
        let receiveControl = GroupsControlCrypto(vault: f.vaults[2], core: f.cores[2])
        let join = try sendControl.prepare(id: UUID(), roster: f.roster(group), change: f.add(group, 2), now: f.now)
        try receiveControl.receive(f.incoming(join, recipient: 2, kind: "control"), now: f.now)
        try receiveControl.confirmBootstrap(XCTUnwrap(receiveControl.pending().first))
        try sendControl.accepted(f.admitted(join), fanout: join); try sendControl.reconciled(join)
        let bob = f.person(1)
        let inactive = GroupMember(user_id: bob.id, display_name: bob.display_name, username: bob.username, role: bob.role, joined_epoch: bob.joined_epoch, device_id: nil)
        let proposal = GroupSnapshot(id: group, title: "Friends", epoch: 5, state: "active", members: [f.person(0), inactive, f.person(2)], invitations: [])
        let sender = GroupsCrypto(vault: f.vaults[0], core: f.cores[0], store: GroupsStore(vault: f.vaults[0]))
        let before = GroupMessage(id: UUID(), groupID: group, epoch: 5, membershipRevision: 3, sender: f.accounts[0], text: "Everyone must receive ordinary data", createdAt: f.now, delivery: .queued)
        XCTAssertThrowsError(try sender.prepare(before, roster: proposal, now: f.now))
        let approved = try XCTUnwrap(owner.current(group))
        let remove = GroupRosterTransition(actor_id: f.accounts[0], action: .remove, target_id: f.accounts[1], from_revision: 3, to_revision: 4,
            server_epoch: 6, previous_members: approved.members, members: approved.members.filter { $0.user_id != f.accounts[1] })
        let removal = try sendControl.prepare(id: UUID(), roster: proposal, change: remove, now: f.now)
        let wire = try JSONSerialization.jsonObject(with: removal.body) as! [String: Any]
        XCTAssertEqual((wire["envelopes"] as! [[String: Any]]).map { $0["recipient_id"] as! String }, [f.accounts[2].uuidString.lowercased()])
        try receiveControl.receive(f.incoming(removal, recipient: 2, kind: "control"), now: f.now)
        try sendControl.accepted(f.admitted(removal), fanout: removal); try sendControl.reconciled(removal)
        XCTAssertFalse(try XCTUnwrap(GroupsMembership(vault: f.vaults[2]).current(group)).contains(f.accounts[1]))
        let after = GroupSnapshot(id: group, title: "Friends", epoch: 6, state: "active", members: [f.person(0), f.person(2)], invitations: [])
        let fresh = GroupMessage(id: UUID(), groupID: group, epoch: 6, membershipRevision: 4, sender: f.accounts[0], text: "Only the approved remaining people", createdAt: f.now, delivery: .queued)
        let data = try sender.prepare(fresh, roster: after, now: f.now)
        let carol = GroupsCrypto(vault: f.vaults[2], core: f.cores[2], store: GroupsStore(vault: f.vaults[2]))
        XCTAssertEqual(try carol.receive(f.incoming(data, recipient: 2, kind: "message"), now: f.now)?.text, fresh.text)
        XCTAssertNil(try sender.pending(group, before.id))
    }

}
