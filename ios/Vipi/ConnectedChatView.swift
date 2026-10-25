import SwiftUI

struct ConnectedChatRoot: View {
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.scenePhase) private var scenePhase
    @State private var chat: ChatSession?
    @State private var error: String?
    var body: some View {
        Group {
            if let chat {
                if chat.profile != nil && chat.ready { HomeView(chat: chat) }
                else if chat.needsProfile { ProfileSetupView(chat: chat) }
                else {
                    ContentUnavailableView {
                        Label(chat.busy ? "Getting your Vipi ready" : "Let’s reconnect", systemImage: "bubble.left.and.bubble.right")
                    } description: { Text(chat.notice ?? "Your conversations stay on your device.") }
                    actions: {
                        if chat.busy { ProgressView() }
                        else {
                            Button("Try again") { Task { await chat.start() } }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                            Button("Sign in again") { authentication.signOutLocally() }
                        }
                    }
                }
            } else if let error {
                ContentUnavailableView("Your conversations couldn’t be opened", systemImage: "lock.shield", description: Text(error))
            } else { ProgressView("Getting your Vipi ready") }
        }
        .background(VipiDesign.canvas)
        .task(id: authentication.session?.userID) {
            try? chat?.close(); chat = nil
            guard let userID = authentication.session?.userID else { return }
            do {
                let value = try ChatSession(authentication: authentication, userID: userID)
                chat = value; await value.start()
            } catch { self.error = "Your saved data is still here. Please close and reopen Vipi to try again." }
        }
        .onDisappear { try? chat?.close() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await chat?.synchronize() } } }
    }
}

struct ProfileSetupView: View {
    let chat: ChatSession
    @State private var name = ""
    @State private var username = ""
    @State private var showDelete = false
    private var valid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 80 &&
        username.range(of: "^[a-zA-Z][a-zA-Z0-9_]{2,23}$", options: .regularExpression) != nil
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VipiMark(size: 50)
                IntroHeading(eyebrow: "Make yourself at home", title: "How will friends\nfind you?", detail: "Choose a name they’ll recognise and a username to share.")
                VStack(alignment: .leading, spacing: 14) {
                    TextField("Your name", text: $name).textContentType(.name).accessibilityIdentifier("profile-name")
                    Divider()
                    HStack { Text("@").foregroundStyle(VipiDesign.secondary); TextField("Username", text: $username)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().textContentType(.username).accessibilityIdentifier("profile-username") }
                }.padding(20).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
                Text("3–24 letters, numbers or underscores. Your phone number and contacts stay private.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
                if let notice = chat.notice { Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).accessibilityIdentifier("profile-error") }
                Button { Task { await chat.createProfile(username: username, name: name) } } label: {
                    HStack { Spacer(); if chat.busy { ProgressView().tint(VipiDesign.onHighlight) } else { Text("Start chatting").fontWeight(.semibold) }; Spacer() }.padding(.vertical, 12)
                }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).disabled(!valid || chat.busy).accessibilityIdentifier("profile-submit")
                Button("Delete account", role: .destructive) { showDelete = true }.disabled(chat.busy)
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.background(VipiDesign.canvas).scrollDismissesKeyboard(.interactively)
            .sheet(isPresented: $showDelete) { NavigationStack { DeleteAccountView(chat: chat)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Back") { showDelete = false } } } } }
    }
}

