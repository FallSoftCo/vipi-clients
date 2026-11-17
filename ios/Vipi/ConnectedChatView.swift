import SwiftUI

struct ConnectedChatRoot: View {
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.scenePhase) private var scenePhase
    @State private var chat: ChatSession?
    @State private var subscriptions: SubscriptionStore?
    @State private var error: String?
    @State private var replacement: OwnDeviceReplacement?
    @State private var showReplacement = false
    var body: some View {
        Group {
            if let chat {
                if chat.profile != nil {
                    HomeView(chat: chat, subscriptions: subscriptions, reauthenticate: { authentication.signIn(expectedUser: chat.userID) }, authenticationBusy: authentication.busy, authenticationError: authentication.errorMessage)
                        .safeAreaInset(edge: .top) {
                            if !chat.ready && !chat.needsReauthentication {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Chatting is paused").font(.headline)
                                    Text(chat.notice ?? "Your saved conversations are available while this device reconnects.").font(.footnote)
                                    if let error = authentication.errorMessage { Text(error).font(.footnote) }
                                    HStack {
                                        if chat.needsDeviceReplacement {
                                            Button("Review this device") {
                                                do { replacement = try chat.deviceReplacementCandidate(); showReplacement = true }
                                                catch { self.error = ChatSession.explanation(error) }
                                            }.accessibilityIdentifier("device-replacement-review")
                                        } else { Button("Try again") { Task { await chat.start() } } }
                                        Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                                    }.disabled(chat.busy || authentication.busy)
                                }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(VipiDesign.surface)
                            }
                        }
                }
                else if chat.needsProfile { ProfileSetupView(chat: chat) }
                else {
                    ContentUnavailableView {
                        Label(LocalizedStringKey(chat.busy ? "Connecting to your chats" : "Reconnect to your chats"), systemImage: "bubble.left.and.bubble.right")
                    } description: { Text(chat.notice ?? "Your conversations stay on your device.") }
                    actions: {
                        if chat.busy { ProgressView() }
                        else {
                            Button("Try again") { Task { await chat.start() } }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                            Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                        }
                    }
                }
            } else if let error {
                ContentUnavailableView("Your conversations couldn’t be opened", systemImage: "lock.shield", description: Text(error))
            } else { ProgressView("Connecting to your chats") }
        }
        .background(VipiDesign.canvas)
        .sheet(isPresented: $showReplacement) {
            if let chat, let replacement { OwnDeviceReplacementView(chat: chat, candidate: replacement) }
        }
        .onChange(of: authentication.session?.accessToken) { _, _ in
            if let chat, !chat.ready || chat.needsReauthentication { Task { await chat.start() } }
        }
        .task(id: authentication.session?.userID) {
            subscriptions?.close(); subscriptions = nil
            PushNotifications.shared.detach()
            try? chat?.close(); chat = nil
            guard let userID = authentication.session?.userID else { return }
            do {
                let value = try ChatSession(authentication: authentication, userID: userID)
                chat = value; await value.start()
            } catch { self.error = String(localized: "Your saved data is still here. Please close and reopen Vipi to try again.") }
        }
        .onDisappear { subscriptions?.close(); PushNotifications.shared.detach(); try? chat?.close() }
        .task(id: chat?.profile?.id) {
            subscriptions?.close(); subscriptions = nil
            guard let profile = chat?.profile, let userID = authentication.session?.userID,
                  let api = try? ServiceClient(authentication: authentication, userID: userID) else { return }
            let store = SubscriptionStore(api: api, accountToken: profile.id)
            subscriptions = store; await store.start()
        }
        .task(id: chat?.ready == true && chat?.needsReauthentication == false) {
            chat?.setForeground(scenePhase == .active)
            if let chat, chat.ready && !chat.needsReauthentication { await PushNotifications.shared.attach(chat) }
        }
        .onChange(of: scenePhase) { _, phase in
            chat?.setForeground(phase == .active)
            if phase == .active { Task { await chat?.synchronize(); await subscriptions?.refresh(); await PushNotifications.shared.refresh() } }
        }
    }
}

