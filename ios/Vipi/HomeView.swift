import SwiftUI
import StoreKit
import VipiCore

private enum HomeDestination: Hashable { case friend(UUID), group(UUID) }

struct HomeView: View {
    var chat: ChatSession? = nil
    var subscriptions: SubscriptionStore? = nil
    var botOwner = BotConversationOwner()
    var reauthenticate: (() -> Void)? = nil
    var authenticationBusy = false
    var authenticationError: String? = nil
    @Environment(AppState.self) private var state
    @Environment(\.requestReview) private var requestReview
    @State private var breakAfterConversation = UUID()
    @State private var returnedToChats = false
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var choosingLanguage = false
    @State private var showingSettings = false
    @State private var offerBase = false
    @State private var offeredBase = false
    @State private var showingInvite = false
    @State private var showingAccount = false
    @State private var composeLabelWidth: CGFloat = 44
    @State private var query = ""
    @State private var path: [HomeDestination] = []
    @State private var inboxWidth: CGFloat = 0
    @State private var languageLabelWidth: CGFloat = 0
    @Environment(\.colorSchemeContrast) private var contrast

    private var languageName: String {
        let language = VipiLanguage.initial.first { $0.id == state.targetLanguage }
        let locale = Bundle.main.preferredLocalizations.first.map { Locale(identifier: $0) } ?? .current
        return language?.localizedName ?? locale.localizedString(forLanguageCode: state.targetLanguage) ?? state.targetLanguage
    }
    private var groupSession: GroupsSession? { chat?.groupComposeSession }
    private var languageFitsToolbar: Bool {
        guard !typeSize.isAccessibilitySize else { return false }
        // Balance both sides of the center against the widest set of actions.
        let flank: CGFloat = 64 + composeLabelWidth
        return inboxWidth == 0 || languageLabelWidth <= inboxWidth - 2 * flank
    }
    private var languageLabel: some View {
        HStack(spacing: 7) {
            Text(verbatim: languageName).font(.headline.weight(.bold))
                .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            Image(systemName: "chevron.down").font(.caption.weight(.bold))
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge).accessibilityHidden(true)
        }
        .foregroundStyle(VipiDesign.highlight)
        .padding(.horizontal, 16).padding(.vertical, 7)
        .background {
            Capsule().fill(VipiDesign.surface)
            Capsule().fill(VipiDesign.highlight.opacity(0.16))
        }
        .overlay {
            Capsule().strokeBorder(VipiDesign.highlight.opacity(contrast == .increased ? 1 : 0.45), lineWidth: 1)
        }
    }
    private var languageButton: some View {
        Button { choosingLanguage = true } label: {
            ViewThatFits(in: .horizontal) {
                languageLabel.fixedSize()
                languageLabel
            }
            .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text("I’m learning"))
        .accessibilityValue(Text(verbatim: languageName))
        .accessibilityIdentifier("inbox-practice-language")
    }
    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                ConversationWaterScene(mode: state.immersionMode, motionEnabled: state.animateConversationBackground, listSurface: true)
                    .ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        if let chat, chat.needsReauthentication, let reauthenticate {
                            ReauthenticationNotice(busy: authenticationBusy || chat.busy, error: authenticationError, signIn: reauthenticate)
                        }
                        if let notice = chat?.notice { Text(notice).font(.body).foregroundStyle(VipiDesign.secondary) }
                        if let chat, chat.showingFundingSurvey, chat.feedbackVault != nil {
                            FundingSurveyCard(choose: chat.chooseFundingResponse)
                        }
                        if let chat, !chat.threads.isEmpty {
                            LazyVStack(spacing:0) {
                                ForEach(chat.threads) { thread in
                                    let ref = ConversationRef.direct(thread.peer)
                                    NavigationLink(value: HomeDestination.friend(thread.peer)) {
                                        HomeConversationRow(vault:chat.feedbackVault, revision:chat.revision, jpeg:chat.avatar(thread.peer),name:chat.name(thread.peer),thread:thread,owner:chat.translationFor(ref),
                                            expectedPair:.init(source:state.knownLanguage,target:chat.targetLanguage(ref)))
                                    }.buttonStyle(.plain)
                                        .accessibilityIdentifier("chat-thread-"+thread.peer.uuidString.lowercased())
                                }
                            }
                        } else if chat == nil && state.guestMode { VStack(alignment: .center, spacing: 20) {
                            Image(systemName: "lock.shield").font(.system(size: 40)).foregroundStyle(VipiDesign.highlight).accessibilityHidden(true)
                            VStack(alignment: .center, spacing: 10) {
                                Group {
                                    if let username = state.invitationUsername {
                                        PendingFriendInvitation(username: username)
                                    } else {
                                        Text("Sign in to start chatting with friends.")
                                    }
                                }.font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                                Text("Friend and group chats are end-to-end encrypted with Signal Protocol.").font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal: false, vertical: true)
                            }
                            Button("Sign in") { showingAccount = true }.buttonStyle(.borderedProminent)
                                .foregroundStyle(VipiDesign.onHighlight).frame(minHeight: 48)
                                .accessibilityIdentifier("guest-sign-in")
                        }.multilineTextAlignment(.center).frame(maxWidth:.infinity).padding(.vertical,60)
                        } else { VStack(alignment: .center, spacing: 20) {
                            Image(systemName:"bubble.left.and.bubble.right").font(.system(size:40)).foregroundStyle(VipiDesign.secondary).accessibilityHidden(true)
                            VStack(alignment: .center, spacing: 8) {
                                Text("Find a friend by username or send them an invite.").font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                            }
                        }.multilineTextAlignment(.center).frame(maxWidth:.infinity).padding(.vertical,60) }

                    }.padding(.horizontal, 20).padding(.vertical, 20).frame(maxWidth: 680).frame(maxWidth: .infinity)
                }.clipped()
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { inboxWidth = $0 }
            .background {
                languageLabel.fixedSize().hidden().accessibilityHidden(true).allowsHitTesting(false)
                    .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { languageLabelWidth = $0 }
            }
            .safeAreaInset(edge: .top, spacing: 0) {
                if !languageFitsToolbar {
                    languageButton.padding(.horizontal, 16).padding(.bottom, 4).frame(maxWidth: .infinity)
                }
            }
            .navigationTitle("Chats").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    ZStack {
                        HStack(spacing: 0) {
                            VipiMark(size: 48, accessibleName: "Vipi")
                                .accessibilityValue(Text("Chats")).accessibilityAddTraits(.isHeader)
                                .accessibilityIdentifier("inbox-wordmark")
                            Spacer(minLength: 0)
                            Button { if chat == nil { showingAccount = true } else { showingInvite = true } } label: {
                                Text("New").font(.headline).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                                    .fixedSize().padding(.horizontal, 5)
                                    .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                            }
                            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { composeLabelWidth = $0 }
                            .accessibilityIdentifier("home-compose")
                            Button { showingSettings = true } label: {
                                Image(systemName: "person.crop.circle").frame(width: 44, height: 44)
                            }.accessibilityLabel("Your profile and settings")
                        }.font(.title3).foregroundStyle(VipiDesign.highlight)
                        if languageFitsToolbar { languageButton }
                    }
                    .frame(width: max(0, inboxWidth - 32), height: 44)
                    .buttonStyle(.plain)
                }
            }
            .navigationDestination(isPresented: $showingSettings) { SettingsView(chat: chat, subscriptions: subscriptions, closeBot: botOwner.close) }
            .sheet(isPresented: $choosingLanguage) {
                NavigationStack {
                    PracticeLanguagePicker()
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) {
                                Button("Cancel") { choosingLanguage = false }
                            }
                        }
                }
            }
            .sheet(isPresented: Binding(get: { showingInvite }, set: { presented in
                // Native Cancel or swipe dismisses this invitation. A session interruption leaves it pending.
                if !presented, chat?.ready == true, chat?.needsReauthentication == false { state.invitationUsername = nil }
                showingInvite = presented
            })) {
                NewChatView(chat: chat, invitationUsername: state.invitationUsername, groupCreated: openCreatedGroup) { peer in
                    if let username = state.invitationUsername, chat?.contacts[peer]?.username == username {
                        state.invitationUsername = nil
                    }
                    showingInvite = false
                    path.append(.friend(peer))
                }
            }
            .sheet(isPresented: $showingAccount) { OnboardingAccountSheet() }
            .onChange(of: groupSession?.account) { _, _ in
                if let index = path.firstIndex(where: { if case .group = $0 { true } else { false } }) {
                    path.removeSubrange(index...)
                }
            }
            .onChange(of: state.invitationUsername, initial: true) { _, _ in presentInvitationIfReady() }
            .onChange(of: chat?.ready == true && chat?.needsReauthentication == false) { _, ready in
                if ready {
                    if PushNotifications.shared.inboxPresentation != nil { presentInboxIfReady() }
                    else { presentInvitationIfReady() }
                }
            }
            .onChange(of: PushNotifications.shared.inboxPresentation, initial: true) { _, _ in presentInboxIfReady() }
            .navigationDestination(for: HomeDestination.self) { destination in
                switch destination {
                case .friend(let peer): if let chat { FriendConversationView(chat: chat, peer: peer) }
                case .group(let id):
                    if let chat, let groups = groupSession {
                        GroupConversationView(groups: groups, groupID: id, people: chat.groupCandidates, chat: chat) { peer in
                            path.append(.friend(peer))
                        }
                    }
                }
            }
            .refreshable { await chat?.synchronize() }
        }
        .overlay(alignment: .top) {
            if scenePhase == .active, let chat, let preview = chat.incomingPreview,
               chat.ready, !chat.needsReauthentication, !chat.changedIdentities.contains(preview.peer),
               !chat.blockedPeers.contains(preview.peer), path.last != .friend(preview.peer) {
                Button {
                    chat.clearPreview()
                    choosingLanguage = false
                    showingSettings = false
                    showingInvite = false
                    path = [.friend(preview.peer)]
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(chat.name(preview.peer)).font(.headline)
                        Text(verbatim: preview.text).font(.body).lineLimit(2)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
                }.buttonStyle(.plain)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal, 12).privacySensitive()
                    .accessibilityIdentifier("foreground-message-preview")
            }
        }
        .onChange(of: path) { old, new in
            if !new.isEmpty { chat?.dismissFundingCard() }
            returnedToChats = !old.isEmpty && new.isEmpty
            if returnedToChats { presentInvitationIfReady() }
            breakAfterConversation = UUID()
        }
        .onChange(of: showingInvite || showingSettings || choosingLanguage) { _, covering in
            if covering { chat?.dismissFundingCard() }
        }
        .task(id: breakAfterConversation) {
            guard returnedToChats, let chat else { return }
            try? await Task.sleep(for: .milliseconds(700))
            guard !Task.isCancelled, idleInChats else { return }
            await chat.reconcileFeedbackHistory()
            let intervention = await chat.considerChatIntervention { idleInChats }
            if intervention == .review { requestReview() }
            await chat.retryFundingResponse()
        }
        .task(id: chat?.ready) {
            await chat?.reconcileFeedbackHistory()
            await chat?.retryFundingResponse()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { chat?.clearPreview() }
            if phase == .background { returnedToChats = false; breakAfterConversation = UUID(); chat?.leftForeground() }
            if phase == .active { Task { await chat?.retryFundingResponse() } }
        }
        .task(id: chat?.incomingPreview?.id) {
            guard let chat, let preview = chat.incomingPreview else { return }
            if path.last == .friend(preview.peer) { chat.clearPreview(); return }
            try? await Task.sleep(for: .seconds(5))
            if !Task.isCancelled, chat.incomingPreview?.id == preview.id { chat.clearPreview() }
        }
    }
    private var idleInChats: Bool {
        returnedToChats && path.isEmpty && scenePhase == .active && !showingSettings && !showingInvite && !choosingLanguage
            && !offerBase && !authenticationBusy && chat?.busy == false && chat?.notice == nil && chat?.incomingPreview == nil
            && state.invitationUsername == nil && PushNotifications.shared.inboxPresentation == nil
    }
    private func openCreatedGroup(_ id: UUID) {
        showingInvite = false
        path.append(.group(id))
    }
    private func presentInvitationIfReady() {
        guard state.invitationUsername != nil, chat?.ready == true, chat?.needsReauthentication == false else { return }
        choosingLanguage = false
        showingSettings = false
        offerBase = false
        path.removeAll()
        showingInvite = true
    }
    private func presentInboxIfReady() {
        guard chat?.ready == true, let request = PushNotifications.shared.inboxPresentation else { return }
        showingInvite = false
        choosingLanguage = false
        showingSettings = false
        offerBase = false
        query = ""
        path = chat.flatMap { PushNotifications.shared.peerDestination(for: $0) }.map { [.friend($0)] } ?? []
        PushNotifications.shared.consumeInboxPresentation(request)
    }
}


