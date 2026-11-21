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
    var provider: String? = nil
    var key: String { String(format: "%020lld", Int64(createdAt.timeIntervalSince1970 * 1000)) + "-" + id.uuidString.lowercased() }
}

/// This storage namespace and request builder contain only the vBot thread.
/// The friend-message journal is never an input to response generation.
@MainActor @Observable final class BotSession {
    private let api: any ChatTransport
    private let vault: MessageVault
    private let now: () -> Date
    private let generator: any LocalBotGenerating
    private var generation: Task<String, Error>?
    private var inputLanguage = "en"
    private var closed = false
    private weak var translationOwner: ConversationImmersion?
    private var translationReplay: Task<Void,Never>?
    func useTranslation(_ owner:ConversationImmersion?) {
        guard translationOwner !== owner else { return }
        translationReplay?.cancel(); translationOwner = owner
        guard let owner else { return }
        translationReplay = Task { @MainActor [weak self,weak owner] in
            guard let self,let owner else { return }
            var cursor:String?
            repeat {
                guard !closed,!Task.isCancelled,translationOwner === owner else { return }
                let page = (try? vault.transaction { try vault.pageIDs("bot-message",prefix:"0",before:cursor,limit:50).compactMap { key -> BotMessage? in
                    guard let bytes = try vault.get("bot-message",key) else { return nil }; return try JSONDecoder().decode(BotMessage.self,from:bytes)
                } }) ?? []
                for message in page {
                    guard !closed,!Task.isCancelled,translationOwner === owner else { return }
                    await owner.prepareStoredMessage(id:"bot-"+message.id.uuidString,text:message.text); await Task.yield()
                }
                cursor = page.count == 50 ? page.map(\.key).min() : nil
            } while cursor != nil
        }
    }

    @ObservationIgnored private var messageObservers: [UUID:(ChatMessageArrival)->Void] = [:]
    func observeNewMessages(_ callback:@escaping(ChatMessageArrival)->Void) -> UUID { let id = UUID(); if !closed { messageObservers[id] = callback }; return id }
    func removeMessageObserver(_ id:UUID) { messageObservers.removeValue(forKey:id) }
    private func messageCommitted(_ value:BotMessage) {
        let key = value.key,id = value.id
        let arrival = ChatMessageArrival(id:"bot-"+id.uuidString) { [weak vault] in
            guard let vault else { return nil }
            return try? vault.transaction {
                guard let bytes = try vault.get("bot-message",key) else { return nil }
                let saved = try JSONDecoder().decode(BotMessage.self,from:bytes)
                return saved.id == id ? saved.text:nil
            }
        }
        translationOwner?.warmStored(id:arrival.id,load:arrival.load)
        for observer in Array(messageObservers.values) { observer(arrival) }
    }

