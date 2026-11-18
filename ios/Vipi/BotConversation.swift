import Foundation
import Observation
import SwiftUI

struct BotMessage: Codable, Identifiable {
    let id: UUID
    let role: String
    let text: String
    let createdAt: Date
    var state: String
    var requestID: UUID? = nil
    var key: String { String(format: "%020lld", Int64(createdAt.timeIntervalSince1970 * 1000)) + "-" + id.uuidString.lowercased() }
}

/// This storage namespace and request builder contain only the vBot thread.
/// The friend-message journal is never an input to response generation.
@MainActor @Observable final class BotSession {
    private let api: any ChatTransport
    private let vault: MessageVault
    private let now: () -> Date
    let familiarity: VocabularyFamiliarityStore
    private var closed = false
    private var allowanceRevision: UInt64 = 0
    private(set) var messages: [BotMessage] = []
    private(set) var consent = false
    private(set) var busy = false
    private(set) var allowance: BotAllowance?
    private(set) var earlierAvailable = false
    var notice: String?
    var draft = ""
    init(api: any ChatTransport, vault: MessageVault, now: @escaping () -> Date = Date.init) throws {
        self.api = api; self.vault = vault; self.now = now
        self.familiarity = VocabularyFamiliarityStore(vault: vault)
        try vault.transaction {
            consent = try vault.get("bot-local", "consent") == Data("deepseek-v1".utf8)
            draft = try vault.get("bot-local", "draft").flatMap { String(data: $0, encoding: .utf8) } ?? ""
        }
        try loadEarlier()
    }
    func close() { closed = true }
    func loadEarlier() throws {
        let before = messages.first?.key
        let page = try vault.transaction {
            try vault.pageIDs("bot-message", prefix: "0", before: before, limit: 50).compactMap { key -> BotMessage? in
                guard let data = try vault.get("bot-message", key) else { return nil }
                var message = try JSONDecoder().decode(BotMessage.self, from: data)
                if message.state == "sending" { message.state = "unconfirmed" }
                return message
            }
        }
        earlierAvailable = page.count == 50
        messages = (page + messages).sorted { $0.key < $1.key }
    }
    func saveDraft() {
        do { try vault.transaction { try vault.put("bot-local", "draft", Data(draft.utf8)) } }
        catch { notice = String(localized: "This draft couldn’t be saved. Keep this conversation open and try again.") }
    }
    func setConsent(_ value: Bool) throws {
        guard !busy else { return }
        try vault.transaction {
            if value { try vault.put("bot-local", "consent", Data("deepseek-v1".utf8)) }
            else { try vault.remove("bot-local", "consent") }
        }
        consent = value
    }
    func clear() throws {
        guard !busy else { return }
        try vault.transaction { for id in try vault.ids("bot-message") { try vault.remove("bot-message", id) } }
        messages = []; earlierAvailable = false
    }
    func refresh(preservingNotice: Bool = false) async {
        guard !closed else { return }
        allowanceRevision &+= 1
        let revision = allowanceRevision
        do {
            let value: BotAllowance = try await api.request("GET", "/v1/bot/allowance")
            guard !closed, revision == allowanceRevision else { return }; allowance = value
        } catch {
            guard !closed, revision == allowanceRevision else { return }
            allowance = nil
            if !preservingNotice || notice == nil { notice = String(localized: "Couldn’t check your Bot mini allowance. Try again.") }
        }
    }
    var canSend: Bool {
        !closed && !busy && consent && allowance?.canSend(at: now()) == true &&
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft.utf8.count <= min(8192, allowance?.max_context_bytes ?? 0)
    }
    struct Context: Codable { let role: String; let content: String }
    static func context(history: [BotMessage], newText: String, maximumBytes: Int) -> [Context]? {
        guard !newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              newText.utf8.count <= min(8192, maximumBytes) else { return nil }
        var values = history.filter { $0.state == "complete" && ["user", "assistant"].contains($0.role) }
            .suffix(11).map { Context(role: $0.role, content: $0.text) }
        values.append(Context(role: "user", content: newText))
        while values.reduce(0, { $0 + $1.content.utf8.count }) > min(8192, maximumBytes) { values.removeFirst() }
        return values
    }
    func send() async {
        guard canSend, let context = Self.context(history: messages, newText: draft, maximumBytes: allowance?.max_context_bytes ?? 0) else { return }
        busy = true; notice = nil
        // A read started before this request cannot restore a spent reply.
        allowanceRevision &+= 1
        defer { busy = false }
        let device: DeviceCredential
        do { device = try DeviceCredential.registered(vault: vault) }
        catch {
            notice = String(localized: "Reconnect this account before sending to vBot. Your draft is still here.")
            return
        }
        var outgoing = BotMessage(id: UUID(), role: "user", text: draft, createdAt: nextMessageDate(), state: "sending")
        struct Request: Encodable { let request_id: UUID; let consent_version: String; let messages: [Context] }
        struct Reply: Decodable { let request_id: UUID; let reply: String; let allowance: BotAllowance }
        do {
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.remove("bot-local", "draft")
            }
            messages.append(outgoing); draft = ""
        } catch { notice = String(localized: "Your message couldn’t be saved. Please try again."); return }
        do {
            let body = try JSONEncoder().encode(Request(request_id: outgoing.id, consent_version: "deepseek-v1", messages: context))
            let reply: Reply = try await api.request("POST", "/v1/bot/messages", body: body, device: device)
            guard reply.request_id == outgoing.id, !reply.reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  reply.reply.utf8.count <= 16384 else { throw ServiceFailure(status: 0, code: "invalid_bot_reply") }
            // Complete the local record even if navigation closed the view
            // while the request was in flight. No follow-up request is sent.
            outgoing.state = "complete"
            var incoming = BotMessage(id: UUID(), role: "assistant", text: reply.reply, createdAt: nextMessageDate(), state: "complete")
            incoming.requestID = outgoing.id
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.put("bot-message", incoming.key, JSONEncoder().encode(incoming))
            }
            if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
            messages.append(incoming)
            allowanceRevision &+= 1
            allowance = reply.allowance
        } catch {
            outgoing.state = (error as? ServiceFailure)?.code == "device_revoked" ? "rejected" : "unconfirmed"
            try? vault.transaction { try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing)) }
            if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
            notice = Self.explanation(error)
            // Never retry a potentially consumed response-generation request.
            if !closed { await refresh(preservingNotice: true) }
        }
    }
    private func nextMessageDate() -> Date {
        guard let previous = messages.last?.createdAt else { return now() }
        // Storage keys have millisecond precision. Two milliseconds leaves room
        // for Date's floating-point rounding and keeps a reply after its prompt,
        // even with an immediate response or a backward device-clock correction.
        return max(now(), previous.addingTimeInterval(0.002))
    }
    static func reportExcerpt(_ text: String) -> String {
        var result = ""
        for character in text {
            guard result.utf8.count + String(character).utf8.count <= 4000 else { break }
            result.append(character)
        }
        return result
    }
    func report(_ message: BotMessage, reason: String) async throws {
        guard !closed, message.role == "assistant", let request = message.requestID,
              ["harmful", "inaccurate", "other"].contains(reason) else { throw ServiceFailure(status: 0, code: "invalid_report") }
        struct Report: Encodable { let request_id: UUID; let reason: String; let selected_reply: String }
        struct Result: Decodable { let reported: Bool }
        let body = try JSONEncoder().encode(Report(request_id: request, reason: reason, selected_reply: Self.reportExcerpt(message.text)))
        let device = try DeviceCredential.registered(vault: vault)
        let result: Result = try await api.request("POST", "/v1/bot/reports", body: body, device: device)
        guard result.reported else { throw ServiceFailure(status: 0, code: "report_unconfirmed") }
    }
    private static func explanation(_ error: Error) -> String {
        if let error = error as? ServiceFailure {
            if error.code == "device_revoked" { return String(localized: "Reconnect this account before sending to vBot. This request wasn’t accepted and won’t be resent automatically.") }
            if error.code == "monthly_allowance_reached" { return String(localized: "You’ve used this month’s Bot mini replies. Your allowance refreshes next month.") }
            if ["base_subscription_required", "bot_subscription_required"].contains(error.code) { return String(localized: "Check your subscriptions to continue this conversation.") }
            if ["bot_unavailable", "bot_busy", "bot_temporarily_unavailable"].contains(error.code) { return String(localized: "vBot is unavailable right now. Your message is saved and won’t be resent automatically.") }
        }
        return String(localized: "We couldn’t confirm vBot’s reply. This message won’t be resent automatically and may have used one reply from your allowance.")
    }
}

