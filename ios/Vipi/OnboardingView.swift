import SwiftUI

enum MamboOnboardingCopy {
    static let homeURL = "https://mambovipi.app"
    static let shareMessage = "Try Vipi—learn a language in the chats you already have.\n" + homeURL
}

private enum MamboPage: Int, CaseIterable {
    case name, languages, shallow, deep, listen, invite, privacy
}

private enum MamboLanguagePicker: String, Identifiable {
    case known, target
    var id: String { rawValue }
}

#if DEBUG
/// Store-capture state only. Release builds always begin at the namesake page
/// with an empty composer.
private enum MamboOnboardingCaptureState {
    private static func argument(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: name), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }
    static var page: Int {
        guard let value = argument("-vipi-mambo-page").flatMap(Int.init),
              (1...MamboPage.allCases.count).contains(value) else { return 0 }
        return value - 1
    }
    static var message: String? {
        ProcessInfo.processInfo.arguments.contains("-vipi-mambo-demo-message")
            ? "Coffee tomorrow?" : argument("-vipi-mambo-message")
    }
}
#endif

/// Seven single-purpose pages. Every interactive example uses the same local
/// translation, speech, water and bubble surfaces as a real conversation, but
/// no message enters chat history and no account is required to continue.
struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    #if DEBUG
    @State private var page = MamboOnboardingCaptureState.page
    #else
    @State private var page = MamboPage.name.rawValue
    #endif
    @State private var draft = ""
    #if DEBUG
    @State private var sentMessage = MamboOnboardingCaptureState.message
    #else
    @State private var sentMessage: String?
    #endif
    @State private var composing = false
    @State private var picker: MamboLanguagePicker?
    @State private var accountSheet = false

    private var current: MamboPage { MamboPage(rawValue: page) ?? .name }
    private var sceneMode: ImmersionMode { current == .deep || current == .listen ? .fullMessages : .incremental }
    private var targetName: String { VipiLanguage.named(state.targetLanguage).localizedName }

    var body: some View {
        ZStack {
            ConversationWaterScene(mode: sceneMode, motionEnabled: state.animateConversationBackground)
                .ignoresSafeArea()
                .accessibilityIdentifier("mambo-background")
            VStack(spacing: 0) {
                header
                Group {
                    switch current {
                    case .name: namePage
                    case .languages: languagesPage
                    case .shallow: shallowPage
                    case .deep: demoPage(title: "Deep immersion", detail: "Shows the full message in \(targetName).", mode: .fullMessages)
                    case .listen: listenPage
                    case .invite: invitePage
                    case .privacy: privacyPage
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .id(current)
            }
        }
        .sheet(item: $picker) { kind in languageSheet(kind) }
        .sheet(isPresented: $accountSheet) {
            OnboardingAccountSheet(continueWithoutAccount: { state.continueWithoutAccount() })
        }
        .onChange(of: current) { old, _ in
            composing = false
            if old == .shallow { draft = "" }
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { composing = false } }
    }

    private var header: some View {
        HStack(spacing: 10) {
            if current != .name {
                Button { goBack() } label: {
                    Image(systemName: "chevron.left").font(.body.weight(.semibold))
                        .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Back")
                .accessibilityIdentifier("mambo-back")
            }
            VipiMark(size: 46, accessibleName: "Vipi")
            Spacer(minLength: 8)
            Text("\(page + 1) of \(MamboPage.allCases.count)")
                .font(.footnote.weight(.medium)).foregroundStyle(VipiDesign.secondary)
                .accessibilityLabel("Step \(page + 1) of \(MamboPage.allCases.count)")
                .accessibilityIdentifier("mambo-step")
        }
        .padding(.horizontal, 20).padding(.top, 8).frame(minHeight: 52)
    }

    private var namePage: some View {
        fullPage {
            Spacer(minLength: 36)
            onboardingCopy("Mambo Vipi", "A Swahili greeting meaning “What’s up?” It’s where our name comes from.", titleIdentifier: "mambo-name-title")
            Spacer(minLength: 36)
            PrimaryButton(title: "Continue") { advance() }
                .accessibilityIdentifier("mambo-continue")
        }
    }

    private var languagesPage: some View {
        fullPage {
            onboardingCopy("Your languages", "Choose what you speak and what you want to learn. Vipi starts with eleven languages and adds more when your device supports them.", titleIdentifier: "mambo-languages-title")
            VStack(alignment: .leading, spacing: 18) {
                languageField("I speak", code: state.knownLanguage, identifier: "mambo-known-language") { picker = .known }
                languageField("I’m learning", code: state.targetLanguage, identifier: "mambo-target-language") { picker = .target }
            }
            Spacer(minLength: 20)
            PrimaryButton(title: "Continue") { advance() }
                .accessibilityIdentifier("mambo-continue")
        }
    }

    private var shallowPage: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    onboardingCopy("Shallow immersion", "Shows one new word per message.", titleIdentifier: "mambo-shallow-title")
                    if let sentMessage {
                        MamboDemoMessage(text: sentMessage, mode: .incremental)
                    }
                }
                .padding(.horizontal, 18).padding(.top, 10).padding(.bottom, 12)
                .frame(maxWidth: 644).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            composer
            if sentMessage != nil {
                PrimaryButton(title: "Continue") { advance() }
                    .accessibilityIdentifier("mambo-continue")
                    .padding(.horizontal, 18).padding(.bottom, 12)
            }
        }
    }

    private var listenPage: some View {
        chatPage {
            onboardingCopy("Hear it", "Tap the message to hear it in \(targetName).", titleIdentifier: "mambo-listen-title")
            MamboDemoMessage(text: demoText, mode: .fullMessages)
            Spacer(minLength: 20)
            PrimaryButton(title: "Continue") { advance() }
                .accessibilityIdentifier("mambo-continue")
        }
    }

    private func demoPage(title: LocalizedStringKey, detail: LocalizedStringKey, mode: ImmersionMode) -> some View {
        chatPage {
            onboardingCopy(title, detail, titleIdentifier: mode == .fullMessages ? "mambo-deep-title" : "mambo-shallow-title")
            MamboDemoMessage(text: demoText, mode: mode)
            Spacer(minLength: 20)
            PrimaryButton(title: "Continue") { advance() }
                .accessibilityIdentifier("mambo-continue")
        }
    }

    private var invitePage: some View {
        fullPage {
            onboardingCopy("Invite a friend", "Invite a friend, then chat daily to build a streak.", titleIdentifier: "mambo-invite-title")
            Spacer(minLength: 20)
            ShareLink(item: MamboOnboardingCopy.shareMessage) {
                HStack(spacing: 10) {
                    Image(systemName: "square.and.arrow.up").font(.body.weight(.semibold))
                    Text("Invite a friend").font(.body.weight(.semibold))
                }
                .foregroundStyle(VipiDesign.onHighlight)
                .frame(maxWidth: .infinity, minHeight: 54).contentShape(Rectangle())
                .background(VipiDesign.highlight, in: RoundedRectangle(cornerRadius: 16))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("mambo-share")
            Button("Continue") { advance() }
                .font(.body.weight(.medium)).frame(minHeight: 48)
                .accessibilityIdentifier("mambo-invite-continue")
        }
    }

    private var privacyPage: some View {
        fullPage {
            onboardingCopy("Private by default", "Every chat—friend or group—is end-to-end encrypted with Signal Protocol. We can’t read them, and we don’t sell your data.", titleIdentifier: "mambo-privacy-title")
            Text("Start using a new language today. Questions? Contact us anytime.")
                .font(.body).foregroundStyle(VipiDesign.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 20)
            PrimaryButton(title: "Start using Vipi") { start() }
                .accessibilityIdentifier("mambo-start")
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 6) {
            MessageEditor(text: $draft, placeholder: String(localized: "Message"), focus: $composing,
                          maximumBytes: ConversationHistory.maximumDraftBytes, rejected: {})
                .padding(13).background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
                .overlay(RoundedRectangle(cornerRadius: 23).strokeBorder(
                    composing ? VipiDesign.focus : VipiDesign.outline, lineWidth: composing ? 1.5 : 1))
                .accessibilityIdentifier("mambo-message-input")
            if !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button(action: send) {
                    Image(systemName: "arrow.up").font(.body.weight(.semibold))
                        .frame(minWidth: 46, minHeight: 46).padding(6)
                        .foregroundStyle(VipiDesign.onHighlight)
                        .background(VipiDesign.highlight, in: Circle())
                }
                .buttonStyle(.plain).accessibilityLabel("Send")
                .accessibilityIdentifier("mambo-send")
            }
        }
        .padding(.horizontal, 14).padding(.bottom, 10).background(VipiDesign.canvas)
    }

    private var demoText: String {
        sentMessage?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? sentMessage! : ImmersionTutorialSource.text(state.knownLanguage)
    }

    private func send() {
        let value = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        sentMessage = value
        draft = ""
        composing = false
    }

    private func start() {
        if authentication.session?.userID != nil { state.onboarding = .account }
        else { accountSheet = true }
    }

    private func advance() {
        guard page + 1 < MamboPage.allCases.count else { start(); return }
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { page += 1 }
    }

    private func goBack() {
        guard page > 0 else { return }
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { page -= 1 }
    }

    private func fullPage<Content: View>(@ViewBuilder content: @escaping () -> Content) -> some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 24) { content() }
                    .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 20)
                    .frame(minHeight: proxy.size.height, alignment: .top)
                    .frame(maxWidth: 560).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }

    /// Chat examples share the production timeline's 18pt gutters and 644pt
    /// reading width so their bubbles align with real conversations.
    private func chatPage<Content: View>(@ViewBuilder content: @escaping () -> Content) -> some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 24) { content() }
                    .padding(.horizontal, 18).padding(.top, 10).padding(.bottom, 20)
                    .frame(minHeight: proxy.size.height, alignment: .top)
                    .frame(maxWidth: 644).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private func onboardingCopy(_ title: LocalizedStringKey, _ detail: LocalizedStringKey,
                                titleIdentifier: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.largeTitle.weight(.bold)).fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader).accessibilityIdentifier(titleIdentifier)
            Text(detail).font(.body).foregroundStyle(VipiDesign.secondary).lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func languageField(_ label: LocalizedStringKey, code: String, identifier: String,
                               choose: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.subheadline.weight(.medium)).foregroundStyle(VipiDesign.secondary)
            Button(action: choose) {
                HStack(spacing: 12) {
                    Text(VipiLanguage.named(code).localizedName).foregroundStyle(VipiDesign.ink)
                    Text(verbatim: VipiLanguage.named(code).localName).foregroundStyle(VipiDesign.secondary)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.down").font(.body.weight(.semibold)).foregroundStyle(VipiDesign.secondary)
                }
                .font(.body).padding(.horizontal, 16).padding(.vertical, 14)
                .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
                .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain).accessibilityLabel(label)
            .accessibilityValue(VipiLanguage.named(code).localizedName)
            .accessibilityIdentifier(identifier)
        }
    }

    private func languageSheet(_ kind: MamboLanguagePicker) -> some View {
        @Bindable var state = state
        let choices = kind == .known ? VipiLanguage.initial : VipiLanguage.initial.filter { $0.id != state.knownLanguage }
        let selection = kind == .known ? Binding(get: { state.knownLanguage }, set: { state.selectKnownLanguage($0) }) : Binding(get: { state.targetLanguage }, set: { state.targetLanguage = $0 })
        return NavigationStack {
            LanguageSelectionView(title: kind == .known ? "I speak" : "I’m learning", selection: selection,
                                  choices: choices, localName: kind == .target,
                                  practiceSource: kind == .target ? state.knownLanguage : nil)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { picker = nil } } }
        }
    }
}

