import SwiftUI
import VipiCore

private enum HomeDestination: Hashable { case friend(UUID) }

struct HomeView: View {
    var chat: ChatSession? = nil
    var subscriptions: SubscriptionStore? = nil
    var botOwner = BotConversationOwner()
    var reauthenticate: (() -> Void)? = nil
    var authenticationBusy = false
    var authenticationError: String? = nil
    @Environment(AppState.self) private var state
    @State private var showingSettings = false
    @State private var offerBase = false
    @State private var offeredBase = false
    @State private var showingInvite = false
    @State private var query = ""
    @State private var path: [HomeDestination] = []
    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        if let chat, chat.needsReauthentication, let reauthenticate {
                            ReauthenticationNotice(busy: authenticationBusy || chat.busy, error: authenticationError, signIn: reauthenticate)
                        }
                        if let notice = chat?.notice { Text(notice).font(.body).foregroundStyle(VipiDesign.secondary) }
                        if let chat, !chat.threads.isEmpty {
                            LazyVStack(spacing:0) {
                                ForEach(chat.threads) { thread in
                                    NavigationLink(value: HomeDestination.friend(thread.peer)) {
                                        HomeConversationRow(name:chat.name(thread.peer),thread:thread,owner:chat.translationOwner,
                                            expectedPair:.init(source:state.knownLanguage,target:state.targetLanguage))
                                    }.buttonStyle(.plain)
                                        .accessibilityIdentifier("chat-thread-"+thread.peer.uuidString.lowercased())
                                    if thread.id != chat.threads.last?.id {
                                        Divider().overlay(VipiDesign.separator).padding(.leading,60).accessibilityHidden(true)
                                    }
                                }
                            }
                        } else { VStack(alignment: .center, spacing: 20) {
                            Image(systemName:"bubble.left.and.bubble.right").font(.system(size:40)).foregroundStyle(VipiDesign.secondary).accessibilityHidden(true)
                            VStack(alignment: .center, spacing: 8) {
                                Text("Find a friend by username or send them an invite.").font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                            }
                            PrimaryButton(title: "New chat") { showingInvite = true }
                                .accessibilityIdentifier("home-start-conversation")
                        }.multilineTextAlignment(.center).frame(maxWidth:.infinity).padding(.vertical,60) }

                    }.padding(.horizontal, 20).padding(.vertical, 20).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }.clipped()
            }
            .navigationTitle("Chats").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    VipiMark(size:44,accessibleName:"Vipi")
                        .accessibilityValue(Text("Chats"))
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("inbox-wordmark")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { showingSettings = true } label: { Image(systemName: "person.crop.circle").font(.title3).frame(width: 44, height: 44) }
                        .accessibilityLabel("Your profile and settings")
                }
                if chat?.threads.isEmpty == false {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showingInvite = true } label: { Image(systemName: "square.and.pencil").font(.title3).frame(width: 44, height: 44) }
                            .accessibilityLabel("New chat")
                    }
                }
            }
            .navigationDestination(isPresented: $showingSettings) { SettingsView(chat: chat, subscriptions: subscriptions, closeBot: botOwner.close) }
            .sheet(isPresented: $showingInvite, onDismiss: { state.invitationUsername = nil }) {
                NewChatView(chat: chat, invitationUsername: state.invitationUsername) { peer in path.append(.friend(peer)) }
            }
            .onChange(of: state.invitationUsername, initial: true) { _, _ in presentInvitationIfReady() }
            .onChange(of: chat?.ready) { _, _ in
                presentInboxIfReady()
                presentInvitationIfReady()
            }
            .onChange(of: PushNotifications.shared.inboxPresentation, initial: true) { _, _ in presentInboxIfReady() }
            .navigationDestination(for: HomeDestination.self) { destination in
                switch destination {
                case .friend(let peer): if let chat { FriendConversationView(chat: chat, peer: peer) }
                }
            }
            .refreshable { await chat?.synchronize() }
        }
    }
    private func presentInvitationIfReady() {
        guard state.invitationUsername != nil, chat?.ready == true else { return }
        showingSettings = false
        offerBase = false
        path.removeAll()
        showingInvite = true
    }
    private func presentInboxIfReady() {
        guard chat?.ready == true, let request = PushNotifications.shared.inboxPresentation else { return }
        state.invitationUsername = nil
        showingInvite = false
        showingSettings = false
        offerBase = false
        query = ""
        path.removeAll()
        PushNotifications.shared.consumeInboxPresentation(request)
    }
}


