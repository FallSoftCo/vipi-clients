import SwiftUI
import AVFoundation

struct FriendConversationView: View {
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var immersion: ConversationImmersion
    @State private var speech = SpeechPlayback()
    @State private var voice = InlineVoiceComposer()
    @State private var autoplay = ChatAutoplay()
    @State private var messageObserver: UUID?
    let chat: ChatSession
    let peer: UUID
    private let usesAppTranslationServices: Bool
    @State private var messages: [ChatItem] = []
    @State private var actionDraft = MessageActionDraft()
    @State private var selectedActions: UUID?
    @State private var highlightedMessage: UUID?
    @State private var quoteJump: Task<Void, Never>?
    @State private var supportsReactions = false
    @State private var text = ""
    @State private var error: String?
    @State private var earlierAvailable = false
    @State private var loaded = false
    @State private var confirmBlock = false
    @State private var blockBusy = false
    @State private var showSecurityNumber = false
    @State private var showVoiceHelp = false
    @State private var showTranslationHelp = false
    @State private var translationHelpPair: TranslationPair?
    @State private var showMessageStatus = false
    @State private var reporting: HumanReportSelection?
    @State private var choosingReport = false
    @State private var copyOriginal = CopyOriginalContext(editorID:"message-input")
    @State private var chosenReportMessage: ChatItem?
    @State private var followingLatest = true
    @State private var conversationActive = false
    @State private var unseenIncoming = Set<UUID>()
    @State private var messageFrames:[UUID:CGRect] = [:]
    @State private var timelineFrame = CGRect.zero
    @State private var composerFrame = CGRect.zero
    @State private var peerTypingFrame = CGRect.zero
    @State private var viewportTopInset:CGFloat = 0
    @State private var viewportContainerHeight:CGFloat = 0
    @State private var reportedIncoming = Set<UUID>()
    @State private var reportedOutgoing = Set<UUID>()
    @State private var notificationInvitation = false
    @State private var notificationTask:Task<Void,Never>?
    @State private var restoreNotificationFocus = false
    @Environment(\.openURL) private var openURL
    @State private var scrolling = false
    @State private var userScrolling = false
    @State private var position = ScrollPosition(idType: UUID.self, edge: .bottom)
    @State private var jumpRevision = 0
    @State private var firstMessageFrame = CGRect.zero
    @State private var viewportHeight: CGFloat = 0
    @State private var viewportBottomInset: CGFloat = 0
    @State private var viewportLeadingInset: CGFloat = 0
    @State private var latestScrollY: CGFloat = 0
    @State private var scrollOffset: CGFloat = 0
    private struct ModeReadingAnchor {
        let message: UUID
        let top: CGFloat
        let mode: ImmersionMode
        let visibleIDs: Set<UUID>
    }
    @State private var modeAnchor: ModeReadingAnchor?
    @State private var modeAnchorTask: Task<Void,Never>?
    @State private var pageAnchorID: UUID?
    @State private var pageAnchorFrame = CGRect.zero
    @State private var pageRestore: Task<Void, Never>?
    @State private var viewportRestore: Task<Void, Never>?
    @State private var textSizeRestore: Task<Void, Never>?
    @State private var textSizeAnchorID: UUID?
    @State private var textSizeAnchorFrame = CGRect.zero
    private var blocked: Bool { chat.blockedPeers.contains(peer) }
    private var canReportVisible:Bool {
        conversationActive && scenePhase == .active && !copyOriginal.presented && !showSecurityNumber && !showVoiceHelp && !showTranslationHelp && !showMessageStatus && !choosingReport && reporting == nil && !confirmBlock
    }
    private var visibleTimeline:CGRect {
        ChatMessageVisibility.viewport(frame:timelineFrame,containerHeight:viewportContainerHeight,
            topInset:viewportTopInset,bottomInset:viewportBottomInset,composer:composerFrame)
    }
    private func reportVisibleMessages() {
        #if DEBUG
        LiveImmersionQualification.recordCurrentMessageViewport(visibleTimeline)
        LiveImmersionQualification.recordCurrentMessageRows(messageFrames)
        #endif
        var incoming = Set<UUID>(),outgoing = Set<UUID>()
        if canReportVisible {
            let viewport = visibleTimeline
            for item in messages where item.state != "imported" {
                guard let frame = messageFrames[item.id],frame.height > 0 else { continue }
                guard ChatMessageVisibility.containsReadableMessage(frame,in:viewport) else { continue }
                if item.outgoing { outgoing.insert(item.id) } else { incoming.insert(item.id) }
            }
        }
        guard incoming != reportedIncoming || outgoing != reportedOutgoing else { return }
        reportedIncoming = incoming; reportedOutgoing = outgoing
        chat.visibleMessages(peer,incoming:incoming.sorted{$0.uuidString < $1.uuidString},outgoing:outgoing.sorted{$0.uuidString < $1.uuidString})
        #if DEBUG
        LiveImmersionQualification.recordFullMessageGeometry(["event":"full_message_visible_geometry","viewport":LiveImmersionQualification.frameFields(visibleTimeline),
            "incoming":incoming.map{$0.uuidString.lowercased()}.sorted(),"outgoing":outgoing.map{$0.uuidString.lowercased()}.sorted(),"foreground":canReportVisible])
        #endif
    }
    private func clearConversationActivity() {
        chat.composerActivity(peer,active:false)
        reportedIncoming.removeAll(); reportedOutgoing.removeAll()
        chat.visibleMessages(peer,incoming:[],outgoing:[])
    }
    private func offerReplyNotificationsAfterSend() {
        notificationTask?.cancel()
        notificationTask = Task { @MainActor in
            await PushNotifications.shared.refresh()
            guard !Task.isCancelled,conversationActive,scenePhase == .active,chat.claimReplyNotificationInvitation() else { return }
            let notifications = PushNotifications.shared
            // An existing grant or an explicit app-level opt-out consumes this
            // one account invitation quietly; neither gets another solicitation.
            guard notifications.enabled,notifications.authorization == .notDetermined || notifications.authorization == .denied else { return }
            notificationInvitation = true
        }
    }
    private func enableReplyNotifications() {
        let notifications = PushNotifications.shared
        notificationInvitation = false
        if notifications.authorization == .denied {
            if let url = URL(string:UIApplication.openNotificationSettingsURLString) { openURL(url) }
        } else {
            restoreNotificationFocus = composing
            notificationTask = Task { @MainActor in
                await notifications.enable()
                guard !Task.isCancelled,conversationActive else { return }
                if scenePhase == .active,restoreNotificationFocus { composing = true; restoreNotificationFocus = false }
            }
        }
    }
    private var messageNotice: String? {
        let notices = [chat.notice, error].compactMap { $0 }.filter { !$0.isEmpty }
        var distinct: [String] = []
        for notice in notices where !distinct.contains(notice) { distinct.append(notice) }
        return distinct.isEmpty ? nil : distinct.joined(separator: "\n\n")
    }
    @State private var rejectedDraftEdit = false
    private var messageTooLong: Bool { text.utf8.count > 32768 }
    @State private var headerViewport: CGFloat = 0
    private var conversationRef: ConversationRef { .direct(peer) }
    private var languageSelection: ConversationLanguageSelection {
        return .init(source: state.knownLanguage,
                     target: chat.usesDefaultLanguage(conversationRef) ? state.targetLanguage : chat.targetLanguage(conversationRef),
                     defaultTarget: state.targetLanguage,
                     usesDefault: chat.usesDefaultLanguage(conversationRef),
                     select: { chat.setConversationLanguage(conversationRef, target: $0) },
                     useDefault: { chat.useDefaultConversationLanguage(conversationRef) })
    }
    private var editableDraft: Binding<String> { Binding(get: { text }, set: { value in
        guard loaded else { return }
        guard value.utf8.count <= ConversationHistory.maximumDraftBytes else { rejectedDraftEdit = true; return }
        guard value != text else { return }
        rejectedDraftEdit = false; text = value
        chat.composerActivity(peer,active:composing && scenePhase == .active && !value.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
    }) }
    private var canSend: Bool { loaded && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && text.utf8.count <= 32768 }
    @State private var composing = false
    init(chat: ChatSession, peer: UUID, immersion: ConversationImmersion? = nil) {
        self.chat = chat; self.peer = peer; usesAppTranslationServices = immersion == nil
        _immersion = State(initialValue: immersion ?? ConversationImmersion())
    }
    private func captureModeAnchor(for mode: ImmersionMode) {
        modeAnchorTask?.cancel(); modeAnchorTask = nil; modeAnchor = nil
        #if DEBUG
        LiveImmersionQualification.record(["event":"mode_switch","next":mode.rawValue,
            "following_latest":followingLatest,"composing":composing,"count":messages.count,
            "offset":Double(scrollOffset),"bottom_inset":Double(viewportBottomInset)])
        #endif
        if followingLatest {
            viewportRestore?.cancel(); viewportRestore = nil
            // Keep the existing visual position while the new face measures.
            // The size-change anchor and an explicit scroll cannot both own
            // this resize without applying the keyboard inset twice.
            return
        }
        guard !scrolling, pageRestore == nil, textSizeRestore == nil else { return }
        let viewport = visibleTimeline
        let visible = messageFrames.filter { $0.value.intersects(viewport) }
        guard let first = visible.min(by:{ $0.value.minY < $1.value.minY }) else { return }
        modeAnchor = .init(message:first.key, top:first.value.minY - viewport.minY,
                           mode:mode, visibleIDs:Set(visible.keys))
    }
    private func settleModeAnchor() {
        guard modeAnchor != nil, modeAnchorTask == nil else { return }
        modeAnchorTask = Task { @MainActor in
            // Read all updated lazy-row frames from the same layout pass.
            do { try await Task.sleep(for:.milliseconds(16)) } catch { return }
            modeAnchorTask = nil
            guard let anchor = modeAnchor, !followingLatest, !userScrolling, !copyOriginal.holdingLayout,
                  immersion.mode == anchor.mode, let row = messageFrames[anchor.message] else { return }
            let delta = row.minY - visibleTimeline.minY - anchor.top
            if abs(delta) > 0.5 {
                scrollVertically(to:scrollOffset + delta)
            } else if messages.lazy.filter({ anchor.visibleIDs.contains($0.id) }).allSatisfy({
                immersion.phase(for:immersion.identity(messageID:$0.id.uuidString,text:$0.text)) != .translating
            }) {
                modeAnchor = nil
            }
        }
    }
    private func cancelPageRestoration() {
        modeAnchorTask?.cancel(); modeAnchorTask = nil; modeAnchor = nil
        pageRestore?.cancel(); pageRestore = nil; pageAnchorID = nil
    }
    private func scrollVertically(to y: CGFloat) {
        // Keyboard resizing can make the y-only overload choose x = 0 even
        // while the measured scroll content still has a horizontal inset.
        // Preserve that inset explicitly when restoring a vertical position.
        // ScrollPosition points start at content origin, while UIKit geometry
        // reports contentOffset with the top inset subtracted. Convert once.
        position.scrollTo(x: -viewportLeadingInset, y: y + viewportTopInset)
    }
    private func settleMeasuredLatest() {
        guard followingLatest,!scrolling,!copyOriginal.holdingLayout,textSizeRestore == nil else { return }
        viewportRestore?.cancel()
        viewportRestore = Task { @MainActor in
            do { try await Task.sleep(for:.milliseconds(80)) } catch { return }
            guard followingLatest,!scrolling,!copyOriginal.holdingLayout else { return }
            scrollToLatest("measured_latest_row")
            viewportRestore = nil
        }
    }
    private var measuredLatestScrollY:CGFloat {
        guard let last = messages.last,let frame = messageFrames[last.id],frame.height > 0,visibleTimeline.height > 0 else { return latestScrollY }
        let bottom = chat.isPeerTyping(peer) && peerTypingFrame.height > 0 ? max(frame.maxY,peerTypingFrame.maxY):frame.maxY
        // Match real clipped global coordinates, after lazy row measurement.
        // A short conversation stays at its natural top rather than overscrolling.
        // Lazy rows can briefly report a global frame outside the current
        // content extent. Never command an impossible offset from that estimate.
        let desired = scrollOffset + bottom - (visibleTimeline.maxY-18)
        return min(latestScrollY,max(-viewportTopInset,desired))
    }
    private func scrollToLatest(_ reason: String) {
        guard !copyOriginal.holdingLayout else { return }
        let target = measuredLatestScrollY
        guard abs(scrollOffset-target) > 0.5 else { return }
        #if DEBUG
        LiveImmersionQualification.record(["event":"latest_scroll_command", "reason":reason,
            "target_y":Double(target), "command_y":Double(target+viewportTopInset), "fallback_y":Double(latestScrollY), "target_x":Double(-viewportLeadingInset), "offset_y":Double(scrollOffset),
            "viewport_height":Double(viewportHeight), "bottom_inset":Double(viewportBottomInset),
            "following_latest":followingLatest, "scrolling":scrolling])
        #endif
        scrollVertically(to:target)
    }
    private func refresh() {
        do {
            let previousIDs = Set(messages.map(\.id))
            let current = try chat.messages(peer), ids = Set(current.map(\.id))
            if loaded && !followingLatest {
                unseenIncoming.formUnion(current.filter{!$0.outgoing && $0.state != "imported" && !previousIDs.contains($0.id)}.map(\.id))
            }
            messages = (current + messages.filter { !ids.contains($0.id) }).sorted { a, b in a.cursor < b.cursor }
            if !loaded { text = try chat.compose(peer); actionDraft.restore(MessageComposerContext.saved(chat.feedbackVault, conversation: ConversationRef.direct(peer).storageKey)); earlierAvailable = current.count == 50; loaded = true }
            if followingLatest && scenePhase == .active { try chat.markRead(peer) }
            reportVisibleMessages()
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
                        if abs(delta) > 0.5 { scrollVertically(to: scrollOffset + delta) }
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
            try chat.send(text, peer: peer, features: actionDraft.composed(text)); text = ""; actionDraft.reset(); error = nil
            chat.composerActivity(peer,active:false)
            viewportRestore?.cancel(); viewportRestore = nil; textSizeRestore?.cancel(); textSizeRestore = nil; textSizeAnchorID = nil
            followingLatest = true; unseenIncoming.removeAll(); jumpRevision += 1; refresh()
            offerReplyNotificationsAfterSend()
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
                if immersion.availability == .downloadable {
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
                    if earlierAvailable { Button("Earlier messages", action: earlier).font(.footnote).padding(8).background(VipiDesign.canvas,in:Capsule()) }
                    if messages.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "lock.shield").font(.title2)
                            Text("Just between you two").font(.headline)
                            Text("Say hello. Your messages are end-to-end encrypted.")
                                .font(.subheadline).multilineTextAlignment(.center)
                        }.foregroundStyle(VipiDesign.secondary).padding(30).background(VipiDesign.canvas,in:RoundedRectangle(cornerRadius:20))
                    }
                    ForEach(messages) { item in
                        MessageBubbleRow(outgoing: item.outgoing) {
                            VStack(alignment: .leading, spacing: 7) {
                                decorations(item)
                                ForEach(item.attachments.filter { $0.kind == .photo }, id: \.id) { photo in
                                    ConversationPhotoButton(available: chat.canViewPhoto(peer: peer)) {
                                        try await chat.viewPhoto(photo, peer: peer)
                                    }
                                }
                                ForEach(item.attachments.filter { $0.kind == .voice || $0.kind == .video }, id: \.id) { attachment in
                                    MediaPlaybackButton(manifest: attachment, available: chat.canViewPhoto(peer: peer)) {
                                        speech.stop()
                                        return try await chat.openMedia(attachment, peer: peer)
                                    }
                                }
                                if item.hasVoiceOnlyPlaceholder {
                                    voiceNoteMetadata(item)
                                        .padding(.horizontal, 12).padding(.bottom, 6)
                                } else {
                                    ConversationImmersionText(text: item.text, id: item.id.uuidString, immersion: immersion,
                                        speech: speech, paused: scrolling || (composing && !text.isEmpty), metadata: AnyView(actionMetadata(item)), onVoiceHelp: { showVoiceHelp = true }, onTranslationSetup: { translationHelpPair = $0; showTranslationHelp = true }, onReport: !item.outgoing && item.state != "imported" ? { reporting = HumanReportSelection(message: item) } : nil,playback:autoplay,accessibilityMessageContext:messageAccessibilityContext(item))
                                }
                            }
                        }.modifier(MessageSwipeActions(reply: { startReply(item) }, actions: { selectedActions = item.id }))
                            .background(highlightedMessage == item.id ? VipiDesign.highlight.opacity(0.3) : .clear, in: RoundedRectangle(cornerRadius: 16))
                            .id(item.id)
                            .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame in
                                messageFrames[item.id] = frame; reportVisibleMessages(); settleModeAnchor()
                                if item.id == messages.last?.id { settleMeasuredLatest() }
                            }
                            .onDisappear { messageFrames.removeValue(forKey:item.id); reportVisibleMessages() }
                            #if DEBUG
                            .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { value in
                                LiveImmersionQualification.recordFullMessageGeometry(["event":"full_message_row_geometry","message_id":item.id.uuidString,"outgoing":item.outgoing,"frame":LiveImmersionQualification.frameFields(value)])
                            }
                            #endif
                            .onGeometryChange(for: CGRect.self) { proxy in proxy.frame(in: .named("conversation-timeline")) } action: { frame in
                                if item.id == messages.first?.id { firstMessageFrame = frame }
                                if item.id == pageAnchorID { pageAnchorFrame = frame }
                                if item.id == textSizeAnchorID { textSizeAnchorFrame = frame }
                            }
                    }
                    if chat.isPeerTyping(peer),conversationActive {
                        PeerTypingBubble().id("peer-typing")
                            .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame in
                                peerTypingFrame = frame;settleMeasuredLatest()
                            }
                            .onDisappear { peerTypingFrame = .zero;settleMeasuredLatest() }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }.scrollTargetLayout().padding(.vertical,18).frame(maxWidth: VipiDesign.conversationWidth).frame(maxWidth: .infinity)
            }.contentMargins(.horizontal,18,for:.scrollContent)
                .clipped()
                .scrollDismissesKeyboard(.interactively)
                .accessibilityIdentifier("conversation-timeline")
                .coordinateSpace(name: "conversation-timeline")
                .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame in timelineFrame = frame; reportVisibleMessages() }
                #if DEBUG
                .onScrollGeometryChange(for:FullMessageViewportGeometry.self) { FullMessageViewportGeometry($0) } action: { _,value in
                    var fields = value.fields; fields["event"] = "full_message_scroll_geometry"; fields["composing"] = composing
                    LiveImmersionQualification.recordFullMessageGeometry(fields)
                }
                #endif
                .scrollPosition($position)
                .onScrollPhaseChange { _, phase in
                    scrolling = phase.isScrolling
                    userScrolling = phase == .interacting || phase == .decelerating
                    // A lazy row may finish measuring during a programmatic
                    // scroll. Its height change was intentionally not followed
                    // while moving; settle that new bottom once motion ends.
                    if phase == .idle,followingLatest,!copyOriginal.holdingLayout,textSizeRestore == nil,
                       abs(scrollOffset-measuredLatestScrollY) > 0.5 {
                        viewportRestore?.cancel()
                        viewportRestore = Task { @MainActor in
                            do { try await Task.sleep(for:.milliseconds(80)) } catch { return }
                            guard followingLatest,!scrolling,!copyOriginal.holdingLayout else { return }
                            scrollToLatest("idle_after_lazy_layout")
                            viewportRestore = nil
                        }
                    }
                    if phase == .tracking || phase == .interacting {
                        cancelPageRestoration()
                        viewportRestore?.cancel(); viewportRestore = nil
                        textSizeRestore?.cancel(); textSizeRestore = nil
                        textSizeAnchorID = nil
                    }
                }
                .onScrollGeometryChange(for: ConversationViewport.self) { geometry in
                    ConversationViewport(offset: geometry.contentOffset.y, visibleOffset: geometry.visibleRect.minY, height: geometry.visibleRect.height,containerHeight:geometry.containerSize.height,
                                         content: geometry.contentSize.height,
                                         bottomInset: geometry.contentInsets.bottom, topInset: geometry.contentInsets.top,
                                         leadingInset: geometry.contentInsets.leading)
                } action: { old, new in
                    #if DEBUG
                    LiveImmersionQualification.record(["event": "viewport", "offset": Double(new.offset), "visible_offset":Double(new.visibleOffset),
                        "height": Double(new.height), "content": Double(new.content), "bottom_inset": Double(new.bottomInset), "top_inset": Double(new.topInset),
                        "following_latest": followingLatest, "scrolling": scrolling, "user_scrolling": userScrolling,
                        "composing": composing, "draft_empty": text.isEmpty])
                    #endif
                    viewportHeight = new.height
                    viewportContainerHeight = new.containerHeight
                    viewportTopInset = new.topInset
                    viewportBottomInset = new.bottomInset
                    viewportLeadingInset = new.leadingInset
                    scrollOffset = new.offset
                    latestScrollY = new.latestScrollY
                    // Only a user's scroll changes reading intent. Lazy row
                    // estimates can briefly look like the bottom during a
                    // keyboard resize, even while reading much older messages.
                    if userScrolling {
                        followingLatest = new.nearBottom
                        if followingLatest { unseenIncoming.removeAll(); try? chat.markRead(peer) }
                    }
                    reportVisibleMessages()
                    // Message changes arrive before lazy rows have their final
                    // heights. Follow the current measured bottom after content
                    // or viewport changes; offset-only changes never reschedule.
                    let layoutChanged = abs(old.height - new.height) > 0.5 || abs(old.content - new.content) > 0.5
                        || abs(old.bottomInset - new.bottomInset) > 0.5 || abs(old.topInset - new.topInset) > 0.5
                        || abs(old.leadingInset - new.leadingInset) > 0.5
                    if !copyOriginal.holdingLayout && followingLatest && !scrolling && textSizeRestore == nil && layoutChanged {
                        viewportRestore?.cancel()
                        viewportRestore = Task { @MainActor in
                            do { try await Task.sleep(for: .milliseconds(80)) }
                            catch { return }
                            guard followingLatest && !scrolling else { return }
                            scrollToLatest("layout_settled")
                            viewportRestore = nil
                        }
                    }
                }
                .refreshable { await chat.synchronize(); refresh() }
                .onChange(of: messages.last?.id) { _, _ in if followingLatest { scrollToLatest("newest_message") } }
                .onChange(of: jumpRevision) { _, _ in scrollToLatest("send") }
                .onChange(of: composing) { _, focused in
                    modeAnchorTask?.cancel(); modeAnchorTask = nil; modeAnchor = nil
                    if focused && followingLatest && !copyOriginal.holdingLayout { scrollToLatest("composer_focus") }
                }
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
                                scrollVertically(to: scrollOffset + delta)
                            } else {
                                settled += 1
                                if settled >= 2 { break }
                            }
                        }
                        textSizeAnchorID = nil
                        textSizeRestore = nil
                    }
                }
                .overlay {
                    GeometryReader { proxy in
                        if !followingLatest && !messages.isEmpty {
                            VStack {
                                Spacer(minLength:0)
                                HStack {
                                    Spacer(minLength:0)
                                    Button {
                                        cancelPageRestoration(); followingLatest = true; unseenIncoming.removeAll(); try? chat.markRead(peer); scrollToLatest("explicit_latest")
                                    } label: {
                                        HStack(spacing:6) {
                                            Image(systemName:"arrow.down").font(.body.weight(.semibold))
                                            if !unseenIncoming.isEmpty {
                                                Text("New messages").font(.subheadline.weight(.medium))
                                                Text(unseenIncoming.count,format:.number).font(.caption.weight(.semibold)).monospacedDigit()
                                            }
                                        }.frame(minWidth:24,minHeight:24).padding(12)
                                    }
                                    .buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).buttonBorderShape(.capsule)
                                    .accessibilityLabel("Jump to latest messages").accessibilityIdentifier("conversation-latest")
                                }
                                .padding(.trailing,12)
                                // The actual overlay frame can include the keyboard
                                // while ScrollView uses content insets. Anchor the
                                // action to the measured readable viewport in either case.
                                .padding(.bottom,max(12,proxy.frame(in:.global).maxY-visibleTimeline.maxY+12))
                            }
                        }
                    }
                }
        }
    }
    var body: some View {
        VStack(spacing: 0) {
            ChatRevealCue(reading: state.chatReading, vault: chat.feedbackVault, composing: composing)
            timeline
        }
        .background { ConversationWaterScene(mode: state.immersionMode, motionEnabled: state.animateConversationBackground) }
        .background { if !usesAppTranslationServices { ConversationTranslationTask(immersion:immersion) } }
        .background { ChatReadingGestureSurface(reading:state.chatReading) }
        .background { CopyOriginalAnchor(context:copyOriginal) }
            #if DEBUG
            .copyOriginalProof(context:copyOriginal,autoplay:autoplay,speech:speech)
            .background { PendingPairRootBinding(autoplay:autoplay,speech:speech) }
            #endif
        .sheet(isPresented:$copyOriginal.presented,onDismiss:{ copyOriginal.restore() }) {
            CopyOriginalPicker(choices:copyOriginal.choices)
                #if DEBUG
                .copyOriginalProof(context:copyOriginal,autoplay:autoplay,speech:speech)
                #endif
        }
        .sheet(isPresented: $showTranslationHelp) {
            NavigationStack { LanguageDownloadView(requestedPair:translationHelpPair).toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showTranslationHelp = false } } } }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { headerViewport = $0 }
        .navigationTitle(chat.name(peer)).navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: VipiDesign.hasNarrowPadToolbar(headerViewport) ? .topBarTrailing : .principal) {
                ConversationStreakReader(vault: chat.feedbackVault, scope: .direct, id: peer, revision: chat.revision) { count in
                    ConversationHeaderActions(viewportWidth: headerViewport, mode: state.immersionMode, autoplay: autoplay.enabled,
                        toggleMode: toggleMode, toggleAutoplay: toggleAutoplay, language: languageSelection) { showsAvatar in
                        ConversationStreakLabel(count: count, scope: .direct, headerName: chat.name(peer),
                            avatar: showsAvatar ? ContactAvatar(peer: peer, name: chat.name(peer), size: 28, jpeg: chat.avatar(peer)) : nil)
                    } options: { conversationOptions }
                }
            }
        }
        .alert(blocked ? "Unblock \(chat.name(peer))?" : "Block \(chat.name(peer))?", isPresented: $confirmBlock) {
            Button("Cancel", role: .cancel) {}
            Button(LocalizedStringKey(blocked ? "Unblock" : "Block"), role: blocked ? nil : .destructive, action: changeBlock)
        } message: {
            Text(LocalizedStringKey(blocked ? "You can exchange new messages again. Stopped messages won’t be resent." : "Messages between you will stop. Your chat stays on this device. You can unblock anytime."))
        }
        .sheet(isPresented: $showSecurityNumber) { SecurityNumberView(chat: chat, peer: peer) }
        .sheet(isPresented:$choosingReport,onDismiss:{
            if let selected = chosenReportMessage { chosenReportMessage = nil; reporting = HumanReportSelection(message:selected) }
        }) {
            ReportMessagePicker(choices:messages.filter{!$0.outgoing && $0.state != "imported"}.map{.init(id:$0.id.uuidString,original:$0.text)}) { id in
                chosenReportMessage = messages.first{$0.id.uuidString == id && !$0.outgoing && $0.state != "imported"}
            }
        }
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
                    Text("Listen in your practice language").font(.title2).fontWeight(.semibold)
                    Text(speech.error ?? "Prepare the voice for the language you’re learning to listen offline.")
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
        .task(id: peer) { supportsReactions = await chat.reactionSupport(peer) }
        .onChange(of: selectedActions) { _, selection in
            if selection != nil { Task { supportsReactions = await chat.reactionSupport(peer) } }
        }
        .task(id:"\(state.knownLanguage)-\(state.targetLanguage)-\(chat.translationGeneration)-\(state.immersionMode.rawValue)-\(chat.translationOwner.map{String(describing:ObjectIdentifier($0))} ?? "local")") {
            copyOriginal.abandon()
            speech.close()
            autoplay.stop(speech:speech)
            if usesAppTranslationServices {
                chat.activateConversation(conversationRef)
                await chat.configureTranslation(pair:.init(source:state.knownLanguage,target:state.targetLanguage),
                                                mode:state.immersionMode,services:state.translationServices)
                guard let owner = chat.translationFor(conversationRef) else { return }
                immersion = owner
            } else { await immersion.configure(pair:.init(source:state.knownLanguage,target:languageSelection.target),mode:state.immersionMode) }
            prepareVoices(); immersion.warm(messages.map{(id:$0.id.uuidString,text:$0.text)})
        }
        .onAppear {
            conversationActive = true
            chat.visibleMessages(peer,incoming:[],outgoing:[])
            reportVisibleMessages()
            state.chatReading.bindPlayback(owner:autoplay.ownerID) { identity,displayed in
                autoplay.manual(identity,displayed:displayed,immersion:immersion,speech:speech,onModels:{translationHelpPair = $0; showTranslationHelp = true},onVoiceHelp:{showVoiceHelp = true})
            }
            if messageObserver == nil {
                messageObserver = chat.observeNewMessages { event in
                    guard event.peer == peer else { return }
                    autoplay.arrived(.init(id:event.id,load:event.load),immersion:immersion,speech:speech,foreground:scenePhase == .active)
                }
            }
        }
        .onChange(of:messages.map(\.id),initial:true) { _,_ in
            immersion.warm(messages.map{(id:$0.id.uuidString,text:$0.text)})
        }
        .onChange(of:immersion.revision) { _,_ in immersion.warm(messages.map{(id:$0.id.uuidString,text:$0.text)}); autoplay.resume(immersion:immersion,speech:speech,foreground:scenePhase == .active) }
        .onDisappear { quoteJump?.cancel(); quoteJump = nil; conversationActive = false; clearConversationActivity(); notificationTask?.cancel(); notificationTask = nil; notificationInvitation = false; restoreNotificationFocus = false; if let messageObserver { chat.removeMessageObserver(messageObserver) }; messageObserver = nil; state.chatReading.unbindPlayback(owner:autoplay.ownerID); autoplay.stop(speech:speech); state.chatReading.cancelInteractions(); copyOriginal.abandon(); cancelPageRestoration(); viewportRestore?.cancel(); viewportRestore = nil; textSizeRestore?.cancel(); textSizeRestore = nil; textSizeAnchorID = nil; if !usesAppTranslationServices { immersion.close() }; speech.close() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                clearConversationActivity(); copyOriginal.abandon(); autoplay.stop(speech:speech); state.chatReading.cancelInteractions(); cancelPageRestoration(); speech.stop() }
            else {
                if restoreNotificationFocus { composing = true; restoreNotificationFocus = false }
                reportVisibleMessages(); Task { await immersion.refreshAvailability(); prepareVoices() }
            }
        }
        .onChange(of:canReportVisible) { _,_ in reportVisibleMessages() }
        .onChange(of:composing) { _,focused in if !focused { chat.composerActivity(peer,active:false) } }
        .onChange(of:state.chatReading.showingMeaning) { _,meaning in
            if meaning { state.chatReading.cancelPendingPlayback(); autoplay.stop(speech:speech) }
        }
        .onChange(of: speech.state) { _, value in if value == .ready { showVoiceHelp = false; autoplay.voicesReady() } }
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
    private var conversationOptions: some View {
        Menu {
            NavigationLink { LanguageDownloadView() } label: { Label("Languages", systemImage: "globe") }
                .accessibilityIdentifier("conversation-languages")
            Button("Copy original message",systemImage:"doc.on.doc") {
                // Firm stop even when autoplay is already OFF with manual work pending.
                cancelPageRestoration(); viewportRestore?.cancel(); viewportRestore = nil
                textSizeRestore?.cancel(); textSizeRestore = nil
                copyOriginal.open(messages.map{.init(id:$0.id.uuidString,original:$0.text)},autoplay:autoplay,speech:speech,reading:state.chatReading,fromMenu:true)
            }.disabled(messages.isEmpty).accessibilityIdentifier("copy-original-picker")
            Button("Verify encryption", systemImage: "lock.shield") { showSecurityNumber = true }
            if messages.contains(where:{!$0.outgoing && $0.state != "imported"}) {
                Button("Report a message",systemImage:"flag") { choosingReport = true }
                    .accessibilityIdentifier("report-message-picker")
            }
            Button("Report person", systemImage: "flag") { reporting = HumanReportSelection(message: nil) }
            Button(LocalizedStringKey(blocked ? "Unblock" : "Block"), role: blocked ? nil : .destructive) { confirmBlock = true }
        } label: {
            if blockBusy { ProgressView() }
            else { Image(systemName: "ellipsis").frame(width: 44, height: 44)
                .background { CopyOriginalMenuCapture(context:copyOriginal) } }
        }.controlSize(.large).disabled(blockBusy).accessibilityLabel("Conversation options").accessibilityIdentifier("conversation-options")
    }
    @ViewBuilder private var recordingHint: some View {
        Text("Hold to record. Release to send.").font(.footnote).foregroundStyle(VipiDesign.secondary)
        Button("Record hands-free") {
            composing = false; speech.stop(); voice.begin(lock: true)
        }.font(.footnote.weight(.semibold)).frame(minHeight: 44).accessibilityIdentifier("voice-hands-free")
    }
    private var composer: some View {
            VStack(spacing: 9) {
                if !blocked && !voice.active {
                    MessageComposerContext(draft: actionDraft, text: text, name: authorName, vault: chat.feedbackVault, conversation: ConversationRef.direct(peer).storageKey)
                }
                // A large optional card must not consume the transcript while
                // an accessibility-size keyboard is open. Keep the invitation
                // pending in this conversation and show it after focus leaves.
                if notificationInvitation && !(typeSize.isAccessibilitySize && composing) {
                    ReplyNotificationInvitation(previews:chat.previewsOutsideApp, denied:PushNotifications.shared.authorization == .denied,busy:PushNotifications.shared.busy,
                        notify:enableReplyNotifications,dismiss:{ notificationInvitation = false })
                }
                if rejectedDraftEdit || messageTooLong {
                    Text(LocalizedStringKey(rejectedDraftEdit ? "That text is too long. Your previous draft is still here." : "This message is too long. Send a shorter message."))
                        .font(.subheadline).foregroundStyle(VipiDesign.destructive).fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 14).accessibilityIdentifier("message-length-notice")
                }
                if let notice = autoplay.voiceNotice {
                    HStack(alignment:.top) {
                        Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
                        Button("Retry voices") { prepareVoices() }.frame(minHeight:44)
                    }.padding(.horizontal,14).accessibilityIdentifier("chat-voice-recovery")
                }
                if blocked {
                    HStack {
                        Text("You blocked this person.").font(.subheadline)
                        Button("Unblock") { confirmBlock = true }.disabled(blockBusy)
                    }.padding(16).accessibilityIdentifier("conversation-blocked")
                } else {
                if voice.showHandsFree {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { recordingHint }
                        VStack(alignment: .leading, spacing: 2) { recordingHint }
                    }.padding(.horizontal, 14)
                }
                if let notice = voice.notice {
                    HStack {
                        Text(notice).font(.footnote).foregroundStyle(VipiDesign.secondary)
                        if voice.denied { Link("Open Settings", destination: URL(string: UIApplication.openSettingsURLString)!) }
                    }.padding(.horizontal, 14)
                }
                HStack(alignment: .bottom, spacing: 6) {
                    if voice.active {
                        InlineVoiceStatus(voice: voice)
                    } else {
                        AttachmentComposeButton(chat: chat, peer: peer) {
                            composing = false
                            speech.stop()
                        } onCommitted: {
                            followingLatest = true
                            refresh()
                            Task { await chat.synchronize() }
                        }
                        MessageEditor(text: editableDraft, placeholder: String(localized: "Message"), focus: $composing,
                            maximumBytes: ConversationHistory.maximumDraftBytes, rejected: { rejectedDraftEdit = true })
                            .disabled(!loaded)
                            .id(typeSize)
                            .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                            .overlay(RoundedRectangle(cornerRadius: 23).strokeBorder(
                                composing ? VipiDesign.focus : VipiDesign.outline, lineWidth: composing ? 1.5 : 1))
                            .accessibilityIdentifier("message-input")
                        if !text.isEmpty {
                            Button(action: send) {
                                Image(systemName: "arrow.up").font(.body.weight(.semibold))
                                    .frame(minWidth: 46, minHeight: 46).padding(6)
                                    .foregroundStyle(canSend ? VipiDesign.onHighlight : VipiDesign.secondary)
                                    .background(canSend ? VipiDesign.highlight : VipiDesign.subdued, in: Circle())
                            }
                            .buttonStyle(.plain).accessibilityLabel("Send message")
                            .accessibilityIdentifier("message-send").disabled(!canSend)
                        }
                    }
                    InlineMicButton(voice: voice, enabled: loaded && chat.canViewPhoto(peer: peer)) {
                        composing = false; speech.stop()
                    }
                }.padding(.horizontal, 14).padding(.bottom, 10)
                }
            }.frame(maxWidth: VipiDesign.conversationWidth).frame(maxWidth: .infinity)
            .background(VipiDesign.canvas)
            .onAppear {
                voice.bind(chat, peer: peer) {
                    followingLatest = true; refresh()
                    Task { await chat.synchronize() }
                }
            }
            .onChange(of: chat.canViewPhoto(peer: peer)) { _, allowed in
                if !allowed { voice.interruption() }
            }
            .onChange(of: voice.recorder.phase) { _,_ in voice.recorderChanged() }
            .onDisappear { voice.interruption(leaving: true) }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { note in
                if (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) == AVAudioSession.InterruptionType.began.rawValue { voice.interruption() }
            }
            .onChange(of: scenePhase) { _,value in if value == .background { voice.interruption() } }
            .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { value in
                composerFrame = value; reportVisibleMessages()
                #if DEBUG
                LiveImmersionQualification.recordFullMessageGeometry(["event":"full_message_composer_geometry","frame":LiveImmersionQualification.frameFields(value)])
                #endif
            }
    }
    @ViewBuilder private func statusLabel(_ title: LocalizedStringKey, symbol: String) -> some View {
        if typeSize.isAccessibilitySize {
            Label(title, systemImage: symbol).labelStyle(.iconOnly).frame(minWidth: 44, minHeight: 44)
        } else {
            Label(title, systemImage: symbol).fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
        }
    }
    private func toggleMode() {
        copyOriginal.abandon()
        autoplay.stop(speech: speech)
        state.chatReading.cancelInteractions()
        captureModeAnchor(for: state.immersionMode.next)
        state.immersionMode = state.immersionMode.next
    }
    private func toggleAutoplay() {
        state.chatReading.cancelPendingPlayback()
        autoplay.toggle(snapshot: messages.map { .init(id: $0.id.uuidString, text: $0.text) },
                        immersion: immersion, speech: speech)
    }
    private func prepareVoices() {
        let language = languageSelection.target
        speech.prepare(source:language,target:language,warmups:[language:VipiLanguage.named(language).localName])
    }
    private func messageDate(_ item: ChatItem) -> Date { Date(timeIntervalSince1970: Double(item.createdAt) / 1000) }
    private func messageAccessibilityContext(_ item: ChatItem) -> String {
        let time = messageDate(item).formatted(date:.abbreviated,time:.shortened)
        if item.state == "imported" { return time + " · " + String(localized:"Saved history") }
        let delivery = MessageDeliveryMark.localizedDescription(item.state)
        return item.outgoing && !delivery.isEmpty ? time + " · " + delivery : time
    }
    private func actionTarget(_ item: ChatItem, account: UUID) -> MessageActionTarget {
        let author = item.outgoing ? account : peer
        return .init(id: item.id, sender: author, quote: .quoting(id: item.id, sender: author, text: item.text, media: item.attachments.first?.kind.rawValue))
    }
    private func startReply(_ item: ChatItem) {
        guard let account = chat.profile?.id else { return }
        actionDraft.reply = actionTarget(item, account: account).quote; composing = true
    }
    private func authorName(_ id: UUID) -> String { id == chat.profile?.id ? String(localized: "You") : chat.name(id) }
    @ViewBuilder private func decorations(_ item: ChatItem) -> some View {
        if let reply = item.features?.reply {
            let original = chat.quotedOriginal(reply.message_id, peer: peer, author: reply.sender_id)
            let value = original.map { quotedText($0, reply: reply) } ?? reply.excerpt
            Button {
                guard let original else { return }
                jumpToQuote(original)
            } label: { ReplyExcerptView(author: authorName(reply.sender_id), excerpt: value) }
                .buttonStyle(.plain).disabled(original == nil).padding(.horizontal, 12).padding(.top, 8)
        }
        if let preview = item.features?.link_preview, let url = URL(string: preview.url) {
            Link(destination: url) { EmbeddedLinkCard(preview: preview) }.buttonStyle(.plain).padding(.horizontal, 8).padding(.top, 6)
        }
    }
    private func jumpToQuote(_ original: ChatItem) {
        quoteJump?.cancel()
        quoteJump = Task {
            var pages: [ChatItem] = []
            var head = messages.first?.cursor
            while let cursor = head, original.cursor < cursor {
                guard !Task.isCancelled else { return }
                guard let page = try? chat.messages(peer, before: cursor), let oldest = page.first, oldest.cursor < cursor else { break }
                pages.append(contentsOf: page); head = oldest.cursor
                await Task.yield()
            }
            guard !Task.isCancelled, conversationActive else { return }
            if !pages.isEmpty {
                let visible = Set(messages.map(\.id))
                messages = (pages.filter { !visible.contains($0.id) } + messages).sorted { $0.cursor < $1.cursor }
            }
            guard messages.contains(where: { $0.id == original.id }) else { return }
            followingLatest = false; highlightedMessage = original.id
            await Task.yield()
            position.scrollTo(id: original.id, anchor: .center)
            try? await Task.sleep(for: .seconds(1))
            if !Task.isCancelled { highlightedMessage = nil }
        }
    }
    private func quotedText(_ item: ChatItem, reply: ChatFeatures.Reply) -> String {
        if reply.kind != "text", let account = chat.profile?.id { return actionTarget(item, account: account).quote.excerpt }
        guard let cached = immersion.cached(item.text, messageID: item.id.uuidString) else { return item.text }
        if state.immersionMode == .fullMessages { return cached.translation ?? item.text }
        return cached.speech(source: state.knownLanguage, target: state.targetLanguage).map(\.text).joined()
    }
    @ViewBuilder private func actionMetadata(_ item: ChatItem) -> some View {
        if let account = chat.profile?.id {
        let target = actionTarget(item, account: account)
        let entries = chat.feedbackVault.flatMap { try? MessageReactions.entries($0, scope: .direct, conversation: peer, target: item.id, author: target.sender) } ?? []
        MessageActionFooter(target: target, account: account, entries: entries,
            allowReaction: supportsReactions && ["accepted","delivered","read"].contains(item.state), metadataLabel: messageAccessibilityContext(item), name: authorName,
            reply: { startReply(item) }, react: { emoji in
                _ = try await chat.sendReaction(peer: peer, target: item.id, author: target.sender, emoji: emoji)
                await chat.synchronize()
            }, selected: $selectedActions) { rowMetadata(item) }
        } else { rowMetadata(item) }
    }
    private func rowMetadata(_ item: ChatItem) -> some View {
        messageMetadata(item).font(.caption2)
            .fixedSize(horizontal: false, vertical: true)
            .foregroundStyle(VipiDesign.messageSecondary(item.outgoing))
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("message-meta-" + item.id.uuidString)
    }

    @ViewBuilder private func voiceNoteMetadata(_ item: ChatItem) -> some View {
        if item.outgoing || item.state == "imported" {
            actionMetadata(item)
        } else {
            actionMetadata(item)
                .contextMenu {
                    Button("Report message", systemImage: "flag") { reporting = HumanReportSelection(message: item) }
                }
                .accessibilityAction(named: "Report message") { reporting = HumanReportSelection(message: item) }
        }
    }

    @ViewBuilder private func messageMetadata(_ item: ChatItem) -> some View {
        let index = messages.firstIndex { $0.id == item.id } ?? 0
        let previous = index > 0 ? messageDate(messages[index-1]) : nil
        let time = MessageTimelineMetadata.timeLabel(for:messageDate(item),previous:previous)
        let displayedTime = time ?? messageDate(item).formatted(date:.omitted,time:.shortened)
        ViewThatFits(in:.horizontal) {
            HStack(spacing:4) {
                Text(displayedTime).monospacedDigit().accessibilityIdentifier("message-time-"+item.id.uuidString)
                if item.state == "imported" { Text("Saved history") }
                else if item.outgoing { MessageDeliveryMark(state:item.state) }
            }.fixedSize(horizontal:true,vertical:false)
            VStack(alignment:.leading,spacing:2) {
                Text(displayedTime).monospacedDigit().fixedSize(horizontal:false,vertical:true)
                    .accessibilityIdentifier("message-time-"+item.id.uuidString)
                if item.state == "imported" { Text("Saved history") }
                else if item.outgoing { MessageDeliveryMark(state:item.state) }
            }
        }.font(.caption2)
    }

}

private struct ConversationViewport: Equatable {
    // Point scroll commands use native contentOffset; visibleRect has a
    // different origin after content/safe-area/keyboard insets are applied.
    let offset: CGFloat
    let visibleOffset: CGFloat
    let height: CGFloat
    let containerHeight: CGFloat
    let content: CGFloat
    let bottomInset: CGFloat
    let topInset: CGFloat
    let leadingInset: CGFloat
    // ScrollGeometry's visible height includes safe-area/keyboard insets on
    // this native path; containerHeight is the already clipped field.
    // Substituting that clipped height counts those insets twice.
    var latestScrollY: CGFloat { max(-topInset, content + bottomInset - height) }
    var nearBottom: Bool { content + bottomInset - offset - height <= 44 }
}