struct FriendConversationView: View {
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
    @State private var followingLatest = true
    @State private var scrolling = false
    @State private var position = ScrollPosition(idType: UUID.self, edge: .bottom)
    @State private var jumpRevision = 0
    @State private var firstMessageFrame = CGRect.zero
    @State private var viewportHeight: CGFloat = 0
    private var blocked: Bool { chat.blockedPeers.contains(peer) }
    @FocusState private var composing: Bool
    private func refresh() {
        do {
            let current = try chat.messages(peer), ids = Set(current.map(\.id))
            messages = (current + messages.filter { !ids.contains($0.id) }).sorted { a, b in a.cursor < b.cursor }
            if !loaded { text = try chat.compose(peer); earlierAvailable = current.count == 50; loaded = true }
            try chat.markRead(peer)
        } catch { self.error = "Your saved messages couldn’t be opened. Please try again." }
    }
    private func earlier() {
        do {
            let anchorID = messages.first?.id
            let frame = firstMessageFrame
            let relativeY = frame.minY / max(1, viewportHeight - frame.height)
            let page = try chat.messages(peer, before: messages.first?.cursor)
            let ids = Set(messages.map(\.id)); messages = page.reversed().filter { !ids.contains($0.id) } + messages
            earlierAvailable = page.count == 50
            if let anchorID {
                followingLatest = false
                Task { @MainActor in
                    await Task.yield()
                    position.scrollTo(id: anchorID, anchor: UnitPoint(x: 0.5, y: relativeY))
                }
            }
        } catch { self.error = "Earlier messages couldn’t be opened. Please try again." }
    }
    private func send() {
        do {
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
            catch { self.error = "Couldn’t confirm the change. Check your connection and try again." }
        }
    }
    private var timeline: some View {
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
                                Text(item.text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                                    .accessibilityIdentifier("message-body-" + item.id.uuidString)
                                ViewThatFits(in: .horizontal) {
                                    HStack(spacing: 6) { messageMetadata(item) }.fixedSize()
                                    VStack(alignment: .leading, spacing: 3) { messageMetadata(item) }
                                }.font(.caption2).foregroundStyle(VipiDesign.secondary)
                            }.padding(.horizontal, 15).padding(.vertical, 12)
                                .background(item.outgoing ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
                            if !item.outgoing { Spacer(minLength: 38) }
                        }.id(item.id)
                            .onGeometryChange(for: CGRect.self) { proxy in proxy.frame(in: .named("conversation-timeline")) } action: { frame in
                                if item.id == messages.first?.id { firstMessageFrame = frame }
                            }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }.scrollTargetLayout().padding(18).frame(maxWidth: 680).frame(maxWidth: .infinity)
            }.scrollDismissesKeyboard(.interactively)
                .accessibilityIdentifier("conversation-timeline")
                .coordinateSpace(name: "conversation-timeline")
                .scrollPosition($position)
                .defaultScrollAnchor(followingLatest ? .bottom : nil, for: .sizeChanges)
                .onScrollPhaseChange { _, phase in scrolling = phase.isScrolling }
                .onScrollGeometryChange(for: ConversationViewport.self) { geometry in
                    ConversationViewport(offset: geometry.visibleRect.minY, height: geometry.visibleRect.height,
                                         content: geometry.contentSize.height,
                                         insets: geometry.contentInsets.top + geometry.contentInsets.bottom)
                } action: { old, new in
                    viewportHeight = new.height
                    if new.nearBottom || scrolling { followingLatest = new.nearBottom }
                    // Composer/row remeasurement can adjust the offset without a user scroll.
                    if followingLatest && (old.height != new.height || old.content != new.content || old.insets != new.insets) {
                        position.scrollTo(edge: .bottom)
                    }
                }
                .refreshable { await chat.synchronize(); refresh() }
                .onChange(of: messages.last?.id) { _, _ in if followingLatest { position.scrollTo(edge: .bottom) } }
                .onChange(of: jumpRevision) { _, _ in position.scrollTo(edge: .bottom) }
                .onChange(of: composing) { _, focused in if focused && followingLatest { position.scrollTo(edge: .bottom) } }
                .overlay(alignment: .bottomTrailing) {
                    if !followingLatest && !messages.isEmpty {
                        Button { followingLatest = true; position.scrollTo(edge: .bottom) } label: {
                            Image(systemName: "arrow.down").font(.body.weight(.semibold)).frame(width: 48, height: 48)
                        }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).buttonBorderShape(.circle).padding(12)
                            .accessibilityLabel("Jump to latest messages").accessibilityIdentifier("conversation-latest")
                    }
                }
    }
    var body: some View {
        timeline
        .background(VipiDesign.canvas)
        .navigationTitle(chat.name(peer)).navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Verify encryption", systemImage: "lock.shield") { showSecurityNumber = true }
                    Button(blocked ? "Unblock" : "Block", role: blocked ? nil : .destructive) { confirmBlock = true }
                } label: {
                    if blockBusy { ProgressView() }
                    else { Image(systemName: "ellipsis").frame(width: 36, height: 36) }
                }.disabled(blockBusy).accessibilityLabel("Conversation options").accessibilityIdentifier("conversation-options")
            }
        }
        .alert(blocked ? "Unblock \(chat.name(peer))?" : "Block \(chat.name(peer))?", isPresented: $confirmBlock) {
            Button("Cancel", role: .cancel) {}
            Button(blocked ? "Unblock" : "Block", role: blocked ? nil : .destructive, action: changeBlock)
        } message: {
            Text(blocked ? "You can exchange new messages again. Stopped messages won’t be resent." : "Messages between you will stop. Your chat stays on this device. You can unblock anytime.")
        }
        .sheet(isPresented: $showSecurityNumber) { SecurityNumberView(chat: chat, peer: peer) }
        .safeAreaInset(edge: .bottom) { composer }
        .task {
            refresh(); blockBusy = true
            do { try await chat.refreshBlock(peer) }
            catch is CancellationError { blockBusy = false; return }
            catch { self.error = "Block status couldn’t be checked. Your last confirmed choice is saved." }
            blockBusy = false; await chat.synchronize()
        }
        .onChange(of: chat.revision) { _, _ in refresh() }
        .onChange(of: text) { _, value in
            guard loaded else { return }
            do { try chat.saveCompose(value, peer: peer) }
            catch { self.error = "This draft couldn’t be saved. Keep this conversation open and try again." }
        }
    }
    private var composer: some View {
            VStack(spacing: 9) {
                if let notice = error ?? chat.notice { Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary).padding(.horizontal, 18).accessibilityIdentifier("conversation-notice") }
                if blocked {
                    HStack {
                        Text("You blocked this person.").font(.subheadline)
                        Button("Unblock") { confirmBlock = true }.disabled(blockBusy)
                    }.padding(16).accessibilityIdentifier("conversation-blocked")
                } else {
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message", text: $text, prompt: Text("Message").foregroundColor(VipiDesign.secondary), axis: .vertical).lineLimit(1...6).focused($composing)
                        .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                        .accessibilityIdentifier("message-input")
                    Button(action: send) { Image(systemName: "arrow.up").font(.body.weight(.semibold)).frame(width: 46, height: 46) }
                        .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).buttonBorderShape(.circle).accessibilityLabel("Send message")
                        .accessibilityIdentifier("message-send")
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || text.utf8.count > 32768)
                }.padding(.horizontal, 14).padding(.bottom, 10)
                }
            }.background(VipiDesign.canvas)
    }
    @ViewBuilder private func messageMetadata(_ item: ChatItem) -> some View {
        Text(Date(timeIntervalSince1970: Double(item.createdAt) / 1000), style: .time)
            .accessibilityIdentifier("message-time-" + item.id.uuidString)
        if item.outgoing {
            Text(status(item.state)).accessibilityIdentifier("message-status-" + item.id.uuidString)
        }
    }
    private func status(_ value: String) -> String {
        switch value {
        case "delivered": "Delivered"
        case "accepted": "Sent"
        case "expired": "Not delivered · 72 hours passed"
        case "failed": "Not delivered"
        case "cancelled": "Stopped"
        default: "Waiting to send"
        }
    }
}

private struct ConversationViewport: Equatable {
    let offset: CGFloat
    let height: CGFloat
    let content: CGFloat
    let insets: CGFloat
    var nearBottom: Bool { content - offset - height <= 44 }
}
