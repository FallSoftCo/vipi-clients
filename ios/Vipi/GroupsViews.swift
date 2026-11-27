import SwiftUI

/// Existing group conversations and invitations when the authenticated relay supports them.
struct GroupsHomeView: View {
    let groups: GroupsSession
    let people: [ChatProfile]
    let chat: ChatSession
    let openCreatedGroup: (UUID) -> Void
    let reviewIdentity: (UUID) -> Void
    @State private var creating = false
    var body: some View {
        List {
            if let notice = groups.notice { Section { Text(notice).font(.body); Button("Try again") { Task { await groups.refresh() } } } }
            if !groups.invitations.isEmpty { Section("Invitations") {
                ForEach(groups.invitations) { invitation in
                    VStack(alignment: .leading, spacing: 12) {
                        Text(invitation.title).font(.headline)
                        Text("You’re invited to join. You’ll receive messages sent after you join; earlier messages stay private.").font(.body)
                        HStack {
                            Button("Join group") { Task { await groups.answer(invitation, accept: true) } }.buttonStyle(.borderedProminent)
                            Button("Decline") { Task { await groups.answer(invitation, accept: false) } }.buttonStyle(.bordered)
                        }.disabled(groups.busy)
                    }.padding(.vertical, 8)
                }
            } }
            Section {
                if groups.busy && !groups.loaded { ProgressView("Loading groups") }
                if groups.groups.isEmpty && !groups.busy {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("No groups yet").font(.title2.bold())
                            .modifier(ScreenSpot(asset: "SpotNewGroup"))
                        Text("Create a group for up to 16 people, including you. Everyone keeps their own language practice settings.").font(.body)
                    }.padding(.vertical, 18)
                }
                ForEach(groups.groups.sorted(by: { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending })) { group in
                    NavigationLink {
                        GroupConversationView(groups: groups, groupID: group.id, people: people, chat: chat, reviewIdentity: reviewIdentity)
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack { Text(group.title).font(.headline); ConversationStreakBadge(vault: groups.store.vault, scope: .group, id: group.id, revision: groups.revision); Spacer(); if GroupsUpgrade.muteDeliveryQualified && groups.preferences(group.id).muted { Image(systemName: "bell.slash").accessibilityLabel("Muted") } }
                            HStack {
                                Text("\(group.members.count) people").font(.body)
                                if groups.unread(group.id) > 0 { Text("\(groups.unread(group.id)) unread").font(.body.bold()).foregroundStyle(VipiDesign.accent) }
                            }
                        }.padding(.vertical, 6)
                    }
                }
            }
            if !groups.departedGroups.isEmpty { Section("Past groups") {
                ForEach(groups.departedGroups) { group in
                    NavigationLink { GroupConversationView(groups: groups, groupID: group.id, people: people, chat: chat, reviewIdentity: reviewIdentity) } label: {
                        VStack(alignment: .leading, spacing: 8) { HStack { Text(group.title).font(.headline); ConversationStreakBadge(vault: groups.store.vault, scope: .group, id: group.id, revision: groups.revision) }; Text("Left group · Messages saved here").font(.body) }
                    }
                }
            } }
        }.navigationTitle("Groups")
            .toolbar { ToolbarItem(placement: .primaryAction) { Button("New group", systemImage: "plus") { creating = true } } }
            .refreshable { await groups.refresh() }.task { await groups.refresh() }
            .sheet(isPresented: $creating) { NavigationStack { GroupCreateView(groups: groups, drafts: groups.store, people: people, onCreated: openCreatedGroup) } }
    }
}

