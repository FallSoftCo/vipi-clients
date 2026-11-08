import Foundation
import XCTest
@testable import Vipi

/// Real native vaults and Signal sessions, with controlled transport failures.
@MainActor final class ChatRecoveryTests: XCTestCase {
    private final class Transport: ChatTransport {
        let profile: ChatProfile
        let staleReceipt: UUID, failedPeer: UUID
        let valid: [String: Any], poison: [String: Any]
        var pages: [String?] = [], acknowledged: [String] = []
        var blocked = false, failBlock = false
        init(profile: ChatProfile, staleReceipt: UUID, failedPeer: UUID, valid: [String: Any], poison: [String: Any]) {
            self.profile = profile; self.staleReceipt = staleReceipt; self.failedPeer = failedPeer
            self.valid = valid; self.poison = poison
        }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            if path.hasPrefix("/v1/people/by-id/") { throw ServiceFailure(status: 404, code: "recipient_unavailable") }
            if path.hasPrefix("/v1/blocks/") {
                if failBlock { throw ServiceFailure(status: 0, code: "offline") }
                if method == "PUT" {
                    let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                    blocked = try XCTUnwrap(input["blocked"] as? Bool)
                }
                return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: ["blocked": blocked]))
            }
            var value: [String: Any]
            switch path {
            case "/v1/me": return try JSONDecoder().decode(type, from: JSONEncoder().encode(profile))
            case "/v1/devices":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                value = ["id": input["device_id"]!, "active": true]
            case "/v1/keys": value = ["revision": 1, "remaining": 20]
            case "/v1/messages/pending":
                pages.append(query["after"])
                if query["after"] == nil { value = ["messages": [poison], "next_cursor": "controlled-next-page"] }
                else { XCTAssertEqual(query["after"], "controlled-next-page"); value = ["messages": [valid], "next_cursor": NSNull()] }
            case "/v1/messages":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(body)) as? [String: Any])
                if input["recipient_id"] as? String == failedPeer.uuidString.lowercased() { throw ServiceFailure(status: 404, code: "recipient_unavailable") }
                value = ["state": "accepted"]
            default:
                guard path.hasSuffix("/receipt") else { XCTFail("Unexpected request \(path)"); throw ServiceFailure(status: 500, code: "unexpected") }
                acknowledged.append(path)
                if path.contains(staleReceipt.uuidString.lowercased()) { throw ServiceFailure(status: 404, code: "message_not_found") }
                value = ["state": "delivered"]
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }
    func testPoisonPageExpiredReceiptAndUnavailablePeerDoNotBlockOtherMessages() async throws {
        let accounts = [UUID(), UUID(), UUID()], userID = "recovery-qa-" + UUID().uuidString
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages")
        defer {
            KeychainStore.delete(account: "profile-" + userID)
            for account in accounts {
                try? FileManager.default.removeItem(at: root.appendingPathComponent(account.uuidString.lowercased()))
                KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
            }
        }
        do {
            let vaults = try accounts.map { try MessageVault(account: $0) }
            let cores = try vaults.map { try MessagingCore(vault: $0) }
            let publications = try cores.map { try $0.keys.publication(now: now, count: 2) }
            for core in cores { try core.keys.published(revision: 1) }
            func establish(_ from: Int, _ to: Int, key: Int = 0) throws {
                let p = publications[to], request = UUID()
                _ = try cores[from].keys.establish(peer: accounts[to], requestID: request, response: ClaimedKeys(
                    request_id: request, user_id: accounts[to], device_id: cores[to].device.id, signal_device_id: 1,
                    registration_id: p.registration_id, identity_key: p.identity_key, signed: p.signed, one_time: p.one_time[key]))
            }
            try establish(1, 0)
            let old = try cores[1].queue(id: UUID(), peer: accounts[0], text: "Already stored before a long disconnection", createdAt: now, now: now)
            _ = try cores[0].receive(old, now: now)
            let fresh = try cores[1].queue(id: UUID(), peer: accounts[0], text: "A good message after an unreadable page", createdAt: now, now: now)
            try establish(0, 2)
            let firstID = UUID(uuidString: "00000000-0000-4000-8000-000000000001")!
            let secondID = UUID(uuidString: "00000000-0000-4000-8000-000000000002")!
            _ = try cores[0].queue(id: firstID, peer: accounts[1], text: "This recipient became unavailable", createdAt: now, now: now)
            _ = try cores[0].queue(id: secondID, peer: accounts[2], text: "This conversation should still send", createdAt: now, now: now)
            var received = try XCTUnwrap(JSONSerialization.jsonObject(with: fresh.sendData()) as? [String: Any])
            received["sender_id"] = accounts[1].uuidString; received["sender_device_id"] = cores[1].device.id.uuidString
            var poison = received; let poisonID = UUID(); poison["id"] = poisonID.uuidString
            let transport = Transport(profile: ChatProfile(id: accounts[0], username: "recovery_qa", display_name: "Recovery QA"),
                staleReceipt: old.envelope.id, failedPeer: accounts[1], valid: received, poison: poison)
            let chat = try ChatSession(api: transport, userID: userID)
            await chat.start()
            XCTAssertTrue(chat.ready)
            XCTAssertEqual(transport.pages.count, 2)
            XCTAssertNil(transport.pages[0]); XCTAssertEqual(transport.pages[1], "controlled-next-page")
            XCTAssertTrue(try chat.messages(accounts[1]).contains { $0.text == "A good message after an unreadable page" })
            XCTAssertEqual(try cores[0].journal.outgoing(firstID)?.state, "failed")
            XCTAssertEqual(try cores[0].journal.outgoing(secondID)?.state, "accepted")
            XCTAssertTrue(try cores[0].journal.pendingReceipts().isEmpty)
            XCTAssertEqual(transport.acknowledged.count, 2)
            XCTAssertFalse(transport.acknowledged.contains { $0.contains(poisonID.uuidString.lowercased()) })
            try chat.send("Queued before blocking", peer: accounts[2])
            let draftID = try XCTUnwrap(cores[0].journal.pendingDrafts(now: now).first?.id)
            try chat.saveCompose("Keep my unsent writing", peer: accounts[2])
            try await chat.setBlocked(true, peer: accounts[2])
            XCTAssertTrue(chat.blockedPeers.contains(accounts[2]))
            XCTAssertThrowsError(try chat.send("Must not queue", peer: accounts[2]))
            XCTAssertEqual(try cores[0].journal.draft(draftID)?.state, "cancelled")
            XCTAssertEqual(try cores[0].journal.outgoing(secondID)?.state, "cancelled")
            try cores[0].journal.applyStatus(secondID, state: "accepted")
            XCTAssertEqual(try cores[0].journal.outgoing(secondID)?.state, "cancelled")
            XCTAssertEqual(try chat.compose(accounts[2]), "Keep my unsent writing")
            let reopened = try ChatSession(api: transport, userID: userID)
            XCTAssertTrue(reopened.blockedPeers.contains(accounts[2]))
            transport.failBlock = true
            do { try await reopened.setBlocked(false, peer: accounts[2]); XCTFail("An offline request must not confirm unblock") }
            catch {}
            XCTAssertTrue(reopened.blockedPeers.contains(accounts[2]))
            transport.failBlock = false
            try await reopened.setBlocked(false, peer: accounts[2])
            XCTAssertFalse(reopened.blockedPeers.contains(accounts[2]))
            XCTAssertTrue(try cores[0].journal.pending(now: now).isEmpty)
            XCTAssertTrue(try cores[0].journal.pendingDrafts(now: now).isEmpty)
            try await chat.refreshBlock(accounts[2])
            XCTAssertFalse(chat.blockedPeers.contains(accounts[2]))
            try chat.send("A new message after unblocking", peer: accounts[2])
            XCTAssertEqual(try cores[0].journal.pendingDrafts(now: now).count, 1)
        }
    }
}

