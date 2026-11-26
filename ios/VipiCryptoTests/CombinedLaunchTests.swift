import AVFoundation
import CryptoKit
import UIKit
import XCTest
@testable import Vipi

/// One regular iOS client against two independent native peers on an explicitly
/// supplied synthetic relay. Stages reuse the same vault, ratchets and group.
@MainActor final class CombinedLaunchTests: XCTestCase {
    private enum Stage: String, Decodable {
        case profile, invite, verify, remove, preview, voice
        case signedInvitation = "signed-invitation"
        case approveAndroid = "approve-android"
        case approveMember = "approve-member"
        case introduceMember = "introduce-member"
    }
    private struct Account: Decodable, ChatAccessTokenSource {
        let subject, username, display_name, access_token: String
        func accessToken(for userID: String, rejected: String?) async throws -> String {
            guard userID == subject, rejected == nil else { throw AuthenticationManager.SessionFailure.signInRequired }
            return access_token
        }
    }
    private struct Fixture: Decodable {
        let endpoint: URL
        let account: Account
        let android, member: String
        let stage: Stage
    }
    private struct Peers {
        let android, member: UUID
    }
    private typealias Receipt = [String: String]

    func testThreeMemberMessagingAndPreview() async throws {
        continueAfterFailure = false
        guard FileManager.default.fileExists(atPath: file("config").path) else {
            throw XCTSkip("Supply private groups-combined-config.json for the signed native-pair fixture")
        }
        let config = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: file("config")))
        guard config.endpoint.scheme == "http", config.endpoint.host == "127.0.0.1", config.endpoint.port != nil,
              config.endpoint.user == nil, config.endpoint.password == nil, config.endpoint.query == nil,
              config.endpoint.path.isEmpty, config.account.subject.hasPrefix("user_localpair_"),
              config.account.username.hasPrefix("vqa_"), config.android != config.member,
              [config.android, config.member].allSatisfy({ FriendLookupUsername.normalize($0) == $0 }) else {
            throw GroupsFailure.invalidResponse
        }
        let result = file(config.stage.rawValue)
        guard !FileManager.default.fileExists(atPath: result.path) else { throw XCTSkip("This stage already completed") }
        // A partial external admission must be reconciled before another dispatch.
        try Data().write(to: file(config.stage.rawValue + "-intent"), options: .withoutOverwriting)
        let record: Receipt
        if config.stage == .preview {
            // Opening a chat session here would drain the message before the extension.
            record = try await preview(endpoint: config.endpoint)
        } else if config.stage == .signedInvitation {
            record = try await signedInvitation(config)
        } else {
            let api = try ServiceClient(authentication: config.account, userID: config.account.subject, endpoint: config.endpoint)
            let chat = try ChatSession(api: api, userID: config.account.subject)
            defer { try? chat.close() }
            await chat.start()
            if config.stage == .profile {
                guard chat.needsProfile else { throw GroupsFailure.retryRequiresReview }
                await chat.createProfile(username: config.account.username, name: config.account.display_name)
            }
            let account = try XCTUnwrap(chat.profile)
            let device = try chat.identityLinkTarget(expectedUser: config.account.subject).device
            let groups = try XCTUnwrap(chat.groups)
            XCTAssertEqual(account.username, config.account.username)
            XCTAssertTrue(chat.ready && api.acceptsGroupEnvelopes)
            let identity = ["account": account.id.uuidString.lowercased(), "device": device.id.uuidString.lowercased()]
            if config.stage == .profile {
                try chat.setOutsidePreviews(true)
                try await chat.registerPush(token: String(repeating: "ab", count: 32), environment: "sandbox")
                record = identity
            } else {
                XCTAssertEqual(try read("profile"), identity, "Preserve the original device and crypto state")
                let android = try await chat.find(config.android)
                let member = try await chat.find(config.member)
                let peers = Peers(android: android.id, member: member.id)
                let evidence = try await conversation(config.stage, chat: chat, groups: groups, peers: peers, account: account.id)
                record = identity.merging(evidence) { original, _ in original }
            }
        }
        try JSONEncoder().encode(record).write(to: result, options: .withoutOverwriting)
    }

    private func conversation(_ stage: Stage, chat: ChatSession, groups: GroupsSession, peers: Peers, account: UUID) async throws -> Receipt {
        await groups.refresh()
        if stage == .invite {
            guard groups.groups.isEmpty, try chat.messages(peers.android).isEmpty else { throw GroupsFailure.retryRequiresReview }
            let created = await groups.create(title: "Launch conversation", invitees: [peers.android, peers.member], expected: nil)
            let group = try XCTUnwrap(created, groups.notice ?? "group creation")
            for person in [peers.android, peers.member] {
                let invited = await groups.invite(try XCTUnwrap(groups.snapshot(group.id)), person: person)
                XCTAssertTrue(invited, groups.notice ?? "invite")
            }
            try XCTUnwrap(chat.groupDraftStore).clearCreationDraft(for: group.id)
            var sent = try await photo(to: peers.android, chat: chat, account: account)
            sent["group"] = group.id.uuidString.lowercased()
            return sent
        }
        let saved = try read("invite")
        let id = try XCTUnwrap(saved["group"].flatMap(UUID.init(uuidString:)))
        let group = try XCTUnwrap(groups.snapshot(id))
        switch stage {
        case .approveAndroid, .approveMember:
            let person = stage == .approveAndroid ? peers.android : peers.member
            XCTAssertEqual(group.role(for: person), .member)
            XCTAssertFalse(groups.approved(id, person: person))
            await groups.approveJoin(group, person: person)
            XCTAssertTrue(groups.approved(id, person: person), groups.notice ?? "join approval")
            return stage == .approveMember ? try await send("Hello from iOS to both friends", group: group, session: groups) : [:]
        case .introduceMember:
            // The relay invitation alone cannot authenticate a new inviter.
            // An explicit ordinary DM gives this previously unknown peer a
            // direct Signal identity before they confirm the original control.
            let text = "Hello before our first group conversation."
            XCTAssertFalse(try chat.messages(peers.member).contains { $0.outgoing })
            try chat.send(text, peer: peers.member)
            await chat.synchronize()
            let row = try XCTUnwrap(chat.messages(peers.member).first { $0.outgoing && $0.text == text })
            XCTAssertTrue(["accepted", "delivered", "read"].contains(row.state))
            return ["message": row.id.uuidString.lowercased()]
        case .remove:
            let removed = await groups.change(group, method: "DELETE", suffix: "/members/" + peers.member.uuidString.lowercased())
            XCTAssertTrue(removed, groups.notice ?? "remove member")
            let current = try XCTUnwrap(groups.snapshot(id))
            XCTAssertNil(current.role(for: peers.member))
            return try await send("Hello to the remaining member", group: current, session: groups)
        case .voice:
            let expected = try read("voice-input")
            let incoming = try XCTUnwrap(chat.messages(peers.android).first { !$0.outgoing && $0.id.uuidString.lowercased() == expected["message"] })
            let manifest = try XCTUnwrap(incoming.attachments.first { $0.kind == .voice })
            let url = try await chat.openMedia(manifest, peer: peers.android)
            defer { try? FileManager.default.removeItem(at: url) }
            let digest = SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
            XCTAssertEqual(digest, expected["sha256"])
            let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
            XCTAssertGreaterThan(file.length, 0)
            XCTAssertLessThan(file.length, 480_000, "This fixture is a short synthetic tone")
            let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: UInt32(file.length)))
            try file.read(into: buffer)
            let samples = UnsafeBufferPointer(start: try XCTUnwrap(buffer.floatChannelData)[0], count: Int(buffer.frameLength))
            let rms = sqrt(samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count))
            let ms = Int((Double(buffer.frameLength) * 1000 / file.processingFormat.sampleRate).rounded())
            XCTAssertGreaterThan(rms, 0.005)
            XCTAssertEqual(ms, try XCTUnwrap(manifest.durationMillis), accuracy: 32)
            return ["message": incoming.id.uuidString.lowercased(), "sha256": digest, "milliseconds": String(ms),
                    "frames": String(buffer.frameLength), "rms": String(rms)]
        case .verify:
            let photo = try XCTUnwrap(chat.messages(peers.android).first { $0.id.uuidString.lowercased() == saved["photo"] })
            XCTAssertTrue(["delivered", "read"].contains(photo.state))
            let replies = groups.messages(id).filter { $0.delivery == .received && $0.sender == peers.android && $0.text == "Android heard the group clearly." }
            XCTAssertEqual(replies.count, 1)
            return ["group_reply": try XCTUnwrap(replies.first).id.uuidString.lowercased(), "photo_state": photo.state]
        default:
            throw GroupsFailure.invalidResponse
        }
    }

    private func photo(to peer: UUID, chat: ChatSession, account: UUID) async throws -> Receipt {
        try await chat.confirmMediaCapability(peer)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let size = CGSize(width: 96, height: 64)
        let image = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.systemTeal.setFill(); context.fill(CGRect(origin: .zero, size: size))
            UIColor.orange.setFill(); context.fill(CGRect(x: 10, y: 12, width: 23, height: 17))
        }
        let clear = try XCTUnwrap(image.pngData())
        let source = FileManager.default.temporaryDirectory.appendingPathComponent("launch-photo.png")
        try clear.write(to: source)
        defer { try? FileManager.default.removeItem(at: source) }
        let manifest = try await AttachmentRepository(account: account).prepare(source: source, kind: .photo)
        let id = try chat.sendAttachments("A photo for the launch conversation", peer: peer, attachments: [manifest])
        await chat.synchronize()
        let row = try XCTUnwrap(chat.messages(peer).first { $0.id == id })
        XCTAssertTrue(["accepted", "delivered", "read"].contains(row.state), chat.notice ?? row.state)
        return ["photo": id.uuidString.lowercased(), "photo_sha256": SHA256.hash(data: clear).map { String(format: "%02x", $0) }.joined()]
    }

    private func send(_ text: String, group: GroupSnapshot, session: GroupsSession) async throws -> Receipt {
        let queued = await session.send(group, text: text)
        XCTAssertTrue(queued, session.notice ?? "group send")
        let row = try XCTUnwrap(session.messages(group.id).first { $0.text == text })
        XCTAssertEqual(row.delivery, .accepted, session.notice ?? "admission")
        return ["message": row.id.uuidString.lowercased()]
    }

    private func signedInvitation(_ config: Fixture) async throws -> Receipt {
        #if DEBUG && targetEnvironment(simulator)
        // An existing human sign-in or interrupted transaction is never replaced.
        for key in ["session", "pending-sign-in", "pending-identity-link"] {
            guard try KeychainStore.read(account: key) == nil else { throw XCTSkip("Requires a dedicated signed-out simulator") }
        }
        let suite = "vipi-invitation-fixture-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let before = AppState(defaults: defaults)
        before.selectKnownLanguage("de")
        before.targetLanguage = "sw"
        XCTAssertTrue(before.acceptInvitation(try XCTUnwrap(URL(string: "https://api.mambovipi.app/invite/" + config.android))))
        let auth = AuthenticationManager()
        defer { auth.signOutLocally() }
        var authorization: URLComponents?
        auth.qualificationSignInLaunch = { authorization = URLComponents(url: $0, resolvingAgainstBaseURL: false) }
        auth.qualificationCodeExchange = { code, verifier, authority in
            XCTAssertEqual(code, "local-callback")
            let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64EncodedString()
                .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
            XCTAssertEqual(authorization?.queryItems?.first { $0.name == "code_challenge" }?.value, challenge)
            return VipiSession(userID: config.account.subject, accessToken: config.account.access_token,
                               refreshToken: "synthetic-local-fixture", authority: authority)
        }
        auth.signIn()
        let state = try XCTUnwrap(authorization?.queryItems?.first { $0.name == "state" }?.value)
        var callback = try XCTUnwrap(URLComponents(string: "co.fallsoft.vipi://auth/callback"))
        callback.queryItems = [URLQueryItem(name: "state", value: state), URLQueryItem(name: "code", value: "local-callback")]
        await auth.complete(try XCTUnwrap(callback.url))
        let restored = AuthenticationManager()
        let session = try XCTUnwrap(restored.session)
        XCTAssertEqual(session.userID, config.account.subject)
        let after = AppState(defaults: defaults)
        XCTAssertEqual([after.knownLanguage, after.targetLanguage], ["de", "sw"])
        let name = try XCTUnwrap(after.invitationUsername)
        // The fixture-only token source never refreshes a synthetic login at a hosted provider.
        let account = Account(subject: session.userID, username: config.account.username,
                              display_name: config.account.display_name, access_token: session.accessToken)
        let api = try ServiceClient(authentication: account, userID: session.userID, endpoint: config.endpoint)
        let chat = try ChatSession(api: api, userID: session.userID)
        defer { try? chat.close() }
        await chat.start()
        let person = try await chat.find(name)
        XCTAssertEqual(person.username, config.android)
        XCTAssertEqual(try XCTUnwrap(chat.profile).id.uuidString.lowercased(), try read("profile")["account"])
        return ["opened_username": name, "peer": person.id.uuidString.lowercased(), "pkce": "verified",
                "provider": "synthetic callback", "languages": after.knownLanguage + "-" + after.targetLanguage]
        #else
        throw XCTSkip("Signed-in invitation fixture runs only on an isolated debug simulator")
        #endif
    }

    private func preview(endpoint: URL) async throws -> Receipt {
        let account = try XCTUnwrap(read("profile")["account"].flatMap(UUID.init(uuidString:)))
        let appVault = try MessageVault(account: account)
        defer { try? appVault.close() }
        let consent = try XCTUnwrap(appVault.transaction { try appVault.notificationConsent() })
        // The OS authorization is simulated. Consent, grant, shared vault, device
        // credentials, ticket, encrypted envelope and decryption are real.
        try appVault.authorizeNotifications(consent)
        defer { try? NotificationAccess.revoke() }
        let grant = try XCTUnwrap(NotificationAccess.grant())
        let extensionVault = try MessageVault(account: account, directory: XCTUnwrap(NotificationAccess.root), previewKey: grant.key)
        defer { try? extensionVault.close() }
        let device = try DeviceCredential.registered(vault: extensionVault)
        let ticket = try read("preview-input")
        var request = URLRequest(url: endpoint.appendingPathComponent("v1/notifications/envelope"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
        request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
        request.httpBody = try JSONEncoder().encode(["ticket": try XCTUnwrap(ticket["ticket"])])
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let envelope = try JSONDecoder().decode(NotificationEnvelope.self, from: data)
        let decoded = try envelope.preview(grant: grant, vault: extensionVault, device: device, checkGrant: NotificationAccess.grant)
        XCTAssertEqual(decoded.body, "Private hello from Android.")
        XCTAssertFalse(decoded.repeated)
        XCTAssertEqual(envelope.id.uuidString.lowercased(), ticket["message"])
        return ["message": envelope.id.uuidString.lowercased(), "sender": envelope.peer.uuidString.lowercased(), "local_body": decoded.body]
    }

    private func file(_ name: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("groups-combined-" + name + ".json")
    }
    private func read(_ name: String) throws -> Receipt {
        try JSONDecoder().decode(Receipt.self, from: Data(contentsOf: file(name)))
    }
}