struct GroupCreateView: View {
    let groups: GroupsSession?
    let drafts: GroupsStore
    let people: [ChatProfile]
    var onSaved: () -> Void = {}
    let onCreated: (UUID) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @FocusState private var editingName: Bool
    @State private var selected = Set<UUID>()
    @State private var created: UUID?
    @State private var selectionNotice: String?
    @State private var submitting = false
    @State private var loaded = false
    private var candidates: Set<UUID> { Set(people.map(\.id)).subtracting([drafts.vault.account]) }
    private var canCreate: Bool {
        loaded && !submitting && groups?.busy != true && (try? GroupSelection.name(title)) != nil
            && (groups == nil || !selected.isEmpty)
    }
    private var actionTitle: LocalizedStringKey {
        if groups == nil { return "Save draft" }
        if selected.isEmpty { return "Create group" }
        if created != nil { return "Retry remaining invitations" }
        return "Create group and invite \(selected.count)"
    }
    var body: some View {
        List {
            Section {
                TextField("For example, Weekend friends", text: $title)
                    .font(.body).disabled(created != nil).accessibilityIdentifier("group-name")
                    .focused($editingName)
            } header: {
                Text("Group name").modifier(ScreenSpot(asset: "SpotNewGroup", editing: editingName))
            }
            Section {
                if groups == nil { Text("Group chats are coming soon. You can save a draft on this phone.") }
                Text("Maximum 16 people").font(.body)
                Text("\(selected.count + 1) of 16 people selected, including you").font(.headline).accessibilityIdentifier("group-selection-count")
            } footer: {
                if groups != nil { Text("Message text is end-to-end encrypted. Vipi can see the group name, people and invitations.") }
            }
            GroupPeoplePicker(people: people, account: drafts.vault.account, selected: $selected, notice: $selectionNotice)
            if let notice = selectionNotice ?? groups?.notice { Section { Text(notice).font(.body).foregroundStyle(VipiDesign.destructive) } }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            Button { Task { await submit() } } label: {
                Text(actionTitle).font(.headline).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, minHeight: 30)
            }
            .buttonStyle(.borderedProminent).controlSize(.large)
            .disabled(!canCreate).accessibilityIdentifier("group-create")
            .padding(.horizontal, 20).padding(.vertical, 8)
            .background(.bar)
        }
        .navigationTitle("New group")
        .task(id: drafts.vault.account) {
            do {
                if let draft = try drafts.creationDraft() {
                    title = draft.title; selected = draft.selected.intersection(candidates); created = draft.groupID
                } else if let pending = groups?.pendingCreateTitle() { title = pending }
                loaded = true
            } catch { selectionNotice = GroupsSession.explanation(error) }
        }
        .onChange(of: candidates) { _, allowed in selected.formIntersection(allowed) }
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(submitting || groups?.busy == true) } }
    }
    private func submit() async {
        guard canCreate else { return }
        submitting = true
        defer { submitting = false }
        do {
            let name = try GroupSelection.name(title)
            let invitees = selected.intersection(candidates)
            guard let groups else {
                try drafts.saveCreationDraft(.init(title: name, selected: invitees, groupID: created))
                dismiss(); onSaved()
                return
            }
            guard !invitees.isEmpty else { return }
            var group = created.flatMap { groups.snapshot($0) }
            if group == nil { group = await groups.create(title: name, invitees: invitees, expected: created) }
            guard var current = group else { created = try drafts.creationDraft()?.groupID; return }
            created = current.id
            var remaining = invitees
            for id in invitees.sorted(by: { $0.uuidString < $1.uuidString }) {
                if !current.members.contains(where: { $0.id == id }) && !current.invitations.contains(where: { $0.user_id == id }) {
                    guard await groups.invite(current, person: id) else { selected = remaining; return }
                    current = groups.snapshot(current.id) ?? current
                }
                remaining.remove(id)
            }
            try drafts.clearCreationDraft(for: current.id)
            dismiss(); onCreated(current.id)
        } catch { selectionNotice = GroupsSession.explanation(error) }
    }
}

private struct GroupPeoplePicker: View {
    let people: [ChatProfile]
    let account: UUID
    var occupied = Set<UUID>()
    @Binding var selected: Set<UUID>
    @Binding var notice: String?
    @State private var search = ""
    private var matches: [ChatProfile] {
        people.filter { $0.id != account && !occupied.contains($0.id) && (search.isEmpty || $0.display_name.localizedCaseInsensitiveContains(search) || $0.username.localizedCaseInsensitiveContains(search)) }
            .sorted { $0.display_name.localizedCaseInsensitiveCompare($1.display_name) == .orderedAscending }
    }
    var body: some View {
        Section("People") {
            TextField("Search names or usernames", text: $search).textInputAutocapitalization(.never).autocorrectionDisabled().font(.body)
            if matches.isEmpty { Text(people.isEmpty ? "Add a friend before creating a group." : "No matching people. Try another name or username.").font(.body) }
            ForEach(matches) { person in
                Button {
                    do { selected = try GroupSelection.toggled(person.id, in: selected, account: account, occupied: occupied); notice = nil }
                    catch { notice = GroupsSession.explanation(error) }
                } label: {
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) { Text(person.display_name).font(.headline); Text("@" + person.username).font(.body).foregroundStyle(VipiDesign.secondary) }
                        Spacer(); Image(systemName: selected.contains(person.id) ? "checkmark.circle.fill" : "circle").font(.title2)
                    }.padding(.vertical, 6).frame(minHeight: 48)
                }.accessibilityLabel("\(person.display_name), @\(person.username)").accessibilityValue(selected.contains(person.id) ? "Selected" : "Not selected")
                    .accessibilityAddTraits(selected.contains(person.id) ? .isSelected : [])
            }
        }
    }
}

