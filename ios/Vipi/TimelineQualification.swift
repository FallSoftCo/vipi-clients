#if DEBUG
import SwiftUI
import AVFAudio
import UIKit
import Security
import CryptoKit
import Observation
import VipiCore

/// Actual hosted reauthentication using only the already-owned staging account.
/// Never supplies a token, creates a device, rotates keys, or takes over another
/// device. Only safe metadata is retained; Release has no launch route.
struct ReauthenticationQualificationView: View {
    @Environment(AuthenticationManager.self) private var authentication
    @State private var subject: String?
    @State private var account: UUID?
    @State private var device: DeviceCredential?
    @State private var before: TimeInterval?
    @State private var status = "Checking owned staging session"
    @State private var started = false
    @State private var completing = false
    @State private var proof: [String: Any] = [:]
    private var receipt: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(
            "reauth-native-r01.json")
    }
    var body: some View {
        VStack(spacing: 20) {
            Text("Owned staging sign-in check").font(.title2)
            Text(status).accessibilityIdentifier("reauth-qa-status")
            if subject != nil && !started {
                Button("Sign in again") {
                    started = true
                    authentication.signIn(expectedUser: subject)
                }
            }
            if let error = authentication.errorMessage { Text(error) }
        }.padding().task { await prepare() }
            .onChange(of: authentication.session?.accessToken) { _, _ in
                guard started, !completing else { return }
                completing = true
                Task { await finish() }
            }
    }
    private func authTime(_ token: String) throws -> TimeInterval {
        // Decode solely for observation. ServiceClient independently proves that
        // the provider-issued token authenticates to the actual live service.
        let parts = token.split(separator: ".")
        guard parts.count == 3 else { throw ServiceFailure(status: 0, code: "invalid_observed_token") }
        var encoded = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
        guard let data = Data(base64Encoded: encoded),
            let claims = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let value = claims["auth_time"] as? Double
        else { throw ServiceFailure(status: 0, code: "missing_auth_time") }
        return value
    }
    private func save(_ stage: String) throws {
        proof["stage"] = stage
        proof["recorded_at"] = Date().timeIntervalSince1970
        try JSONSerialization.data(withJSONObject: proof, options: [.sortedKeys, .prettyPrinted]).write(
            to: receipt, options: .atomic)
    }
    private func prepare() async {
        do {
            guard !FileManager.default.fileExists(atPath: receipt.path),
                Bundle.main.object(forInfoDictionaryKey: "WorkOSClientID") as? String
                    == "client_01M5S2CDSQ8F7FEX26G3CY9VS1",
                let session = authentication.session
            else { throw ServiceFailure(status: 0, code: "owned_staging_session_required") }
            let api = try ServiceClient(authentication: authentication, userID: session.userID)
            let profile: ChatProfile = try await api.request("GET", "/v1/me")
            guard profile.username == "vqa_1107_ios01", let current = authentication.session,
                current.userID == session.userID
            else { throw ServiceFailure(status: 0, code: "owned_staging_identity_required") }
            let vault = try MessageVault(account: profile.id)
            guard let saved = try vault.transaction({ try vault.get("local", "service-device") }) else {
                throw ServiceFailure(status: 0, code: "existing_device_required")
            }
            let credential = try JSONDecoder().decode(DeviceCredential.self, from: saved)
            guard
                try vault.transaction({ try vault.get("local", "registered-device") })
                    == Data(credential.id.uuidString.lowercased().utf8)
            else {
                throw ServiceFailure(status: 0, code: "registered_device_required")
            }
            let time = try authTime(current.accessToken)
            before = time
            account = profile.id
            device = credential
            subject = current.userID
            proof = [
                "subject": current.userID, "account": profile.id.uuidString.lowercased(),
                "device": credential.id.uuidString.lowercased(), "before_auth_time": time,
                "native_hosted_pkce": true, "requested_max_age": 0, "replace_active": false,
                "token_injection": false, "credentials_logged": false
            ]
            try save("prepared")
            status = "Ready to sign in again"
        } catch {
            status = "Preparation failed: " + ((error as? ServiceFailure)?.code ?? String(describing: type(of: error)))
        }
    }
    private func finish() async {
        do {
            guard let before, let account, let device, let session = authentication.session,
                session.userID == subject
            else { throw ServiceFailure(status: 0, code: "same_account_required") }
            let after = try authTime(session.accessToken), now = Date().timeIntervalSince1970
            guard after > before, (0..<600).contains(now - after) else {
                throw ServiceFailure(status: 0, code: "active_authentication_not_advanced")
            }
            let api = try ServiceClient(authentication: authentication, userID: session.userID)
            let profile: ChatProfile = try await api.request("GET", "/v1/me")
            guard profile.id == account, profile.username == "vqa_1107_ios01" else {
                throw ServiceFailure(status: 0, code: "profile_changed")
            }
            let vault = try MessageVault(account: account)
            guard let saved = try vault.transaction({ try vault.get("local", "service-device") }),
                let currentDevice = try? JSONDecoder().decode(DeviceCredential.self, from: saved),
                currentDevice.id == device.id, currentDevice.secret == device.secret
            else {
                throw ServiceFailure(status: 0, code: "device_changed")
            }
            struct Registered: Decodable {
                let id: UUID
                let active: Bool
            }
            let body = try JSONSerialization.data(withJSONObject: [
                "device_id": device.id.uuidString.lowercased(), "secret": device.secret, "replace_active": false
            ])
            let result: Registered = try await api.request("POST", "/v1/devices", body: body)
            guard result.active, result.id == device.id else {
                throw ServiceFailure(status: 0, code: "registration_changed")
            }
            proof["after_auth_time"] = after
            proof["auth_time_advanced_seconds"] = after - before
            proof["same_account"] = true
            proof["same_device"] = true
            proof["live_idempotent_registration_accepted"] = true
            try save("complete")
            status = "Fresh sign-in verified"
        } catch {
            proof["failure_code"] = (error as? ServiceFailure)?.code ?? "local_validation"
            try? save("failed")
            status = "Reauthentication proof failed"
        }
    }
}

/// Read-only geometry for the exact synthetic full-message root qualification.
struct FullMessageViewportGeometry: Equatable {
    let offset: CGPoint, content: CGSize, container: CGSize, visible: CGRect
    let leading: CGFloat, trailing: CGFloat, top: CGFloat, bottom: CGFloat
    init(_ value: ScrollGeometry) {
        offset = value.contentOffset
        content = value.contentSize
        container = value.containerSize
        visible = value.visibleRect
        leading = value.contentInsets.leading
        trailing = value.contentInsets.trailing
        top = value.contentInsets.top
        bottom = value.contentInsets.bottom
    }
    var fields: [String: Any] {
        [
            "offset_x": offset.x, "offset_y": offset.y, "content_width": content.width,
            "content_height": content.height,
            "container_width": container.width, "container_height": container.height,
            "visible_x": visible.minX, "visible_y": visible.minY, "visible_width": visible.width,
            "visible_height": visible.height,
            "inset_leading": leading, "inset_trailing": trailing, "inset_top": top, "inset_bottom": bottom
        ]
    }
}

