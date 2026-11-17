import SwiftUI

struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.locale) private var locale
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
                    VStack(alignment: .leading, spacing: state.onboarding == .language ? 16 : 24) {
                        HStack(spacing: 10) {
                            VipiMark(size: 34)
                            Text(verbatim: "vipi").font(.system(.title, design: .rounded).weight(.semibold)).tracking(-1)
                            Spacer()
                            if state.onboarding != .welcome {
                                Text(dynamicTypeSize.isAccessibilitySize
                                     ? (state.onboarding == .language ? "1 of 2" : "2 of 2")
                                     : (state.onboarding == .language ? "Language · 1 of 2" : "Account · 2 of 2"))
                                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
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
                .clipped() // Keep scrolling content out of the opaque system status area.
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
            IntroHeading(eyebrow: "", title: "Chat with friends.\nLearn new words.", detail: "A few words switch languages as you chat.")
            VStack(alignment: .leading, spacing: 14) {
                Text("Try a little Spanish").font(.body.weight(.semibold)).foregroundStyle(VipiDesign.ink)
                ImmersionBubble(result: .complete(ImmersionPreview.result), mode: previewMode, speech: speech, interactionPaused: scrolling)
                if let error = speech.error {
                    Text(error).font(.subheadline).foregroundStyle(VipiDesign.secondary)
                    if speech.state == .unavailable { Button("Retry voices") { preparePreviewVoices() }.font(.footnote) }
                }
                Text("Tap a highlighted word to see its meaning.").font(.subheadline).foregroundStyle(VipiDesign.secondary).lineSpacing(3)
            }
        }.onAppear { preparePreviewVoices() }
            .onDisappear { speech.close() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { speech.stop() } }
    }

    private func preparePreviewVoices() { speech.prepare(source: "en", target: "es", warmups: ["en": "Hello.", "es": "Hola."]) }

    private var languages: some View {
        VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "", title: "Your languages", detail: "", showsDetail: false)
            VStack(alignment: .leading, spacing: 10) {
                Text("I speak").font(.body.weight(.semibold))
                Menu {
                    ForEach(VipiLanguage.initial) { language in
                        Button { state.selectKnownLanguage(language.id) } label: {
                            Text(language.localizedName)
                            if state.knownLanguage == language.id { Image(systemName: "checkmark") }
                        }
                    }
                } label: { languageLabel(state.knownLanguage) }
                    .accessibilityLabel("I speak")
                    .accessibilityValue(VipiLanguage.named(state.knownLanguage).localizedName)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text("I’m learning").font(.body.weight(.semibold))
                Menu {
                    ForEach(VipiLanguage.initial.filter { $0.id != state.knownLanguage }) { language in
                        Button { state.targetLanguage = language.id } label: {
                            Text("\(language.localizedName) · \(language.localName)")
                            if state.targetLanguage == language.id { Image(systemName: "checkmark") }
                        }
                    }
                } label: { languageLabel(state.targetLanguage) }
                    .accessibilityLabel("I’m learning")
                    .accessibilityValue(VipiLanguage.named(state.targetLanguage).localizedName)
            }
            ConversationPreview(source: state.knownLanguage, target: state.targetLanguage, scrolling: scrolling)
                .id("\(state.knownLanguage)-\(state.targetLanguage)")
        }
    }

    private func languageLabel(_ code: String) -> some View {
        HStack(spacing: 12) {
            Text(VipiLanguage.named(code).localizedName).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Image(systemName: "chevron.down").font(.body.weight(.semibold))
        }.font(.body).foregroundStyle(VipiDesign.ink)
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
    }

    private var account: some View {
        VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "", title: "Sign in to Vipi", detail: "Sign in, choose a username, and find your friends.")
            VStack(alignment: .leading, spacing: 16) {
                Label("Private chats with friends", systemImage: "lock")
                    .font(.body.weight(.semibold))
                Text("Chats with friends are end-to-end encrypted. Friends see your username, never your email.")
                    .font(.body).foregroundStyle(VipiDesign.secondary)
                Text("30 days free. No card needed. Then choose whether to subscribe.")
                    .font(.body.weight(.medium))
            }
            Toggle(isOn: $acceptedTerms) {
                Text("I agree to the Terms of Service and have read the Privacy Policy.").font(.subheadline).foregroundStyle(VipiDesign.secondary)
            }.tint(VipiDesign.highlight)
            legalLinks
            if let signInError = authentication.errorMessage { Text(signInError).font(.subheadline).foregroundStyle(VipiDesign.destructive).accessibilityIdentifier("signInError") }
        }
    }

    private var legalLinks: some View {
        let layout = dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 20)) : AnyLayout(HStackLayout(spacing: 20))
        return layout {
                Link("Terms of Service", destination: URL(string: "https://api.mambovipi.app/terms")!).frame(minHeight: 44)
                Link("Privacy Policy", destination: URL(string: "https://api.mambovipi.app/privacy")!).frame(minHeight: 44)
            }.font(.subheadline)
    }

    private var bottomAction: some View {
        VStack(spacing: 12) {
            PrimaryButton(title: state.onboarding == .welcome ? "Choose languages" : state.onboarding == .language ? "Continue" : "Continue to sign in", busy: authentication.busy) {
                switch state.onboarding {
                case .welcome: advance(.language)
                case .language: advance(.account)
                case .account: authentication.signIn()
                }
            }.disabled(state.onboarding == .account && !acceptedTerms).opacity(state.onboarding == .account && !acceptedTerms ? 0.5 : 1)
        }.padding(.horizontal, dynamicTypeSize.isAccessibilitySize ? 0 : 26).padding(.top, 14).padding(.bottom, 12)
            .frame(maxWidth: 560).frame(maxWidth: .infinity).background(VipiDesign.canvas)
    }
    private func advance(_ step: OnboardingStep) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { state.onboarding = step }
    }
}