/// Shared signed-out account action. The wizard and the signed-out inbox use
/// the same explanation and native sign-in entry point.
struct OnboardingAccountSheet: View {
    var continueWithoutAccount: (() -> Void)?
    @Environment(\.dismiss) private var dismiss
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VipiMark(size: 52, accessibleName: "Vipi")
                    Text("Create an account to chat with friends.")
                        .font(.title.bold()).fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    Text("Sign in or create an account to invite friends and chat securely. Every friend and group chat stays end-to-end encrypted with Signal Protocol.")
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let error = authentication.errorMessage {
                        Text(error).font(.subheadline).foregroundStyle(VipiDesign.destructive)
                    }
                    PrimaryButton(title: "Sign in", busy: authentication.busy) { authentication.signIn() }
                        .disabled(authentication.busy)
                        .accessibilityIdentifier("mambo-create-account")
                    Button("Not now") {
                        dismiss()
                        continueWithoutAccount?()
                    }
                    .font(.body).foregroundStyle(VipiDesign.secondary)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .accessibilityIdentifier("mambo-not-now")
                    legalLinks
                }
                .padding(26).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(VipiDesign.canvas)
            .navigationTitle("Account").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        }
        .presentationDetents(typeSize.isAccessibilitySize ? [.large] : [.medium, .large])
        .onChange(of: authentication.session?.userID) { _, user in if user != nil { dismiss() } }
    }

    private var legalLinks: some View {
        let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 12)) : AnyLayout(HStackLayout(spacing: 20))
        return layout {
            Link("Terms of Service", destination: URL(string: "https://mambovipi.app/terms.html")!)
                .frame(minHeight: 44)
            Link("Privacy Policy", destination: URL(string: "https://mambovipi.app/privacy.html")!)
                .frame(minHeight: 44)
        }.font(.subheadline)
    }
}