/// Explicit debug-only observation of owned live QA sessions. Contains no
/// message text, keys, tokens or audio; it never changes presentation state.
@MainActor enum LiveImmersionQualification {
    private static func digest(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    static func recordSpeech(_ message: String, spans: [(text: String, language: String)]) {
        let arguments = ProcessInfo.processInfo.arguments
        let authoredWelcome =
            arguments.contains("-vipi-welcome") && Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
        let ownedFirstMonth =
            Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" && arguments.contains("-vipi-first-month-root-qa")
            && FirstMonthRootQualification.current != nil
        guard (arguments.contains("-vipi-timeline-qa") || authoredWelcome || ownedFirstMonth),
            arguments.contains("-vipi-live-immersion-state")
        else { return }
        record([
            "event": "speech_input", "message_id": message,
            "inputs": spans.map { span in
                [
                    "language": span.language, "utf8_bytes": span.text.utf8.count,
                    "sha256": SHA256.hash(data: Data(span.text.utf8)).map { String(format: "%02x", $0) }.joined()
                ] as [String: Any]
            }
        ])
    }
    static var fullMessageGeometryEnabled: Bool {
        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
            && ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa")
            && FirstMonthRootQualification.current != nil
    }
    private(set) static var currentMessageViewport: [String: Double] = [:]
    private(set) static var currentMessageRows: [String: [String: Any]] = [:]
    static func recordCurrentMessageRows(_ frames: [UUID: CGRect]) {
        guard fullMessageGeometryEnabled else { return }
        currentMessageRows = Dictionary(
            uniqueKeysWithValues: frames.map { ($0.key.uuidString.lowercased(), frameFields($0.value)) })
    }
    static func recordCurrentMessageViewport(_ frame: CGRect) {
        guard fullMessageGeometryEnabled,
            [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite })
        else { return }
        currentMessageViewport = [
            "x": Double(frame.minX), "y": Double(frame.minY), "width": Double(frame.width),
            "height": Double(frame.height)
        ]
    }
    static func recordFullMessageGeometry(_ fields: [String: Any]) {
        guard fullMessageGeometryEnabled else { return }
        record(fields)
    }
    static func frameFields(_ value: CGRect) -> [String: Any] {
        guard [value.minX, value.minY, value.width, value.height].allSatisfy({ $0.isFinite }) else {
            return ["unavailable": true]
        }
        return ["x": value.minX, "y": value.minY, "width": value.width, "height": value.height]
    }
    static func recordFirstMonthSpeechOutput(_ fields: [String: Any]) {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
            ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa"),
            FirstMonthRootQualification.current != nil
        else { return }
        record(fields)
    }
    static func record(_ fields: [String: Any]) {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "-vipi-live-immersion-state"), index + 1 < arguments.count else {
            return
        }
        let revision = arguments[index + 1]
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else { return }
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(
            "live-immersion-state-\(revision).jsonl")
        if let size = try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize, size > 524_288 { return }
        var row = fields
        row["at"] = Date().timeIntervalSince1970
        guard var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else { return }
        data.append(10)
        if !FileManager.default.fileExists(atPath: file.path) {
            FileManager.default.createFile(atPath: file.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        try? handle.seekToEnd()
        try? handle.write(contentsOf: data)
    }
}

/// Records real platform state only in the explicitly selected synthetic QA
/// conversation. Absent from Release, and never enabled for a signed-in chat.
@MainActor enum VoiceOverQualification {
    static func record(_ event: String, enabled: Bool, original: Bool) {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("-vipi-timeline-qa"),
            let index = arguments.firstIndex(of: "-vipi-voiceover-qa"), index + 1 < arguments.count
        else { return }
        let revision = arguments[index + 1]
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else { return }
        let row: [String: Any] = [
            "event": event, "at": Date().timeIntervalSince1970,
            "swiftui_voiceover": enabled, "uikit_voiceover": UIAccessibility.isVoiceOverRunning,
            "original_phase": original, "app_state": UIApplication.shared.applicationState.rawValue
        ]
        guard var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else { return }
        data.append(10)
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("voiceover-state-\(revision).jsonl")
        if !FileManager.default.fileExists(atPath: file.path) {
            FileManager.default.createFile(atPath: file.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        try? handle.seekToEnd()
        try? handle.write(contentsOf: data)
    }
}

/// Isolated synthetic history for native UI automation. No service requests or
/// changes to the signed-in account. Entire harness is absent from Release.
private actor TimelineReadingGate {
    private var opened = false
    private var waiting: [CheckedContinuation<Void, Never>] = []
    func hold() async {
        guard !opened else { return }
        await withCheckedContinuation { waiting.append($0) }
    }
    func release() {
        opened = true
        let pending = waiting
        waiting.removeAll()
        for value in pending { value.resume() }
    }
}

struct TimelineQualificationView: View {
    static let fundingServices = MessageTranslationServices(
        status: { _ in .installed },
        translate: { text, pair in
            guard pair == TranslationPair(source: "en", target: "es") else { throw MessageVault.Failure.invalidRecord }
            switch text.lowercased() {
            case "water, water!": return "¡Agua, agua!"
            case "water": return "agua"
            case "coffee tomorrow?": return "¿Café mañana?"
            case "coffee": return "café"
            case "tomorrow": return "mañana"
            default: throw MessageVault.Failure.invalidRecord
            }
        })
    @Environment(AppState.self) private var appState
    @State private var chat: ChatSession?
    @State private var owner = UUID()
    @State private var peer = UUID()
    @State private var user = "timeline-ui-" + UUID().uuidString
    @State private var status = "Preparing synthetic conversation"
    @State private var finished = false
    @State private var readingGate = TimelineReadingGate()
    @State private var readingOwner: ConversationImmersion?
    @State private var readingReleased = false
    private var delayedReading: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-delayed-reading-qa") }
    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("-vipi-base-expiry-qa") {
            BaseExpiryQualificationView()
        } else if (ProcessInfo.processInfo.arguments.contains("-vipi-funding-qa")
            || ProcessInfo.processInfo.arguments.contains("-vipi-streaks-qa")), let chat
        {
            HomeView(chat: chat)
        } else {
            timeline
        }
    }
    private var timeline: some View {
        NavigationStack {
            Group {
                if let chat {
                    FriendConversationView(chat: chat, peer: peer, immersion: readingOwner)
                        .frame(
                            maxWidth: ProcessInfo.processInfo.arguments.contains("-vipi-voice-narrow-qa")
                                ? 245 : .infinity)
                } else {
                    Text(status).accessibilityIdentifier("timeline-qa-status")
                }
            }.toolbar {
                if delayedReading && !readingReleased {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Release reading") {
                            readingReleased = true
                            Task { await readingGate.release() }
                        }.accessibilityIdentifier("timeline-qa-release-reading")
                    }
                }
                if !ProcessInfo.processInfo.arguments.contains("-vipi-timeline-audit") {
                    ToolbarItem(placement: .topBarLeading) {
                        if let chat {
                            Button("Append QA") {
                                try? chat.send("Appended while reading earlier messages.", peer: peer)
                            }.accessibilityIdentifier("timeline-qa-append")
                        }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        if !finished {
                            Button("Finish QA", action: finish).accessibilityIdentifier("timeline-qa-finish")
                        }
                    }
                }
            }
        }.task {
            guard chat == nil && !finished else { return }
            do {
                try removeAbandonedTimelineFixtures()
                if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-cleanup") {
                    finished = true
                    status = "Synthetic conversation removed"
                    return
                }
                let voiceLayout = ProcessInfo.processInfo.arguments.contains("-vipi-voice-layout-qa")
                let offlineMedia =
                    voiceLayout
                    ? try CiphertextTransport(endpoint: URL(string: "https://fixture.invalid")!) { _ in
                        throw CancellationError()
                    } : nil
                let value = try ChatSession(
                    api: TimelineTransport(owner: owner, peer: peer), userID: user, media: offlineMedia)
                await value.start()
                guard value.ready else { throw ServiceFailure(status: 0, code: "fixture_not_ready") }
                _ = try await value.find("alex")
                if ProcessInfo.processInfo.arguments.contains("-vipi-streaks-qa"), let vault = value.feedbackVault {
                    for friend in TimelineTransport.streakFriends { _ = try await value.find(friend.name.lowercased()) }
                    try seedStreaks(vault)
                    await value.configureTranslation(
                        pair: .init(source: "en", target: "es"),
                        services: .init(status: { _ in .unsupported }, translate: { _, _ in throw CancellationError() })
                    )
                    await value.synchronize()
                    value.notice = nil
                    chat = value
                    return
                }
                if ProcessInfo.processInfo.arguments.contains("-vipi-message-actions-qa"),
                    let vault = value.feedbackVault
                {
                    // Owned synthetic text and offline model state for action screenshots.
                    readingOwner = ConversationImmersion(
                        modelStatus: { _ in .installed }, identify: { _ in "en" },
                        nativeTranslation: { text, _ in
                            let samples = [
                                "library": "biblioteca", "Saturday": "sábado", "Coffee": "Café",
                                "Meet at the library on Saturday?": "¿Nos vemos en la biblioteca el sábado?",
                                "Perfect. Coffee afterwards?": "Perfecto. ¿Un café después?"
                            ]
                            return samples[text] ?? text
                        })
                    try seedMessageActions(vault)
                    await value.synchronize()
                    value.notice = nil
                    chat = value
                    return
                }
                if voiceLayout, let vault = value.feedbackVault {
                    try await seedVoiceLayout(vault)
                    await value.synchronize()
                    value.notice = nil
                    chat = value
                    return
                }
                if ProcessInfo.processInfo.arguments.contains("-vipi-funding-qa"), let vault = value.feedbackVault {
                    try vault.transaction {
                        var usage = ChatFeedback()
                        for i in 0..<20 { usage.accepted(authoredAt: Int64(i % 7) * 86_400_000) }
                        try usage.save(vault)
                    }
                    await value.configureTranslation(
                        pair: .init(source: "en", target: "es"), mode: appState.immersionMode,
                        services: Self.fundingServices)
                    let journal = MessageJournal(vault: vault)
                    let now = Int64(Date().timeIntervalSince1970 * 1_000)
                    let id = UUID()
                    _ = try journal.queue(id: id, recipient: peer, text: "Water, water!", createdAt: now, now: now) {
                        _ in
                        (2, Data(repeating: 1, count: 64))
                    }
                    try journal.applyStatus(id, state: "delivered")
                    await value.synchronize()
                    value.notice = nil
                    chat = value
                    return
                }
                if delayedReading {
                    let gate = readingGate
                    readingOwner = ConversationImmersion(
                        modelStatus: { _ in .unsupported },
                        fullReadingProducer: { text, language in
                            await gate.hold()
                            return FullSentenceReadings.resolve(text, language: language)
                        })
                }
                let immersionQA = ProcessInfo.processInfo.arguments.contains("-vipi-immersion-chat-qa")
                let immersionMessages =
                    ProcessInfo.processInfo.arguments.contains("-vipi-reverse-spanish-qa")
                    ? ["Estoy leyendo un libro ahora."]
                    : ProcessInfo.processInfo.arguments.contains("-vipi-reverse-chinese-qa")
                        ? ["我正在读一本书。"]
                        : ProcessInfo.processInfo.arguments.contains("-vipi-source-unit-routing-qa")
                            ? ["I need water. Did you finish the report?"]
                            : ProcessInfo.processInfo.arguments.contains("-vipi-learning-language-qa")
                                ? ["Ninapenda muziki."]
                                : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-response-qa")
                                    ? ["yes"]
                                    : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-opener-qa")
                                        ? ["Thank you very much."]
                                        : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-request-qa")
                                            ? ["I need a phone charger."]
                                            : ProcessInfo.processInfo.arguments.contains("-vipi-immersion-single-qa")
                                                ? ["I like music."]
                                                : [
                                                    "I am reading a book now.", "I am drinking water now.",
                                                    "Where is the phone charger?", "I like music."
                                                ]
                let immersionHistory = ProcessInfo.processInfo.arguments.contains("-vipi-immersion-history-qa")
                for index in 1...(immersionQA && !immersionHistory ? immersionMessages.count : 70) {
                    let extra =
                        index <= 20
                        ? String(repeating: " We can meet by the station and decide where to walk.", count: index % 5)
                        : ""
                    try value.send(
                        immersionQA
                            ? immersionMessages[(index - 1) % immersionMessages.count]
                            : "History message \(index). We are making plans for tomorrow." + extra, peer: peer)
                    try await Task.sleep(for: .milliseconds(2))
                }
                chat = value
            } catch { status = "Fixture failed: \(error.localizedDescription)" }
        }.onDisappear { Task { await readingGate.release() } }
    }
    private func seedStreaks(_ vault: MessageVault) throws {
        let today = ConversationStreak.today()
        let group = TimelineTransport.streakGroup
        let other = TimelineTransport.streakMember
        let store = GroupsStore(vault: vault)
        try vault.transaction {
            let threads = [(id: peer, name: "Alex", days: 105)] + TimelineTransport.streakFriends
            for (order, friend) in threads.enumerated() {
                for offset in 0..<friend.days {
                    let start = (today - Int64(offset)) * ConversationStreak.millisecondsPerDay
                    for (index, sender) in [friend.id, owner].enumerated() {
                        let outgoing = sender == owner, id = UUID(), kind = outgoing ? "outgoing" : "incoming"
                        let at = start + Int64(10 - order) * 1_000 + Int64(index)
                        let envelope = ChatEnvelope(
                            id: id, sender: sender, recipient: outgoing ? friend.id : owner, createdAt: at, type: 3,
                            ciphertext: Data([1]))
                        let row = StoredChat(
                            envelope: envelope, text: outgoing ? "See you at the café!" : "Coffee tomorrow?",
                            state: "delivered", seen: true)
                        try vault.put(kind, id.uuidString.lowercased(), JSONEncoder().encode(row))
                        try ConversationHistory.record(vault, kind: kind, id: id, peer: friend.id, createdAt: at)
                    }
                    if order == 0 && offset < 7 {
                        for sender in [peer, other] {
                            try store.saveMessageInTransaction(
                                .init(
                                    id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: sender,
                                    text: sender == peer ? "Which book is next?" : "I have a suggestion.",
                                    createdAt: start + 2_000, delivery: .received))
                        }
                    }
                }
            }
        }
    }
    private func seedMessageActions(_ vault: MessageVault) throws {
        let first = UUID(), second = UUID(), last = UUID(), time = Int64(Date().timeIntervalSince1970 * 1000) - 480_000
        let question = "Meet at the library on Saturday?"
        let quote = ChatFeatures.Reply.quoting(id: first, sender: peer, text: question)
        let link = ChatFeatures.Preview(url: "https://example.com/", title: "Saturday at the library")
        try vault.transaction {
            try vault.put(
                "peer-device", peer.uuidString.lowercased(),
                Data(TimelineTransport.actionDevice.uuidString.lowercased().utf8))
            func record(_ id: UUID, _ outgoing: Bool, _ body: String, _ date: Int64, _ features: ChatFeatures? = nil)
                throws
            {
                let envelope = ChatEnvelope(
                    id: id, sender: outgoing ? owner : peer, recipient: outgoing ? peer : owner, createdAt: date,
                    type: 2, ciphertext: Data(repeating: 4, count: 32))
                let row = StoredChat(envelope: envelope, text: body, state: "delivered", features: features)
                let kind = outgoing ? "outgoing" : "incoming"
                try vault.put(kind, id.uuidString.lowercased(), JSONEncoder().encode(row))
                try ConversationHistory.record(vault, kind: kind, id: id, peer: peer, createdAt: date)
            }
            try record(first, false, question, time)
            try record(
                second, true, "Yes! Here’s the schedule: https://example.com/", time + 70_000,
                .init(reply: quote, link_preview: link))
            try record(last, false, "Perfect. Coffee afterwards?", time + 130_000)
            try MessageReactions.apply(
                vault, scope: .direct, conversation: peer, actor: peer, device: TimelineTransport.actionDevice,
                event: UUID(),
                reaction: .init(message_id: second, target_sender_id: owner, sequence: 1, emoji: "❤️"), targetKnown: true
            )
        }
    }
    private func seedVoiceLayout(_ vault: MessageVault) async throws {
        let repository = try AttachmentRepository(account: vault.account)
        let now = Int64(Date().timeIntervalSince1970 * 1_000)
        for (index, seconds) in [180, 8].enumerated() {
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
            defer { try? FileManager.default.removeItem(at: url) }
            let format = AVAudioFormat(standardFormatWithSampleRate: 8_000, channels: 1)!
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 8_000)!
            buffer.frameLength = 8_000
            buffer.floatChannelData![0].update(repeating: 0, count: 8_000)
            do {
                let file = try AVAudioFile(forWriting: url, settings: format.settings)
                for _ in 0..<seconds { try file.write(from: buffer) }
            }
            let manifest = try await repository.prepare(source: url, kind: .voice)
            let outgoing = index == 0
            let kind = outgoing ? "outgoing" : "incoming"
            let id = UUID()
            let created = now - Int64(2 - index) * 60_000
            let envelope = ChatEnvelope(
                id: id, sender: outgoing ? vault.account : peer, recipient: outgoing ? peer : vault.account,
                createdAt: created, type: 3, ciphertext: Data(repeating: 1, count: 64))
            let record = StoredChat(
                envelope: envelope, text: "Voice message", state: outgoing ? "read" : "received",
                seen: true, attachments: [manifest])
            try vault.transaction {
                try vault.put(kind, id.uuidString.lowercased(), JSONEncoder().encode(record))
                try ConversationHistory.record(vault, kind: kind, id: id, peer: peer, createdAt: created)
            }
        }
    }
    private func finish() {
        do {
            try chat?.close()
            chat = nil
            let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("Messages")
            let directory = root.appendingPathComponent(owner.uuidString.lowercased())
            if FileManager.default.fileExists(atPath: directory.path) {
                try FileManager.default.removeItem(at: directory)
            }
            try KeychainStore.deleteChecked(account: "profile-" + user)
            try KeychainStore.deleteChecked(account: "messages-" + owner.uuidString.lowercased())
            finished = true
            status = "Synthetic conversation removed"
        } catch { status = "Fixture cleanup failed: \(error.localizedDescription)" }
    }
}

