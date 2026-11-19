import SwiftUI
import VipiCore

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
    @State private var path: [UUID] = []
    private var botDescription: String {
        guard let subscriptions, let access = subscriptions.snapshot?.bot_mini else { return String(localized: "Optional Bot mini plan") }
        if subscriptions.accessVerificationPending(.botMini) { return String(localized: "Chatbot access is being checked. Please try again later.") }
        if access.isReviewAccess { return String(localized: "Review access is active.") }
        if subscriptions.accessActive(.botMini) { return String(localized: "Active") }
        return String(localized: "Optional Bot mini plan")
    }
    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        if let chat, chat.needsReauthentication, let reauthenticate {
                            ReauthenticationNotice(busy: authenticationBusy || chat.busy, error: authenticationError, signIn: reauthenticate)
                        }
                        if let subscriptions, subscriptions.snapshot?.base.active == false, !subscriptions.accessVerificationPending(.base) {
                            Button { offerBase = true } label: {
                                Text("See your Vipi subscription").font(.subheadline.weight(.semibold))
                                    .frame(minHeight: 44, alignment: .leading).contentShape(Rectangle())
                            }
                        }
                        if let notice = chat?.notice { Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary) }
                        if let chat, !chat.threads.isEmpty {
                            ForEach(chat.threads) { thread in
                                NavigationLink(value: thread.peer) {
                                    HStack(spacing: 14) {
                                        Text(String(chat.name(thread.peer).prefix(1))).font(.title2)
                                            .frame(width: 48, height: 48).background(VipiDesign.outgoing, in: Circle())
                                        VStack(alignment: .leading, spacing: 5) {
                                            Text(chat.name(thread.peer)).fontWeight(thread.unread > 0 ? .semibold : .medium).foregroundStyle(.primary)
                                            HomeMessagePreview(owner:chat.translationOwner,message:thread.latest,expectedPair:.init(source:state.knownLanguage,target:state.targetLanguage))
                                        }
                                        Spacer(minLength: 4)
                                        if thread.unread > 0 { Text("\(thread.unread)").font(.caption.weight(.semibold)).padding(7).background(VipiDesign.outgoing, in: Circle()) }
                                    }.padding(.vertical, 8)
                                }.buttonStyle(.plain)
                                    .accessibilityIdentifier("chat-thread-"+thread.peer.uuidString.lowercased())
                            }
                        } else { VStack(alignment: .leading, spacing: 16) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Start a chat with a friend.").font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                                Text("Find a friend by username.").font(.body).foregroundStyle(VipiDesign.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            PrimaryButton(title: "New chat") { showingInvite = true }
                                .accessibilityIdentifier("home-start-conversation")
                        } }
                        NavigationLink {
                            if let profile = chat?.profile, let subscriptions {
                                BotConversationView(account: profile.id, subscriptions: subscriptions, owner: botOwner)
                            } else { BotIntroductionView(subscriptions: subscriptions) }
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "sparkle").font(.title2).frame(width: 48, height: 48).background(VipiDesign.outgoing, in: Circle())
                                VStack(alignment: .leading, spacing: 5) {
                                    Text("vBot").font(.body.weight(.semibold)).foregroundStyle(.primary)
                                    Text(botDescription).font(.body).foregroundStyle(VipiDesign.secondary).multilineTextAlignment(.leading)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(VipiDesign.secondary)
                            }.padding(.vertical, 12)
                        }.buttonStyle(.plain)
                        if let chat, chat.ready, !chat.threads.isEmpty, PushNotifications.shared.authorization == .notDetermined {
                            Button { Task { await PushNotifications.shared.enable() } } label: {
                                Text("Notify me when friends reply").font(.subheadline.weight(.semibold))
                                    .frame(minHeight: 44, alignment: .leading).contentShape(Rectangle())
                            }
                        }
                    }.padding(.horizontal, 20).padding(.vertical, 20).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }.clipped()
            }
            .navigationTitle("Chats").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showingSettings = true } label: { Image(systemName: "person.crop.circle").font(.title3).frame(width: 44, height: 44) }
                        .accessibilityLabel("Your profile and settings")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingInvite = true } label: { Image(systemName: "square.and.pencil").font(.title3).frame(width: 44, height: 44) }
                        .accessibilityLabel("New chat")
                }
            }
            .navigationDestination(isPresented: $showingSettings) { SettingsView(chat: chat, subscriptions: subscriptions, closeBot: botOwner.close) }
            .sheet(isPresented: $showingInvite) { NewChatView(chat: chat) { peer in path.append(peer) } }
            .navigationDestination(for: UUID.self) { peer in if let chat { FriendConversationView(chat: chat, peer: peer) } }
            .sheet(isPresented: $offerBase) {
                if let subscriptions { NavigationStack { SubscriptionOfferView(store: subscriptions, plan: .base)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Not now") { offerBase = false } } } } }
            }
            .onChange(of: subscriptions?.canPurchase(.base) == true, initial: true) { _, available in
                guard available, !offeredBase, chat?.threads.isEmpty == true,
                      let profile = chat?.profile else { return }
                let key = "vipi.base-offer-seen.\(profile.id.uuidString.lowercased())"
                guard !UserDefaults.standard.bool(forKey: key) else { return }
                UserDefaults.standard.set(true, forKey: key)
                offeredBase = true; offerBase = true
            }
            .refreshable { await chat?.synchronize(); await subscriptions?.refresh() }
        }
    }
}