struct BotConversationView: View {
    let account: UUID
    let subscriptions: SubscriptionStore
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var session: BotSession?
    @State private var immersion = ConversationImmersion()
    @State private var speech = SpeechPlayback()
    @State private var error: String?
    @State private var clearConfirmation = false
    @State private var voiceHelp = false
    @State private var scrolling = false
    @State private var followingLatest = true
    @State private var reporting: BotMessage?
    @FocusState private var composing: Bool
    var body: some View {
        Group {
            if let session { conversation(session) }
            else { ContentUnavailableView("Your vBot conversation", systemImage: "bubble.left", description: Text(error ?? String(localized: "Opening your saved conversation…"))) }
        }.background(VipiDesign.canvas).navigationTitle("vBot").navigationBarTitleDisplayMode(.inline)
            .background { ConversationTranslationTask(immersion: immersion) }
            .task(id: account) {
                do {
                    guard let userID = authentication.session?.userID else { return }
                    let value = try BotSession(api: ServiceClient(authentication: authentication, userID: userID, responseTimeout: 90), vault: MessageVault(account: account))
                    session = value; await value.refresh()
                } catch { self.error = String(localized: "Your saved conversation couldn’t be opened. Please try again.") }
            }
            .task(id: "\(state.knownLanguage)-\(state.targetLanguage)-\(state.density)-\(session != nil)") {
                speech.close()
                await immersion.configure(pair: .init(source: state.knownLanguage, target: state.targetLanguage), density: state.density, familiarity: session?.familiarity)
                prepareVoices()
            }
            .onDisappear { session?.close(); immersion.close(); speech.close() }
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { speech.stop() }
                else { Task { await session?.refresh(); await immersion.refreshAvailability(); prepareVoices() } }
            }
            .alert("Delete this vBot conversation?", isPresented: $clearConfirmation) {
                Button("Delete conversation", role: .destructive) { do { try session?.clear() } catch { self.error = String(localized: "The conversation couldn’t be deleted.") } }
                Button("Cancel", role: .cancel) { }
            } message: { Text("This removes the saved vBot messages from this device. It does not cancel your subscription or erase messages already processed by DeepSeek.") }
            .alert("Hear both languages", isPresented: $voiceHelp) {
                Button("Retry voices") { prepareVoices() }; Button("Done", role: .cancel) { }
            } message: { Text(speech.error ?? String(localized: "Voices are preparing. Please try again shortly.")) }
            .sheet(item: $reporting) { message in
                if let session { BotReportView(session: session, message: message) }
            }
    }
    @ViewBuilder private func conversation(_ value: BotSession) -> some View {
        @Bindable var value = value
        ScrollViewReader { scroll in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    Text("Powered by DeepSeek · Bot conversations aren’t end-to-end encrypted.")
                        .font(.footnote).foregroundStyle(VipiDesign.secondary)
                    if value.earlierAvailable { Button("Earlier messages") { do { try value.loadEarlier() } catch { self.error = String(localized: "Earlier messages couldn’t be opened.") } } }
                    ForEach(value.messages) { item in
                        HStack {
                            if item.role == "user" { Spacer(minLength: 38) }
                            ConversationImmersionText(text: item.text, id: "bot-" + item.id.uuidString, immersion: immersion,
                                speech: speech, paused: scrolling || composing,
                                metadata: AnyView(Text(item.state == "sending" ? String(localized: "Waiting for vBot") : item.state == "unconfirmed" ? String(localized: "Reply unconfirmed") : item.state == "rejected" ? String(localized: "Request not accepted") : item.createdAt.formatted(date: .omitted, time: .shortened)).font(.caption).foregroundStyle(VipiDesign.secondary)),
                                onVoiceHelp: { voiceHelp = true })
                                .padding(15).background(item.role == "user" ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
                                .contextMenu {
                                    if item.role == "assistant", item.requestID != nil {
                                        Button("Report reply", systemImage: "flag") { reporting = item }
                                    }
                                }
                            if item.role != "user" { Spacer(minLength: 38) }
                        }.id(item.id)
                    }
                    if let notice = value.notice ?? error { Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary) }
                    if !value.consent {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Before you start").font(.headline)
                            Text("Your message and up to 11 recent messages from this conversation are sent to Vipi and DeepSeek to generate each reply. Friend conversations are never included automatically. You can withdraw consent in this conversation’s menu.")
                            Link("DeepSeek privacy policy", destination: URL(string: "https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html")!)
                            Link("Vipi privacy policy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                            Button("Agree and start chatting") { do { try value.setConsent(true) } catch { self.error = String(localized: "Your choice couldn’t be saved.") } }
                                .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                        }.padding(20).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
                    }
                    Color.clear.frame(height: 1).id("bot-bottom")
                }.padding(18).frame(maxWidth: 680).frame(maxWidth: .infinity)
            }.scrollDismissesKeyboard(.interactively).onScrollPhaseChange { _, phase in scrolling = phase.isScrolling }
                .onScrollGeometryChange(for: Bool.self) { geometry in
                    geometry.contentSize.height - geometry.visibleRect.maxY <= 44
                } action: { _, nearBottom in
                    if nearBottom || scrolling { followingLatest = nearBottom }
                }
                .onChange(of: value.messages.last?.id) { _, _ in if followingLatest { scroll.scrollTo("bot-bottom", anchor: .bottom) } }
                .overlay(alignment: .bottomTrailing) {
                    if !followingLatest && !value.messages.isEmpty {
                        Button { followingLatest = true; scroll.scrollTo("bot-bottom", anchor: .bottom) } label: {
                            Image(systemName: "arrow.down").frame(width: 46, height: 46)
                        }.buttonStyle(.borderedProminent).buttonBorderShape(.circle).padding(12).accessibilityLabel("Jump to latest messages")
                    }
                }
                .refreshable { await value.refresh() }
        }
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 7) {
                if let allowance = value.allowance {
                    if allowance.available {
                        Text("\(allowance.remaining_replies) of \(allowance.monthly_replies) replies left this month").font(.caption).foregroundStyle(VipiDesign.secondary)
                    } else if !allowance.service_ready {
                        Text("vBot isn’t available yet.").font(.caption).foregroundStyle(VipiDesign.secondary)
                    } else {
                        NavigationLink("Check Bot mini") { SubscriptionOfferView(store: subscriptions, plan: .botMini) }
                    }
                }
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message vBot", text: $value.draft, axis: .vertical).lineLimit(1...6).focused($composing)
                        .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                        .onChange(of: value.draft) { _, _ in value.saveDraft() }
                    Button { composing = false; followingLatest = true; Task { await value.send() } } label: {
                        if value.busy { ProgressView().frame(width: 46, height: 46) }
                        else { Image(systemName: "arrow.up").frame(width: 46, height: 46).background(VipiDesign.highlight, in: Circle()).foregroundStyle(VipiDesign.onHighlight) }
                    }.disabled(!value.canSend).accessibilityLabel("Send to vBot")
                }
            }.padding(14).background(VipiDesign.canvas)
        }
        .toolbar { ToolbarItem(placement: .topBarTrailing) {
            Menu {
                NavigationLink("Languages") { LanguageDownloadView() }
                NavigationLink("Bot mini subscription") { SubscriptionOfferView(store: subscriptions, plan: .botMini) }
                if let latest = value.messages.last(where: { $0.role == "assistant" && $0.requestID != nil }) {
                    Button("Report latest reply", systemImage: "flag") { reporting = latest }
                }
                if value.consent { Button("Withdraw DeepSeek consent") { do { try value.setConsent(false) } catch { self.error = String(localized: "Your choice couldn’t be saved.") } }.disabled(value.busy) }
                Button("Delete conversation", role: .destructive) { clearConfirmation = true }.disabled(value.busy)
            } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }.accessibilityLabel("vBot options")
        } }
    }
    private func prepareVoices() {
        if let source = ConversationExamples.examples?.languages[state.knownLanguage]?.text,
           let target = ConversationExamples.examples?.languages[state.targetLanguage]?.text {
            speech.prepare(source: state.knownLanguage, target: state.targetLanguage, warmups: [state.knownLanguage: source, state.targetLanguage: target])
        }
    }
}

