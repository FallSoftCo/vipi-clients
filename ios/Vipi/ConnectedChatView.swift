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
                            Button("Try again") { Task { await chat.start() } }.buttonStyle(.borderedProminent)
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
            guard let userID = authentication.session?.userID else { chat = nil; return }
            do {
                let value = try ChatSession(authentication: authentication, userID: userID)
                chat = value; await value.start()
            } catch { self.error = "Your saved data is still here. Please close and reopen Vipi to try again." }
        }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await chat?.synchronize() } } }
    }
}

struct ProfileSetupView: View {
    let chat: ChatSession
    @State private var name = ""
    @State private var username = ""
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
                    HStack { Spacer(); if chat.busy { ProgressView().tint(.white) } else { Text("Start chatting").fontWeight(.semibold) }; Spacer() }.padding(.vertical, 12)
                }.buttonStyle(.borderedProminent).disabled(!valid || chat.busy).accessibilityIdentifier("profile-submit")
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.background(VipiDesign.canvas).scrollDismissesKeyboard(.interactively)
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
            let page = try chat.messages(peer, before: messages.first?.cursor)
            let ids = Set(messages.map(\.id)); messages = page.reversed().filter { !ids.contains($0.id) } + messages
            earlierAvailable = page.count == 50
        } catch { self.error = "Earlier messages couldn’t be opened. Please try again." }
    }
    private func send() {
        do {
            try chat.send(text, peer: peer); text = ""; error = nil; refresh()
            Task { await chat.synchronize() }
        } catch { self.error = ChatSession.explanation(error) }
    }
    var body: some View {
        ScrollViewReader { proxy in
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
                                HStack(spacing: 6) {
                                    Text(Date(timeIntervalSince1970: Double(item.createdAt) / 1000), style: .time)
                                    if item.outgoing { Text(status(item.state)) }
                                }.font(.caption2).foregroundStyle(VipiDesign.secondary)
                            }.padding(.horizontal, 15).padding(.vertical, 12)
                                .background(item.outgoing ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
                            if !item.outgoing { Spacer(minLength: 38) }
                        }.id(item.id)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }.padding(18).frame(maxWidth: 680).frame(maxWidth: .infinity)
            }.scrollDismissesKeyboard(.interactively)
                .refreshable { await chat.synchronize(); refresh() }
                .onChange(of: messages.last?.id) { _, _ in proxy.scrollTo("bottom", anchor: .bottom) }
                .onChange(of: composing) { _, focused in if focused { proxy.scrollTo("bottom", anchor: .bottom) } }
        }
        .background(VipiDesign.canvas)
        .navigationTitle(chat.name(peer)).navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 9) {
                if let notice = error ?? chat.notice { Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary).padding(.horizontal, 18) }
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message", text: $text, axis: .vertical).lineLimit(1...6).focused($composing)
                        .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                        .accessibilityIdentifier("message-input")
                    Button(action: send) { Image(systemName: "arrow.up").font(.body.weight(.semibold)).frame(width: 46, height: 46) }
                        .buttonStyle(.borderedProminent).buttonBorderShape(.circle).accessibilityLabel("Send message")
                        .accessibilityIdentifier("message-send")
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || text.utf8.count > 32768)
                }.padding(.horizontal, 14).padding(.bottom, 10)
            }.background(VipiDesign.canvas)
        }
        .task { refresh(); await chat.synchronize() }
        .onChange(of: chat.revision) { _, _ in refresh() }
        .onChange(of: text) { _, value in
            guard loaded else { return }
            do { try chat.saveCompose(value, peer: peer) }
            catch { self.error = "This draft couldn’t be saved. Keep this conversation open and try again." }
        }
    }
    private func status(_ value: String) -> String {
        switch value {
        case "delivered": "Delivered"
        case "accepted": "Sent"
        case "expired": "Not delivered · 72 hours passed"
        case "failed": "Not delivered"
        default: "Waiting to send"
        }
    }
}