struct GroupConversationView: View {
    let groups: GroupsSession
    let groupID: UUID
    let people: [ChatProfile]
    let chat: ChatSession
    let reviewIdentity: (UUID) -> Void
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var text = ""
    @FocusState private var composing: Bool
    @State private var immersion: ConversationImmersion
    @State private var speech = SpeechPlayback()
    @State private var autoplay = ChatAutoplay()
    @State private var showInfo = false
    @State private var arrivalObserver: UUID?
    @State private var visibleMessages = Set<UUID>()
    @State private var actionDraft = MessageActionDraft()
    @State private var selectedActions: UUID?
    @State private var highlightedMessage: UUID?
    @State private var voiceHelp = false
    @State private var translationHelp: TranslationPair?
    private var group: GroupSnapshot? { groups.snapshot(groupID) }
    private var messages: [GroupMessage] { groups.messages(groupID) }
    @State private var headerViewport: CGFloat = 0
    private var conversationRef: ConversationRef { .group(groupID) }
    private var languageSelection: ConversationLanguageSelection {
        .init(source: state.knownLanguage,
              target: chat.targetLanguage(conversationRef),
              defaultTarget: chat.defaultTargetLanguage(),
              usesDefault: chat.usesDefaultLanguage(conversationRef),
              select: { chat.setConversationLanguage(conversationRef, target: $0) },
              useDefault: { chat.useDefaultConversationLanguage(conversationRef) })
    }
    @MainActor init(groups: GroupsSession, groupID: UUID, people: [ChatProfile], chat: ChatSession,
                    reviewIdentity: @escaping (UUID) -> Void) {
        self.groups = groups; self.groupID = groupID; self.people = people
        self.chat = chat; self.reviewIdentity = reviewIdentity
        _immersion = State(initialValue: chat.translationFor(.group(groupID)) ?? ConversationImmersion())
    }
    var body: some View {
        VStack(spacing: 0) {
            ChatRevealCue(reading: state.chatReading, vault: groups.store.vault, composing: composing)
            if let notice = groups.notice { VStack(alignment: .leading, spacing: 10) { Text(notice).font(.body); Button("Refresh group") { Task { await groups.refresh() } } }.padding().frame(maxWidth: .infinity, alignment: .leading).background(VipiDesign.surface) }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        if messages.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Your group starts here").font(.title2.bold())
                                Text("Say hello. Invited people can read new messages after they join. Your language practice settings apply only to you.").font(.body)
                            }.padding(.vertical, 24)
                        }
                        ForEach(groups.heldMessages(groupID), id: \.id) { item in
                            heldMessageRow(item)
                        }
                        ForEach(messages) { message in messageRow(message, proxy: proxy) }
                    }.padding(18).frame(maxWidth: VipiDesign.conversationWidth).frame(maxWidth: .infinity)
                }.scrollDismissesKeyboard(.interactively).background { ChatReadingGestureSurface(reading: state.chatReading) }
                    .onChange(of: messages.count) { old, _ in scrollToNewest(proxy, oldCount: old) }
            }
            VStack(spacing: 0) { conversationFooter }
                .frame(maxWidth: VipiDesign.conversationWidth).frame(maxWidth: .infinity)
        }
        .background(VipiDesign.canvas)
            .background { ConversationTranslationTask(immersion: immersion) }
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { headerViewport = $0 }
            .navigationTitle(group?.title ?? "Group").navigationBarTitleDisplayMode(.inline)
            .toolbar { groupToolbar }
            .sheet(isPresented: $showInfo) { if let group { NavigationStack { GroupInfoView(groups: groups, groupID: group.id, people: people, reviewIdentity: reviewIdentity) } } }
            .alert("Speech isn’t available", isPresented: $voiceHelp) { Button("OK", role: .cancel) {} } message: { Text("Check the voice for your practice language in language settings.") }
            .alert("Language download needed", isPresented: Binding(get: { translationHelp != nil }, set: { if !$0 { translationHelp = nil } })) { Button("OK", role: .cancel) { translationHelp = nil } } message: { Text("Open language settings to download the language used in this message.") }
            .task(id: "\(state.knownLanguage)-\(state.targetLanguage)-\(state.immersionMode.rawValue)-\(chat.translationGeneration)") {
                chat.activateConversation(conversationRef)
                await chat.configureTranslation(pair: .init(source: state.knownLanguage, target: state.targetLanguage),
                                                mode: state.immersionMode, services: state.translationServices)
                guard let owner = chat.translationFor(conversationRef) else { return }
                guard !Task.isCancelled else { return }
                immersion = owner
                immersion.warm(messages.map { (id: $0.renderID, text: $0.text) })
            }
            .task(id: languageSelection.target) {
                autoplay.stop(speech: speech)
                speech.close()
                let language = languageSelection.target
                speech.prepare(source: language, target: language, warmups: [language: VipiLanguage.named(language).localName])
            }
            .task {
                text = groups.preferences(groupID).draft
                actionDraft.restore(MessageComposerContext.saved(groups.store.vault, conversation: conversationRef.storageKey))
                arrivalObserver = groups.observe { message in
                    guard message.groupID == groupID else { return }
                    let id = message.id
                    autoplay.arrived(.init(id: message.renderID, load: { groups.messageOriginal(id, group: groupID) }), immersion: immersion, speech: speech, foreground: scenePhase == .active)
                }
                await groups.refresh()
            }
            .onChange(of: text) { _, value in groups.saveDraft(groupID, value) }
            .onChange(of: messages) { _, value in immersion.warm(value.map { (id: $0.renderID, text: $0.text) }) }
            .onChange(of: messages) { _, _ in if scenePhase == .active { groups.markRead(groupID, visible: visibleMessages) } }
            .onChange(of: scenePhase) { _, phase in if phase != .active { autoplay.stop(speech: speech); speech.stop() } else { groups.markRead(groupID, visible: visibleMessages) } }
            .onDisappear { if let arrivalObserver { groups.removeObserver(arrivalObserver) }; arrivalObserver = nil; autoplay.stop(speech: speech); speech.close(); state.chatReading.cancelInteractions() }
    }
    private func scrollToNewest(_ proxy: ScrollViewProxy, oldCount: Int) {
        guard oldCount == 0, let id = messages.last?.id else { return }
        proxy.scrollTo(id, anchor: .bottom)
    }
    @ViewBuilder private var conversationFooter: some View {
        if groups.isActive(groupID), group?.role(for: groups.account) != nil {
            MessageComposerContext(draft: actionDraft, text: text, name: authorName, vault: groups.store.vault, conversation: conversationRef.storageKey)
            groupComposer
        } else {
            Text("You’re no longer in this group. Saved messages remain on this device.")
                .font(.body).padding()
        }
    }
    @ViewBuilder private func heldMessageRow(_ item: GroupIncoming) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Message waiting for encryption review").font(.headline)
            Text("Confirm this sender’s encryption details to open their saved message. It is kept securely on this device.").font(.body)
            Button("Review sender’s encryption details") { reviewIdentity(item.sender_id) }
            Button("Try opening saved message") { groups.retryHeld(groupID) }
        }.padding(16).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
    }
    private var groupComposer: some View {
        HStack(alignment: .bottom, spacing: 12) {
            TextField("Message the group", text: $text, axis: .vertical)
                .focused($composing).font(.body).lineLimit(1...6).padding(12)
                .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 14))
                .accessibilityIdentifier("group-message-input")
            Button("Send") {
                Task {
                    guard let group else { return }
                    let draft = text
                    if await groups.send(group, text: draft, features: actionDraft.composed(draft)), text == draft { text = ""; actionDraft.reset() }
                }
            }
            .font(.headline).frame(minWidth: 52, minHeight: 48)
            .disabled(groups.busy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }.padding().background(VipiDesign.canvas)
    }
    @ToolbarContentBuilder private var groupToolbar: some ToolbarContent {
        ToolbarItem(placement: VipiDesign.hasNarrowPadToolbar(headerViewport) ? .topBarTrailing : .principal) {
            ConversationStreakReader(vault: groups.store.vault, scope: .group, id: groupID, revision: groups.revision) { count in
                ConversationHeaderActions(viewportWidth: headerViewport, mode: state.immersionMode, autoplay: autoplay.enabled,
                    toggleMode: toggleMode, toggleAutoplay: toggleAutoplay, language: languageSelection) { _ in
                    ConversationStreakLabel(count: count, scope: .group, headerName: group?.title ?? String(localized: "Group"))
                } options: {
                    Button { showInfo = true } label: {
                        Image(systemName: "person.3").resizable().scaledToFit()
                            .frame(width: 22, height: 20)
                            .frame(width: 44, height: 44).contentShape(Rectangle())
                    }
                    .accessibilityLabel("Group info")
                    .accessibilityIdentifier("conversation-group-info")
                }
            }
        }
    }
    private func toggleMode() {
        autoplay.stop(speech: speech)
        state.chatReading.cancelInteractions()
        state.immersionMode = state.immersionMode.next
    }
    private func toggleAutoplay() {
        state.chatReading.cancelPendingPlayback()
        autoplay.toggle(snapshot: messages.map { .init(id: $0.renderID, text: $0.text) },
                        immersion: immersion, speech: speech)
    }
    private func authorName(_ id: UUID) -> String {
        id == groups.account ? String(localized: "You") : (group?.members.first { $0.id == id }?.display_name ?? groups.savedSenderName(groupID, person: id) ?? String(localized: "Group member"))
    }
    private func startReply(_ message: GroupMessage) {
        guard message.delivery != .withheld else { return }
        actionDraft.reply = .quoting(id: message.id, sender: message.sender, text: message.text); composing = true
    }
    private func actionMetadata(_ message: GroupMessage) -> some View {
        let target = MessageActionTarget(id: message.id, sender: message.sender, quote: .quoting(id: message.id, sender: message.sender, text: message.text))
        let entries = (try? MessageReactions.entries(groups.store.vault, scope: .group, conversation: groupID, target: message.id, author: message.sender)) ?? []
        return MessageActionFooter(target: target, account: groups.account, entries: entries,
            allowReaction: groups.isActive(groupID) && [.accepted, .received].contains(message.delivery) &&
                group?.members.filter({ $0.id != groups.account }).allSatisfy({ $0.chat_features_version == 1 }) == true,
            metadataLabel: status(message), name: authorName, reply: { startReply(message) }, react: { emoji in
                guard let group else { throw GroupsFailure.notMember }
                _ = try await groups.sendReaction(group, target: message, emoji: emoji)
            }, selected: $selectedActions) { Text(status(message)).font(.caption).foregroundStyle(VipiDesign.secondary) }
    }
    @ViewBuilder private func decorations(_ message: GroupMessage, proxy: ScrollViewProxy) -> some View {
        if let reply = message.features?.reply {
            let original = messages.first { $0.id == reply.message_id && $0.sender == reply.sender_id && $0.delivery != .withheld }
            let cached = original.flatMap { immersion.cached($0.text, messageID: $0.renderID) }
            let text = (state.immersionMode == .fullMessages ? cached?.translation : cached?.speech(source: state.knownLanguage, target: state.targetLanguage).map(\.text).joined()) ?? original?.text ?? reply.excerpt
            Button {
                guard let original else { return }
                highlightedMessage = original.id; proxy.scrollTo(original.id, anchor: .center)
                Task { try? await Task.sleep(for: .seconds(1)); if highlightedMessage == original.id { highlightedMessage = nil } }
            } label: { ReplyExcerptView(author: authorName(reply.sender_id), excerpt: text) }.buttonStyle(.plain).disabled(original == nil)
        }
        if let preview = message.features?.link_preview, let url = URL(string: preview.url) {
            Link(destination: url) { EmbeddedLinkCard(preview: preview) }.buttonStyle(.plain)
        }
    }
    private func messageRow(_ message: GroupMessage, proxy: ScrollViewProxy) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(sender(message)).font(.headline).accessibilityAddTraits(.isHeader)
            if message.delivery == .withheld {
                if message.withheldReason == "changed" {
                    Text("The people in this group changed before this message arrived. Ask \(sender(message)) to send it again.").font(.body)
                    Button("Ask sender to resend") { text = "\(sender(message)), could you send your last message again?"; groups.saveDraft(groupID, text) }
                } else {
                    Text("An admin needs to confirm who’s in this group before this message can open. It is saved securely on this device.").font(.body)
                    Button("Review group approval") { showInfo = true }
                }
            } else {
            decorations(message, proxy: proxy)
            ConversationImmersionText(text: message.text, id: message.renderID, immersion: immersion, speech: speech,
                paused: scenePhase != .active, metadata: AnyView(actionMetadata(message)),
                onVoiceHelp: { voiceHelp = true }, onTranslationSetup: { translationHelp = $0 }, playback: autoplay,
                accessibilityMessageContext: sender(message) + ". " + status(message))
            }
            if message.sender == groups.account && [.queued, .failed].contains(message.delivery) {
                Button("Retry sending to everyone") { Task { await groups.retry(message) } }.font(.body).disabled(groups.busy)
            }
            if [.membershipChanged, .identityChanged].contains(message.delivery) {
                Text("This message wasn’t sent. Review Group info, then copy it into a new message when you’re ready.").font(.body)
                Button("Copy to draft") { text = message.text; groups.saveDraft(groupID, text) }
            }
        }.padding(14).frame(maxWidth: 600, alignment: .leading)
            .background(message.sender == groups.account ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 18))
            .modifier(MessageSwipeActions(reply: { startReply(message) }, actions: { if message.delivery != .withheld { selectedActions = message.id } }))
            .overlay { if highlightedMessage == message.id { RoundedRectangle(cornerRadius: 18).stroke(VipiDesign.focus, lineWidth: 2).allowsHitTesting(false) } }
            .id(message.id)
            .onScrollVisibilityChange(threshold: 0.5) { visible in
                if visible { visibleMessages.insert(message.id) } else { visibleMessages.remove(message.id) }
                if visible && scenePhase == .active { groups.markRead(groupID, visible: [message.id]) }
            }
    }
    private func sender(_ message: GroupMessage) -> String {
        if message.sender == groups.account { return "You" }
        return group?.members.first { $0.id == message.sender }?.display_name ?? people.first { $0.id == message.sender }?.display_name ?? groups.savedSenderName(groupID, person: message.sender) ?? "Group member"
    }
    private func status(_ message: GroupMessage) -> String {
        switch message.delivery {
        case .queued, .sending: return "Saved on this device · Waiting to send"
        case .accepted: return "Sent to the group"
        case .failed: return "Couldn’t send to everyone"
        case .expired: return "Not sent · Message expired"
        case .membershipChanged: return "Not sent · Group changed"
        case .identityChanged: return "Not sent · Encryption review needed"
        case .withheld: return "Held · Membership confirmation needed"
        case .received: return Date(timeIntervalSince1970: Double(message.createdAt) / 1000).formatted(date: .omitted, time: .shortened)
        }
    }
}