    private(set) var messages: [BotMessage] = []
    private(set) var busy = false
    private(set) var availability: LocalBotAvailability = .checking
    var maximumMessageBytes: Int { generator.maximumContextBytes }
    private(set) var earlierAvailable = false
    var notice: String?
    var draft = ""
    init(api: any ChatTransport, vault: MessageVault, generator: any LocalBotGenerating = AppleLocalBot(), now: @escaping () -> Date = Date.init) throws {
        self.api = api; self.vault = vault; self.generator = generator; self.now = now
        try vault.transaction {
            draft = try vault.get("bot-local", "draft").flatMap { String(data: $0, encoding: .utf8) } ?? ""
            if let key = try vault.pageIDs("bot-message", prefix: "0", before: nil, limit: 1).first,
               let bytes = try vault.get("bot-message", key) {
                var interrupted = try JSONDecoder().decode(BotMessage.self, from: bytes)
                if interrupted.state == "sending", interrupted.provider != nil {
                    interrupted.state = "stopped"
                    try vault.put("bot-message", key, JSONEncoder().encode(interrupted))
                    if draft.isEmpty {
                        draft = interrupted.text
                        try vault.put("bot-local", "draft", Data(draft.utf8))
                    }
                }
            }
        }
        try loadEarlier()
    }
    func close() throws {
        closed = true; generation?.cancel(); generation = nil; translationReplay?.cancel(); translationReplay = nil; translationOwner = nil; messageObservers.removeAll()
        messages = []; draft = ""; availability = .checking; notice = nil; earlierAvailable = false
        // Retry remains possible if SQLite refuses while a transaction is open.
        try vault.close()
    }
    func loadEarlier() throws {
        guard !closed else { throw CancellationError() }
        let before = messages.first?.key
        let page = try vault.transaction {
            try vault.pageIDs("bot-message", prefix: "0", before: before, limit: 50).compactMap { key -> BotMessage? in
                guard let data = try vault.get("bot-message", key) else { return nil }
                var message = try JSONDecoder().decode(BotMessage.self, from: data)
                if message.state == "sending" { message.state = message.provider == nil ? "unconfirmed" : "stopped" }
                return message
            }
        }
        earlierAvailable = page.count == 50
        messages = (page + messages).sorted { $0.key < $1.key }
    }
    func saveDraft() {
        guard !closed else { return }
        guard draft.utf8.count <= ConversationHistory.maximumDraftBytes else {
            notice = String(localized: "This draft couldn’t be saved. Keep this conversation open and try again."); return
        }
        do { try vault.transaction { try vault.put("bot-local", "draft", Data(draft.utf8)) } }
        catch { notice = String(localized: "This draft couldn’t be saved. Keep this conversation open and try again.") }
    }
    func useInputLanguage(_ language: String) {
        guard !closed else { return }
        if inputLanguage != language { cancelGeneration(); inputLanguage = language }
        availability = generator.availability(language: language)
    }
    func cancelGeneration() { generation?.cancel() }
    func clear() throws {
        guard !closed && !busy else { return }
        translationReplay?.cancel(); translationReplay = nil
        let ids: Set<String> = try vault.transaction { Set(try vault.ids("bot-message").compactMap { key -> String? in
            guard let bytes = try vault.get("bot-message",key) else { return nil }
            return "bot-"+(try JSONDecoder().decode(BotMessage.self,from:bytes)).id.uuidString
        }) }
        try translationOwner?.forget(messageIDs:ids)
        try vault.transaction {
            for id in try vault.ids("bot-message") { try vault.remove("bot-message",id) }
            for id in try vault.ids("bot-report-id") { try vault.remove("bot-report-id",id) }
        }
        messages = []; earlierAvailable = false
    }
    func refresh(preservingNotice: Bool = false) async {
        guard !closed else { return }
        availability = generator.availability(language: inputLanguage)
    }
    var canSend: Bool {
        !closed && !busy && availability == .ready &&
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft.utf8.count <= maximumMessageBytes
    }
    typealias Context = LocalBotTurn
    static func context(history: [BotMessage], newText: String, maximumBytes: Int) -> [Context]? {
        guard !newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              newText.utf8.count <= min(8192, maximumBytes) else { return nil }
        var values = history.filter { $0.state == "complete" && ["user", "assistant"].contains($0.role) }
            .suffix(11).map { Context(role: $0.role, content: $0.text) }
        values.append(Context(role: "user", content: newText))
        while values.reduce(0, { $0 + $1.content.utf8.count }) > min(8192, maximumBytes) { values.removeFirst() }
        while values.first?.role == "assistant" { values.removeFirst() }
        return values
    }
    func send() async {
        guard canSend, let context = Self.context(history: messages, newText: draft, maximumBytes: maximumMessageBytes) else { return }
        busy = true; notice = nil
        defer { busy = false; generation = nil }
        var outgoing = BotMessage(id: UUID(), role: "user", text: draft, createdAt: nextMessageDate(), state: "sending")
        outgoing.provider = generator.provider
        do {
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.remove("bot-local", "draft")
            }
            messages.append(outgoing); draft = ""; messageCommitted(outgoing)
        } catch { notice = String(localized: "Your message couldn’t be saved. Please try again."); return }
        let task = Task { @MainActor [generator, inputLanguage] in
            try await generator.reply(to: context, language: inputLanguage)
        }
        generation = task
        do {
            let reply = try await task.value
            guard !closed else { return }
            guard !task.isCancelled else { throw CancellationError() }
            guard !reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, reply.utf8.count <= 16384 else { throw LocalBotFailure.incomplete }
            outgoing.state = "complete"
            var incoming = BotMessage(id: UUID(), role: "assistant", text: reply, createdAt: nextMessageDate(), state: "complete")
            incoming.requestID = outgoing.id; incoming.provider = generator.provider
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.put("bot-message", incoming.key, JSONEncoder().encode(incoming))
            }
            if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
            messages.append(incoming); messageCommitted(incoming)
        } catch {
            guard !closed else { return }
            outgoing.state = "stopped"
            // Restore only an empty composer. Never replace a newer draft.
            if draft.isEmpty { draft = outgoing.text }
            do {
                try vault.transaction {
                    try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                    try vault.put("bot-local", "draft", Data(draft.utf8))
                }
                if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
                notice = task.isCancelled || error is CancellationError
                    ? String(localized: "vBot stopped. Your message is still here.")
                    : (error as? LocalBotFailure)?.errorDescription ?? String(localized: "vBot couldn’t finish. Your message is still here.")
            } catch { notice = String(localized: "This draft couldn’t be saved. Keep this conversation open and try again.") }
            await refresh(preservingNotice: true)
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
        struct Result: Decodable { let reported: Bool; var report_id: UUID? }
        let device = try DeviceCredential.registered(vault: vault)
        if let provider = message.provider {
            guard ["apple-foundation-models", "gemini-nano"].contains(provider) else { throw ServiceFailure(status: 0, code: "invalid_report") }
            let key = message.id.uuidString.lowercased() + "-" + reason
            let reportID: UUID = try vault.transaction {
                if let data = try vault.get("bot-report-id", key), let text = String(data: data, encoding: .utf8), let saved = UUID(uuidString: text) { return saved }
                let id = UUID(); try vault.put("bot-report-id", key, Data(id.uuidString.lowercased().utf8)); return id
            }
            struct Report: Encodable { let report_id: UUID; let provider: String; let reason: String; let selected_reply: String; let consent_version: String }
            let body = try JSONEncoder().encode(Report(report_id: reportID, provider: provider, reason: reason, selected_reply: Self.reportExcerpt(message.text), consent_version: "local-bot-report-v1"))
            let result: Result = try await api.request("POST", "/v1/bot/local-reports", body: body, device: device)
            guard result.reported, result.report_id == reportID else { throw ServiceFailure(status: 0, code: "report_unconfirmed") }
        } else {
            // Existing DeepSeek replies retain their original request binding.
            struct Report: Encodable { let request_id: UUID; let reason: String; let selected_reply: String }
            let body = try JSONEncoder().encode(Report(request_id: request, reason: reason, selected_reply: Self.reportExcerpt(message.text)))
            let result: Result = try await api.request("POST", "/v1/bot/reports", body: body, device: device)
            guard result.reported else { throw ServiceFailure(status: 0, code: "report_unconfirmed") }
        }
    }

}

