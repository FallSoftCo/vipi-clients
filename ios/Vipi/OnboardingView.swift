import SwiftUI

struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var previewMode: ReadingMode = .immersed
    @State private var search = ""
    @State private var scrolling = false
    @State private var acceptedTerms = false
    @State private var speech = SpeechPlayback()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: state.onboarding == .welcome ? 24 : 32) {
                        HStack(spacing: 10) {
                            VipiMark(size: 34)
                            Text("vipi").font(.system(size: 27, weight: .semibold, design: .rounded)).tracking(-1)
                            Spacer()
                            if state.onboarding != .welcome {
                                Text(dynamicTypeSize.isAccessibilitySize
                                     ? (state.onboarding == .language ? "1 of 2" : "2 of 2")
                                     : (state.onboarding == .language ? "Language · 1 of 2" : "Account · 2 of 2"))
                                    .font(.caption).foregroundStyle(VipiDesign.secondary)
                                    .accessibilityLabel(LocalizedStringKey(state.onboarding == .language ? "Language, step 1 of 2" : "Account, step 2 of 2"))
                            }
                        }.padding(.top, 18)
                        switch state.onboarding {
                        case .welcome: welcome
                        case .language: languages
                        case .account: account
                        }
                        // Large controls belong in the scroll flow, so they cannot cover the form.
                        if dynamicTypeSize.isAccessibilitySize { bottomAction }
                    }.padding(.horizontal, 26).padding(.bottom, 24).frame(maxWidth: 560)
                        .frame(maxWidth: .infinity)
                }
                .id(state.onboarding) // Each onboarding step begins at its own heading.
            }
            .onScrollPhaseChange { _, phase in scrolling = phase != .idle }
            .onChange(of: state.onboarding) { _, _ in scrolling = false }
            .safeAreaInset(edge: .bottom) {
                if !dynamicTypeSize.isAccessibilitySize { bottomAction }
            }
            .toolbar {
                if state.onboarding != .welcome {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { advance(state.onboarding == .account ? .language : .welcome) } label: { Image(systemName: "chevron.left") }
                            .accessibilityLabel("Back")
                    }
                }
            }
            .toolbarBackground(VipiDesign.canvas, for: .navigationBar)
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "Language learning through chat", title: "Chat with friends.\nLearn new words.", detail: "Selected words and short phrases switch between your language and the language you choose. Word order and grammar stay the same.")
            VStack(alignment: .leading, spacing: 14) {
                HStack { Text("EXAMPLE: ENGLISH AND SPANISH").font(.caption2.weight(.semibold)).tracking(1.4); Spacer(); Image(systemName: "arrow.triangle.2.circlepath") }.foregroundStyle(VipiDesign.secondary)
                ImmersionBubble(result: .complete(ImmersionPreview.result), mode: previewMode, speech: speech, interactionPaused: scrolling)
                if let error = speech.error {
                    Text(error).font(.footnote).foregroundStyle(VipiDesign.secondary)
                    if speech.state == .unavailable { Button("Retry voices") { preparePreviewVoices() }.font(.footnote) }
                }
                Text("Watch the highlighted words switch in place. Tap Pause to stop them or Listen to hear pronunciation.").font(.footnote).foregroundStyle(VipiDesign.secondary).lineSpacing(3)
                Button {
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.18)) {
                        previewMode = previewMode == .original ? .immersed : .original
                    }
                } label: {
                    Label(LocalizedStringKey(previewMode == .original ? "Resume Spanish words" : "Show original message"), systemImage: "arrow.triangle.2.circlepath")
                        .font(.footnote.weight(.semibold)).frame(minHeight: 44, alignment: .leading)
                }
            }.padding(20).background(VipiDesign.outgoing.opacity(0.48), in: RoundedRectangle(cornerRadius: 28))
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "leaf").font(.title3).foregroundStyle(VipiDesign.highlight)
                Text("This is an example. In your chats, only supported words and phrases switch. The rest stays unchanged.").font(.subheadline).foregroundStyle(VipiDesign.secondary).lineSpacing(3)
            }
        }.onAppear { preparePreviewVoices() }
            .onDisappear { speech.close() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { speech.stop() } }
    }

    private func preparePreviewVoices() { speech.prepare(source: "en", target: "es", warmups: ["en": "Hello.", "es": "Hola."]) }

    private var languages: some View {
        @Bindable var state = state
        return VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "Language settings", title: "Choose your\nlanguages.", detail: "Choose the language you know and the one you want to learn. You can change these later.")
            VStack(alignment: .leading, spacing: 10) {
                Text("I already speak").font(.subheadline.weight(.medium)).foregroundStyle(VipiDesign.secondary)
                Picker("I already speak", selection: Binding(get: { state.knownLanguage }, set: { state.selectKnownLanguage($0) })) {
                    ForEach(VipiLanguage.initial) { Text($0.name).tag($0.id) }
                }.pickerStyle(.menu).tint(.primary).padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
            }
            Text("I want to learn").font(.subheadline.weight(.medium)).foregroundStyle(VipiDesign.secondary)
            Picker("I want to learn", selection: $state.targetLanguage) {
                ForEach(VipiLanguage.initial.filter { $0.id != state.knownLanguage }) { language in
                    Text("\(language.name) · \(language.localName)").tag(language.id)
                }
            }.pickerStyle(.menu).tint(.primary).padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
            ConversationPreview(source: state.knownLanguage, target: state.targetLanguage, scrolling: scrolling)
                .id("\(state.knownLanguage)-\(state.targetLanguage)")
            if ["ar", "zh", "ja", "ko"].contains(state.targetLanguage) {
                Text("Reading guides show words in Latin letters. Tap Listen to hear pronunciation.")
                    .font(.footnote).foregroundStyle(VipiDesign.secondary)
            }
            Label("Available words and phrases vary by language. Pronunciation may need a voice download.", systemImage: "arrow.down.circle")
                .font(.footnote).foregroundStyle(VipiDesign.secondary)
        }
    }

    private var account: some View {
        VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "Your account", title: "Sign in to\nchat with friends.", detail: "Create an account or sign in to an existing one. Friends find you by username, not your email.")
            VStack(alignment: .leading, spacing: 20) {
                Label("Find friends by username.", systemImage: "bubble.left.and.bubble.right")
                Label("Your email is not shown to friends.", systemImage: "iphone")
                Label("Chats with friends are end-to-end encrypted.", systemImage: "person.crop.circle.badge.checkmark")
                Label("New accounts include 30 days free. No payment method is required.", systemImage: "calendar")
            }.font(.subheadline).padding(22).frame(maxWidth: .infinity, alignment: .leading)
                .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 22))
            Toggle(isOn: $acceptedTerms) {
                Text("I agree to the Terms of Service and have read the Privacy Policy.").font(.footnote).foregroundStyle(VipiDesign.secondary)
            }.tint(VipiDesign.highlight)
            legalLinks
            if let signInError = authentication.errorMessage { Text(signInError).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("signInError") }
        }
    }

    private var legalLinks: some View {
        let layout = dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 20)) : AnyLayout(HStackLayout(spacing: 20))
        return layout {
                Link("Terms of Service", destination: URL(string: "https://api.mambovipi.app/terms")!)
                Link("Privacy Policy", destination: URL(string: "https://api.mambovipi.app/privacy")!)
            }.font(.footnote)
    }

    private var bottomAction: some View {
        VStack(spacing: 12) {
            PrimaryButton(title: state.onboarding == .welcome ? "Choose languages" : state.onboarding == .language ? "Continue with \(VipiLanguage.named(state.targetLanguage).name)" : "Continue to sign in", busy: authentication.busy) {
                switch state.onboarding {
                case .welcome: advance(.language)
                case .language: advance(.account)
                case .account: authentication.signIn()
                }
            }.disabled(state.onboarding == .account && !acceptedTerms).opacity(state.onboarding == .account && !acceptedTerms ? 0.5 : 1)
            if state.onboarding == .welcome && !dynamicTypeSize.isAccessibilitySize { Text("No account needed to try this example.").font(.caption).foregroundStyle(VipiDesign.secondary) }
        }.padding(.horizontal, dynamicTypeSize.isAccessibilitySize ? 0 : 26).padding(.top, 14).padding(.bottom, 12)
            .frame(maxWidth: 560).frame(maxWidth: .infinity).background(VipiDesign.canvas)
    }
    private func advance(_ step: OnboardingStep) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { state.onboarding = step }
    }
}
