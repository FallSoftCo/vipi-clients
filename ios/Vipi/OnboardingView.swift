import SwiftUI

struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var previewMode: ReadingMode = .immersed
    @State private var search = ""
    @State private var acceptedTerms = false
    @State private var speech = SpeechPlayback()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 32) {
                        HStack(spacing: 10) {
                            VipiMark(size: 34)
                            Text("vipi").font(.system(size: 27, weight: .semibold, design: .rounded)).tracking(-1)
                            Spacer()
                            if state.onboarding != .welcome {
                                Text(state.onboarding == .language ? "1 of 2" : "2 of 2").font(.caption).foregroundStyle(VipiDesign.secondary)
                            }
                        }.padding(.top, 18)
                        switch state.onboarding {
                        case .welcome: welcome
                        case .language: languages
                        case .account: account
                        }
                    }.padding(.horizontal, 26).padding(.bottom, 24).frame(maxWidth: 560)
                        .frame(maxWidth: .infinity)
                }
            }
            .safeAreaInset(edge: .bottom) { bottomAction }
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
        VStack(alignment: .leading, spacing: 30) {
            IntroHeading(eyebrow: "A little more language. A lot more life.", title: "Your conversations.\nA new language.", detail: "Chat about what matters to you. Pick up another language along the way.")
            VStack(alignment: .leading, spacing: 14) {
                HStack { Text("TRY A LITTLE SPANISH").font(.caption2.weight(.semibold)).tracking(1.4); Spacer(); Image(systemName: "hand.tap") }.foregroundStyle(VipiDesign.secondary)
                ImmersionBubble(result: ImmersionPreview.result, mode: previewMode, speech: speech)
                if let error = speech.error {
                    Text(error).font(.footnote).foregroundStyle(VipiDesign.secondary)
                    if speech.state == .unavailable { Button("Retry voices") { preparePreviewVoices() }.font(.footnote) }
                }
                Text("Tap an underlined word. Its meaning is right there.").font(.footnote).foregroundStyle(VipiDesign.secondary).lineSpacing(3)
                Button {
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.18)) {
                        previewMode = previewMode == .translation ? .immersed : .translation
                    }
                } label: {
                    Label(previewMode == .translation ? "Back to a little Spanish" : "See the whole thought in Spanish", systemImage: "arrow.triangle.2.circlepath")
                        .font(.footnote.weight(.semibold)).frame(minHeight: 44, alignment: .leading)
                }
            }.padding(20).background(VipiDesign.outgoing.opacity(0.48), in: RoundedRectangle(cornerRadius: 28))
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "leaf").font(.title3).foregroundStyle(VipiDesign.highlight)
                Text("No lessons to finish. No streak to keep. Just the words in your world.").font(.subheadline).foregroundStyle(VipiDesign.secondary).lineSpacing(3)
            }
        }.onAppear { preparePreviewVoices() }
            .onDisappear { speech.close() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { speech.stop() } }
    }

    private func preparePreviewVoices() { speech.prepare(source: "en", target: "es", warmups: ["en": "Hello.", "es": "Hola."]) }

    private var languages: some View {
        @Bindable var state = state
        return VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "Make it your world", title: "What language\nwill you live in?", detail: "Start with one. You can change it whenever you like.")
            VStack(alignment: .leading, spacing: 10) {
                Text("I already speak").font(.subheadline.weight(.medium)).foregroundStyle(VipiDesign.secondary)
                Picker("I already speak", selection: $state.knownLanguage) {
                    ForEach(VipiLanguage.initial) { Text($0.name).tag($0.id) }
                }.pickerStyle(.menu).tint(.primary).padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 16))
                    .onChange(of: state.knownLanguage) { _, value in
                        if value == state.targetLanguage { state.targetLanguage = value == "es" ? "en" : "es" }
                    }
            }
            Text("I want to pick up").font(.subheadline.weight(.medium)).foregroundStyle(VipiDesign.secondary)
            VStack(spacing: 0) {
                ForEach(VipiLanguage.initial.filter { $0.id != state.knownLanguage }) { language in
                    Button { state.targetLanguage = language.id } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(language.name).font(.body.weight(.medium)).foregroundStyle(.primary)
                                Text(language.localName).font(.footnote).foregroundStyle(VipiDesign.secondary)
                            }
                            Spacer()
                            Image(systemName: state.targetLanguage == language.id ? "checkmark.circle.fill" : "circle")
                                .font(.title3).foregroundStyle(state.targetLanguage == language.id ? VipiDesign.highlight : Color.secondary.opacity(0.35))
                        }.padding(.horizontal, 18).padding(.vertical, 14).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityAddTraits(state.targetLanguage == language.id ? .isSelected : [])
                    if language.id != VipiLanguage.initial.last?.id { Divider().padding(.leading, 18) }
                }
            }.background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 20))
            Label("Language downloads stay on your phone. You choose when to download them.", systemImage: "arrow.down.circle")
                .font(.footnote).foregroundStyle(VipiDesign.secondary)
        }
    }

    private var account: some View {
        VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "A place for your people", title: "Say hello\nas yourself.", detail: "Create an account or sign in. Your email stays private; friends will find you by your username.")
            VStack(alignment: .leading, spacing: 20) {
                Label("Your chats belong to you.", systemImage: "bubble.left.and.bubble.right")
                Label("Your immersion happens on your phone.", systemImage: "iphone")
                Label("You decide who can reach you.", systemImage: "person.crop.circle.badge.checkmark")
            }.font(.subheadline).padding(22).frame(maxWidth: .infinity, alignment: .leading)
                .background(VipiDesign.surface, in: RoundedRectangle(cornerRadius: 22))
            Toggle(isOn: $acceptedTerms) {
                Text("I agree to the Terms of Service and have read the Privacy Policy.").font(.footnote).foregroundStyle(VipiDesign.secondary)
            }.tint(VipiDesign.accent)
            HStack(spacing: 20) {
                Link("Terms of Service", destination: URL(string: "https://fallsoft.co/terms-of-service")!)
                Link("Privacy Policy", destination: URL(string: "https://fallsoft.co/privacy-policy")!)
            }.font(.footnote)
            if let signInError = authentication.errorMessage { Text(signInError).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("signInError") }
        }
    }

    private var bottomAction: some View {
        VStack(spacing: 12) {
            PrimaryButton(title: state.onboarding == .welcome ? "Find your language" : state.onboarding == .language ? "Continue with \(VipiLanguage.named(state.targetLanguage).name)" : "Continue to sign in", busy: authentication.busy) {
                switch state.onboarding {
                case .welcome: advance(.language)
                case .language: advance(.account)
                case .account: authentication.signIn()
                }
            }.disabled(state.onboarding == .account && !acceptedTerms).opacity(state.onboarding == .account && !acceptedTerms ? 0.5 : 1)
            if state.onboarding == .welcome { Text("Learn through life, one conversation at a time.").font(.caption).foregroundStyle(VipiDesign.secondary) }
        }.padding(.horizontal, 26).padding(.top, 14).padding(.bottom, 12)
            .frame(maxWidth: 560).frame(maxWidth: .infinity).background(VipiDesign.canvas)
    }
    private func advance(_ step: OnboardingStep) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { state.onboarding = step }
    }
}
