import SwiftUI

struct HomeView: View {
    var chat: ChatSession? = nil
    var subscriptions: SubscriptionStore? = nil
    @Environment(AppState.self) private var state
    @State private var showingSettings = false
    @State private var offerBase = false
    @State private var offeredBase = false
    @State private var showingInvite = false
    @State private var query = ""
    @State private var path: [UUID] = []
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
                            Text("Your world,\none conversation away.").font(.system(.title, design: .serif)).fixedSize(horizontal: false, vertical: true)
                            Text("Bring a friend. Make plans. Talk about your day. A little \(VipiLanguage.named(state.targetLanguage).name) will find its way in.")
                                .foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                            PrimaryButton(title: "Start a conversation") { showingInvite = true }
                        }.padding(26).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 28)) }
                        if let subscriptions, !subscriptions.baseActive {
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
                                    Text("A conversation whenever you feel like one.").font(.subheadline).foregroundStyle(VipiDesign.secondary).multilineTextAlignment(.leading)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(VipiDesign.secondary)
                            }.padding(.vertical, 12)
                        }.buttonStyle(.plain)
                    }.padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }
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
                IntroHeading(eyebrow: "Meet vBot", title: "Something\non your mind?", detail: "Talk about your day, follow a curiosity, or make a plan. vBot keeps the conversation going while your chosen language becomes more familiar.")
                Text("vBot is powered by DeepSeek. Messages in this conversation are sent to Vipi and DeepSeek to generate replies. Your conversations with friends are never included automatically.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                Text("Available with Bot mini").font(.subheadline.weight(.semibold))
                if let subscriptions {
                    NavigationLink("See Bot mini") { SubscriptionOfferView(store: subscriptions, plan: .botMini) }
                        .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight)
                }
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.background(VipiDesign.canvas).navigationTitle("vBot").navigationBarTitleDisplayMode(.inline)
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
                    ShareLink(item: "Find me on Vipi: @\(profile.username)\nhttps://mambovipi.app") {
                        Label("Invite a friend", systemImage: "square.and.arrow.up")
                    }
                }
            }
            Section("Your immersion") {
                NavigationLink { LanguageDownloadView() } label: {
                    LabeledContent("Languages", value: VipiLanguage.named(state.targetLanguage).name)
                }.accessibilityIdentifier("language-settings-link")
                VStack(alignment: .leading, spacing: 12) {
                    HStack { Text("A little or a little more"); Spacer(); Text("\(Int(state.density * 100))%").foregroundStyle(VipiDesign.secondary) }
                    Slider(value: $state.density, in: 0...0.75, step: 0.05).accessibilityLabel("Immersion amount")
                    Text("The amount of unfamiliar vocabulary you see. You can always reveal the original.").font(.footnote).foregroundStyle(VipiDesign.secondary)
                }.padding(.vertical, 8)
            }
            Section("Make yourself at home") {
                if chat != nil { NavigationLink("Notifications") { NotificationSettingsView() } }
                Picker("Appearance", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text($0.title).tag($0) } }
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
                Section("Account") { NavigationLink("Delete account") { DeleteAccountView(chat: chat) }.foregroundStyle(.red) }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("Your Vipi").navigationBarTitleDisplayMode(.inline)
    }
}