private struct BotReportView: View {
    let session: BotSession
    let message: BotMessage
    @Environment(\.dismiss) private var dismiss
    @State private var reason = "harmful"
    @State private var busy = false
    @State private var sent = false
    @State private var notice: String?
    var body: some View {
        NavigationStack {
            Form {
                Section("Selected reply") { Text(BotSession.reportExcerpt(message.text)).textSelection(.enabled) }
                if !sent {
                    Section {
                        Picker("Reason", selection: $reason) {
                            Text("Harmful").tag("harmful"); Text("Inaccurate").tag("inaccurate"); Text("Other").tag("other")
                        }
                        Text("Send only the reply shown above and your selected reason to Vipi. Reports are stored encrypted for up to 30 days. Your other messages aren’t included.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        Button("Send report") {
                            busy = true; notice = nil
                            Task {
                                defer { busy = false }
                                do { try await session.report(message, reason: reason); sent = true }
                                catch { notice = String(localized: "Your report couldn’t be confirmed. Please try again.") }
                            }
                        }.disabled(busy)
                    }
                } else { Section { Label("Report received", systemImage: "checkmark.circle") } }
                if let notice { Section { Text(notice) } }
            }.navigationTitle("Report reply").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(sent ? "Done" : "Cancel") { dismiss() }.disabled(busy) } }
        }
    }
}