struct HomeConversationRow:View {
    var vault: MessageVault? = nil
    var revision = 0
    var jpeg: Data? = nil
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
            ContactAvatar(peer:thread.peer,name:name,size:46,jpeg:jpeg)
            VStack(alignment:.leading,spacing:5) {
                HStack(alignment:.firstTextBaseline,spacing:8) {
                    Text(name).font(.body.weight(thread.unread > 0 ? .semibold:.medium))
                        .foregroundStyle(VipiDesign.ink).lineLimit(textSize.isAccessibilitySize ? 2:1)
                        .layoutPriority(1)
                    ConversationStreakBadge(vault: vault, scope: .direct, id: thread.peer, revision: revision)
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

private extension ChatSession {
    var groupComposeSession: GroupsSession? {
        guard ready, !needsReauthentication, translationOwner != nil else { return nil }
        return groups
    }
    var groupCandidates: [ChatProfile] { contacts.values.filter { !blockedPeers.contains($0.id) } }
}

private enum NewChatDestination: Hashable { case groupForm, directory }

struct NewChatView: View {
    var chat: ChatSession? = nil
    var invitationUsername: String? = nil
    var groupCreated: (UUID) -> Void
    var selected: (UUID) -> Void = { _ in }
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var error: String?
    @State private var busy = false
    @State private var lookup: Task<Void, Never>?
    @State private var showingInvitation = false
    @State private var path: [NewChatDestination] = []
    @State private var savedDraft = false
    @FocusState private var editingName: Bool

    var body: some View {
        NavigationStack(path: $path) {
            Form {
                if chat?.groupDraftStore != nil {
                    Section {
                        Button { savedDraft = false; path.append(.groupForm) } label: {
                            HStack(spacing: 12) {
                                Image(decorative: "SpotNewGroup").resizable().scaledToFit().frame(width: 44, height: 30)
                                Text("New group").font(.headline)
                            }.frame(minHeight: 44)
                        }.accessibilityIdentifier("new-chat-new-group")
                    } footer: {
                        if savedDraft { Text("Draft saved on this phone.").accessibilityIdentifier("group-draft-saved") }
                        if chat?.groupComposeSession != nil {
                            Button { path.append(.directory) } label: {
                                HStack(spacing: 5) {
                                    Text("Groups and invitations")
                                    Image(systemName: "chevron.forward").font(.caption.bold()).accessibilityHidden(true)
                                }.font(.subheadline.weight(.medium)).frame(minHeight: 44)
                            }.buttonStyle(.plain).foregroundStyle(VipiDesign.accent).accessibilityIdentifier("open-groups")
                        }
                    }
                }
                Section {
                    TextField("Name or @username", text: $username)
                        .accessibilityIdentifier("Friend’s username")
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .onSubmit { findFriend() }
                        .focused($editingName)
                    Button(action: findFriend) {
                        if busy { ProgressView("Finding your friend") } else { Text("Find friend") }
                    }.disabled(FriendLookupUsername.normalize(username) == nil || busy)
                } header: {
                    Text("Find friend looks up an exact Vipi username.")
                        .font(.footnote).textCase(nil).fixedSize(horizontal: false, vertical: true)
                        .modifier(ScreenSpot(asset: "SpotNewChat", editing: editingName))
                }
                if let chat, !chat.needsReauthentication, let account = chat.profile?.id {
                    let friends = chat.savedFriends(matching: username)
                    if !friends.isEmpty {
                        Section("Saved Vipi friends") {
                            ForEach(friends) { friend in
                                Button {
                                    guard let valid = chat.savedFriend(friend.id, account: account) else { return }
                                    selected(valid.id); dismiss()
                                } label: {
                                    HStack {
                                        ContactAvatar(peer: friend.id, name: friend.display_name, size: 38, jpeg: chat.avatar(friend.id))
                                        VStack(alignment: .leading) {
                                            Text(verbatim: friend.display_name).font(.headline)
                                            Text(verbatim: "@" + friend.username).font(.subheadline).foregroundStyle(.secondary)
                                        }
                                    }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                                }.accessibilityIdentifier("saved-vipi-friend-" + friend.id.uuidString.lowercased())
                            }
                        }
                    }
                    Section {
                        Button { showingInvitation = true } label: { Label("Invite a friend", systemImage: "person.badge.plus") }
                            .accessibilityIdentifier("new-chat-invite-friend")
                    }
                }
                if let error { Section { Text(error).foregroundStyle(VipiDesign.secondary) } }
            }
            .scrollContentBackground(.hidden).background(VipiDesign.canvas)
            .navigationTitle("New chat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .onChange(of: invitationUsername, initial: true) { _, value in
                if let value {
                    path.removeAll()
                    showingInvitation = false
                    username = value
                    error = nil
                }
            }
            .onChange(of: chat?.groupComposeSession?.account) { _, current in
                if current == nil, path.contains(.directory) { path.removeAll() }
            }
            .onChange(of: username) { _, _ in lookup?.cancel(); busy = false; error = nil }
            .onChange(of: chat?.profile?.id) { _, _ in lookup?.cancel(); showingInvitation = false; dismiss() }
            .onChange(of: chat?.needsReauthentication) { _, expired in
                if expired == true { lookup?.cancel(); showingInvitation = false; dismiss() }
            }
            .onDisappear { lookup?.cancel() }
            .navigationDestination(for: NewChatDestination.self) { destination in
                switch destination {
                case .groupForm:
                    if let chat, let drafts = chat.groupDraftStore {
                        GroupCreateView(groups: chat.groupComposeSession, drafts: drafts, people: chat.groupCandidates,
                                        onSaved: { savedDraft = true }, onCreated: groupCreated)
                            .navigationBarBackButtonHidden()
                    }
                case .directory:
                    if let chat, let groups = chat.groupComposeSession {
                        GroupsHomeView(groups: groups, people: chat.groupCandidates, chat: chat, openCreatedGroup: groupCreated) { peer in selected(peer); dismiss() }
                    }
                }
            }
            .sheet(isPresented: $showingInvitation) {
                if let profile = chat?.profile {
                    FriendInviteView(username: profile.username).id(profile.id)
                }
            }
        }
    }
    private func findFriend() {
        guard !busy else { return }
        guard let chat, let account = chat.profile?.id else { error = String(localized: "Sign in to find your friends."); return }
        guard let normalized = FriendLookupUsername.normalize(username) else { return }
        if let saved = chat.savedFriends(matching: "@" + normalized).first(where: { $0.username == normalized }) {
            selected(saved.id); dismiss(); return
        }
        busy = true; error = nil
        lookup = Task {
            defer { if !Task.isCancelled { busy = false } }
            do {
                let person = try await chat.find(normalized)
                guard !Task.isCancelled, chat.savedFriend(person.id, account: account) != nil else { return }
                selected(person.id); dismiss()
            } catch { if !Task.isCancelled { self.error = ChatSession.explanation(error) } }
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

private struct PrivacyPromiseMark: View {
    let maxWidth: CGFloat
    var body: some View {
        Image("PrivacyMarkFull")
            .resizable().scaledToFit()
            .frame(maxWidth: maxWidth)
            .accessibilityLabel("Certified Zucker Free, FallSoft’s privacy mark")
            .frame(maxWidth: .infinity)
    }
}

struct PrivacyPromiseView: View {
    static let policy = URL(string: "https://mambovipi.app/privacy.html")!
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(spacing: 6) {
                    PrivacyPromiseMark(maxWidth: 392)
                    Text("FallSoft’s privacy promise").font(.subheadline.weight(.semibold))
                        .foregroundStyle(VipiDesign.secondary).multilineTextAlignment(.center)
                }
                Text("We don’t sell your chat content.")
                    .font(.title2.bold()).accessibilityAddTraits(.isHeader)
                Text("Phone contacts stay on this device. Vipi saves your Vipi friends separately.")
                Link("Privacy Policy", destination: Self.policy).frame(minHeight: 44)
            }
            .frame(maxWidth: 560, alignment: .leading).padding(24)
            .frame(maxWidth: .infinity)
        }
        .background(VipiDesign.canvas).foregroundStyle(VipiDesign.ink)
        .navigationTitle("Privacy").navigationBarTitleDisplayMode(.inline)
    }
}

struct SettingsView: View {
    @State private var showingPrivacy = false
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
                    HStack(spacing: 14) {
                        ContactAvatar(peer: profile.id, name: profile.display_name, size: 52, jpeg: chat?.avatar(profile.id))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(profile.display_name).font(.headline)
                            Text("@" + profile.username).font(.subheadline).foregroundStyle(VipiDesign.secondary).textSelection(.enabled)
                        }
                    }.padding(.vertical, 5)
                    .modifier(ScreenSpot(asset: "SpotSettings"))
                    if let chat { AvatarEditor(chat: chat, account: profile.id) }
                    ShareLink(item: FriendInvitation.message(username: profile.username)) {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Image(systemName: "square.and.arrow.up").accessibilityHidden(true)
                            Text("Invite a friend").fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.body).multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }.accessibilityIdentifier("settings-invite-friend")
                }
            }
            Section {
                NavigationLink { LanguageDownloadView() } label: {
                    LabeledContent("Languages") { Text(VipiLanguage.named(state.targetLanguage).localizedName).foregroundStyle(VipiDesign.secondary) }
                }.accessibilityIdentifier("language-settings-link")
                NavigationLink { NativeHelpView() } label: { Text("help_title", tableName: "NativeHelp") }.accessibilityIdentifier("settings-help")
                Picker("Immersion",selection:$state.immersionMode) {
                    ForEach(ImmersionMode.allCases) { Text($0.title).tag($0) }
                }.accessibilityIdentifier("settings-immersion-picker")
                if let chat { NavigationLink("Chat backup") { HistoryBackupView(chat: chat) } }
            } header: {
                if chat?.profile == nil {
                    Text("Your chats").modifier(ScreenSpot(asset: "SpotSettings"))
                } else { Text("Your chats") }
            }
            Section {
                Picker("Theme", selection: $state.appearance) { ForEach(AppAppearance.allCases) { Text(LocalizedStringKey($0.title)).tag($0) } }
                Toggle("Animate conversation background", isOn: $state.animateConversationBackground)
                    .accessibilityIdentifier("settings-conversation-motion")
            } header: { Text("Appearance") }
            if let chat {
                Section {
                    NavigationLink("Notifications") { NotificationSettingsView(chat: chat) }
                }
            }
            Section("Privacy") {
                Button { showingPrivacy = true } label: {
                    VStack(spacing: 8) {
                        PrivacyPromiseMark(maxWidth: 304).accessibilityHidden(true)
                        HStack(spacing: 6) {
                            Text("FallSoft’s privacy promise").font(.headline)
                                .multilineTextAlignment(.center)
                            Image(systemName: "chevron.forward").font(.caption.bold())
                                .dynamicTypeSize(...DynamicTypeSize.xxxLarge).accessibilityHidden(true)
                        }
                    }
                    .padding(.vertical, 10).frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityValue("Certified Zucker Free, FallSoft’s privacy mark")
                .accessibilityIdentifier("settings-privacy-promise")
            }
            Section {
                Link("Terms of Service", destination: URL(string: "https://mambovipi.app/terms.html")!)
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
                                .font(.footnote).foregroundStyle(VipiDesign.secondary)
                            if let error = authentication.errorMessage { Text(error).font(.body).foregroundStyle(VipiDesign.secondary) }
                        }
                    }
                    NavigationLink("Delete Vipi account") { DeleteAccountView(chat: chat, closeBot: closeBot) }.foregroundStyle(VipiDesign.destructive)
                } header: { Text("Account").foregroundStyle(VipiDesign.secondary) }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("Settings")
        .navigationDestination(isPresented: $showingPrivacy) { PrivacyPromiseView() }
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