/// A list row displays the same account-owned completed message as its chat.
/// Scroll visibility, rather than non-lazy VStack appearance, owns resident pins.
struct HomeMessagePreview: View {
    let owner: ConversationImmersion?
    let message: ChatItem
    let expectedPair: TranslationPair
    var body: some View {
        Group {
            if let owner,owner.pair == expectedPair {
                let identity = owner.identity(messageID:message.id.uuidString,text:message.text)
                VisibleHomeMessagePreview(owner:owner,identity:identity).id(identity)
            } else {
                Text("Translating…")
            }
        }.lineLimit(1).font(.body).foregroundStyle(VipiDesign.secondary)
            .accessibilityIdentifier("chat-preview-"+message.id.uuidString.lowercased())
    }
}

private struct VisibleHomeMessagePreview: View {
    let owner: ConversationImmersion
    let identity: ImmersionRequestIdentity
    @State private var visible = false
    @State private var pinned = false
    private var displayed:String {
        if let value = owner.translation(for:identity) {
            guard let readingState = value.readingState else { return String(localized:"Translating…") }
            switch readingState.status {
            case .available:
                return owner.reading(for:value) ?? String(localized:"Reading guide unavailable.")
            case .notNeeded:
                return value.practiceText
            case .unavailable:
                return String(localized:"Reading guide unavailable.")
            }
        }
        switch owner.phase(for:identity) {
        case .translating,.ready: return String(localized:"Translating…")
        case .needsDownload,.unsupported,.failed,.timedOut: return String(localized:"Translation unavailable")
        }
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
                Text("vBot is powered by DeepSeek. Messages in this conversation are sent to Vipi and DeepSeek to generate replies. Your conversations with friends are never included automatically.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                Text("Available with Bot mini").font(.subheadline.weight(.semibold))
                if let subscriptions {
                    NavigationLink("See Bot mini") { SubscriptionOfferView(store: subscriptions, plan: .botMini) }
                        .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                }
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
                if chat != nil {
                    NavigationLink { NotificationSettingsView() } label: {
                        Text("Notifications").font(.body).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Picker("Appearance", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text(LocalizedStringKey($0.title)).tag($0) } }
            } header: { Text("Appearance and notifications").foregroundStyle(VipiDesign.secondary) }
            if let subscriptions {
                Section {
                    NavigationLink { SubscriptionsView(store: subscriptions) } label: {
                        Text("Subscriptions").font(.body).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
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
                            Text("Sign in to Vipi again, then connect your Fallsoft login. Your chats, profile and original trial stay with you.")
                                .font(.footnote).foregroundStyle(VipiDesign.secondary)
                            if let error = authentication.errorMessage { Text(error).font(.footnote).foregroundStyle(VipiDesign.secondary) }
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
            Text("Your saved conversations are still on this device.").font(.footnote)
            if let error { Text(error).font(.footnote) }
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