/// One live session per account root, retained across ordinary navigation.
/// Closing an owner is final; a new account/root must create another owner.
@MainActor @Observable final class BotConversationOwner {
    private(set) var translationOwner: ConversationImmersion?
    func useTranslation(_ owner:ConversationImmersion?) { translationOwner = owner; session?.useTranslation(owner) }
    private var account: UUID?
    private var session: BotSession?
    private var closed = false
    func session(for account: UUID, create: () throws -> BotSession?) throws -> BotSession? {
        guard !closed else { throw CancellationError() }
        if let current = self.account, current != account {
            throw ServiceFailure(status: 0, code: "bot_account_changed")
        }
        if let session { return session }
        guard let value = try create() else { return nil }
        self.account = account; session = value; value.useTranslation(translationOwner); return value
    }
    func close() throws {
        closed = true
        // Keep the resource on failure so explicit disposal can retry. The
        // closed session already rejects sends and late response writes.
        try session?.close()
        session = nil; account = nil; translationOwner = nil
    }
}

struct BotConversationView: View {
    let account: UUID
    let subscriptions: SubscriptionStore
    let owner: BotConversationOwner
    private let sessionFactory: @MainActor (AuthenticationManager, UUID) throws -> BotSession?
    init(account: UUID, subscriptions: SubscriptionStore, owner: BotConversationOwner,
         sessionFactory: @escaping @MainActor (AuthenticationManager, UUID) throws -> BotSession? = { authentication, account in
             guard let userID = authentication.session?.userID else { return nil }
             return try BotSession(api: ServiceClient(authentication: authentication, userID: userID, responseTimeout: 90), vault: MessageVault(account: account))
         }) {
        self.account = account; self.subscriptions = subscriptions; self.owner = owner; self.sessionFactory = sessionFactory
    }
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var session: BotSession?
    @State private var immersion = ConversationImmersion()
    @State private var speech = SpeechPlayback()
    @State private var autoplay = ChatAutoplay()
    @State private var messageObserver: UUID?
    @State private var error: String?
    @State private var clearConfirmation = false
    @State private var voiceHelp = false
    @State private var translationHelp = false
    @State private var translationHelpPair: TranslationPair?
    @State private var scrolling = false
    @State private var followingLatest = true
    @State private var reporting: BotMessage?
    @State private var choosingReport = false
    @State private var copyOriginal = CopyOriginalContext(editorID:"bot-message-input",timelineID:"bot-conversation-timeline")
    @State private var chosenReportMessage: BotMessage?
    @State private var rejectedDraftEdit = false
    @State private var composing = false
    var body: some View {
        Group {
            if let session { conversation(session) }
            else { ContentUnavailableView("Your vBot conversation", systemImage: "bubble.left", description: Text(error ?? String(localized: "Opening your saved conversation…"))) }
        }.safeAreaInset(edge:.top,spacing:0) { ChatGestureCue(reading:state.chatReading,composing:composing) }.background(VipiDesign.canvas).navigationTitle("vBot").navigationBarTitleDisplayMode(.inline)
            .background { if owner.translationOwner == nil { ConversationTranslationTask(immersion:immersion) } }
            .background { ChatReadingGestureSurface(reading:state.chatReading) }
            .background { CopyOriginalAnchor(context:copyOriginal) }
            #if DEBUG
            .copyOriginalProof(context:copyOriginal,autoplay:autoplay,speech:speech)
            #endif
            .sheet(isPresented:$copyOriginal.presented,onDismiss:{ copyOriginal.restore() }) {
                CopyOriginalPicker(choices:copyOriginal.choices)
                #if DEBUG
                .copyOriginalProof(context:copyOriginal,autoplay:autoplay,speech:speech)
                #endif
            }
            .sheet(isPresented:$translationHelp) { NavigationStack { LanguageDownloadView(requestedPair:translationHelpPair).toolbar { ToolbarItem(placement:.confirmationAction) { Button("Done") { translationHelp = false } } } } }
            .task(id: account) {
                do {
                    guard let value = try owner.session(for: account, create: { try sessionFactory(authentication, account) }) else { return }
                    session = value
                value.useInputLanguage(state.knownLanguage)
                messageObserver = value.observeNewMessages { event in autoplay.arrived(.init(id:event.id,load:event.load),immersion:immersion,speech:speech,foreground:scenePhase == .active) }
                await value.refresh()
                } catch { self.error = String(localized: "Your saved conversation couldn’t be opened. Please try again.") }
            }
            .task(id:"\(state.knownLanguage)-\(state.targetLanguage)-\(session != nil)-\(owner.translationOwner.map{String(describing:ObjectIdentifier($0))} ?? "local")") {
                session?.useInputLanguage(state.knownLanguage)
                copyOriginal.abandon()
                speech.close()
                autoplay.stop(speech:speech)
                if let accountOwner = owner.translationOwner { immersion = accountOwner }
                else { immersion.close(); immersion = state.translationServices.makeOwner(); await immersion.configure(pair:.init(source:state.knownLanguage,target:state.targetLanguage)) }
                prepareVoices(); immersion.warm((session?.messages ?? []).map{(id:"bot-"+$0.id.uuidString,text:$0.text)})
            }
            .onAppear {
                state.chatReading.bindPlayback(owner:autoplay.ownerID) { identity,displayed in
                    autoplay.manual(identity,displayed:displayed,immersion:immersion,speech:speech,onModels:{translationHelpPair = $0; translationHelp = true},onVoiceHelp:{voiceHelp = true})
                }
            }
            .onDisappear {
                if let messageObserver { session?.removeMessageObserver(messageObserver) }; messageObserver = nil
                state.chatReading.unbindPlayback(owner:autoplay.ownerID); autoplay.stop(speech:speech); state.chatReading.cancelInteractions(); copyOriginal.abandon()
                if owner.translationOwner == nil { immersion.close() }; speech.close()
            }
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { session?.cancelGeneration(); copyOriginal.abandon(); autoplay.stop(speech:speech); state.chatReading.cancelInteractions(); speech.stop() }
                else { Task { await session?.refresh(); await immersion.refreshAvailability(); prepareVoices() } }
            }
            .onChange(of:speech.state) { _,value in if value == .ready { autoplay.voicesReady() } }
            .alert("Delete this vBot conversation?", isPresented: $clearConfirmation) {
                Button("Delete conversation", role: .destructive) { do { try session?.clear(); autoplay.stop(speech:speech); state.chatReading.cancelPendingPlayback() } catch { self.error = String(localized: "The conversation couldn’t be deleted.") } }
                Button("Cancel", role: .cancel) { }
            } message: { Text("This removes the saved vBot messages from this device. Reports you already sent to Vipi are kept for up to 30 days. Existing subscriptions are managed separately.") }
            .alert("Listen in your practice language", isPresented: $voiceHelp) {
                Button("Retry voices") { prepareVoices() }; Button("Done", role: .cancel) { }
            } message: { Text(speech.error ?? String(localized: "Voices are preparing. Please try again shortly.")) }
            .sheet(isPresented:$choosingReport,onDismiss:{
                if let selected = chosenReportMessage { chosenReportMessage = nil; reporting = selected }
            }) {
                ReportMessagePicker(choices:(session?.messages ?? []).filter{$0.role == "assistant" && $0.requestID != nil}.map{.init(id:$0.id.uuidString,original:$0.text)}) { id in
                    chosenReportMessage = session?.messages.first{$0.id.uuidString == id && $0.role == "assistant" && $0.requestID != nil}
                }
            }
            .sheet(item: $reporting) { message in
                if let session { BotReportView(session: session, message: message) }
            }
    }
    private func pendingStatus(_ item: BotMessage) -> String? {
        switch item.state {
        case "sending": String(localized:"Waiting for vBot")
        case "unconfirmed": String(localized:"Reply unconfirmed")
        case "rejected": String(localized:"Request not accepted")
        case "stopped": String(localized:"No reply — message saved")
        default: nil
        }
    }
    private func messageAccessibilityContext(_ item: BotMessage) -> String {
        [item.createdAt.formatted(date:.abbreviated,time:.shortened),pendingStatus(item)].compactMap { $0 }.joined(separator:" · ")
    }
    @ViewBuilder private func messageMetadata(_ item: BotMessage, in messages: [BotMessage]) -> some View {
        let index = messages.firstIndex { $0.id == item.id } ?? 0
        let previous = index > 0 ? messages[index-1].createdAt : nil
        let time = MessageTimelineMetadata.timeLabel(for:item.createdAt,previous:previous)
        let pending = pendingStatus(item)
        if time != nil || pending != nil {
            Text([time,pending].compactMap { $0 }.joined(separator:" · "))
        }
    }
    @ViewBuilder private func conversation(_ value: BotSession) -> some View {
        @Bindable var value = value
        ScrollViewReader { scroll in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    Text("Chat with vBot on this device, at no extra charge. Replies can be wrong.")
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                    if value.earlierAvailable { Button("Earlier messages") { do { try value.loadEarlier() } catch { self.error = String(localized: "Earlier messages couldn’t be opened.") } } }
                    ForEach(value.messages) { item in
                        HStack {
                            if item.role == "user" { Spacer(minLength: 38) }
                            ConversationImmersionText(text: item.text, id: "bot-" + item.id.uuidString, immersion: immersion,
                                speech: speech, paused: scrolling || composing,
                                metadata: AnyView(messageMetadata(item,in:value.messages).font(.subheadline).foregroundStyle(VipiDesign.secondary)),
                                onVoiceHelp: { voiceHelp = true }, onTranslationSetup: { translationHelpPair = $0; translationHelp = true }, onReport:item.role == "assistant" && item.requestID != nil ? { reporting = item } : nil,playback:autoplay,accessibilityMessageContext:messageAccessibilityContext(item))
                                .background(item.role == "user" ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))

                            if item.role != "user" { Spacer(minLength: 38) }
                        }.id(item.id)
                    }
                    if let notice = value.notice ?? error { Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary) }
                    Color.clear.frame(height: 1).id("bot-bottom")
                }.padding(.vertical,18).frame(maxWidth:644).frame(maxWidth:.infinity)
            }.contentMargins(.horizontal,18,for:.scrollContent)
                .accessibilityIdentifier("bot-conversation-timeline")
                .scrollDismissesKeyboard(.interactively).onScrollPhaseChange { _, phase in scrolling = phase.isScrolling }
                .onScrollGeometryChange(for: Bool.self) { geometry in
                    geometry.contentSize.height - geometry.visibleRect.maxY <= 44
                } action: { _, nearBottom in
                    if !copyOriginal.holdingLayout && (nearBottom || scrolling) { followingLatest = nearBottom }
                }
                .onChange(of: value.messages.last?.id) { _, _ in if followingLatest && !copyOriginal.holdingLayout { scroll.scrollTo("bot-bottom", anchor: .bottom) } }
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
                if let message = value.availability.message {
                    HStack(alignment: .top, spacing: 12) {
                        Text(message).font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal: false, vertical: true)
                        Button("Check again") { Task { await value.refresh() } }.frame(minHeight: 44)
                    }
                }
                if let notice = autoplay.voiceNotice {
                    HStack(alignment:.top) {
                        Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
                        Button("Retry voices") { prepareVoices() }.frame(minHeight:44)
                    }.accessibilityIdentifier("chat-voice-recovery")
                }
                if rejectedDraftEdit || value.draft.utf8.count > value.maximumMessageBytes {
                    Text(LocalizedStringKey(rejectedDraftEdit ? "That text is too long. Your previous draft is still here." : "This message is too long. Send a shorter message."))
                        .font(.subheadline).foregroundStyle(VipiDesign.destructive).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("bot-message-length-notice")
                }
                HStack(alignment: .bottom, spacing: 10) {
                    MessageEditor(text: Binding(get: { value.draft }, set: { draft in
                        guard draft.utf8.count <= ConversationHistory.maximumDraftBytes else { rejectedDraftEdit = true; return }
                        rejectedDraftEdit = false; value.draft = draft
                    }), placeholder: String(localized: "Message vBot"), focus: $composing,
                        maximumBytes: ConversationHistory.maximumDraftBytes, rejected: { rejectedDraftEdit = true })
                        .accessibilityIdentifier("bot-message-input")
                        .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                        .onChange(of: value.draft) { _, _ in value.saveDraft() }
                    Button {
                        if value.busy { value.cancelGeneration() }
                        else { composing = false; followingLatest = true; Task { await value.send() } }
                    } label: {
                        if value.busy {
                            Image(systemName: "stop.fill").frame(width: 46, height: 46)
                                .background(VipiDesign.highlight, in: Circle()).foregroundStyle(VipiDesign.onHighlight)
                        }
                        else { Image(systemName: "arrow.up").frame(width: 46, height: 46)
                            .background(value.canSend ? VipiDesign.highlight : VipiDesign.secondary.opacity(0.16), in: Circle())
                            .foregroundStyle(value.canSend ? VipiDesign.onHighlight : VipiDesign.secondary) }
                    }.disabled(!value.busy && !value.canSend).accessibilityLabel(value.busy ? String(localized: "Stop vBot reply") : String(localized: "Send to vBot"))
                        .accessibilityHint(sendHint(value)).accessibilityIdentifier("bot-message-send")
                }
            }.padding(14).background(VipiDesign.canvas)
        }
        .safeAreaInset(edge:.top,spacing:0) {
            autoplayButton.buttonStyle(.plain).frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,18)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
            Menu {
                Button("Copy original message",systemImage:"doc.on.doc") {
                    copyOriginal.open(value.messages.map{.init(id:$0.id.uuidString,original:$0.text)},autoplay:autoplay,speech:speech,reading:state.chatReading,fromMenu:true)
                }.disabled(value.messages.isEmpty).accessibilityIdentifier("copy-original-picker")
                NavigationLink("Languages") { LanguageDownloadView() }
                if value.messages.contains(where:{$0.role == "assistant" && $0.requestID != nil}) {
                    Button("Report a message",systemImage:"flag") { choosingReport = true }
                        .accessibilityIdentifier("report-message-picker")
                }
                Button("Delete conversation", role: .destructive) { clearConfirmation = true }.disabled(value.busy)
             } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44)
                .background { CopyOriginalMenuCapture(context:copyOriginal) } }.accessibilityLabel("vBot options")
        } }
        .onChange(of:value.messages.map(\.id),initial:true) { _,_ in
            immersion.warm(value.messages.map{(id:"bot-"+$0.id.uuidString,text:$0.text)})
        }
        .onChange(of:immersion.revision) { _,_ in
            immersion.warm(value.messages.map{(id:"bot-"+$0.id.uuidString,text:$0.text)})
            autoplay.resume(immersion:immersion,speech:speech,foreground:scenePhase == .active)
        }

    }
    private func sendHint(_ value: BotSession) -> Text {
        if value.draft.utf8.count > value.maximumMessageBytes { return Text("This message is too long. Send a shorter message.") }
        if let message = value.availability.message { return Text(verbatim: message) }
        if value.busy { return Text("Waiting for vBot") }
        if let notice = value.notice ?? error { return Text(verbatim: notice) }
        return Text("Message vBot")
    }
    private var autoplayButton: some View {
        ChatAutoplayButton(enabled:autoplay.enabled) {
            state.chatReading.cancelPendingPlayback()
            autoplay.toggle(snapshot:(session?.messages ?? []).map { .init(id:"bot-"+$0.id.uuidString,text:$0.text) },immersion:immersion,speech:speech)
        }
    }
    private func prepareVoices() {
        let language = state.targetLanguage
        speech.prepare(source:language,target:language,warmups:[language:VipiLanguage.named(language).localName])
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
                        Text("Only the selected reply and report details are sent to Vipi’s developers. Reports are encrypted, kept for up to 30 days, and removed when you delete your account.")
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