/// Transient translation demo. It shares the production translation owner,
/// bubble renderer and speech controls; closing it discards its display cache.
private struct MamboDemoMessage: View {
    let text: String
    let mode: ImmersionMode
    @Environment(AppState.self) private var state
    @State private var immersion: ConversationImmersion?
    @State private var configuredPair: TranslationPair?
    @State private var speech = SpeechPlayback()
    @State private var voiceHelp = false
    @State private var translationHelp: TranslationPair?

    private var pair: TranslationPair { .init(source: state.knownLanguage, target: state.targetLanguage) }
    private var messageID: String { "mambo-demo-" + pair.source + "-" + pair.target }

    var body: some View {
        MessageBubbleRow(outgoing: true) {
            Group {
                if let immersion, configuredPair == pair, immersion.pair == pair {
                    ConversationImmersionText(text: text, id: messageID, immersion: immersion, speech: speech,
                        paused: false, metadata: AnyView(demoMetadata), onVoiceHelp: { voiceHelp = true },
                        onTranslationSetup: { translationHelp = $0 })
                        .background { ConversationTranslationTask(immersion: immersion) }
                } else {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Preparing this example…").font(.subheadline).foregroundStyle(VipiDesign.messageSecondary(true))
                    }
                    .padding(.horizontal, 15).padding(.vertical, 12)
                }
            }
        }
        .accessibilityIdentifier("mambo-message-bubble")
        .task(id: "\(pair.source)-\(pair.target)-\(mode.rawValue)-\(text)") {
            let owner = immersion ?? state.translationServices.makeOwner()
            if immersion == nil { immersion = owner }
            await owner.configure(pair: pair, mode: mode)
            guard !Task.isCancelled else { return }
            owner.selectInputLanguage(pair.source, for: messageID)
            owner.warm([(id: messageID, text: text)])
            configuredPair = pair
            speech.prepare(source: pair.target, target: pair.target,
                           warmups: [pair.target: VipiLanguage.named(pair.target).localName])
        }
        .onDisappear {
            immersion?.close(); immersion = nil; configuredPair = nil
            speech.close(); state.chatReading.cancelInteractions()
        }
        .alert("Speech isn’t available", isPresented: $voiceHelp) {
            Button("Retry voices") { speech.prepare(source: pair.target, target: pair.target,
                                                    warmups: [pair.target: VipiLanguage.named(pair.target).localName]) }
            Button("OK", role: .cancel) {}
        } message: { Text(speech.error ?? String(localized: "The voice for this language isn’t ready.")) }
        .sheet(isPresented: Binding(get: { translationHelp != nil }, set: { if !$0 { translationHelp = nil } }),
               onDismiss: {
                   guard let immersion else { return }
                   immersion.retry(immersion.identity(messageID: messageID, text: text))
               }) {
            if let translationHelp {
                NavigationStack {
                    LanguageDownloadView(requestedPair: translationHelp)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { self.translationHelp = nil } } }
                }
            }
        }
    }

    private var demoMetadata: some View {
        let value: String = {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-vipi-onboarding-screenshot-fixture") { return "9:41 AM" }
            #endif
            return Date().formatted(date: .omitted, time: .shortened)
        }()
        return HStack(spacing: 4) {
            Text(value).monospacedDigit()
            MessageDeliveryMark(state: "accepted")
        }
        .font(.caption2)
        .fixedSize(horizontal: true, vertical: false)
        .foregroundStyle(VipiDesign.messageSecondary(true))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("mambo-message-meta")
    }
}