@MainActor final class DeviceRecoveryTests: XCTestCase {
    private final class Transport: ChatTransport {
        let profile: ChatProfile
        var active = UUID()
        var loseNextRegistrationResponse = false
        var recentAuthentication = true
        var registrations: [(UUID, Bool)] = []
        init(_ profile: ChatProfile) { self.profile = profile }
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            var reply: [String: Any]
            switch path {
            case "/v1/me": return try JSONDecoder().decode(type, from: JSONEncoder().encode(profile))
            case "/v1/devices":
                let data = try XCTUnwrap(body), input = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
                let id = try XCTUnwrap(UUID(uuidString: try XCTUnwrap(input["device_id"] as? String))), replacing = input["replace_active"] as? Bool ?? false
                registrations.append((id, replacing))
                guard id == active || replacing else { throw ServiceFailure(status: 409, code: "device_replacement_confirmation_required") }
                if replacing && !recentAuthentication { throw ServiceFailure(status: 403, code: "recent_sign_in_required") }
                active = id
                if loseNextRegistrationResponse { loseNextRegistrationResponse = false; throw URLError(.networkConnectionLost) }
                reply = ["id": id.uuidString.lowercased(), "active": true]
            case "/v1/keys":
                guard device?.id == active else { throw ServiceFailure(status: 401, code: "device_revoked") }
                reply = ["revision": 1, "remaining": 20]
            case "/v1/messages/pending": reply = ["messages": [], "next_cursor": NSNull()]
            default: throw ServiceFailure(status: 500, code: "unexpected")
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: reply))
        }
    }
    func testLostReplacementResponseReusesConsentButDisplacementRequiresNewConfirmation() async throws {
        let account = UUID(), user = "device-recovery-qa-" + UUID().uuidString
        let profile = ChatProfile(id: account, username: "device_recovery_qa", display_name: "Device recovery QA")
        let api = Transport(profile), chat = try ChatSession(api: api, userID: user)
        defer {
            try? chat.close(); KeychainStore.delete(account: "profile-" + user)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
            let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages/" + account.uuidString.lowercased())
            try? FileManager.default.removeItem(at: folder)
        }
        await chat.start()
        XCTAssertFalse(chat.ready); XCTAssertTrue(chat.needsDeviceReplacement)
        XCTAssertEqual(api.registrations.count, 1); XCTAssertFalse(api.registrations[0].1)
        let candidate = try chat.deviceReplacementCandidate(); api.loseNextRegistrationResponse = true
        do { try await chat.confirmDeviceReplacement(candidate); XCTFail("Lost response must remain uncertain") } catch {}
        XCTAssertFalse(chat.ready); XCTAssertEqual(api.active, candidate.device.id)
        await chat.start()
        XCTAssertTrue(chat.ready); XCTAssertFalse(chat.needsDeviceReplacement)
        XCTAssertEqual(Array(api.registrations.map { $0.0 }.suffix(2)), [candidate.device.id, candidate.device.id])
        XCTAssertTrue(api.registrations.suffix(2).allSatisfy { $0.1 })
        api.active = UUID()
        await chat.start()
        XCTAssertFalse(chat.ready); XCTAssertTrue(chat.needsDeviceReplacement)
        let count = api.registrations.count
        await chat.start()
        XCTAssertEqual(api.registrations.count, count, "A displaced device cannot retry takeover without a new confirmation")
        let next = try chat.deviceReplacementCandidate()
        XCTAssertNotEqual(next.device.id, candidate.device.id)
        try await chat.confirmDeviceReplacement(next)
        XCTAssertTrue(chat.ready); XCTAssertEqual(api.active, next.device.id)
    }
    func testExpiredAuthenticationKeepsConfirmedCandidateAcrossReopenAndFreshSignIn() async throws {
        let account = UUID(), user = "device-reauth-qa-" + UUID().uuidString
        let profile = ChatProfile(id: account, username: "device_reauth_qa", display_name: "Device reauth QA")
        let api = Transport(profile), chat = try ChatSession(api: api, userID: user)
        defer {
            try? chat.close(); KeychainStore.delete(account: "profile-" + user)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
            let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages/" + account.uuidString.lowercased())
            try? FileManager.default.removeItem(at: folder)
        }
        await chat.start()
        let candidate = try chat.deviceReplacementCandidate(), oldActive = api.active
        api.recentAuthentication = false
        do { try await chat.confirmDeviceReplacement(candidate); XCTFail("Old authentication must not replace the active device") }
        catch let error as ServiceFailure { XCTAssertEqual(error.code, "recent_sign_in_required") }
        XCTAssertEqual(api.active, oldActive)
        XCTAssertTrue(chat.needsRecentSignIn); XCTAssertTrue(chat.hasPendingDeviceReplacement)
        XCTAssertFalse(chat.needsDeviceReplacement); XCTAssertFalse(chat.ready)
        try chat.close()
        let reopened = try ChatSession(api: api, userID: user)
        defer { try? reopened.close() }
        XCTAssertTrue(reopened.hasPendingDeviceReplacement)
        await reopened.start()
        XCTAssertTrue(reopened.needsRecentSignIn); XCTAssertEqual(api.active, oldActive)
        api.recentAuthentication = true // Models a new provider-authenticated session, not a token refresh.
        try await reopened.resumeDeviceReplacement()
        XCTAssertTrue(reopened.ready); XCTAssertFalse(reopened.needsRecentSignIn)
        XCTAssertFalse(reopened.hasPendingDeviceReplacement); XCTAssertEqual(api.active, candidate.device.id)
        XCTAssertTrue(api.registrations.suffix(3).allSatisfy { $0.0 == candidate.device.id && $0.1 })
    }
}