struct HomeConversationRow:View {
    let name:String
    let thread:ChatThread
    let owner:ConversationImmersion?
    let expectedPair:TranslationPair
    @Environment(\.dynamicTypeSize) private var textSize
    private var date:Date { Date(timeIntervalSince1970:Double(thread.latest.createdAt)/1000) }
    private var dateText:String {
        if Calendar.current.isDateInToday(date) { return date.formatted(date:.omitted,time:.shortened) }
        if let days = Calendar.current.dateComponents([.day],from:Calendar.current.startOfDay(for:date),to:Calendar.current.startOfDay(for:Date())).day,(1...6).contains(days) {
            return date.formatted(.dateTime.weekday(.abbreviated))
        }
        if Calendar.current.component(.year,from:date) != Calendar.current.component(.year,from:Date()) { return date.formatted(.dateTime.year().month(.abbreviated).day()) }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }
    private var timestamp:some View {
        Text(dateText).font(.caption).foregroundStyle(thread.unread > 0 ? VipiDesign.highlight:VipiDesign.secondary)
            .lineLimit(1).accessibilityLabel(date.formatted(date:.complete,time:.shortened))
    }
    var body:some View {
        HStack(alignment:.center,spacing:14) {
            ContactAvatar(peer:thread.peer,name:name,size:46)
            VStack(alignment:.leading,spacing:5) {
                HStack(alignment:.firstTextBaseline,spacing:8) {
                    Text(name).font(.body.weight(thread.unread > 0 ? .semibold:.medium))
                        .foregroundStyle(VipiDesign.ink).lineLimit(textSize.isAccessibilitySize ? 2:1)
                        .layoutPriority(1)
                    Spacer(minLength:0)
                    if !textSize.isAccessibilitySize { timestamp.fixedSize(horizontal:true,vertical:false) }
                }
                if textSize.isAccessibilitySize { timestamp }
                HStack(alignment:.top,spacing:6) {
                    if thread.latest.outgoing {
                        MessageDeliveryMark(state:thread.latest.state)
                    }
                    HomeMessagePreview(owner:owner,message:thread.latest,expectedPair:expectedPair,unread:thread.unread > 0)
                        .frame(maxWidth:.infinity,alignment:.leading)
                    if thread.unread > 0 {
                        Text(thread.unread.formatted()).font(.caption.weight(.semibold)).monospacedDigit()
                            .foregroundStyle(VipiDesign.onHighlight).padding(.horizontal,7).frame(minWidth:24,minHeight:24)
                            .background(VipiDesign.highlight,in:Capsule())
                            .accessibilityLabel(String(localized:"\(thread.unread) unread messages"))
                    }
                }
            }
        }.padding(.vertical,14).contentShape(Rectangle())
            .accessibilityElement(children:.combine)
    }
}


/// A list row displays the same account-owned completed message as its chat.
/// Scroll visibility, rather than non-lazy VStack appearance, owns resident pins.
struct HomeMessagePreview: View {
    let owner: ConversationImmersion?
    let message: ChatItem
    let expectedPair: TranslationPair
    var unread = false
    var body: some View {
        Group {
            if let owner,owner.pair == expectedPair {
                let identity = owner.identity(messageID:message.id.uuidString,text:message.text)
                VisibleHomeMessagePreview(owner:owner,identity:identity).id(identity)
            } else {
                Text(message.text)
            }
        }.lineLimit(2).font(.subheadline.weight(unread ? .medium:.regular))
            .foregroundStyle(unread ? VipiDesign.ink:VipiDesign.secondary)
            .accessibilityIdentifier("chat-preview-"+message.id.uuidString.lowercased())
    }
}