/// XCTest can terminate the app before Swift defer/onDisappear runs. Enumerate
/// attributes only, then read/remove solely our synthetic profile namespace.
private func removeAbandonedTimelineFixtures() throws {
    try removeAbandonedBaseExpiryFixtures()
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "co.fallsoft.vipi.private", kSecReturnAttributes as String: true,
        kSecMatchLimit as String: kSecMatchLimitAll
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return }
    guard status == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    for item in (result as? [[String: Any]]) ?? [] {
        guard let key = item[kSecAttrAccount as String] as? String, key.hasPrefix("profile-timeline-ui-"),
            UUID(uuidString: String(key.dropFirst("profile-timeline-ui-".count))) != nil,
            let data = try KeychainStore.read(account: key),
            let profile = try? JSONDecoder().decode(ChatProfile.self, from: data), profile.username == "timeline_qa"
        else { continue }
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages")
        let directory = root.appendingPathComponent(profile.id.uuidString.lowercased())
        try AttachmentRepository.eraseFiles(account: profile.id)
        if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
        try KeychainStore.deleteChecked(account: "messages-" + profile.id.uuidString.lowercased())
        try KeychainStore.deleteChecked(account: key)
    }
}

/// This is the production HomeView navigation owner, not a copied auth/root
/// router. Only the service/store boundary and isolated encrypted accounts are
/// supplied. Release builds contain neither this fixture nor its launch flag.
private struct BaseExpiryQualificationView: View {
    @State private var fixture: BaseExpiryFixture?
    @State private var status = "Preparing isolated expiry QA"
    var body: some View {
        Group {
            if let fixture {
                VStack(spacing: 0) {
                    HomeView(chat: fixture.chat, subscriptions: fixture.subscriptions, botOwner: fixture.owner)
                    // Read-only fixture evidence, outside the production view.
                    // No test button dispatches navigation, sends or purchases.
                    TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                        Text(fixture.proof).font(.caption2).lineLimit(1)
                            .accessibilityIdentifier("base-expiry-qa-proof")
                    }
                }
            } else {
                Text(status).accessibilityIdentifier("base-expiry-qa-status")
            }
        }.task {
            guard fixture == nil, Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { return }
            do {
                try removeAbandonedTimelineFixtures()
                let value = try BaseExpiryFixture()
                try await value.prepare()
                fixture = value
            } catch { status = "Synthetic expiry preparation failed" }
        }
    }
}

private struct BaseExpiryOwnership: Codable {
    let account: UUID
    let peer: UUID
    let user: String
    static var root: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("TimelineExpiryQualification", isDirectory: true)
    }
}

private func removeAbandonedBaseExpiryFixtures() throws {
    guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { return }
    let root = BaseExpiryOwnership.root
    guard FileManager.default.fileExists(atPath: root.path) else { return }
    for directory in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
        let record = try JSONDecoder().decode(
            BaseExpiryOwnership.self, from: Data(contentsOf: directory.appendingPathComponent("owner.json")))
        guard directory.lastPathComponent == record.account.uuidString.lowercased(), record.account != record.peer,
            record.user.hasPrefix("timeline-ui-"),
            UUID(uuidString: String(record.user.dropFirst("timeline-ui-".count))) != nil
        else {
            throw ServiceFailure(status: 0, code: "invalid_expiry_fixture_ownership")
        }
        if let data = try KeychainStore.read(account: "profile-" + record.user) {
            let profile = try JSONDecoder().decode(ChatProfile.self, from: data)
            guard profile.id == record.account, profile.username == "timeline_qa" else {
                throw ServiceFailure(status: 0, code: "expiry_fixture_profile_mismatch")
            }
        }
        let accountDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(record.account.uuidString.lowercased())
        if FileManager.default.fileExists(atPath: accountDirectory.path) {
            try FileManager.default.removeItem(at: accountDirectory)
        }
        try KeychainStore.deleteChecked(account: "profile-" + record.user)
        for id in [record.account, record.peer] {
            try KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased())
        }
        try FileManager.default.removeItem(at: directory)
    }
}

@MainActor private final class BaseExpiryFixture {
    let account = UUID(), peer = UUID()
    let user = "timeline-ui-" + UUID().uuidString
    let owner = BotConversationOwner()
    let api: BaseExpiryTransport
    let chat: ChatSession
    let subscriptions: SubscriptionStore
    private let peerVault: MessageVault
    init() throws {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else {
            throw ServiceFailure(status: 0, code: "qa_bundle_required")
        }
        let directory = BaseExpiryOwnership.root.appendingPathComponent(
            account.uuidString.lowercased(), isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONEncoder().encode(BaseExpiryOwnership(account: account, peer: peer, user: user))
            .write(to: directory.appendingPathComponent("owner.json"), options: .atomic)
        peerVault = try MessageVault(account: peer, directory: directory.appendingPathComponent("peer"))
        api = try BaseExpiryTransport(account: account, peer: peer, peerCore: MessagingCore(vault: peerVault))
        chat = try ChatSession(api: api, userID: user)
        subscriptions = SubscriptionStore(api: api, accountToken: account)
    }
    func prepare() async throws {
        await chat.start()
        guard chat.ready else { throw ServiceFailure(status: 0, code: "expiry_fixture_not_ready") }
        _ = try await chat.find("alex")
        try chat.send("Saved before the free period ended.", peer: peer)
        await chat.synchronize()
        let saved = try chat.messages(peer)
        guard saved.count == 1, saved.first?.state == "delivered", api.setupDecryptions == 1 else {
            throw ServiceFailure(status: 0, code: "expiry_fixture_setup_not_delivered")
        }
        await subscriptions.refreshEntitlements()
        guard subscriptions.baseActive, !subscriptions.botAvailable, !subscriptions.purchaseReady else {
            throw ServiceFailure(status: 0, code: "expiry_fixture_trial_required")
        }
        api.setupComplete = true
    }
    var proof: String {
        // Observe actual model revisions, then independently reopen encrypted
        // storage. Never insert a row, draft or navigation state for the test.
        _ = chat.revision
        do {
            let vault = try MessageVault(account: account)
            defer { try? vault.close() }
            let history = try ConversationHistory(vault: vault)
            let rows = try history.messages(peer: peer)
            let queued = rows.filter { $0.text != "Saved before the free period ended." }
            let data = try JSONSerialization.data(
                withJSONObject: [
                    "setup_decryptions": api.setupDecryptions, "expired_posts": api.expiredPosts,
                    "expired_ids": api.expiredIDs.sorted(), "rows": rows.count,
                    "queued_count": queued.count, "queued_text": queued.first?.text ?? "",
                    "queued_id": queued.first?.id.uuidString.lowercased() ?? "",
                    "queued_state": queued.first?.state ?? "", "draft": try history.composeDraft(peer),
                    "base_active": subscriptions.baseActive, "bot_active": subscriptions.botAvailable,
                    "purchase_ready": subscriptions.purchaseReady, "unexpected_requests": api.unexpectedRequests
                ], options: [.sortedKeys])
            return String(decoding: data, as: UTF8.self)
        } catch { return "{\"durable_read_failed\":true}" }
    }
}

@MainActor @Observable private final class BaseExpiryTransport: ChatTransport {
    let account: UUID, peer: UUID
    let peerCore: MessagingCore
    let publication: KeyPublication
    var setupComplete = false
    var setupDecryptions = 0
    var expiredPosts = 0
    var expiredIDs = Set<String>()
    var unexpectedRequests = 0
    private var device: DeviceCredential?
    init(account: UUID, peer: UUID, peerCore: MessagingCore) throws {
        self.account = account
        self.peer = peer
        self.peerCore = peerCore
        publication = try peerCore.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000), count: 2)
        try peerCore.keys.published(revision: publication.revision)
    }
    func request<T: Decodable>(
        _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
        as type: T.Type
    ) async throws -> T {
        let input: [String: Any]
        if let body {
            input = try JSONSerialization.jsonObject(with: body) as? [String: Any] ?? [:]
        } else {
            input = [:]
        }
        let value: [String: Any]
        switch (method, path) {
        case ("GET", "/v1/me"):
            value = ["id": account.uuidString, "username": "timeline_qa", "display_name": "Expiry QA"]
        case ("POST", "/v1/devices"):
            guard let id = input["device_id"] as? String, let uuid = UUID(uuidString: id),
                let secret = input["secret"] as? String
            else { throw ServiceFailure(status: 0, code: "invalid_qa_device") }
            self.device = DeviceCredential(id: uuid, secret: secret)
            value = ["id": id, "active": true]
        case ("GET", "/v1/keys"): value = ["revision": 1, "remaining": 20]
        case ("GET", "/v1/messages/pending"): value = ["messages": [], "next_cursor": NSNull()]
        case ("GET", "/v1/people/alex"), ("GET", "/v1/people/by-id/" + peer.uuidString.lowercased()):
            value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
        case ("GET", "/v1/blocks/" + peer.uuidString.lowercased()): value = ["blocked": false]
        case ("POST", "/v1/people/" + peer.uuidString.lowercased() + "/keys"):
            guard let raw = input["request_id"] as? String, let request = UUID(uuidString: raw) else {
                throw ServiceFailure(status: 0, code: "invalid_qa_claim")
            }
            let claim = ClaimedKeys(
                request_id: request, user_id: peer, device_id: peerCore.device.id, signal_device_id: 1,
                registration_id: publication.registration_id, identity_key: publication.identity_key,
                signed: publication.signed, one_time: publication.one_time[0])
            return try JSONDecoder().decode(type, from: JSONEncoder().encode(claim))
        case ("POST", "/v1/messages"):
            guard device?.id == self.device?.id, let body, let id = input["id"] as? String else {
                throw ServiceFailure(status: 0, code: "invalid_qa_message")
            }
            if setupComplete {
                expiredPosts += 1
                expiredIDs.insert(id)
                throw ServiceFailure(status: 402, code: "base_subscription_required")
            }
            var routed = try JSONSerialization.jsonObject(with: body) as! [String: Any]
            routed["sender_id"] = account.uuidString
            routed["sender_device_id"] = device!.id.uuidString
            let received = try JSONDecoder().decode(
                RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: routed))
            let message = try peerCore.receive(
                received.routed(account: peer), now: Int64(Date().timeIntervalSince1970 * 1000))
            guard message.text == "Saved before the free period ended." else {
                throw ServiceFailure(status: 0, code: "unexpected_qa_plaintext")
            }
            setupDecryptions += 1
            value = ["state": "delivered"]
        case ("GET", "/v1/entitlements"):
            // The controlled server crosses its exact exclusive trial end on
            // the user's first POST. No device clock or paid grant is changed.
            let ended = expiredPosts > 0
            let end = Date(timeIntervalSince1970: 1_800_000_000)
            let format = ISO8601DateFormatter()
            var base: [String: Any] = [
                "active": !ended,
                "cardless_trial": [
                    "started_at": format.string(from: end.addingTimeInterval(-30 * 86400)),
                    "ends_at": format.string(from: end), "active": !ended
                ]
            ]
            if ended {
                base["expires_at"] = NSNull()
                base["access_source"] = NSNull()
            } else {
                base["expires_at"] = format.string(from: end)
                base["access_source"] = "cardless_trial"
            }
            value = [
                "server_time": format.string(from: ended ? end : end.addingTimeInterval(-3600)),
                "base": base,
                "bot_mini": ["active": false, "available": false], "billing_account_id": "synthetic-expiry-only",
                "app_account_token": account.uuidString, "purchases_ready": ["apple": false, "google": false]
            ]
        case ("GET", "/v1/bot/allowance"): throw ServiceFailure(status: 503, code: "bot_not_available")
        default:
            unexpectedRequests += 1
            throw ServiceFailure(status: 0, code: "unexpected_expiry_qa_request")
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
}