struct ProfileSetupView: View {
    let chat: ChatSession
    @State private var name = ""
    @State private var username = ""
    @State private var showDelete = false
    @State private var acceptedTerms = false
    private var valid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 80 &&
        username.range(of: "^[a-zA-Z][a-zA-Z0-9_]{2,23}$", options: .regularExpression) != nil
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VipiMark(size: 50)
                IntroHeading(eyebrow: "Your profile", title: "How will friends\nfind you?", detail: "Choose a name they’ll recognise and a username to share.")
                VStack(alignment: .leading, spacing: 14) {
                    TextField("Your name", text: $name, prompt: Text("Your name").foregroundStyle(VipiDesign.secondary)).textContentType(.name).accessibilityIdentifier("profile-name")
                    Divider()
                    HStack { Text("@").foregroundStyle(VipiDesign.secondary); TextField("Username", text: $username, prompt: Text("Username").foregroundStyle(VipiDesign.secondary))
                        .textInputAutocapitalization(.never).autocorrectionDisabled().textContentType(.username).accessibilityIdentifier("profile-username") }
                }.padding(20).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
                Text("Use 3–24 English letters, numbers or underscores. Start with a letter. Your phone number and contacts stay private.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                Toggle("I agree to the Terms of Service and have read the Privacy Policy.", isOn: $acceptedTerms)
                    .font(.footnote).tint(VipiDesign.accent).accessibilityIdentifier("profile-accept-terms")
                HStack(spacing: 20) {
                    Link("Terms", destination: URL(string: "https://api.mambovipi.app/terms")!)
                    Link("Privacy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                }.font(.footnote)
                if let notice = chat.notice { Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("profile-error") }
                Button { Task { await chat.createProfile(username: username, name: name) } } label: {
                    HStack { Spacer(); if chat.busy { ProgressView().tint(VipiDesign.onHighlight) } else { Text("Start chatting").fontWeight(.semibold) }; Spacer() }.padding(.vertical, 12)
                }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).disabled(!valid || !acceptedTerms || chat.busy).accessibilityIdentifier("profile-submit")
                Button("Delete account", role: .destructive) { showDelete = true }.foregroundStyle(VipiDesign.destructive).disabled(chat.busy)
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.clipped().background(VipiDesign.canvas).scrollDismissesKeyboard(.interactively)
            .sheet(isPresented: $showDelete) { NavigationStack { DeleteAccountView(chat: chat)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Back") { showDelete = false } } } } }
    }
}

struct FriendConversationView: View {
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var immersion: ConversationImmersion
    @State private var speech = SpeechPlayback()
    @ScaledMetric(relativeTo: .body) private var metadataSize = 14
    let chat: ChatSession
    let peer: UUID
    @State private var messages: [ChatItem] = []
    @State private var text = ""
    @State private var error: String?
    @State private var earlierAvailable = false
    @State private var loaded = false
    @State private var confirmBlock = false
    @State private var blockBusy = false
    @State private var showSecurityNumber = false
    @State private var showVoiceHelp = false
    @State private var showMessageStatus = false
    @State private var reporting: HumanReportSelection?
    @State private var followingLatest = true
    @State private var scrolling = false
    @State private var userScrolling = false
    @State private var position = ScrollPosition(idType: UUID.self, edge: .bottom)
    @State private var jumpRevision = 0
    @State private var firstMessageFrame = CGRect.zero
    @State private var viewportHeight: CGFloat = 0
    @State private var viewportBottomInset: CGFloat = 0
    @State private var scrollOffset: CGFloat = 0
    @State private var pageAnchorID: UUID?
    @State private var pageAnchorFrame = CGRect.zero
    @State private var pageRestore: Task<Void, Never>?
    @State private var viewportRestore: Task<Void, Never>?
    @State private var textSizeRestore: Task<Void, Never>?
    @State private var textSizeAnchorID: UUID?
    @State private var textSizeAnchorFrame = CGRect.zero
    private var blocked: Bool { chat.blockedPeers.contains(peer) }
    private var messageNotice: String? { error ?? chat.notice }
    private var canSend: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && text.utf8.count <= 32768 }
    @FocusState private var composing: Bool
    init(chat: ChatSession, peer: UUID, immersion: ConversationImmersion? = nil) {
        self.chat = chat; self.peer = peer
        _immersion = State(initialValue: immersion ?? ConversationImmersion())
    }
    private func cancelPageRestoration() {
        pageRestore?.cancel(); pageRestore = nil; pageAnchorID = nil
    }
    private func refresh() {
        do {
            let current = try chat.messages(peer), ids = Set(current.map(\.id))
            messages = (current + messages.filter { !ids.contains($0.id) }).sorted { a, b in a.cursor < b.cursor }
            if !loaded { text = try chat.compose(peer); earlierAvailable = current.count == 50; loaded = true }
            try chat.markRead(peer)
        } catch { self.error = String(localized: "Your saved messages couldn’t be opened. Please try again.") }
    }
    private func earlier() {
        do {
            let anchorID = messages.first?.id
            let frame = firstMessageFrame
            let relativeY = frame.minY / max(1, viewportHeight - frame.height)
            pageRestore?.cancel()
            pageAnchorID = anchorID
            pageAnchorFrame = frame
            let page = try chat.messages(peer, before: messages.first?.cursor)
            let ids = Set(messages.map(\.id)); messages = page.reversed().filter { !ids.contains($0.id) } + messages
            earlierAvailable = page.count == 50
            if let anchorID {
                followingLatest = false
                pageRestore = Task { @MainActor in
                    await Task.yield()
                    guard !Task.isCancelled else { return }
                    position.scrollTo(id: anchorID, anchor: UnitPoint(x: 0.5, y: relativeY))
                    // Lazy row estimates can make ID restoration inaccurate on
                    // iPadOS 18. Preserve the measured row position as the new
                    // page lays out. A fresh touch cancels this bounded settling.
                    for _ in 0..<8 {
                        do { try await Task.sleep(for: .milliseconds(40)) }
                        catch { return }
                        guard pageAnchorID == anchorID else { return }
                        let delta = pageAnchorFrame.minY - frame.minY
                        if abs(delta) > 0.5 { position.scrollTo(y: scrollOffset + delta) }
                    }
                    pageAnchorID = nil
                    pageRestore = nil
                }
            }
        } catch { self.error = String(localized: "Earlier messages couldn’t be opened. Please try again.") }
    }
    private func send() {
        do {
            cancelPageRestoration()
            try chat.send(text, peer: peer); text = ""; error = nil
            followingLatest = true; jumpRevision += 1; refresh()
            Task { await chat.synchronize() }
        } catch { self.error = ChatSession.explanation(error) }
    }
    private func changeBlock() {
        let desired = !blocked
        blockBusy = true
        Task {
            defer { blockBusy = false }
            do { try await chat.setBlocked(desired, peer: peer); error = nil; refresh() }
            catch is CancellationError {}
            catch { self.error = String(localized: "Couldn’t confirm the change. Check your connection and try again.") }
        }
    }
    private var timeline: some View {
        VStack(spacing: 0) {
            // At accessibility sizes, labelled controls expose the same details
            // without pinning several paragraphs above the composer.
            HStack(spacing: 12) {
                if immersion.availability == .downloadable || immersion.availability == .unsupported {
                    NavigationLink { LanguageDownloadView() } label: {
                        statusLabel("Translation downloads", symbol: "arrow.down.circle")
                    }.accessibilityIdentifier("conversation-language-download")
                }
                Spacer(minLength: 0)
                if chat.changedIdentities.contains(peer) {
                    Button("Review changed keys", systemImage: "lock.trianglebadge.exclamationmark") { showSecurityNumber = true }
                        .accessibilityIdentifier("peer-identity-review")
                }
                if let notice = messageNotice {
                    Button { showMessageStatus = true } label: {
                        statusLabel("Message status", symbol: "exclamationmark.circle")
                    }.accessibilityHint(notice).accessibilityIdentifier("conversation-notice")
                }
                if speech.state != .unavailable, let notice = speech.error {
                    Button { showVoiceHelp = true } label: {
                        statusLabel("Audio", symbol: "speaker.badge.exclamationmark")
                    }.accessibilityHint(notice)
                }
            }.font(.subheadline).padding(.horizontal, 18)
            ScrollView {
                LazyVStack(spacing: 14) {
                    if earlierAvailable { Button("Earlier messages", action: earlier).font(.footnote).padding(8) }
                    if messages.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "lock.shield").font(.title2)
                            Text("Just between you two").font(.headline)
                            Text("Say hello. Your messages are end-to-end encrypted.")
                                .font(.subheadline).multilineTextAlignment(.center)
                        }.foregroundStyle(VipiDesign.secondary).padding(30)
                    }
                    ForEach(messages) { item in
                        HStack {
                            if item.outgoing { Spacer(minLength: 38) }
                            VStack(alignment: .leading, spacing: 7) {
                                ConversationImmersionText(text: item.text, id: item.id.uuidString, immersion: immersion,
                                    speech: speech, paused: scrolling || (composing && !text.isEmpty), metadata: AnyView(
                                messageMetadata(item).font(.system(size: metadataSize))
                                    .fixedSize(horizontal: false, vertical: true).foregroundStyle(VipiDesign.secondary)
                                    .accessibilityIdentifier("message-meta-" + item.id.uuidString)), onVoiceHelp: { showVoiceHelp = true })
                            }.padding(.horizontal, 15).padding(.vertical, 12)
                                .background(item.outgoing ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
                            if !item.outgoing { Spacer(minLength: 38) }
                        }.id(item.id)
                            .contextMenu {
                                if !item.outgoing && item.state != "imported" {
                                    Button("Report message", systemImage: "flag") { reporting = HumanReportSelection(message: item) }
                                }
                            }
                            .accessibilityActions {
                                if !item.outgoing && item.state != "imported" {
                                    Button("Report message") { reporting = HumanReportSelection(message: item) }
                                }
                            }
                            .onGeometryChange(for: CGRect.self) { proxy in proxy.frame(in: .named("conversation-timeline")) } action: { frame in
                                if item.id == messages.first?.id { firstMessageFrame = frame }
                                if item.id == pageAnchorID { pageAnchorFrame = frame }
                                if item.id == textSizeAnchorID { textSizeAnchorFrame = frame }
                            }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }.scrollTargetLayout().padding(18).frame(maxWidth: 680).frame(maxWidth: .infinity)
            }.scrollDismissesKeyboard(.interactively)
                .accessibilityIdentifier("conversation-timeline")
                .coordinateSpace(name: "conversation-timeline")
                .scrollPosition($position)
                .defaultScrollAnchor(followingLatest ? .bottom : nil, for: .sizeChanges)
                .onScrollPhaseChange { _, phase in
                    scrolling = phase.isScrolling
                    userScrolling = phase == .interacting || phase == .decelerating
                    if phase == .tracking || phase == .interacting {
                        cancelPageRestoration()
                        viewportRestore?.cancel(); viewportRestore = nil
                        textSizeRestore?.cancel(); textSizeRestore = nil
                        textSizeAnchorID = nil
                    }
                }
                .onScrollGeometryChange(for: ConversationViewport.self) { geometry in
                    ConversationViewport(offset: geometry.visibleRect.minY, height: geometry.visibleRect.height,
                                         content: geometry.contentSize.height,
                                         bottomInset: geometry.contentInsets.bottom)
                } action: { old, new in
                    #if DEBUG
                    LiveImmersionQualification.record(["event": "viewport", "offset": Double(new.offset),
                        "height": Double(new.height), "content": Double(new.content), "bottom_inset": Double(new.bottomInset),
                        "following_latest": followingLatest, "scrolling": scrolling, "user_scrolling": userScrolling,
                        "composing": composing, "draft_empty": text.isEmpty])
                    #endif
                    viewportHeight = new.height
                    viewportBottomInset = new.bottomInset
                    scrollOffset = new.offset
                    // Only a user's scroll changes reading intent. Lazy row
                    // estimates can briefly look like the bottom during a
                    // keyboard resize, even while reading much older messages.
                    if userScrolling { followingLatest = new.nearBottom }
                    // Wait until a real viewport resize settles before moving
                    // the scroll position. Mutating it during lazy layout can
                    // invalidate the visible rows or feed another measurement.
                    if followingLatest && !scrolling && textSizeRestore == nil && abs(old.height - new.height) > 0.5 {
                        viewportRestore?.cancel()
                        viewportRestore = Task { @MainActor in
                            do { try await Task.sleep(for: .milliseconds(80)) }
                            catch { return }
                            guard followingLatest && !scrolling else { return }
                            position.scrollTo(edge: .bottom)
                            viewportRestore = nil
                        }
                    }
                }
                .refreshable { await chat.synchronize(); refresh() }
                .onChange(of: messages.last?.id) { _, _ in if followingLatest { position.scrollTo(edge: .bottom) } }
                .onChange(of: jumpRevision) { _, _ in position.scrollTo(edge: .bottom) }
                .onChange(of: composing) { _, focused in if focused && followingLatest { position.scrollTo(edge: .bottom) } }
                .onChange(of: typeSize) { _, _ in
                    // Font changes invalidate every lazy row's measured height.
                    // Restore a semantic message anchor after the new layout,
                    // rather than keeping an offset calculated with old fonts.
                    let latest = followingLatest
                    guard let target = latest ? messages.last?.id : position.viewID(type: UUID.self) else { return }
                    cancelPageRestoration()
                    viewportRestore?.cancel(); viewportRestore = nil
                    textSizeRestore?.cancel()
                    textSizeAnchorID = target; textSizeAnchorFrame = .zero
                    textSizeRestore = Task { @MainActor in
                        do { try await Task.sleep(for: .milliseconds(80)) }
                        catch { return }
                        guard !scrolling else { textSizeRestore = nil; return }
                        position.scrollTo(id: target, anchor: latest ? .bottom : .top)
                        // Realizing a large lazy row can replace another size
                        // estimate after the initial ID scroll. Settle only this
                        // explicit font change against its measured row; never
                        // turn ordinary content growth into automatic following.
                        var settled = 0
                        for _ in 0..<8 {
                            do { try await Task.sleep(for: .milliseconds(40)) }
                            catch { return }
                            guard textSizeAnchorID == target, !userScrolling,
                                  messages.contains(where: { $0.id == target }) else { return }
                            guard textSizeAnchorFrame.height > 0 else { continue }
                            let desired = latest ? viewportHeight - viewportBottomInset - 18 : 0
                            let actual = latest ? textSizeAnchorFrame.maxY : textSizeAnchorFrame.minY
                            let delta = actual - desired
                            #if DEBUG
                            LiveImmersionQualification.record(["event": "text_size_anchor", "message_id": target.uuidString,
                                "latest": latest, "actual": Double(actual), "desired": Double(desired), "delta": Double(delta)])
                            #endif
                            if abs(delta) > 0.5 {
                                settled = 0
                                position.scrollTo(y: scrollOffset + delta)
                            } else {
                                settled += 1
                                if settled >= 2 { break }
                            }
                        }
                        textSizeAnchorID = nil
                        textSizeRestore = nil
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    if !followingLatest && !messages.isEmpty {
                        Button { cancelPageRestoration(); followingLatest = true; position.scrollTo(edge: .bottom) } label: {
                            Image(systemName: "arrow.down").font(.body.weight(.semibold)).frame(width: 48, height: 48)
                        }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).buttonBorderShape(.circle).padding(12)
                            .accessibilityLabel("Jump to latest messages").accessibilityIdentifier("conversation-latest")
                    }
                }
        }
    }
    var body: some View {
        timeline
        .background(VipiDesign.canvas)
        .background { ConversationTranslationTask(immersion: immersion) }
        .navigationTitle(chat.name(peer)).navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if #available(iOS 26.0, *) {
                conversationOptions.sharedBackgroundVisibility(.hidden)
            } else { conversationOptions }
        }
        .alert(blocked ? "Unblock \(chat.name(peer))?" : "Block \(chat.name(peer))?", isPresented: $confirmBlock) {
            Button("Cancel", role: .cancel) {}
            Button(LocalizedStringKey(blocked ? "Unblock" : "Block"), role: blocked ? nil : .destructive, action: changeBlock)
        } message: {
            Text(LocalizedStringKey(blocked ? "You can exchange new messages again. Stopped messages won’t be resent." : "Messages between you will stop. Your chat stays on this device. You can unblock anytime."))
        }
        .sheet(isPresented: $showSecurityNumber) { SecurityNumberView(chat: chat, peer: peer) }
        .sheet(item: $reporting) { selection in HumanReportView(chat: chat, peer: peer, message: selection.message) }
        .sheet(isPresented: $showMessageStatus) {
            NavigationStack {
                ScrollView {
                    Text(messageNotice ?? "Your messages are up to date.")
                        .frame(maxWidth: .infinity, alignment: .leading).padding(24)
                        .accessibilityIdentifier("conversation-notice-detail")
                }.background(VipiDesign.canvas).navigationTitle("Message status")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showMessageStatus = false } } }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showVoiceHelp) {
            NavigationStack {
                ScrollView {
                  VStack(alignment: .leading, spacing: 20) {
                    Text("Hear both languages").font(.title2).fontWeight(.semibold)
                    Text(speech.error ?? "Prepare the voices for both languages to listen without a connection.")
                    Button("Retry voices") { prepareVoices() }
                        .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                        .disabled(speech.state == .preparing)
                    if speech.state == .preparing { ProgressView("Preparing voices") }
                  }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
                }
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showVoiceHelp = false } } }
                    .background(VipiDesign.canvas)
            }.presentationDetents([.medium, .large])
        }
        .safeAreaInset(edge: .bottom) { composer }
        .task(id: "\(state.knownLanguage)-\(state.targetLanguage)-\(state.density)") {
            speech.close()
            await immersion.configure(pair: .init(source: state.knownLanguage, target: state.targetLanguage), density: state.density, familiarity: chat.familiarity)
            prepareVoices()
        }
        .onDisappear { cancelPageRestoration(); viewportRestore?.cancel(); viewportRestore = nil; textSizeRestore?.cancel(); textSizeRestore = nil; textSizeAnchorID = nil; immersion.close(); speech.close() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { cancelPageRestoration(); speech.stop() }
            else { Task { await immersion.refreshAvailability(); prepareVoices() } }
        }
        .onChange(of: speech.state) { _, value in if value == .ready { showVoiceHelp = false } }
        .task {
            refresh(); blockBusy = true
            do { try await chat.refreshBlock(peer) }
            catch is CancellationError { blockBusy = false; return }
            catch { self.error = String(localized: "Block status couldn’t be checked. Your last confirmed choice is saved.") }
            blockBusy = false; await chat.synchronize()
        }
        .onChange(of: chat.revision) { _, _ in refresh() }
        .onChange(of: text) { _, value in
            guard loaded else { return }
            do { try chat.saveCompose(value, peer: peer) }
            catch { self.error = String(localized: "This draft couldn’t be saved. Keep this conversation open and try again.") }
        }
    }
    private var conversationOptions: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                NavigationLink { LanguageDownloadView() } label: { Label("Languages", systemImage: "globe") }
                    .accessibilityIdentifier("conversation-languages")
                Button("Verify encryption", systemImage: "lock.shield") { showSecurityNumber = true }
                Button("Report person", systemImage: "flag") { reporting = HumanReportSelection(message: nil) }
                Button(LocalizedStringKey(blocked ? "Unblock" : "Block"), role: blocked ? nil : .destructive) { confirmBlock = true }
            } label: {
                if blockBusy { ProgressView() }
                else { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
            }.disabled(blockBusy).accessibilityLabel("Conversation options").accessibilityIdentifier("conversation-options")
        }
    }
    private var composer: some View {
            VStack(spacing: 9) {
                if blocked {
                    HStack {
                        Text("You blocked this person.").font(.subheadline)
                        Button("Unblock") { confirmBlock = true }.disabled(blockBusy)
                    }.padding(16).accessibilityIdentifier("conversation-blocked")
                } else {
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message", text: $text, prompt: Text("Message").foregroundColor(VipiDesign.secondary), axis: .vertical).lineLimit(1...6).focused($composing)
                        .fixedSize(horizontal: false, vertical: true)
                        .id(typeSize)
                        .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                        .accessibilityIdentifier("message-input")
                    Button(action: send) {
                        Image(systemName: "arrow.up").font(.body.weight(.semibold))
                            .frame(minWidth: 46, minHeight: 46).padding(6)
                            .foregroundStyle(canSend ? VipiDesign.onHighlight : VipiDesign.secondary)
                            .background(canSend ? VipiDesign.highlight : VipiDesign.secondary.opacity(0.12), in: Circle())
                    }.buttonStyle(.plain).accessibilityLabel("Send message")
                        .accessibilityIdentifier("message-send")
                        .disabled(!canSend)
                }.padding(.horizontal, 14).padding(.bottom, 10)
                }
            }.background(VipiDesign.canvas)
    }
    @ViewBuilder private func statusLabel(_ title: LocalizedStringKey, symbol: String) -> some View {
        if typeSize.isAccessibilitySize {
            Label(title, systemImage: symbol).labelStyle(.iconOnly).frame(minWidth: 44, minHeight: 44)
        } else {
            Label(title, systemImage: symbol).fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
        }
    }
    private func prepareVoices() {
        if let source = ConversationExamples.examples?.languages[state.knownLanguage]?.text,
           let target = ConversationExamples.examples?.languages[state.targetLanguage]?.text {
            speech.prepare(source: state.knownLanguage, target: state.targetLanguage,
                warmups: [state.knownLanguage: source, state.targetLanguage: target])
        }
    }
    private func messageMetadata(_ item: ChatItem) -> Text {
        let time = Text(Date(timeIntervalSince1970: Double(item.createdAt) / 1000), style: .time)
        if item.state == "imported" { return time + Text(" · Saved history") }
        return item.outgoing ? time + Text(" · " + status(item.state)) : time
    }
    private func status(_ value: String) -> String {
        switch value {
        case "delivered": String(localized: "Delivered")
        case "accepted": String(localized: "Sent")
        case "expired": String(localized: "Not delivered · 72 hours passed")
        case "failed": String(localized: "Not delivered")
        case "cancelled": String(localized: "Stopped")
        default: String(localized: "Waiting to send")
        }
    }
}