struct GroupInfoView: View {
    let groups: GroupsSession
    let groupID: UUID
    let people: [ChatProfile]
    let reviewIdentity: (UUID) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var adding = false
    @State private var confirmation: GroupConfirmation?
    @State private var bootstrap: GroupPendingControl?
    private var group: GroupSnapshot? { groups.snapshot(groupID) }
    var body: some View {
        List {
            if let group {
                if !groups.isActive(groupID) { Text("You’re no longer in this group. These people and roles describe the last saved roster. Your messages remain available here.").font(.body) }
                if groups.hasMembershipConflict(groupID) { Text("Conflicting encrypted group approvals were received. New messages are held. Ask an admin to resolve the group history or create a new group with confirmed identities.").font(.body) }
                if groups.hasRejectedApproval(groupID) { Section("An invalid group approval was blocked") {
                    Text("That approval couldn’t change who’s in this group. Your existing messages are still saved. Review the people and their encryption details before continuing.").font(.body)
                    Button("Dismiss this notice") { groups.dismissRejectedApproval(groupID) }
                } }
                if groups.pendingChanges(groupID) > 0 { Section("Saved group change") {
                    ForEach(groups.pendingDescriptions(groupID, people: people), id: \.self) { Text($0).font(.headline) }
                    Text("This change is waiting to be confirmed. Continue it before making another change or sending messages.").font(.body)
                    Button("Resume saved group change") { Task { await groups.resumePending(groupID) } }.disabled(groups.busy)
                } }
                Section("Group name") {
                    if groups.isActive(groupID) && group.canManage(groups.account) {
                        TextField("Group name", text: $name).font(.body)
                        Button("Save name") { Task { _ = await groups.rename(group, title: name) } }.disabled(groups.busy || name == group.title || (try? GroupSelection.name(name)) == nil)
                    } else { Text(group.title).font(.title2.bold()) }
                }
                Section {
                    if GroupsUpgrade.muteDeliveryQualified {
                        Toggle("Mute this group", isOn: Binding(get: { groups.preferences(groupID).muted }, set: { groups.setMuted(groupID, $0) })).font(.body)
                        Text("Muted groups keep unread counts. Your device won’t alert you about new messages from this group.").font(.body)
                    }
                    Text("Your language practice settings apply to you alone. Other people can practise different languages in the same conversation.").font(.body)
                }
                ForEach(groups.heldControls(groupID), id: \.id) { item in
                    Section("Group approval waiting for encryption review") {
                        Text("Confirm the inviter’s existing encryption details, then try opening the saved group approval.").font(.body)
                        Button("Review inviter’s encryption details") { reviewIdentity(item.sender_id) }
                        Button("Try opening group approval") { groups.retryHeld(groupID) }
                    }
                }
                ForEach(groups.pendingApprovals(groupID)) { control in
                    Section("Confirm group membership") {
                        Text("This approval came through an existing encrypted conversation. Review the inviter’s encryption details and everyone listed below before you confirm.").font(.body)
                        Button("Review inviter’s encryption details") { reviewIdentity(control.sender) }
                        ForEach(control.transition.members, id: \.user_id) { person in
                            let member = group.members.first { $0.id == person.user_id }
                            VStack(alignment: .leading, spacing: 6) {
                                Text(member?.display_name ?? "Group member").font(.headline)
                                Text((member.map { "@" + $0.username } ?? person.user_id.uuidString.lowercased()) + " · " + person.role.rawValue.capitalized).font(.body)
                            }
                        }
                        if groups.canBootstrap(control) { Button("Confirm these people") { bootstrap = control }.disabled(groups.busy) }
                        else { Text("An earlier group approval is missing. If its original sender is still in this group, ask them to resend it. If they’ve left or changed devices, start a new group after confirming everyone’s encryption details. These messages stay saved here.").font(.body) }
                    }
                }
                Section("People · \(group.members.count) of 16") {
                    ForEach(group.members) { member in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(member.display_name + (member.id == groups.account ? " (you)" : "")).font(.headline)
                            Text("@\(member.username) · \(member.role.rawValue.capitalized)").font(.body)
                            if member.id != groups.account { Button("Encryption details") { reviewIdentity(member.id) }.font(.body) }
                            if !groups.approved(groupID, person: member.id) && groups.isActive(groupID) && group.canManage(groups.account) && member.id != groups.account {
                                Text("This person joined, and an existing admin still needs to approve their membership securely.").font(.body)
                                Button("Approve this person") { confirmation = .init(title: "Approve \(member.display_name) for this group?", detail: "Confirm their encryption details first. Your approval will let everyone send them future group messages.", action: "Approve membership", suffix: "/approve/\(member.id.uuidString.lowercased())", method: "POST", fields: [:]) }
                            }
                            if groups.isActive(groupID) && group.role(for: groups.account) == .owner && member.id != groups.account {
                                Button(member.role == .admin ? "Remove admin role" : "Make admin") { confirmation = .init(title: member.role == .admin ? "Remove admin role?" : "Make \(member.display_name) an admin?", detail: "Admins can invite people, rename the group and remove members.", action: "Confirm role change", suffix: "/members/\(member.id.uuidString.lowercased())", method: "PATCH", fields: ["role": member.role == .admin ? "member" : "admin"]) }
                                Button("Transfer ownership") { confirmation = .init(title: "Make \(member.display_name) the owner?", detail: "They’ll manage admin roles and ownership. You’ll become an admin.", action: "Transfer ownership", suffix: "/members/\(member.id.uuidString.lowercased())", method: "PATCH", fields: ["role": "owner"]) }
                            }
                            if groups.isActive(groupID) && group.canRemove(groups.account, member.id) {
                                Button("Remove from group", role: .destructive) { confirmation = .init(title: "Remove \(member.display_name)?", detail: "They won’t receive future messages. Messages already delivered stay on their device.", action: "Remove person", suffix: "/members/\(member.id.uuidString.lowercased())", method: "DELETE", fields: [:]) }
                            }
                        }.padding(.vertical, 8)
                    }
                    if groups.isActive(groupID) && group.canManage(groups.account) { Button("Invite people") { adding = true }.disabled(group.members.count >= 16) }
                }
                if !group.invitations.isEmpty { Section("Pending invitations") {
                    ForEach(group.invitations) { invitation in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(people.first { $0.id == invitation.user_id }?.display_name ?? "Invited person").font(.headline)
                            Text("Waiting for them to accept").font(.body)
                            if groups.isActive(groupID) && group.canManage(groups.account) { Button("Cancel invitation", role: .destructive) { confirmation = .init(title: "Cancel this invitation?", detail: "This person won’t be able to join using this invitation.", action: "Cancel invitation", suffix: "/invitations/\(invitation.id.uuidString.lowercased())", method: "DELETE", fields: [:]) } }
                        }
                    }
                } }
                Section {
                    Text("Message text is end-to-end encrypted between current devices. Vipi can see the group name, people, roles and invitations. New members don’t receive earlier messages.").font(.body)
                    Text("Removing someone or leaving can’t erase copies already delivered. Blocking a person also leaves groups you share.").font(.body)
                    Button("Leave group", role: .destructive) { confirmation = .init(title: "Leave \(group.title)?", detail: group.role(for: groups.account) == .owner ? "Transfer ownership to another person first. After that, you can leave while keeping your saved messages on this device." : "You’ll stop receiving new messages. Your saved messages remain on this device.", action: "Leave group", suffix: "/leave", method: "POST", fields: [:]) }.disabled(!groups.isActive(groupID))
                }
                if let notice = groups.notice { Section { Text(notice).font(.body); Button("Refresh group") { Task { await groups.refresh() } } } }
            } else { Text("You’re no longer a member of this group.").font(.body) }
        }.navigationTitle("Group info").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task { name = group?.title ?? "" }
            .sheet(isPresented: $adding) { if let group { NavigationStack { GroupInviteView(groups: groups, groupID: group.id, people: people) } } }
            .alert(item: $confirmation) { action in Alert(title: Text(action.title), message: Text(action.detail), primaryButton: .destructive(Text(action.action)) {
                Task { guard let group else { return }; if action.suffix == "/leave" { if await groups.leave(group) { dismiss() } } else if action.suffix.hasPrefix("/approve/"), let person = UUID(uuidString: String(action.suffix.dropFirst("/approve/".count))) { await groups.approveJoin(group, person: person) } else { _ = await groups.change(group, method: action.method, suffix: action.suffix, fields: action.fields) } }
            }, secondaryButton: .cancel()) }
            .confirmationDialog("Trust this inviter and confirm this exact group?", isPresented: Binding(get: { bootstrap != nil }, set: { if !$0 { bootstrap = nil } }), titleVisibility: .visible) {
                Button("Confirm group membership") { if let bootstrap { groups.confirmBootstrap(bootstrap) }; bootstrap = nil }
                Button("Cancel", role: .cancel) { bootstrap = nil }
            } message: { Text("Only confirm after reviewing the inviter’s existing encryption details and the complete list of people above.") }
    }
}
private struct GroupConfirmation: Identifiable { let id = UUID(); let title: String; let detail: String; let action: String; let suffix: String; let method: String; let fields: [String: String] }
private struct GroupInviteView: View {
    let groups: GroupsSession; let groupID: UUID; let people: [ChatProfile]
    @Environment(\.dismiss) private var dismiss
    @State private var selected = Set<UUID>()
    @State private var notice: String?
    var body: some View {
        List {
            Text("People choose whether to join. They’ll only receive messages sent after they accept.").font(.body)
            if let group = groups.snapshot(groupID) {
                GroupPeoplePicker(people: people, account: groups.account, occupied: Set(group.members.filter { $0.id != groups.account }.map(\.id) + group.invitations.map(\.user_id)), selected: $selected, notice: $notice)
                if let message = notice ?? groups.notice { Text(message).font(.body) }
                Button("Invite \(selected.count) people") { Task {
                    for id in selected.sorted(by: { $0.uuidString < $1.uuidString }) {
                        guard let current = groups.snapshot(groupID), await groups.invite(current, person: id) else { return }
                        selected.remove(id)
                    }; dismiss()
                } }.font(.headline).disabled(groups.busy || selected.isEmpty)
            }
        }.navigationTitle("Invite people").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
    }
}