private struct VisibleHomeMessagePreview: View {
    let owner: ConversationImmersion
    let identity: ImmersionRequestIdentity
    @State private var visible = false
    @State private var pinned = false
    private var displayed:String {
        guard let value = owner.translation(for:identity) else { return identity.text }
        if let guide = owner.reading(for:value) { return guide }
        return value.readingState?.status == .notNeeded ? value.practiceText : identity.text
    }
    private func releasePin() {
        if pinned { owner.releaseVisible(identity); pinned = false }
    }
    var body: some View {
        Text(displayed)
            .onScrollVisibilityChange(threshold:0.01) { onScreen in
                visible = onScreen
                if onScreen,!pinned { owner.retainVisible(identity); pinned = true }
                else if !onScreen { releasePin() }
            }
            .task(id:visible ? identity : nil) {
                guard visible else { return }
                _ = await owner.translatedMessage(for:identity)
            }
            .onDisappear { visible = false; releasePin() }
    }
}

struct NewChatView: View {
    var chat: ChatSession? = nil
    var invitationUsername: String? = nil
    var selected: (UUID) -> Void = { _ in }
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var error: String?
    @State private var busy = false
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Friend’s username", text: $username).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .onSubmit { findFriend() }
                } footer: { Text("Enter their exact Vipi username. Your phone contacts stay private.") }
                Section {
                    Button(action: findFriend) { if busy { ProgressView("Finding your friend") } else { Text("Find friend") } }
                        .disabled(username.trimmingCharacters(in: .whitespaces).isEmpty || busy)
                }
                if let profile = chat?.profile {
                    Section("Invite someone new") {
                        Text("Your username is @\(profile.username). Share it so your friend can find you after signing in.")
                            .font(.subheadline).textSelection(.enabled)
                        ShareLink(item: FriendInvitation.message(username: profile.username)) {
                            Label("Invite a friend", systemImage: "square.and.arrow.up")
                        }.accessibilityIdentifier("new-chat-invite-friend")
                    }
                }
                if let error { Section { Text(error).foregroundStyle(VipiDesign.secondary) } }
            }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("New conversation").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
                .onChange(of: invitationUsername, initial: true) { _, value in
                    if let value { username = value; error = nil }
                }
        }
    }
    private func findFriend() {
        guard !busy else { return }
        guard let chat else { error = String(localized: "Sign in to find your friends."); return }
        busy = true; error = nil
        Task {
            defer { busy = false }
            do { let person = try await chat.find(username); selected(person.id); dismiss() }
            catch { self.error = ChatSession.explanation(error) }
        }
    }
}

struct BotIntroductionView: View {
    var subscriptions: SubscriptionStore? = nil
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Image(systemName: "sparkle").font(.system(size: 44)).foregroundStyle(VipiDesign.highlight)
                IntroHeading(eyebrow: "Meet vBot", title: "Chat with\na chatbot.", detail: "Ask vBot a question or talk about your day. Read and hear the replies in the language you’re learning. vBot can make mistakes; check important details.")
                Text("vBot replies on supported devices using Apple Intelligence. Your messages stay on this device unless you choose to report a reply.")
                    .font(.body).foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                Text("No extra subscription. Availability and reply languages depend on your device.")
                    .font(.body).foregroundStyle(VipiDesign.secondary)
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.clipped().background(VipiDesign.canvas).navigationTitle("vBot").navigationBarTitleDisplayMode(.inline)
    }
}