private struct ConversationViewport: Equatable {
    let offset: CGFloat
    let height: CGFloat
    let content: CGFloat
    let bottomInset: CGFloat
    // visibleRect includes the area underneath the composer and keyboard.
    // A message hidden there must not count as being at the visible bottom.
    var nearBottom: Bool { content + bottomInset - offset - height <= 44 }
}

struct OwnDeviceReplacementView: View {
    let chat: ChatSession
    let candidate: OwnDeviceReplacement
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.dismiss) private var dismiss
    @State private var confirming = false
    @State private var working = false
    @State private var error: String?
    @State private var attempted = false
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Use Vipi on this device") .font(.title2.weight(.semibold))
                    Text("This device will replace whichever other device is currently active and sign it out. A recent sign-in is required.")
                    Text("Your saved history stays here. Pending messages from the previous device won’t be resent. Friends will see changed encryption keys.")
                }
                Section {
                    if chat.needsRecentSignIn {
                        Text("Sign in again to finish moving your account. The device change you confirmed is saved.").font(.footnote)
                        Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                            .accessibilityIdentifier("device-replacement-sign-in")
                            .disabled(working || authentication.busy || chat.busy)
                    } else if chat.hasPendingDeviceReplacement {
                        Button("Try again") {
                            working = true
                            Task {
                                defer { working = false }
                                do { try await chat.resumeDeviceReplacement(); dismiss() }
                                catch { self.error = ChatSession.explanation(error) }
                            }
                        }.disabled(working || chat.busy).accessibilityIdentifier("device-replacement-retry")
                    } else if attempted && chat.needsDeviceReplacement {
                        Text("The active device changed again. Review this device once more before replacing it.").font(.footnote)
                        Button("Review again") { dismiss() }.accessibilityIdentifier("device-replacement-review-again")
                    } else {
                        Button("Use this device") { confirming = true }.disabled(working || !chat.needsDeviceReplacement)
                            .accessibilityIdentifier("device-replacement-confirm")
                    }
                    if working { ProgressView("Registering this device") }
                    if let error { Text(error).font(.footnote) }
                    if let error = authentication.errorMessage { Text(error).font(.footnote) }
                }
            }.scrollContentBackground(.hidden).background(VipiDesign.canvas)
                .navigationTitle("Move your account").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(working) } }
                .alert("Replace the active device?", isPresented: $confirming) {
                    Button("Cancel", role: .cancel) {}
                    Button("Use this device") {
                        working = true; attempted = true
                        Task {
                            defer { working = false }
                            do { try await chat.confirmDeviceReplacement(candidate); dismiss() }
                            catch { self.error = ChatSession.explanation(error) }
                        }
                    }
                } message: { Text("The currently active device will be signed out. Saved history remains, but pending old messages won’t be resent.") }
        }.tint(VipiDesign.highlight).interactiveDismissDisabled(working)
            .onChange(of: chat.ready) { _, ready in if ready { dismiss() } }
    }
}
