import SwiftUI
#if DEBUG && VIPI_MEDIA_QUALIFICATION

/// Synthetic cached-receipt journey for the separately signed media QA bundle.
struct ReceivedPhotoQualification: View {
    @State private var session: ChatSession?
    @State private var sender: UUID?
    @State private var failure: String?
    var body: some View {
        Group {
            if let session, let sender {
                NavigationStack { FriendConversationView(chat: session, peer: sender) }
            } else if let failure {
                Text(verbatim: failure)
            } else {
                ProgressView()
            }
        }.task {
            guard KeychainStore.isMediaQualification, session == nil else { return }
            do { (session, sender) = try await Self.prepare() } catch { failure = "Photo fixture failed: \(error)" }
        }
    }

    @MainActor private final class Transport: ChatTransport {
        let profile: ChatProfile
        init(_ id: UUID) { profile = ChatProfile(id: id, username: "photo_reader", display_name: "Maya") }
        func request<T: Decodable>(
            _ method: String, _ path: String, body: Data?, device: DeviceCredential?,
            query: [String: String], as type: T.Type
        ) async throws -> T {
            let input = try body.flatMap { try JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
            let value: [String: Any]
            switch path {
            case "/v1/me": return try JSONDecoder().decode(type, from: JSONEncoder().encode(profile))
            case "/v1/devices": value = ["id": input["device_id"] ?? "", "active": true]
            case "/v1/keys": value = ["revision": 1, "remaining": 20]
            case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
            case let route where route.hasPrefix("/v1/blocks/"): value = ["blocked": false]
            case let route where route.hasSuffix("/receipt"): value = ["state": "delivered"]
            case let route where route.hasSuffix("/receipts"): value = ["acknowledged": input["seen"] ?? [], "read": []]
            default: throw ServiceFailure(status: 404, code: "unused_fixture_route")
            }
            return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
        }
    }

    @MainActor private static func prepare() async throws -> (ChatSession, UUID) {
        let sender = UUID(), receiver = UUID(), id = UUID(), claim = UUID()
        let fm = FileManager.default
        let source = fm.temporaryDirectory.appendingPathComponent("vipi-photo-\(UUID()).jpg")
        defer { try? fm.removeItem(at: source) }
        let art = UIGraphicsImageRenderer(size: CGSize(width: 320, height: 200)).jpegData(withCompressionQuality: 0.9) {
            ctx in
            let g = ctx.cgContext
            UIColor(red: 0.96, green: 0.65, blue: 0.53, alpha: 1).setFill()
            g.fill(CGRect(x: 0, y: 0, width: 320, height: 200))
            UIColor.systemYellow.setFill()
            g.fillEllipse(in: CGRect(x: 30, y: 57, width: 260, height: 95))
            UIColor.systemTeal.setFill()
            g.fill(CGRect(x: 80, y: 71, width: 50, height: 38))
            UIColor.systemBrown.setFill()
            g.fill(CGRect(x: 188, y: 60, width: 44, height: 32))
        }
        try art.write(to: source, options: .atomic)
        let from = try AttachmentRepository(account: sender), to = try AttachmentRepository(account: receiver)
        let attachment = try await from.prepare(source: source, kind: .photo)
        let sendingVault = try MessageVault(account: sender), receivingVault = try MessageVault(account: receiver)
        defer {
            try? sendingVault.close()
            try? receivingVault.close()
        }
        let alice = try MessagingCore(vault: sendingVault), bob = try MessagingCore(vault: receivingVault)
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let keys = try bob.keys.publication(now: now, count: 1)
        guard let oneTime = keys.one_time.first else { throw SignalKeys.Failure.invalidBundle }
        _ = try alice.keys.establish(
            peer: receiver, requestID: claim,
            response: ClaimedKeys(
                request_id: claim,
                user_id: receiver, device_id: bob.device.id, signal_device_id: 1, registration_id: keys.registration_id,
                identity_key: keys.identity_key, signed: keys.signed, one_time: oneTime))
        let caption = "Coffee for two"
        try alice.journal.saveDraft(
            id: id, recipient: receiver, text: caption, createdAt: now, now: now, attachments: [attachment])
        let routed = try alice.queue(
            id: id, peer: receiver, text: caption, createdAt: now, now: now, attachments: [attachment])
        let received = try bob.receive(routed, now: now)
        guard received.attachments == [attachment] else { throw MediaCryptography.Failure.authentication }
        try receivingVault.transaction {
            try receivingVault.put(
                "contact", sender.uuidString.lowercased(),
                JSONEncoder().encode(ChatProfile(id: sender, username: "photo_sender", display_name: "Alex")))
        }
        // Model an offline re-open using only the original received ciphertext.
        let sourceCiphertext = from.ciphertext(attachment.original)
        let cachedCiphertext = to.ciphertext(attachment.original)
        try fm.copyItem(at: sourceCiphertext, to: cachedCiphertext)
        var repairOnOfflineFetch = ProcessInfo.processInfo.arguments.contains("-vipi-photo-damaged-cache")
        if repairOnOfflineFetch {
            var damaged = try Data(contentsOf: cachedCiphertext)
            damaged[damaged.count - 1] ^= 1
            try damaged.write(to: cachedCiphertext, options: .atomic)
        }
        let offline = try CiphertextTransport(endpoint: URL(string: "http://127.0.0.1:1")!) { _ in
            if repairOnOfflineFetch {
                // The first tap rejected damaged cache bytes and tried to fetch.
                // Restore only the fixture’s original for the user's explicit retry.
                repairOnOfflineFetch = false
                try Data(contentsOf: sourceCiphertext).write(to: cachedCiphertext, options: .atomic)
            }
            throw URLError(.notConnectedToInternet)
        }
        let chat = try ChatSession(
            api: Transport(receiver), userID: "user_localmedia_viewer_\(receiver)", media: offline)
        await chat.start()
        guard chat.ready else { throw ServiceFailure(status: 0, code: "fixture_not_ready") }
        return (chat, sender)
    }
}
#elseif DEBUG
typealias ReceivedPhotoQualification = EmptyView
#endif