struct SettingsView: View {
    var chat: ChatSession? = nil
    var subscriptions: SubscriptionStore? = nil
    var closeBot: () throws -> Void = {}
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    var body: some View {
        @Bindable var state = state
        Form {
            if let profile = chat?.profile {
                Section {
                    LabeledContent("Name") { Text(profile.display_name).foregroundStyle(VipiDesign.secondary) }
                    LabeledContent("Username") { Text("@" + profile.username).foregroundStyle(VipiDesign.secondary) }.textSelection(.enabled)
                    ShareLink(item: FriendInvitation.message(username: profile.username)) {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Image(systemName: "square.and.arrow.up").accessibilityHidden(true)
                            Text("Invite a friend").fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.body).multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }.accessibilityIdentifier("settings-invite-friend")
                } header: { Text("Your profile").foregroundStyle(VipiDesign.secondary) }
            }
            Section {
                NavigationLink { LanguageDownloadView() } label: {
                    LabeledContent("Languages") { Text(VipiLanguage.named(state.targetLanguage).localizedName).foregroundStyle(VipiDesign.secondary) }
                }.accessibilityIdentifier("language-settings-link")
            }
            Section {
                Picker("Immersion",selection:$state.immersionMode) {
                    ForEach(ImmersionMode.allCases) { Text($0.title).tag($0) }
                }.accessibilityIdentifier("settings-immersion-picker")
                Text(state.immersionMode == .fullMessages ? String(localized:"Every message appears in the language you’re learning.") : String(localized:"One new word at a time")).font(.footnote).foregroundStyle(VipiDesign.secondary)
            }
            Section {
                if chat != nil {
                    NavigationLink { NotificationSettingsView() } label: {
                        Text("Notifications").font(.body).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Picker("Appearance", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text(LocalizedStringKey($0.title)).tag($0) } }
            } header: { Text("Appearance and notifications").foregroundStyle(VipiDesign.secondary) }
            if let chat { Section { NavigationLink("Chat backup") { HistoryBackupView(chat: chat) } } }
            Section {
                Link("Privacy Policy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                Link("Terms of Service", destination: URL(string: "https://api.mambovipi.app/terms")!)
                Link("Help and safety", destination: URL(string: "https://api.mambovipi.app/help")!)
                NavigationLink("Licenses and notices") { NoticesView() }
                LabeledContent("Made by") {
                    Text(verbatim: "FallSoft.Co").foregroundStyle(VipiDesign.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("settings-maker-value")
                }
            } header: { Text("About Vipi").foregroundStyle(VipiDesign.secondary) }
            if let chat {
                Section {
                    if authentication.canLinkFallsoft {
                        VStack(alignment: .leading, spacing: 8) {
                            Button("Use your Fallsoft login") {
                                do {
                                    guard let userID = authentication.session?.userID else { throw AuthenticationManager.SessionFailure.signInRequired }
                                    let target = try chat.identityLinkTarget(expectedUser: userID)
                                    authentication.beginFallsoftLink(accountID: target.accountID, device: target.device)
                                } catch { authentication.errorMessage = String(localized: "Sign in to reconnect") }
                            }.disabled(authentication.busy || !chat.ready || chat.needsReauthentication || chat.userID != authentication.session?.userID)
                                .accessibilityIdentifier("fallsoft-link-start")
                            Text("Sign in to Vipi again, then connect your Fallsoft login. Your chats and profile stay with you.")
                                .font(.body).foregroundStyle(VipiDesign.secondary)
                            if let error = authentication.errorMessage { Text(error).font(.body).foregroundStyle(VipiDesign.secondary) }
                        }
                    }
                    NavigationLink("Delete Vipi account") { DeleteAccountView(chat: chat, closeBot: closeBot) }.foregroundStyle(VipiDesign.destructive)
                } header: { Text("Account").foregroundStyle(VipiDesign.secondary) }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("Settings")
        .toolbarBackground(VipiDesign.canvas, for: .navigationBar).toolbarBackground(.visible, for: .navigationBar).navigationBarTitleDisplayMode(.inline)
    }
}

struct ReauthenticationNotice: View {
    let busy: Bool
    let error: String?
    let signIn: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Sign in to reconnect").font(.headline)
            Text("Your saved conversations are still on this device.").font(.body)
            if let error { Text(error).font(.body) }
            Button("Sign in again", action: signIn)
                .disabled(busy).accessibilityIdentifier("chat-reauthenticate")
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
    }
}

/// The public invitation contains only the already public username.
enum FriendInvitation {
    static func message(username: String) -> String {
        let url = URL(string: "https://api.mambovipi.app/invite")!.appendingPathComponent(username)
        return String(localized: "Chat with me on Vipi and learn words as we talk. My username is @\(username). After signing in, choose New chat and find my username.\n\(url.absoluteString)")
    }
}