private final class TimelineTransport: ChatTransport {
    static let actionDevice = UUID()
    static let streakFriends: [(id: UUID, name: String, days: Int)] = [
        (UUID(), "Maya", 2), (UUID(), "Sam", 7), (UUID(), "Lina", 30), (UUID(), "Amir", 1024)
    ]
    static let streakGroup = UUID(uuidString: "83872d1c-e5d1-4ae0-934a-0a16edec6075")!
    static let streakMember = UUID(uuidString: "910a1a95-723e-4060-9b31-91a724881981")!
    let owner: UUID, peer: UUID
    init(owner: UUID, peer: UUID) {
        self.owner = owner
        self.peer = peer
    }
    func request<T: Decodable>(
        _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
        as type: T.Type
    ) async throws -> T {
        var value: [String: Any]
        switch path {
        case "/v1/devices/chat-features" where ProcessInfo.processInfo.arguments.contains("-vipi-message-actions-qa"):
            value = ["version": 1, "device_id": device?.id.uuidString ?? ""]
        case _
        where path.hasSuffix("/chat-features") && ProcessInfo.processInfo.arguments.contains("-vipi-message-actions-qa"):
            value = ["version": 1, "device_id": Self.actionDevice.uuidString]
        case ChatFeedback.route where method == "GET": value = ["available": true]
        case ChatFeedback.route where method == "PUT":
            guard let body, let choice = try JSONDecoder().decode([String: String].self, from: body)["choice"],
                FundingChoice(rawValue: choice) != nil, let ack = NoContentResponse() as? T
            else { throw MessageVault.Failure.invalidRecord }
            return ack

        case "/v1/me":
            value = ["id": owner.uuidString, "username": "timeline_qa", "display_name": "Timeline QA"]
            if ProcessInfo.processInfo.arguments.contains("-vipi-streaks-qa") { value["group_protocol_version"] = 1 }
        case "/v1/groups" where ProcessInfo.processInfo.arguments.contains("-vipi-streaks-qa"):
            let members: [[String: Any]] = [
                (owner, "Me", "owner"), (peer, "Alex", "member"), (Self.streakMember, "Maya", "member")
            ].map { person, name, role in
                [
                    "user_id": person.uuidString, "display_name": name, "username": name.lowercased(), "role": role,
                    "joined_epoch": 1
                ]
            }
            let group: [String: Any] = [
                "id": Self.streakGroup.uuidString, "title": "Book club", "epoch": 1, "state": "active",
                "members": members, "invitations": []
            ]
            value = ["groups": [group], "invitations": []]
        case "/v1/people/alex": value = ["id": peer.uuidString, "username": "alex", "display_name": "Alex"]
        case _ where ProcessInfo.processInfo.arguments.contains("-vipi-streaks-qa") && path.hasPrefix("/v1/people/"):
            guard let friend = Self.streakFriends.first(where: { path == "/v1/people/" + $0.name.lowercased() }) else {
                throw MessageVault.Failure.invalidRecord
            }
            value = ["id": friend.id.uuidString, "username": friend.name.lowercased(), "display_name": friend.name]
        case "/v1/devices":
            guard let body, let input = try JSONSerialization.jsonObject(with: body) as? [String: Any],
                let id = input["device_id"]
            else { throw ServiceFailure(status: 0, code: "invalid_fixture") }
            value = ["id": id, "active": true]
        case "/v1/keys": value = ["revision": 1, "remaining": 20]
        case "/v1/messages/pending": value = ["messages": [], "next_cursor": NSNull()]
        default:
            guard path.hasPrefix("/v1/blocks/") else { throw ServiceFailure(status: 0, code: "offline") }
            value = ["blocked": false]
        }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
}

/// Binds actual Friend playback objects for read-only DEBUG lifecycle evidence.
/// No row, session, navigation, language, playback or translation is injected here.
struct PendingPairRootBinding: View {
    let autoplay: ChatAutoplay
    let speech: SpeechPlayback
    var body: some View {
        if let fixture = FirstMonthRootQualification.current, fixture.pendingPairEnabled {
            Color.clear.frame(width: 1, height: 1).allowsHitTesting(false).accessibilityHidden(true)
                .task(id: autoplay.ownerID) { fixture.bindPendingPair(autoplay: autoplay, speech: speech) }
        }
    }
}

/// Supplies owned local service/auth boundaries to the actual app root. No
/// session, profile, chat row, draft or navigation state is injected.
@MainActor final class FirstMonthRootQualification: ChatTransport {
    private(set) static var current: FirstMonthRootQualification?
    private struct Ledger: Codable {
        let account: UUID, peer: UUID, user: String
        var starts = 0, launches = 0, exchanges = 0, profiles = 0, registrations = 0
        var decrypted = 0, expiredPosts = 0, unexpected = 0
        var controlledTranslations: [String] = []
        var controlledTranslationFailures = 0
        var cueCaptured: Bool?
        var cuePriorSeen: Bool?
        var invitationCaptured: Bool?
        var priorInvitation: String?
        var immersionCaptured: Bool?
        var priorImmersionMode: String?
        var groupRequests: Int?
        var friendUsernameLookups: Int?
        var typingUpdates: [Bool]?
        var visibleReadRequests: Int?
        var polishBacklogSeeded: Bool?
        var pendingHash: String?, verifierHash: String?, callback: String?
        var device: DeviceCredential?
        var acceptedIDs = Set<String>(), expiredIDs = Set<String>(), receipts = Set<String>()
        var inbox: [Data] = []
    }
    private static var directory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("FirstMonthRootQualification", isDirectory: true)
    }
    private static var file: URL { directory.appendingPathComponent("owner.json") }
    private var ledger: Ledger
    private let peerVault: MessageVault
    private let peerCore: MessagingCore
    private let publication: KeyPublication
    private var chats: [ChatSession] = []
    private var createdGroups: [String: [String: Any]] = [:]
    private var directoryFixtureEnabled: Bool {
        ProcessInfo.processInfo.arguments.contains("-vipi-group-directory-qa")
    }
    private var directoryOwner: [String: Any] {
        [
            "user_id": ledger.account.uuidString, "display_name": "Alex",
            "username": "firstmonth_qa", "role": "owner", "joined_epoch": 1
        ]
    }
    /// Screenshot-only data, not evidence of Apple Translation inference.
    private static var marketingEnabled: Bool {
        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
            && ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa")
            && ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa")
            && ProcessInfo.processInfo.arguments.contains("-vipi-marketing-root-qa")
    }
    private static let marketingTurns: [(outgoing: Bool, text: String, practice: String)] = [
        (true, "Would you like to get coffee tomorrow?", "明天想一起喝咖啡吗？"),
        (false, "Yes! Let's meet at ten.", "好啊！我们十点见。"),
        (true, "I'll see you at the café.", "我们在咖啡馆见。"),
        (false, "I'll bring my camera.", "我会带上相机。"),
        (true, "We can take a walk after coffee.", "喝完咖啡后，我们可以散散步。")
    ]
    var pendingPairEnabled: Bool {
        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
            && ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa")
            && ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa")
            && ProcessInfo.processInfo.arguments.contains("-vipi-pending-pair-root-qa")
    }
    private struct PairCall {
        let id: UUID
        let source: String
        let target: String
        let textSHA256: String
        var returned = false
    }
    private var pairCalls: [PairCall] = []
    private var pairGates: [UUID: CheckedContinuation<Void, Never>] = [:]
    private(set) var pendingPairReleased = false
    private weak var pairPlayback: ChatAutoplay?
    private weak var pairSpeech: SpeechPlayback?
    private var oldPairOwner: ConversationImmersion?
    private var oldPairPlayback: ChatAutoplay?
    private var oldPairTasks: [ImmersionRequestIdentity: Task<FullMessageTranslation?, Never>] = [:]
    private var oldPairTaskResults: [[String: Any]] = []
    private var oldPlaybackTasks: [String: Task<Void, Never>] = [:]
    private var oldPlaybackTaskResults: [[String: Any]] = []
    func bindPendingPair(autoplay: ChatAutoplay, speech: SpeechPlayback) {
        guard pendingPairEnabled else { return }
        pairPlayback = autoplay
        pairSpeech = speech
    }
    private func pendingPairTranslation(_ text: String, pair: TranslationPair) async throws -> String {
        try Self.validate(ledger)
        let values: [String: [String: String]] = [
            "Hello! How are you?": ["zh": "你好！你好吗？", "ar": "مرحبًا! كيف حالك؟", "fr": "Bonjour ! Comment vas-tu ?"],
            Self.outgoing: [
                "zh": "明天下班后我们能一起喝咖啡吗？", "ar": "هل يمكننا شرب القهوة معًا بعد العمل غدًا؟",
                "fr": "Peut-on prendre un café ensemble après le travail demain ?"
            ],
            Self.firstReply: ["zh": "你的私人消息已送达。", "ar": "وصلت رسالتك الخاصة.", "fr": "Ton message privé est arrivé."]
        ]
        guard pair.source == "en", let output = values[text]?[pair.target] else {
            throw ServiceFailure(status: 0, code: "pending_pair_controlled_output_not_supplied")
        }
        let id = UUID()
        pairCalls.append(
            .init(id: id, source: pair.source, target: pair.target, textSHA256: Self.hash(Data(text.utf8))))
        ledger.controlledTranslations.append(Self.hash(Data(text.utf8)))
        try save()
        if pair.target == "zh", text != "Hello! How are you?" {
            guard !pendingPairReleased else {
                throw ServiceFailure(status: 0, code: "pending_pair_unexpected_old_retranslation")
            }
            // Deliberately non-cooperative SDK boundary: cancellation alone does
            // not release this continuation. The UI releases the real old result
            // only after selecting both new languages and returning to Friend.
            await withCheckedContinuation { pairGates[id] = $0 }
        }
        if let index = pairCalls.firstIndex(where: { $0.id == id }) { pairCalls[index].returned = true }
        return output
    }
    func releasePendingPair() {
        guard pendingPairEnabled, !pendingPairReleased else { return }
        capturePendingPairTasks()
        pendingPairReleased = true
        let held = Array(pairGates.values)
        pairGates.removeAll()
        for continuation in held { continuation.resume() }
        let retained = oldPairTasks, playbackTasks = oldPlaybackTasks
        Task { @MainActor [self] in
            // The exact Tasks captured before registry invalidation, not a new
            // request or a registry count, establish final cancellation/completion.
            for (identity, task) in retained.sorted(by: { $0.key.messageID < $1.key.messageID }) {
                let value = await task.value
                oldPairTaskResults.append([
                    "id": identity.messageID, "source": identity.source, "target": identity.target,
                    "generation": identity.generation.uuidString, "completed": true,
                    "cancelled": task.isCancelled, "has_value": value != nil
                ])
            }
            for (kind, task) in playbackTasks.sorted(by: { $0.key < $1.key }) {
                await task.value
                oldPlaybackTaskResults.append(["kind": kind, "completed": true, "cancelled": task.isCancelled])
            }
        }
    }
    private func capturePendingPairTasks() {
        guard pendingPairEnabled, !pendingPairReleased, let owner = chats.last?.translationOwner,
            owner.pair == TranslationPair(source: "en", target: "zh"), !pairGates.isEmpty
        else { return }
        if oldPairOwner == nil {
            oldPairOwner = owner
            oldPairPlayback = pairPlayback
        }
        guard oldPairOwner === owner else { return }
        for (kind, task) in oldPairPlayback?.pendingPairQualificationTasks ?? [:] { oldPlaybackTasks[kind] = task }
        for (identity, task) in owner.pendingPairQualificationTasks
        where identity.text == Self.outgoing || identity.text == Self.firstReply {
            oldPairTasks[identity] = task
        }
    }
    private func pendingPairProof(rows: [ChatItem], vault: MessageVault) throws -> [String: Any] {
        capturePendingPairTasks()
        let rowIDs = Set(rows.map { $0.id.uuidString.lowercased() })
        var envelopes: [String: String] = [:]
        for row in rows {
            let id = row.id.uuidString.lowercased(), namespace = row.outgoing ? "outgoing" : "incoming"
            guard let bytes = try vault.get(namespace, id) else { throw MessageJournal.Failure.missingMessage }
            let saved = try JSONDecoder().decode(StoredChat.self, from: bytes)
            guard saved.text.utf8.elementsEqual(row.text.utf8) else { throw MessageVault.Failure.incompatible }
            envelopes[id] = Self.hash(saved.envelope.fingerprint())
        }
        // This uniquely validated synthetic account has at most sixteen derivative rows.
        // pageIDs requires a nonempty key prefix; enumerate this owned fixture only.
        let keys = try vault.ids("full-message-translation")
        guard keys.count <= 16 else { throw MessageVault.Failure.incompatible }
        var cache: [[String: Any]] = []
        for key in keys {
            guard let bytes = try vault.get("full-message-translation", key),
                let saved = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                let id = saved["messageID"] as? String,
                let source = saved["source"] as? String, let target = saved["target"] as? String,
                let value = saved["value"] as? [String: Any],
                let original = value["original"] as? String
            else { throw MessageVault.Failure.incompatible }
            guard rowIDs.contains(id.lowercased()) else { throw MessageVault.Failure.incompatible }
            cache.append([
                "id": id, "source": source, "target": target, "original_sha256": Self.hash(Data(original.utf8)),
                "practice_text": value["practiceText"] as? String ?? "",
                "practice_reading": value["practiceReading"] as? String ?? "",
                "reading_status": (value["readingState"] as? [String: Any])?["status"] as? String ?? ""
            ])
        }
        let current = chats.last?.translationOwner
        return [
            "controlled_provider": true, "gate_released": pendingPairReleased, "held_calls": pairGates.count,
            "calls": pairCalls.map {
                [
                    "id": $0.id.uuidString, "source": $0.source, "target": $0.target, "text_sha256": $0.textSHA256,
                    "returned": $0.returned
                ] as [String: Any]
            },
            "known": UserDefaults.standard.string(forKey: "knownLanguage") ?? "",
            "practice": UserDefaults.standard.string(forKey: "targetLanguage") ?? "",
            "current_owner_pair": ["source": current?.pair.source ?? "", "target": current?.pair.target ?? ""],
            "old_owner_closed": oldPairOwner?.pendingPairQualificationClosed ?? false,
            "retained_task_ids": oldPairTasks.keys.map(\.messageID).sorted(),
            "task_results": oldPairTaskResults,
            "retained_playback_kinds": oldPlaybackTasks.keys.sorted(), "playback_task_results": oldPlaybackTaskResults,
            "playback": pairPlayback?.pendingPairQualificationState ?? [:],
            "old_playback": oldPairPlayback?.pendingPairQualificationState ?? [:],
            "speech_state": pairSpeech.map { String(describing: $0.state) } ?? "unbound",
            "active_message": pairSpeech?.activeMessage ?? "", "envelope_fingerprints": envelopes, "cache": cache
        ]
    }
    private var stores: [SubscriptionStore] = []
    private var owners: [BotConversationOwner] = []
    private static var copyRootEnabled: Bool {
        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
            && ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa")
            && ProcessInfo.processInfo.arguments.contains("-vipi-copy-original-root-qa")
    }
    static let copyClipboardSentinel = "Vipi owned simulator Copy sentinel — no customer text"
    private static let copyImported = "Imported original: cafe\u{301} 👩🏽‍💻\nSecond line."
    private static let copyBotOriginals = [
        "Original Bot request: cafe\u{301} 👩🏽‍💻\nSecond line.",
        "Original Bot reply: keep this exact text.", "Saved Bot reply without report receipt."
    ]
    private var copyAllowance: [String: Any] {
        [
            "available": true, "service_ready": true, "remaining_replies": 150, "monthly_replies": 150,
            "resets_at": "2099-01-01T00:00:00Z", "max_context_bytes": 8192
        ]
    }
    private func seedCopyImported() throws {
        guard Self.copyRootEnabled, !ledger.acceptedIDs.isEmpty, ledger.device != nil else { return }
        let vault = try MessageVault(account: ledger.account)
        defer { try? vault.close() }
        let id = UUID(uuidString: "93632D92-287A-418F-91B5-8939D46B28F3")!
        try vault.transaction {
            if let existing = try vault.get("imported", id.uuidString.lowercased()) {
                let saved = try JSONDecoder().decode(HistoryBackupMessage.self, from: existing)
                guard saved.id == id, saved.peer == ledger.peer, !saved.outgoing, saved.text == Self.copyImported else {
                    throw CancellationError()
                }
            } else {
                let message = HistoryBackupMessage(
                    id: id, peer: ledger.peer, outgoing: false,
                    createdAt: Int64(Date().timeIntervalSince1970 * 1000) - 5_000, text: Self.copyImported)
                try vault.put("imported", id.uuidString.lowercased(), JSONEncoder().encode(message))
                try ConversationHistory.record(
                    vault, kind: "imported", id: id, peer: ledger.peer, createdAt: message.createdAt)
            }
        }
    }
    private(set) static var cleaned = false
    private static let access = "synthetic-first-month-access-never-transmitted"
    private static let refresh = "synthetic-first-month-refresh-never-transmitted"
    static var incrementalJourney: Bool {
        ProcessInfo.processInfo.arguments.contains("-vipi-incremental-invitation-qa")
    }
    static var outgoing: String {
        if incrementalJourney { return "Water, water!" }
        if marketingEnabled { return marketingTurns[0].text }
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "-vipi-first-month-reading-probe") else {
            return "Hello Alex. This is my first private message."
        }
        precondition(index + 1 < arguments.count, "Owned reading probe requires a known fixture")
        switch arguments[index + 1] {
        case "en-zh": return "Can we have coffee together after work tomorrow?"
        case "ar-en": return "هل يمكن أن نشرب القهوة معًا بعد العمل غدًا؟"
        default: preconditionFailure("Unknown first-month reading fixture")
        }
    }
    static var firstReply: String {
        incrementalJourney
            ? "water and bread" : marketingEnabled ? marketingTurns[1].text : "Your private message arrived."
    }
    static let expiredReply = "You can still read my reply."
    private static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    private func save() throws { try JSONEncoder().encode(ledger).write(to: Self.file, options: .atomic) }
    private static func validate(_ value: Ledger) throws {
        guard
            directory.standardizedFileURL.pathComponents
                == directory.resolvingSymlinksInPath().standardizedFileURL.pathComponents,
            file.standardizedFileURL.pathComponents == file.resolvingSymlinksInPath().standardizedFileURL.pathComponents
        else {
            throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_ledger")
        }
        let messages = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages")
        // Resolve the existing parent independently: resolving a nonexistent
        // leaf alone can miss a parent symlink on Foundation.
        for path in [
            messages, messages.appendingPathComponent(value.account.uuidString.lowercased(), isDirectory: true),
            directory.appendingPathComponent("peer", isDirectory: true)
        ] {
            guard
                path.standardizedFileURL.pathComponents
                    == path.resolvingSymlinksInPath().standardizedFileURL.pathComponents
            else {
                throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_path")
            }
        }
        guard value.account != value.peer, value.user == "first-month-root-ui-" + value.account.uuidString.lowercased(),
            try KeychainDeletionStore().load() == nil,
            try KeychainStore.read(account: "pending-identity-link") == nil
        else {
            throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_identity")
        }
        if let bytes = try KeychainStore.read(account: "session") {
            let session = try JSONDecoder().decode(VipiSession.self, from: bytes)
            guard session.userID == value.user, session.authority == .vipiStaging,
                session.accessToken == access, session.refreshToken == refresh
            else {
                throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_session")
            }
        }
        if let bytes = try KeychainStore.read(account: "pending-sign-in") {
            guard hash(bytes) == value.pendingHash else {
                throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_pending")
            }
        }
        if let bytes = try KeychainStore.read(account: "profile-" + value.user) {
            let profile = try JSONDecoder().decode(ChatProfile.self, from: bytes)
            guard profile.id == value.account, profile.username == "firstmonth_qa" else {
                throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_profile")
            }
        }
    }
    static func prepareIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa") else { return }
        precondition(
            Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
                && !ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-qa"), "Owned first-month root only")
        do {
            if ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-cleanup") {
                try cleanup()
                cleaned = true
                return
            }
            if copyRootEnabled {
                precondition(
                    ProcessInfo.processInfo.environment["VIPI_COPY_CLIPBOARD_ISOLATED"] == "true",
                    "Copy QA requires owned simulator clipboard isolation")
            }
            current = try FirstMonthRootQualification()
            if ProcessInfo.processInfo.arguments.contains("-vipi-immersion-mode-qa"), let current,
                current.ledger.immersionCaptured != true
            {
                let prior = UserDefaults.standard.object(forKey: "immersionMode")
                guard prior == nil || prior is String else {
                    throw ServiceFailure(status: 0, code: "preserve_unknown_immersion_mode")
                }
                current.ledger.priorImmersionMode = prior as? String
                current.ledger.immersionCaptured = true
                try current.save()
                UserDefaults.standard.removeObject(forKey: "immersionMode")
            }
            if ProcessInfo.processInfo.arguments.contains("-vipi-invitation-root-qa"), let current,
                current.ledger.invitationCaptured != true
            {
                precondition(ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa"))
                let prior = UserDefaults.standard.object(forKey: "invitationUsername")
                guard prior == nil || prior is String else {
                    throw ServiceFailure(status: 0, code: "preserve_unknown_invitation_preference")
                }
                current.ledger.priorInvitation = prior as? String
                current.ledger.invitationCaptured = true
                try current.save()
                UserDefaults.standard.removeObject(forKey: "invitationUsername")
            }
            if ProcessInfo.processInfo.arguments.contains("-vipi-marketing-root-qa") {
                precondition(
                    marketingEnabled && !copyRootEnabled && !(current?.pendingPairEnabled ?? false),
                    "Natural marketing requires the isolated controlled full-message fixture")
            }
            if (ProcessInfo.processInfo.arguments.contains("-vipi-first-cue-root-qa") || marketingEnabled), let current
            {
                precondition(ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa"))
                if current.ledger.cueCaptured != true {
                    let previous = UserDefaults.standard.object(forKey: "full-message-gestures-v1-seen")
                    guard previous == nil || previous is Bool else {
                        throw ServiceFailure(status: 0, code: "preserve_unknown_gesture_preference")
                    }
                    current.ledger.cuePriorSeen = previous as? Bool
                    current.ledger.cueCaptured = true
                    try current.save()
                    UserDefaults.standard.set(false, forKey: "full-message-gestures-v1-seen")
                }
            }
            if copyRootEnabled {
                // Only after existing account/path authority has validated.
                // Native owner isolated sync; never inspect a preexisting value.
                UIPasteboard.general.string = copyClipboardSentinel
            }
        } catch { preconditionFailure("Preserve unknown first-month QA identity before bootstrap") }
    }
    private init() throws {
        if FileManager.default.fileExists(atPath: Self.file.path) {
            ledger = try JSONDecoder().decode(Ledger.self, from: Data(contentsOf: Self.file))
        } else {
            for key in ["session", "pending-sign-in", "pending-identity-link", "account-deletion"] {
                guard try KeychainStore.read(account: key) == nil else {
                    throw ServiceFailure(status: 0, code: "empty_owned_identity_required")
                }
            }
            let account = UUID()
            ledger = Ledger(
                account: account, peer: UUID(), user: "first-month-root-ui-" + account.uuidString.lowercased())
            try FileManager.default.createDirectory(at: Self.directory, withIntermediateDirectories: true)
            try JSONEncoder().encode(ledger).write(to: Self.file, options: .atomic)
        }
        try Self.validate(ledger)
        peerVault = try MessageVault(account: ledger.peer, directory: Self.directory.appendingPathComponent("peer"))
        peerCore = try MessagingCore(vault: peerVault)
        publication = try peerCore.keys.publication(now: Int64(Date().timeIntervalSince1970 * 1000), count: 2)
        try peerCore.keys.published(revision: publication.revision)
        ledger.starts += 1
        try save()
    }
    func bind(_ authentication: AuthenticationManager) {
        authentication.qualificationSignInLaunch = { [weak self] url in
            guard let self, let bytes = try KeychainStore.read(account: "pending-sign-in") else {
                throw CancellationError()
            }
            let pending = try JSONDecoder().decode(PendingSignIn.self, from: bytes)
            guard pending.authority == .vipiStaging, pending.expectedUser == nil, pending.link == nil,
                pending.sourceLink == nil,
                URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "state" }
                )?.value == pending.state
            else {
                throw ServiceFailure(status: 0, code: "first_month_auth_boundary_changed")
            }
            self.ledger.pendingHash = Self.hash(bytes)
            self.ledger.verifierHash = Self.hash(Data(pending.verifier.utf8))
            var callback = URLComponents(string: "co.fallsoft.vipi://auth/callback")!
            callback.queryItems = [
                .init(name: "state", value: pending.state), .init(name: "code", value: "owned-local-first-month-code")
            ]
            self.ledger.callback = callback.url!.absoluteString
            self.ledger.launches += 1
            try self.save()
        }
        authentication.qualificationCodeExchange = { [weak self] code, verifier, authority in
            guard let self, code == "owned-local-first-month-code", authority == .vipiStaging,
                Self.hash(Data(verifier.utf8)) == self.ledger.verifierHash,
                self.ledger.exchanges == 0
            else { throw ServiceFailure(status: 0, code: "invalid_first_month_code") }
            self.ledger.exchanges += 1
            try self.save()
            return VipiSession(
                userID: self.ledger.user, accessToken: Self.access, refreshToken: Self.refresh, authority: authority)
        }
    }
    /// Simulator-only SDK boundary. Real auth/profile/Signal/vault/root views
    /// remain production code; these explicitly supplied outputs are not model proof.
    var fullTranslationServices: MessageTranslationServices? {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa") else { return nil }
        precondition(Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa")
        return MessageTranslationServices(
            status: { [weak self] _ in
                guard let self, (try? Self.validate(self.ledger)) != nil else { return .unsupported }
                return .installed
            },
            translate: { [weak self] text, pair in
                guard let self else { throw CancellationError() }
                try Self.validate(self.ledger)
                if self.pendingPairEnabled { return try await self.pendingPairTranslation(text, pair: pair) }
                guard pair == TranslationPair(source: "en", target: "zh") else {
                    throw ServiceFailure(status: 0, code: "controlled_sdk_pair_not_supplied")
                }
                self.ledger.controlledTranslations.append(Self.hash(Data(text.utf8)))
                try self.save()
                if Self.incrementalJourney {
                    // These controlled word equivalents make the progression observable
                    // through the real signed-in chat UI on a simulator without models.
                    switch text.lowercased() {
                    case "water, water!": return "水，水！"
                    case "water and bread": return "水和面包"
                    case "hello": return "你好"
                    case "water": return "水"
                    case "bread": return "面包"
                    default: return text
                    }
                }
                if Self.marketingEnabled {
                    if text == "Hello! How are you?" { return "你好！你好吗？" }
                    // The journey opens in Shallow before switching to full sentences.
                    switch text.lowercased() {
                    case "coffee": return "咖啡"
                    case "meet": return "见面"
                    default: break
                    }
                    if Self.marketingTurns.prefix(2).contains(where: { turn in
                        IncrementalWords.tokens(turn.text, language: "en").contains { $0.text == text }
                    }) {
                        return text
                    }
                    guard let turn = Self.marketingTurns.first(where: { $0.text == text }) else {
                        throw ServiceFailure(status: 0, code: "marketing_controlled_output_not_supplied")
                    }
                    return turn.practice
                }
                let output: String
                switch text {
                case "Hello! How are you?": output = "你好！你好吗？"
                case Self.outgoing:
                    if self.ledger.controlledTranslationFailures == 0
                        && !ProcessInfo.processInfo.arguments.contains("-vipi-first-cue-root-qa")
                    {
                        self.ledger.controlledTranslationFailures += 1
                        try self.save()
                        throw ServiceFailure(status: 0, code: "controlled_sdk_translation_failed_once")
                    }
                    output = "明天下班后我们能一起喝咖啡吗？"
                case Self.firstReply: output = "你的私人消息已送达。"
                case Self.expiredReply: output = "你仍然可以阅读我的回复。"
                case Self.copyImported where Self.copyRootEnabled: output = "导入的原始消息：第二行。"
                case Self.copyBotOriginals[0] where Self.copyRootEnabled: output = "原始机器人请求：第二行。"
                case Self.copyBotOriginals[1] where Self.copyRootEnabled: output = "原始机器人回复：请保留这条完整的消息。"
                case Self.copyBotOriginals[2] where Self.copyRootEnabled: output = "没有举报凭据的已保存机器人回复。"
                default: throw ServiceFailure(status: 0, code: "controlled_sdk_output_not_supplied")
                }
                return output
            },
            prepare: { [weak self] _ in
                guard let self else { throw CancellationError() }
                try Self.validate(self.ledger)
            })
    }
    var connection: ConnectedChatRoot.Qualification {
        .init(
            makeChat: { [self] authentication, user in
                try Self.validate(ledger)
                guard user == ledger.user, authentication.session?.userID == user else { throw CancellationError() }
                let chat = try ChatSession(api: self, userID: user)
                chats.append(chat)
                return chat
            },
            makeSubscriptions: { [self] _, user, account in
                guard user == ledger.user, account == ledger.account else { throw CancellationError() }
                let store = SubscriptionStore(api: self, accountToken: account)
                stores.append(store)
                return store
            },
            makeBotOwner: { [self] account in
                let owner = BotConversationOwner()
                owners.append(owner)
                guard Self.copyRootEnabled, let account else { return owner }
                do {
                    try Self.validate(ledger)
                    guard account == ledger.account, ledger.device != nil else { throw CancellationError() }
                    let vault = try MessageVault(account: account)
                    do {
                        try vault.transaction {
                            if try vault.get("bot-local", "copy-seeded-v1") == nil {
                                for (index, text) in Self.copyBotOriginals.enumerated() {
                                    let message = BotMessage(
                                        id: UUID(), role: index == 0 ? "user" : "assistant", text: text,
                                        createdAt: Date().addingTimeInterval(Double(index) - 3), state: "complete",
                                        requestID: index == 1 ? UUID() : nil)
                                    try vault.put("bot-message", message.key, JSONEncoder().encode(message))
                                }
                                try vault.put("bot-local", "consent", Data("deepseek-v1".utf8))
                                try vault.put("bot-local", "copy-seeded-v1", Data([1]))
                            }
                        }
                        let session = try BotSession(api: self, vault: vault, generator: TimelineOnlyBotGenerator())
                        _ = try owner.session(for: account) { session }
                    } catch {
                        try? vault.close()
                        throw error
                    }
                } catch { preconditionFailure("Preserve unknown Copy root Bot fixture; no live fallback") }
                return owner
            })
    }
    private static var illustrationGroupsFixture: Bool {
        ProcessInfo.processInfo.arguments.contains("-vipi-illustration-groups-qa")
    }
    private var profile: [String: Any] {
        var value: [String: Any] = [
            "id": ledger.account.uuidString, "username": "firstmonth_qa",
            "display_name": Self.marketingEnabled ? "Alex" : "First Month QA"
        ]
        if directoryFixtureEnabled || Self.illustrationGroupsFixture { value["group_protocol_version"] = 1 }
        return value
    }
    private func reply(_ text: String) throws {
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let routed = try peerCore.queue(id: UUID(), peer: ledger.account, text: text, createdAt: now, now: now)
        var value = try JSONSerialization.jsonObject(with: routed.sendData()) as! [String: Any]
        value["sender_id"] = ledger.peer.uuidString
        value["sender_device_id"] = peerCore.device.id.uuidString
        ledger.inbox.append(try JSONSerialization.data(withJSONObject: value))
        if ProcessInfo.processInfo.arguments.contains("-vipi-chat-polish-qa") {
            for chat in chats { chat.peerActivityEvent(.typing(ledger.peer, true)) }
        }
    }
    func request<T: Decodable>(
        _ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String],
        as type: T.Type
    ) async throws -> T {
        try Self.validate(ledger)
        let input = try body.map { try JSONSerialization.jsonObject(with: $0) as? [String: Any] ?? [:] } ?? [:]
        if path.hasPrefix("/v1/groups") {
            ledger.groupRequests = (ledger.groupRequests ?? 0) + 1
            try save()
        }
        let value: [String: Any]
        switch (method, path) {

        case ("GET", "/v1/groups") where directoryFixtureEnabled:
            let peer: [String: Any] = [
                "user_id": ledger.peer.uuidString, "display_name": "Maya",
                "username": "inbox_qa_0", "role": "member", "joined_epoch": 1
            ]
            let group: [String: Any] = [
                "id": "80b02690-c1eb-4922-a2ab-8c5fe9c4b2f1", "title": "Book club",
                "epoch": 1, "state": "active", "members": [directoryOwner, peer], "invitations": []
            ]
            let invitation: [String: Any] = [
                "id": "2da68340-02e0-4c55-b278-b2ed81713464",
                "group_id": "9fec7471-ee13-4f41-90bd-7d037c226a15", "title": "Weekend plans",
                "invited_by": ledger.peer.uuidString, "epoch": 1, "expires_at": "2099-01-01T00:00:00Z"
            ]
            value = ["groups": [group] + Array(createdGroups.values), "invitations": [invitation]]
        case ("POST", "/v1/groups") where directoryFixtureEnabled:
            guard let id = input["id"] as? String, UUID(uuidString: id) != nil,
                createdGroups[id] == nil, let title = input["title"] as? String
            else { throw GroupsFailure.invalidResponse }
            value = [
                "id": id, "title": title, "epoch": 1, "state": "active", "members": [directoryOwner], "invitations": []
            ]
            createdGroups[id] = value
        case ("POST", _)
        where directoryFixtureEnabled && path.hasPrefix("/v1/groups/") && path.hasSuffix("/invitations"):
            let parts = path.split(separator: "/")
            guard parts.count == 4, var group = createdGroups[String(parts[2])],
                let person = input["user_id"] as? String,
                let request = input["request_id"] as? String
            else { throw GroupsFailure.invalidResponse }
            let pending = [
                "id": request, "user_id": person, "invited_by": ledger.account.uuidString,
                "expires_at": "2099-01-01T00:00:00Z", "state": "pending"
            ]
            group["invitations"] = (group["invitations"] as? [[String: String]] ?? []) + [pending]
            createdGroups[String(parts[2])] = group
            value = group
        case ("GET", "/v1/groups")
        where Self.illustrationGroupsFixture && ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa"):
            value = ["groups": [], "invitations": []]
        case ("GET", "/v1/me"):
            guard ledger.profiles == 1 else { throw ServiceFailure(status: 404, code: "profile_required") }
            value = profile
        case ("PUT", "/v1/me"):
            guard ledger.profiles == 0, input["username"] as? String == "firstmonth_qa",
                input["display_name"] as? String == (Self.marketingEnabled ? "Alex" : "First Month QA")
            else { throw ServiceFailure(status: 0, code: "unexpected_first_month_profile") }
            ledger.profiles += 1
            value = profile
        case ("POST", "/v1/devices"):
            guard ledger.registrations == 0, let raw = input["device_id"] as? String, let id = UUID(uuidString: raw),
                let secret = input["secret"] as? String
            else { throw ServiceFailure(status: 0, code: "unexpected_first_month_registration") }
            ledger.device = DeviceCredential(id: id, secret: secret)
            ledger.registrations += 1
            value = ["id": id.uuidString, "active": true]
        case ("PUT", "/v1/devices/chat-features"),
            ("GET", "/v1/people/" + ledger.peer.uuidString.lowercased() + "/chat-features"):
            do {
                // validate(ledger) already checks the identity of a present session.
                guard try KeychainStore.read(account: "session") != nil else {
                    throw ServiceFailure(status: 401, code: "sign_in_required")
                }
                let version: Int
                if method == "PUT" {
                    guard Set(input.keys) == ["version"], let number = input["version"] as? NSNumber,
                        CFGetTypeID(number) != CFBooleanGetTypeID(), !CFNumberIsFloatType(number),
                        number == 0 || number == 1
                    else { throw ServiceFailure(status: 422, code: "invalid_request") }
                    version = number.intValue
                } else {
                    // This peer has encryption keys but has never advertised chat features.
                    version = 0
                }
                guard ledger.profiles == 1 else { throw ServiceFailure(status: 404, code: "profile_required") }
                guard let registered = ledger.device, let device,
                    device.id == registered.id, device.secret == registered.secret
                else { throw ServiceFailure(status: 401, code: "device_revoked") }
                let deviceID = method == "PUT" ? registered.id : peerCore.device.id
                value = ["version": version, "device_id": deviceID.uuidString.lowercased()]
            } catch {
                ledger.unexpected += 1
                try save()
                throw error
            }
        case ("GET", "/v1/keys"): value = ["revision": 1, "remaining": 20]
        case ("GET", "/v1/people/alex"), ("GET", "/v1/people/by-id/" + ledger.peer.uuidString.lowercased()):
            if path == "/v1/people/alex" {
                ledger.friendUsernameLookups = (ledger.friendUsernameLookups ?? 0) + 1
                try save()
            }
            value = [
                "id": ledger.peer.uuidString, "username": Self.marketingEnabled ? "maya" : "alex",
                "display_name": Self.marketingEnabled
                    ? "Maya"
                    : (ProcessInfo.processInfo.arguments.contains("-vipi-long-header-contact-qa")
                        ? "Alexandria Rivera Hernández" : "Alex")
            ]
        case ("GET", "/v1/people/maya") where Self.marketingEnabled:
            value = ["id": ledger.peer.uuidString, "username": "maya", "display_name": "Maya"]
        case ("GET", let candidate)
        where ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa")
            && candidate.hasPrefix("/v1/blocks/")
            && chats.contains(where: { chat in
                chat.threads.contains(where: { candidate == "/v1/blocks/" + $0.peer.uuidString.lowercased() })
            }):
            value = ["blocked": false]
        case ("GET", "/v1/blocks/" + ledger.peer.uuidString.lowercased()):
            // Only after the real expired-send queue survives process restart:
            // exercise a distinct local block warning beside transport recovery.
            if ledger.starts >= 3 && !ledger.expiredIDs.isEmpty {
                throw ServiceFailure(status: 0, code: "offline")
            }
            value = ["blocked": false]
        case ("POST", "/v1/people/" + ledger.peer.uuidString.lowercased() + "/keys"):
            guard let raw = input["request_id"] as? String, let request = UUID(uuidString: raw) else {
                throw ServiceFailure(status: 0, code: "invalid_first_month_claim")
            }
            let keys = ClaimedKeys(
                request_id: request, user_id: ledger.peer, device_id: peerCore.device.id, signal_device_id: 1,
                registration_id: publication.registration_id, identity_key: publication.identity_key,
                signed: publication.signed, one_time: publication.one_time[0])
            return try JSONDecoder().decode(type, from: JSONEncoder().encode(keys))
        case ("POST", "/v1/messages"):
            guard device?.id == ledger.device?.id, device?.secret == ledger.device?.secret, let body,
                let id = input["id"] as? String
            else { throw ServiceFailure(status: 0, code: "invalid_first_month_route") }
            if Self.marketingEnabled {
                if ledger.acceptedIDs.contains(id) {
                    value = ["state": "delivered"]
                } else {
                    let outgoing = Self.marketingTurns.filter { $0.outgoing }, index = ledger.decrypted
                    guard index < outgoing.count, ledger.acceptedIDs.count == index else {
                        throw ServiceFailure(status: 0, code: "unexpected_marketing_message_count")
                    }
                    var routed = try JSONSerialization.jsonObject(with: body) as! [String: Any]
                    routed["sender_id"] = ledger.account.uuidString
                    routed["sender_device_id"] = device!.id.uuidString
                    let received = try JSONDecoder().decode(
                        RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: routed))
                    let opened = try peerCore.receive(
                        received.routed(account: ledger.peer), now: Int64(Date().timeIntervalSince1970 * 1000))
                    guard opened.text == outgoing[index].text else {
                        throw ServiceFailure(status: 0, code: "unexpected_marketing_original")
                    }
                    ledger.decrypted += 1
                    ledger.acceptedIDs.insert(id)
                    if index < 2 { try reply(Self.marketingTurns[index * 2 + 1].text) }
                    value = ["state": "delivered"]
                }
            } else if ProcessInfo.processInfo.arguments.contains("-vipi-chat-polish-qa") {
                if ledger.acceptedIDs.contains(id) {
                    value = ["state": "delivered"]
                } else {
                    var routed = try JSONSerialization.jsonObject(with: body) as! [String: Any]
                    routed["sender_id"] = ledger.account.uuidString
                    routed["sender_device_id"] = device!.id.uuidString
                    let received = try JSONDecoder().decode(
                        RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: routed))
                    let opened = try peerCore.receive(
                        received.routed(account: ledger.peer), now: Int64(Date().timeIntervalSince1970 * 1000))
                    guard [Self.outgoing, "Local send from older messages."].contains(opened.text) else {
                        throw ServiceFailure(status: 0, code: "unowned_polish_original")
                    }
                    ledger.decrypted += 1
                    ledger.acceptedIDs.insert(id)
                    try reply(Self.firstReply)
                    if ledger.polishBacklogSeeded != true {
                        for _ in 0..<27 { try reply(Self.firstReply) }
                        ledger.polishBacklogSeeded = true
                    }
                    value = ["state": "delivered"]
                }
            } else if ledger.acceptedIDs.isEmpty {
                var routed = try JSONSerialization.jsonObject(with: body) as! [String: Any]
                routed["sender_id"] = ledger.account.uuidString
                routed["sender_device_id"] = device!.id.uuidString
                let received = try JSONDecoder().decode(
                    RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: routed))
                let opened = try peerCore.receive(
                    received.routed(account: ledger.peer), now: Int64(Date().timeIntervalSince1970 * 1000))
                guard opened.text == Self.outgoing else {
                    throw ServiceFailure(status: 0, code: "unexpected_first_month_message")
                }
                ledger.decrypted += 1
                ledger.acceptedIDs.insert(id)
                try reply(Self.firstReply)
                value = ["state": "delivered"]
            } else if ledger.acceptedIDs.contains(id) {
                value = ["state": "delivered"]
            } else {
                ledger.expiredPosts += 1
                if ledger.expiredIDs.insert(id).inserted { try reply(Self.expiredReply) }
                try save()
                throw ServiceFailure(status: 402, code: "base_subscription_required")
            }
        case ("GET", "/v1/messages/pending"):
            for chat in chats { try chat.seedOwnedInboxPresentation() }
            try seedCopyImported()
            let messages = try ledger.inbox.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] }
                .filter { !ledger.receipts.contains(($0["id"] as? String ?? "").lowercased()) }
            value = ["messages": messages, "next_cursor": NSNull()]
        case ("GET", "/v1/entitlements"):
            let ended = ledger.expiredPosts > 0, end = Date(timeIntervalSince1970: 1_800_000_000),
                format = ISO8601DateFormatter()
            value = [
                "server_time": format.string(from: ended ? end : end.addingTimeInterval(-86400)),
                "base": [
                    "active": !ended, "access_source": "cardless_trial", "expires_at": format.string(from: end),
                    "cardless_trial": [
                        "active": !ended, "started_at": format.string(from: end.addingTimeInterval(-30 * 86400)),
                        "ends_at": format.string(from: end)
                    ]
                ],
                "bot_mini": [
                    "active": Self.copyRootEnabled, "available": Self.copyRootEnabled,
                    "expires_at": "2099-01-01T00:00:00Z"
                ], "billing_account_id": "local-first-month-only",
                "app_account_token": ledger.account.uuidString, "purchases_ready": ["apple": false, "google": false]
            ]
        case ("GET", "/v1/bot/allowance"):
            // The production allowance endpoint is account-authenticated; the
            // SubscriptionStore request correctly has no device credential.
            guard Self.copyRootEnabled else { throw ServiceFailure(status: 503, code: "bot_not_available") }
            if let device {
                guard device.id == ledger.device?.id, device.secret == ledger.device?.secret else {
                    throw ServiceFailure(status: 503, code: "bot_not_available")
                }
            }
            value = copyAllowance
        case ("POST", let path)
        where path == "/v1/conversations/" + ledger.peer.uuidString.lowercased() + "/typing"
            || (ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa")
                && chats.contains { chat in
                    chat.threads.contains { path == "/v1/conversations/" + $0.peer.uuidString.lowercased() + "/typing" }
                }):
            guard device?.id == ledger.device?.id, Set(input.keys) == ["active"], let active = input["active"] as? Bool
            else {
                throw ServiceFailure(status: 0, code: "invalid_owned_typing_request")
            }
            ledger.typingUpdates = (ledger.typingUpdates ?? []) + [active]
            value = [:]
        case ("POST", let path) where path == "/v1/conversations/" + ledger.peer.uuidString.lowercased() + "/receipts":
            guard device?.id == ledger.device?.id, Set(input.keys) == ["seen", "check"],
                let seen = input["seen"] as? [String], let check = input["check"] as? [String], seen.count <= 64,
                check.count <= 64
            else {
                throw ServiceFailure(status: 0, code: "invalid_owned_visible_receipt_request")
            }
            let incoming = Set(
                try ledger.inbox.map {
                    try JSONDecoder().decode(RoutedMessage.Received.self, from: $0).id.uuidString.lowercased()
                })
            guard Set(seen).isSubset(of: incoming) else {
                throw ServiceFailure(status: 0, code: "unowned_visible_receipt")
            }
            ledger.visibleReadRequests = (ledger.visibleReadRequests ?? 0) + 1
            // SDK-boundary UI fixture only. No remote reading is invented by
            // the default journey. The explicit polish test opts into a supplied
            // peer-view acknowledgement, separately from backend E2E evidence.
            let reads =
                ProcessInfo.processInfo.arguments.contains("-vipi-chat-polish-qa")
                ? check.filter { ledger.acceptedIDs.contains($0) } : []
            value = ["acknowledged": seen, "read": reads]
        case ("PUT", "/v1/devices/push"), ("DELETE", "/v1/devices/push"): value = [:]
        default:
            if method == "POST", path.hasPrefix("/v1/messages/"), path.hasSuffix("/receipt") {
                let id = String(path.dropFirst("/v1/messages/".count).dropLast("/receipt".count))
                guard
                    ledger.inbox.contains(where: {
                        (try? JSONDecoder().decode(RoutedMessage.Received.self, from: $0).id.uuidString.lowercased())
                            == id
                    })
                else { throw ServiceFailure(status: 0, code: "unknown_first_month_receipt") }
                ledger.receipts.insert(id)
                value = ["state": "delivered"]
            } else {
                ledger.unexpected += 1
                try save()
                throw ServiceFailure(status: 0, code: "unexpected_first_month_request")
            }
        }
        try save()
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
    private var speechObservations: [[String: Any]] {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "-vipi-live-immersion-state"), index + 1 < arguments.count else {
            return []
        }
        let run = arguments[index + 1]
        guard run.count == 3, run.allSatisfy(\.isNumber) else { return [] }
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("live-immersion-state-\(run).jsonl")
        guard let size = try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 524_288,
            let bytes = try? Data(contentsOf: file)
        else { return [] }
        return bytes.split(separator: 10).compactMap {
            try? JSONSerialization.jsonObject(with: Data($0)) as? [String: Any]
        }
    }
    private var compositionGeometry: [String: Any] {
        guard ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa") else { return [:] }
        var windows: [[String: Any]] = []
        for scene in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
        where scene.activationState == .foregroundActive {
            for window in scene.windows where !window.isHidden && window.alpha > 0 {
                var responders: [[String: Any]] = []
                var visited = 0
                func visit(_ view: UIView, _ depth: Int) {
                    guard depth < 32, visited < 4096 else { return }
                    visited += 1
                    if view.isFirstResponder {
                        var item: [String: Any] = [
                            "class": String(describing: type(of: view)),
                            "frame": LiveImmersionQualification.frameFields(view.convert(view.bounds, to: window))
                        ]
                        if let input = view as? any UITextInput, let range = input.selectedTextRange {
                            item["caret"] = LiveImmersionQualification.frameFields(
                                view.convert(input.caretRect(for: range.end), to: window))
                            item["selection_start"] = input.offset(from: input.beginningOfDocument, to: range.start)
                            item["selection_end"] = input.offset(from: input.beginningOfDocument, to: range.end)
                        }
                        if let input = view as? UITextView {
                            item["font_point_size"] = input.font?.pointSize ?? 0
                            item["scroll_enabled"] = input.isScrollEnabled
                            item["content_size"] = [
                                "width": input.contentSize.width, "height": input.contentSize.height
                            ]
                            item["content_offset"] = ["x": input.contentOffset.x, "y": input.contentOffset.y]
                        } else if let input = view as? UITextField {
                            item["font_point_size"] = input.font?.pointSize ?? 0
                        }
                        responders.append(item)
                    }
                    for child in view.subviews { visit(child, depth + 1) }
                }
                visit(window, 0)
                windows.append([
                    "window": LiveImmersionQualification.frameFields(window.bounds),
                    "keyboard_guide": LiveImmersionQualification.frameFields(window.keyboardLayoutGuide.layoutFrame),
                    "first_responders": responders
                ])
            }
        }
        return ["sample_uptime": ProcessInfo.processInfo.systemUptime, "windows": windows]
    }
    /// Public UIKit observations only. This existing proof is refreshed by
    /// VipiApp's 0.5-second TimelineView; it is not a synchronous audit hook.
    private var systemTypeDiagnostic: [String: Any] {
        let sampledAt = ProcessInfo.processInfo.systemUptime
        let app = UIApplication.shared
        let scenes: [[String: Any]] = app.connectedScenes.compactMap { $0 as? UIWindowScene }
            .sorted { $0.session.persistentIdentifier < $1.session.persistentIdentifier }
            .map { scene in
                let windows: [[String: Any]] = scene.windows.map { window in
                    // Observe only: never force layout, change a window, or
                    // dismiss an overlay to obtain a passing audit snapshot.
                    var scrolls: [[String: Any]] = []
                    var visited = 0
                    @MainActor func visit(_ view: UIView, depth: Int) {
                        guard depth < 24, visited < 1024 else { return }
                        visited += 1
                        if let scroll = view as? UIScrollView, !scroll.isHidden, scroll.alpha > 0 {
                            var value: [String: Any] = [
                                "class": String(describing: type(of: scroll)),
                                "frame": LiveImmersionQualification.frameFields(
                                    scroll.convert(scroll.bounds, to: window)),
                                "content_width": scroll.contentSize.width, "content_height": scroll.contentSize.height,
                                "offset_x": scroll.contentOffset.x, "offset_y": scroll.contentOffset.y,
                                "alpha": scroll.alpha
                            ]
                            if let collection = scroll as? UICollectionView {
                                value["visible_cells"] = collection.visibleCells.count
                                value["section_count"] = collection.numberOfSections
                            }
                            scrolls.append(value)
                        }
                        for child in view.subviews { visit(child, depth: depth + 1) }
                    }
                    visit(window, depth: 0)
                    return [
                        "category": window.traitCollection.preferredContentSizeCategory.rawValue,
                        "class": String(describing: type(of: window)), "level": window.windowLevel.rawValue,
                        "root_class": window.rootViewController.map { String(describing: type(of: $0)) } ?? "",
                        "root_hidden": window.rootViewController?.viewIfLoaded?.isHidden ?? true,
                        "root_alpha": window.rootViewController?.viewIfLoaded?.alpha ?? 0,
                        "scrolls": scrolls, "visited_views": visited,
                        "is_key": window.isKeyWindow, "is_hidden": window.isHidden,
                        "alpha": Double(window.alpha), "has_root": window.rootViewController != nil,
                        "window_x": Double(window.frame.minX), "window_y": Double(window.frame.minY),
                        "screen_x": Double(window.screen.bounds.minX), "screen_y": Double(window.screen.bounds.minY),
                        "screen_width": Double(window.screen.bounds.width),
                        "screen_height": Double(window.screen.bounds.height),
                        "screen_scale": Double(window.screen.scale),
                        "width": Double(window.bounds.width), "height": Double(window.bounds.height)
                    ]
                }
                return [
                    "foreground_active": scene.activationState == .foregroundActive,
                    "category": scene.traitCollection.preferredContentSizeCategory.rawValue,
                    "windows": windows
                ]
            }
        return [
            "sample_uptime": sampledAt,
            "application_category": app.preferredContentSizeCategory.rawValue,
            "argument_override_present": UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
                .keys.contains("UIPreferredContentSizeCategoryName"),
            "scenes": scenes
        ]
    }
    var proof: String {
        do {
            var rows: [ChatItem] = [], draft = ""
            if ledger.profiles == 1 {
                let vault = try MessageVault(account: ledger.account)
                defer { try? vault.close() }
                let history = try ConversationHistory(vault: vault)
                rows = try history.messages(peer: ledger.peer)
                draft = try history.composeDraft(ledger.peer)
            }
            var value: [String: Any] = [
                "starts": ledger.starts, "auth_launches": ledger.launches, "exchanges": ledger.exchanges,
                "callback": ledger.callback ?? "",
                "pending_auth": try KeychainStore.read(account: "pending-sign-in") != nil,
                "session": try KeychainStore.read(account: "session") != nil, "profiles": ledger.profiles,
                "registrations": ledger.registrations,
                "peer_decryptions": ledger.decrypted, "accepted_ids": ledger.acceptedIDs.sorted(),
                "expired_ids": ledger.expiredIDs.sorted(),
                "expired_posts": ledger.expiredPosts, "receipts": ledger.receipts.count, "draft": draft,
                "texts": rows.map(\.text), "ids": rows.map { $0.id.uuidString.lowercased() },
                "states": rows.map(\.state),
                "base_active": stores.last?.baseActive ?? false, "bot_active": stores.last?.botAvailable ?? false,
                "trial_started": stores.last?.snapshot?.base.cardless_trial?.started_at ?? "",
                "trial_ends": stores.last?.snapshot?.base.cardless_trial?.ends_at ?? "",
                "purchase_ready": stores.last?.purchaseReady ?? false, "unexpected": ledger.unexpected,
                "invitation_username": ledger.invitationCaptured == true
                    ? UserDefaults.standard.string(forKey: "invitationUsername") ?? "" : "",
                "friend_username_lookups": ledger.friendUsernameLookups ?? 0,
                "group_requests": ledger.groupRequests ?? 0,
                "composer_activity_requests": ledger.typingUpdates ?? [],
                "visible_receipt_requests": ledger.visibleReadRequests ?? 0,
                "inbox_rows": ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa")
                    ? (chats.last?.threads.map { thread -> [String: Any] in
                        [
                            "peer": thread.peer.uuidString.lowercased(), "name": chats.last?.name(thread.peer) ?? "",
                            "text": thread.latest.text, "unread": thread.unread, "state": thread.latest.state
                        ]
                    } ?? []) : [],
                "controlled_peer_read_acknowledgement": ProcessInfo.processInfo.arguments.contains(
                    "-vipi-chat-polish-qa"),
                "notifications_authorization": PushNotifications.shared.authorization.rawValue,
                "notifications_enabled": PushNotifications.shared.enabled,
                "controlled_sdk_translation": ProcessInfo.processInfo.arguments.contains(
                    "-vipi-full-translation-sdk-qa"),
                "controlled_translation_inputs": ledger.controlledTranslations,
                "controlled_translation_failures": ledger.controlledTranslationFailures,
                "gesture_policy_seen": UserDefaults.standard.bool(forKey: "full-message-gestures-v1-seen"),
                "controlled_native_faces": speechObservations.filter {
                    $0["event"] as? String == "full_message_native_face"
                },
                "composition_geometry": compositionGeometry,
                "current_message_viewport": LiveImmersionQualification.currentMessageViewport,
                "current_message_rows": LiveImmersionQualification.currentMessageRows,
                "full_message_geometry": Array(
                    speechObservations.filter { ($0["event"] as? String ?? "").hasSuffix("_geometry") }.suffix(64)),
                // Scroll/row callbacks can fill the recent event window while
                // the composer stays still. Keep its actual latest measurement.
                "full_message_composer_geometry": speechObservations.last {
                    $0["event"] as? String == "full_message_composer_geometry"
                } ?? [:],
                "speech_inputs": speechObservations.filter { $0["event"] as? String == "speech_input" }.count,
                "speech_played": speechObservations.filter { $0["event"] as? String == "speech_file_played_back" }
                    .count,
                "speech_last_output": speechObservations.last { $0["event"] as? String == "speech_file_played_back" }
                    ?? [:],
                "speech_last_input": speechObservations.last { $0["event"] as? String == "speech_input" } ?? [:]
            ]
            if Self.marketingEnabled {
                value["marketing"] = [
                    "controlled_screenshot_data": true, "model_inference_proof": false,
                    "account_name": "Alex", "friend_name": "Maya",
                    "originals": Self.marketingTurns.map { $0.text },
                    "practice": Self.marketingTurns.map { $0.practice }
                ]
            }
            if ProcessInfo.processInfo.arguments.contains("-vipi-inbox-populated-qa") {
                value["inbox_target"] = chats.last?.translationOwner?.pair.target ?? ""
            }
            if pendingPairEnabled, ledger.profiles == 1 {
                let vault = try MessageVault(account: ledger.account)
                defer { try? vault.close() }
                value["pending_pair"] = try vault.transaction { try pendingPairProof(rows: rows, vault: vault) }
            }
            if ProcessInfo.processInfo.environment["VIPI_SYSTEM_TYPE_DIAGNOSTIC"] == "true" {
                value["system_type_diagnostic"] = systemTypeDiagnostic
            }
            return String(
                decoding: try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), as: UTF8.self)
        } catch { return "{\"durable_read_failed\":true}" }
    }
    private static func cleanup() throws {
        guard FileManager.default.fileExists(atPath: file.path) else {
            for key in ["session", "pending-sign-in", "pending-identity-link", "account-deletion"] {
                guard try KeychainStore.read(account: key) == nil else {
                    throw ServiceFailure(status: 0, code: "preserve_unowned_first_month_cleanup")
                }
            }
            return
        }
        let ledger = try JSONDecoder().decode(Ledger.self, from: Data(contentsOf: file))
        try validate(ledger)
        for key in ["session", "pending-sign-in", "profile-" + ledger.user] {
            try KeychainStore.deleteChecked(account: key)
        }
        let messages = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages")
        let owned = messages.appendingPathComponent(ledger.account.uuidString.lowercased(), isDirectory: true)
        guard
            owned.standardizedFileURL.pathComponents
                == owned.resolvingSymlinksInPath().standardizedFileURL.pathComponents
        else { throw ServiceFailure(status: 0, code: "preserve_unknown_first_month_path") }
        if FileManager.default.fileExists(atPath: owned.path) { try FileManager.default.removeItem(at: owned) }
        for id in [ledger.account, ledger.peer] {
            try KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased())
        }
        if ledger.cueCaptured == true {
            if let prior = ledger.cuePriorSeen {
                UserDefaults.standard.set(prior, forKey: "full-message-gestures-v1-seen")
            } else {
                UserDefaults.standard.removeObject(forKey: "full-message-gestures-v1-seen")
            }
        }
        if ledger.immersionCaptured == true {
            if let prior = ledger.priorImmersionMode {
                UserDefaults.standard.set(prior, forKey: "immersionMode")
            } else {
                UserDefaults.standard.removeObject(forKey: "immersionMode")
            }
        }
        if ledger.invitationCaptured == true {
            if let prior = ledger.priorInvitation {
                UserDefaults.standard.set(prior, forKey: "invitationUsername")
            } else {
                UserDefaults.standard.removeObject(forKey: "invitationUsername")
            }
        }
        try FileManager.default.removeItem(at: directory)
    }
}

/// Timeline fixtures never start a real model or certify response quality.
@MainActor private final class TimelineOnlyBotGenerator: LocalBotGenerating {
    let provider = "apple-foundation-models"
    let maximumContextBytes = 3072
    func availability(language: String) -> LocalBotAvailability { .ready }
    func reply(to turns: [LocalBotTurn], language: String) async throws -> String { throw LocalBotFailure.incomplete }
}
#endif
