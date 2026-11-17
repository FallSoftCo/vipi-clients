import SwiftUI

struct HomeView: View {
    var chat: ChatSession? = nil
    var subscriptions: SubscriptionStore? = nil
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
        guard let subscriptions, let access = subscriptions.snapshot?.bot_mini else { return String(localized: "Chat with a chatbot.") }
        if subscriptions.accessVerificationPending(.botMini) { return String(localized: "Chatbot access is being checked. Please try again later.") }
        if access.isReviewAccess { return String(localized: "Chat with a chatbot. Review access is active.") }
        if subscriptions.accessActive(.botMini) { return String(localized: "Chat with a chatbot. Bot mini access is active.") }
        return String(localized: "Chat with a chatbot. Requires the separate Bot mini plan.")
    }
    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        HStack {
                            Text("Chats").font(.system(.largeTitle, design: .serif).weight(.medium))
                            Spacer()
                            Button { showingInvite = true } label: { Image(systemName: "square.and.pencil").font(.title3).frame(width: 44, height: 44) }.accessibilityLabel("New chat")
                        }
                        if let chat, chat.needsReauthentication, let reauthenticate {
                            ReauthenticationNotice(busy: authenticationBusy || chat.busy, error: authenticationError, signIn: reauthenticate)
                        }
                        if let chat, !chat.threads.isEmpty {
                            ForEach(chat.threads) { thread in
                                NavigationLink(value: thread.peer) {
                                    HStack(spacing: 14) {
                                        Text(String(chat.name(thread.peer).prefix(1))).font(.title2)
                                            .frame(width: 48, height: 48).background(VipiDesign.outgoing, in: Circle())
                                        VStack(alignment: .leading, spacing: 5) {
                                            Text(chat.name(thread.peer)).fontWeight(thread.unread > 0 ? .semibold : .medium).foregroundStyle(.primary)
                                            Text(thread.latest.text).lineLimit(1).font(.subheadline).foregroundStyle(VipiDesign.secondary)
                                        }
                                        Spacer(minLength: 4)
                                        if thread.unread > 0 { Text("\(thread.unread)").font(.caption.weight(.semibold)).padding(7).background(VipiDesign.outgoing, in: Circle()) }
                                    }.padding(.vertical, 8)
                                }.buttonStyle(.plain)
                            }
                        } else { VStack(alignment: .leading, spacing: 16) {
                            VipiMark(size: 54)
                            Text("Start a chat\nwith a friend.").font(.system(.title, design: .serif)).fixedSize(horizontal: false, vertical: true)
                            Text("Find a friend by username and send a message. Supported words and phrases will switch into \(VipiLanguage.named(state.targetLanguage).localizedName) as you read.")
                                .foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                            PrimaryButton(title: "Start a conversation") { showingInvite = true }
                        }.padding(26).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 28)) }
                        if let subscriptions, subscriptions.snapshot?.base.active == false, !subscriptions.accessVerificationPending(.base) {
                            Button("See your Vipi subscription") { offerBase = true }
                                .font(.subheadline.weight(.semibold))
                        }
                        if chat != nil && PushNotifications.shared.authorization == .notDetermined {
                            Button("Notify me when friends reply") { Task { await PushNotifications.shared.enable() } }
                                .font(.subheadline.weight(.semibold))
                        }
                        if let notice = chat?.notice { Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary) }
                        NavigationLink {
                            if let profile = chat?.profile, let subscriptions {
                                BotConversationView(account: profile.id, subscriptions: subscriptions)
                            } else { BotIntroductionView(subscriptions: subscriptions) }
                        } label: {
                            HStack(spacing: 16) {
                                Image(systemName: "sparkle").font(.title2).frame(width: 50, height: 50).background(VipiDesign.outgoing, in: RoundedRectangle(cornerRadius: 18))
                                VStack(alignment: .leading, spacing: 5) {
                                    Text("vBot").font(.body.weight(.semibold)).foregroundStyle(.primary)
                                    Text(botDescription).font(.subheadline).foregroundStyle(VipiDesign.secondary).multilineTextAlignment(.leading)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(VipiDesign.secondary)
                            }.padding(.vertical, 12)
                        }.buttonStyle(.plain)
                    }.padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }.clipped()
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { VipiMark(size: 25).accessibilityLabel("Vipi") }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingSettings = true } label: { Image(systemName: "person.crop.circle").font(.title3) }.accessibilityLabel("Your profile and settings")
                }
            }
            .navigationDestination(isPresented: $showingSettings) { SettingsView(chat: chat, subscriptions: subscriptions) }
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
        guard let chat else { error = "Sign in to find your friends."; return }
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
                IntroHeading(eyebrow: "Meet vBot", title: "Chat with\na chatbot.", detail: "Ask vBot a question or talk about your day. Supported words switch into your chosen language as you read. vBot can make mistakes; check important details.")
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
    @Environment(AppState.self) private var state
    var body: some View {
        @Bindable var state = state
        Form {
            if let profile = chat?.profile {
                Section("Your profile") {
                    LabeledContent("Name", value: profile.display_name)
                    LabeledContent("Username", value: "@" + profile.username).textSelection(.enabled)
                    ShareLink(item: FriendInvitation.message(username: profile.username)) {
                        Label("Invite a friend", systemImage: "square.and.arrow.up")
                    }
                }
            }
            Section("Words in your chats") {
                NavigationLink { LanguageDownloadView() } label: {
                    LabeledContent("Languages", value: VipiLanguage.named(state.targetLanguage).localizedName)
                }.accessibilityIdentifier("language-settings-link")
                VStack(alignment: .leading, spacing: 12) {
                    HStack { Text("New words"); Spacer(); Text("\(Int(state.density * 100))%").foregroundStyle(VipiDesign.secondary) }
                    Slider(value: $state.density, in: 0...0.75, step: 0.05).accessibilityLabel("New words")
                    Text("Choose how many new words appear. Words you’ve seen can keep appearing too, so the total can grow. Set to 0% to turn word switching off.").font(.footnote).foregroundStyle(VipiDesign.secondary)
                }.padding(.vertical, 8)
            }
            Section("Appearance and notifications") {
                if chat != nil { NavigationLink("Notifications") { NotificationSettingsView() } }
                Picker("Appearance", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text(LocalizedStringKey($0.title)).tag($0) } }
            }
            if let subscriptions { Section { NavigationLink("Subscriptions") { SubscriptionsView(store: subscriptions) } } }
            if let chat { Section { NavigationLink("Chat backup") { HistoryBackupView(chat: chat) } } }
            Section("About Vipi") {
                Link("Privacy Policy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
                Link("Terms of Service", destination: URL(string: "https://api.mambovipi.app/terms")!)
                Link("Help and safety", destination: URL(string: "https://api.mambovipi.app/help")!)
                NavigationLink("Licenses and notices") { NoticesView() }
                LabeledContent("Made by", value: "FallSoft.Co")
            }
            if let chat {
                Section("Account") { NavigationLink("Delete account") { DeleteAccountView(chat: chat) }.foregroundStyle(VipiDesign.destructive) }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
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
