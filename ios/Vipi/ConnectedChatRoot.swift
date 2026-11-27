import SwiftUI

struct ConnectedChatRoot: View {
    #if DEBUG
    @MainActor struct Qualification {
        let makeChat: (AuthenticationManager, String) throws -> ChatSession
        let makeSubscriptions: (AuthenticationManager, String, UUID) throws -> SubscriptionStore
        let makeBotOwner: (UUID?) -> BotConversationOwner
    }
    private let qualification: Qualification?
    init(qualification: Qualification? = nil) {
        if qualification != nil {
            precondition(
                Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
                    && (ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-qa")
                        || ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa")),
                "Owned root qualification only")
        }
        self.qualification = qualification
    }
    #endif
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.scenePhase) private var scenePhase
    @State private var chat: ChatSession?
    @State private var subscriptions: SubscriptionStore?
    @State private var botOwner = BotConversationOwner()
    @State private var error: String?
    @State private var replacement: OwnDeviceReplacement?
    @State private var showReplacement = false
    var body: some View {
        Group {
            if let chat {
                if chat.profile != nil {
                    HomeView(
                        chat: chat, subscriptions: subscriptions, botOwner: botOwner,
                        reauthenticate: { authentication.signIn(expectedUser: chat.userID) },
                        authenticationBusy: authentication.busy, authenticationError: authentication.errorMessage
                    )
                    .safeAreaInset(edge: .top) {
                        if !chat.ready && !chat.needsReauthentication {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Chatting is paused").font(.headline)
                                Text(
                                    chat.notice
                                        ?? "Your saved conversations are available while this device reconnects."
                                ).font(.footnote)
                                if let error = authentication.errorMessage { Text(error).font(.footnote) }
                                HStack {
                                    if chat.needsDeviceReplacement {
                                        Button("Review this device") {
                                            do {
                                                replacement = try chat.deviceReplacementCandidate()
                                                showReplacement = true
                                            } catch { self.error = ChatSession.explanation(error) }
                                        }.accessibilityIdentifier("device-replacement-review")
                                    } else {
                                        Button("Try again") { Task { await chat.start() } }
                                    }
                                    Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                                }.disabled(chat.busy || authentication.busy)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(VipiDesign.surface)
                        }
                    }
                } else if chat.needsProfile {
                    ProfileSetupView(chat: chat)
                } else {
                    ContentUnavailableView {
                        Label(
                            LocalizedStringKey(chat.busy ? "Connecting to your chats" : "Reconnect to your chats"),
                            systemImage: "bubble.left.and.bubble.right")
                    } description: {
                        Text(chat.notice ?? "Your conversations stay on your device.")
                    } actions: {
                        if chat.busy {
                            ProgressView()
                        } else {
                            Button("Try again") { Task { await chat.start() } }.buttonStyle(.borderedProminent)
                                .foregroundStyle(VipiDesign.onHighlight)
                            Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                        }
                    }
                }
            } else if let error {
                ContentUnavailableView(
                    "Your conversations couldn’t be opened", systemImage: "lock.shield", description: Text(error))
            } else {
                ProgressView("Connecting to your chats")
            }
        }
        .background(VipiDesign.canvas)
        .background { if let owner = chat?.translationOwner { ConversationTranslationTask(immersion: owner) } }
        .task(
            id: "\(state.knownLanguage)-\(state.targetLanguage)-\(state.immersionMode.rawValue)-\(chat?.userID ?? "")"
        ) {
            if let chat {
                await chat.configureTranslation(
                    pair: .init(source: state.knownLanguage, target: state.targetLanguage), mode: state.immersionMode,
                    services: state.translationServices)
                botOwner.useTranslation(chat.translationOwner)
            }
        }
        .sheet(isPresented: $showReplacement) {
            if let chat, let replacement { OwnDeviceReplacementView(chat: chat, candidate: replacement) }
        }
        .onChange(of: authentication.session?.accessToken) { _, _ in
            if let chat, !chat.ready || chat.needsReauthentication { Task { await chat.start() } }
        }
        .task(id: authentication.session?.userID) {
            try? botOwner.close()
            #if DEBUG
            botOwner = qualification?.makeBotOwner(nil) ?? BotConversationOwner()
            #else
            botOwner = BotConversationOwner()
            #endif
            subscriptions?.close()
            subscriptions = nil
            PushNotifications.shared.detach()
            try? chat?.close()
            chat = nil
            guard let userID = authentication.session?.userID else { return }
            do {
                #if DEBUG
                let value =
                    try qualification?.makeChat(authentication, userID)
                    ?? ChatSession(authentication: authentication, userID: userID)
                #else
                let value = try ChatSession(authentication: authentication, userID: userID)
                #endif
                await value.configureTranslation(
                    pair: .init(source: state.knownLanguage, target: state.targetLanguage), mode: state.immersionMode,
                    services: state.translationServices)
                chat = value
                await value.start()
            } catch {
                self.error = String(
                    localized: "Your saved data is still here. Please close and reopen Vipi to try again.")
            }
        }
        .onDisappear {
            try? botOwner.close()
            subscriptions?.close()
            PushNotifications.shared.detach()
            try? chat?.close()
        }
        .task(id: chat?.ready == true && chat?.needsReauthentication == false) {
            chat?.setForeground(scenePhase == .active)
            if let chat, chat.ready && !chat.needsReauthentication { await PushNotifications.shared.attach(chat) }
        }
        .onChange(of: scenePhase) { _, phase in
            chat?.setForeground(phase == .active)
            if phase == .active {
                Task {
                    await chat?.synchronize()
                    await PushNotifications.shared.refresh()
                }
            }
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
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 80
            && username.range(of: "^[a-zA-Z][a-zA-Z0-9_]{2,23}$", options: .regularExpression) != nil
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VipiMark(size: 50)
                IntroHeading(
                    eyebrow: "Your profile", title: "How will friends\nfind you?",
                    detail: "Choose a name they’ll recognise and a username to share.")
                VStack(alignment: .leading, spacing: 14) {
                    TextField("Your name", text: $name, prompt: Text("Your name").foregroundStyle(VipiDesign.secondary))
                        .textContentType(.name).accessibilityIdentifier("profile-name")
                    Divider()
                    HStack {
                        Text("@").foregroundStyle(VipiDesign.secondary)
                        TextField(
                            "Username", text: $username, prompt: Text("Username").foregroundStyle(VipiDesign.secondary)
                        )
                        .textInputAutocapitalization(.never).autocorrectionDisabled().textContentType(.username)
                        .accessibilityIdentifier("profile-username")
                    }
                }.padding(20).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
                Text(
                    "Use 3–24 English letters, numbers or underscores. Start with a letter. Your phone number and contacts stay private."
                )
                .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                Toggle("I agree to the Terms of Service and have read the Privacy Policy.", isOn: $acceptedTerms)
                    .font(.subheadline).tint(VipiDesign.accent).accessibilityIdentifier("profile-accept-terms")
                HStack(spacing: 20) {
                    Link(destination: URL(string: "https://mambovipi.app/terms.html")!) {
                        Text("Terms").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                    }
                    Link(destination: URL(string: "https://mambovipi.app/privacy.html")!) {
                        Text("Privacy").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                    }
                }.font(.subheadline)
                if let notice = chat.notice {
                    Text(notice).font(.subheadline).foregroundStyle(VipiDesign.secondary).accessibilityIdentifier(
                        "profile-error")
                }
                Button {
                    Task { await chat.createProfile(username: username, name: name) }
                } label: {
                    HStack {
                        Spacer()
                        if chat.busy {
                            ProgressView().tint(VipiDesign.onHighlight)
                        } else {
                            Text("Start chatting").fontWeight(.semibold)
                        }
                        Spacer()
                    }.padding(.vertical, 12)
                }.buttonStyle(.borderedProminent).foregroundStyle(VipiDesign.onHighlight).disabled(
                    !valid || !acceptedTerms || chat.busy
                ).accessibilityIdentifier("profile-submit")
                Button("Delete Vipi account", role: .destructive) { showDelete = true }.foregroundStyle(
                    VipiDesign.destructive
                ).disabled(chat.busy)
            }.padding(28).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }.clipped().background(VipiDesign.canvas).scrollDismissesKeyboard(.interactively)
            .sheet(isPresented: $showDelete) {
                NavigationStack {
                    DeleteAccountView(chat: chat)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) { Button("Back") { showDelete = false } }
                        }
                }
            }
    }
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
                    Text("Use Vipi on this device").font(.title2.weight(.semibold))
                    Text(
                        "This device will replace whichever other device is currently active and sign it out. A recent sign-in is required."
                    )
                    Text(
                        "Your saved history stays here. Pending messages from the previous device won’t be resent. Friends will see changed encryption keys."
                    )
                }
                Section {
                    if chat.needsRecentSignIn {
                        Text("Sign in again to finish moving your account. The device change you confirmed is saved.")
                            .font(.footnote)
                        Button("Sign in again") { authentication.signIn(expectedUser: chat.userID) }
                            .accessibilityIdentifier("device-replacement-sign-in")
                            .disabled(working || authentication.busy || chat.busy)
                    } else if chat.hasPendingDeviceReplacement {
                        Button("Try again") {
                            working = true
                            Task {
                                defer { working = false }
                                do {
                                    try await chat.resumeDeviceReplacement()
                                    dismiss()
                                } catch { self.error = ChatSession.explanation(error) }
                            }
                        }.disabled(working || chat.busy).accessibilityIdentifier("device-replacement-retry")
                    } else if attempted && chat.needsDeviceReplacement {
                        Text("The active device changed again. Review this device once more before replacing it.").font(
                            .footnote)
                        Button("Review again") { dismiss() }.accessibilityIdentifier("device-replacement-review-again")
                    } else {
                        Button("Use this device") { confirming = true }.disabled(
                            working || !chat.needsDeviceReplacement
                        )
                        .accessibilityIdentifier("device-replacement-confirm")
                    }
                    if working { ProgressView("Registering this device") }
                    if let error { Text(error).font(.footnote) }
                    if let error = authentication.errorMessage { Text(error).font(.footnote) }
                }
            }.scrollContentBackground(.hidden).background(VipiDesign.canvas)
                .navigationTitle("Move your account").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(working) }
                }
                .alert("Replace the active device?", isPresented: $confirming) {
                    Button("Cancel", role: .cancel) {}
                    Button("Use this device") {
                        working = true
                        attempted = true
                        Task {
                            defer { working = false }
                            do {
                                try await chat.confirmDeviceReplacement(candidate)
                                dismiss()
                            } catch { self.error = ChatSession.explanation(error) }
                        }
                    }
                } message: {
                    Text(
                        "The currently active device will be signed out. Saved history remains, but pending old messages won’t be resent."
                    )
                }
        }.tint(VipiDesign.highlight).interactiveDismissDisabled(working)
            .onChange(of: chat.ready) { _, ready in if ready { dismiss() } }
    }
}
