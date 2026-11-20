import SwiftUI

struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Environment(AuthenticationManager.self) private var authentication
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.locale) private var locale
    @State private var preparation = LanguagePreparation()
    @State private var search = ""
    @State private var scrolling = false
    @State private var voiceState = SpeechState.preparing
    @State private var voiceProblem: String?
    @State private var voiceRetry = 0
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack {
            ZStack {
                VipiDesign.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: state.onboarding == .language ? 16 : 24) {
                        HStack(spacing: 10) {
                            VipiMark(size:64).accessibilityHidden(false).accessibilityLabel(Text(verbatim:"Vipi"))
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
            .task(id:"\(state.knownLanguage)-\(state.targetLanguage)-\(state.onboarding)") {
                guard state.onboarding == .language else { preparation.invalidate(); return }
                preparation.invalidate(); preparation = state.translationServices.makePreparation()
                await preparation.refresh(.init(source:state.knownLanguage,target:state.targetLanguage))
                if !Task.isCancelled { preparation.prepare() }
            }
        }
    }

    private var welcome: some View {
        VStack(alignment:.leading,spacing:24) {
            IntroHeading(eyebrow:"",title:"Chat with friends.\nLearn a language.",detail:"Vipi swaps in one new word at a time. Words you’ve seen show up again.")
        }
    }

    private var languages: some View {
        @Bindable var state = state
        return VStack(alignment: .leading, spacing: 24) {
            IntroHeading(eyebrow: "", title: "Your languages", detail: "", showsDetail: false)
            VStack(alignment: .leading, spacing: 10) {
                Text("I speak").font(.body.weight(.semibold))
                NavigationLink {
                    LanguageSelectionView(title: "I speak",
                        selection: Binding(get: { state.knownLanguage }, set: { state.selectKnownLanguage($0) }),
                        choices: VipiLanguage.initial, localName: false)
                } label: { languageLabel(state.knownLanguage) }
                    .accessibilityLabel("I speak")
                    .accessibilityValue(VipiLanguage.named(state.knownLanguage).localizedName)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text("I’m learning").font(.body.weight(.semibold))
                NavigationLink {
                    LanguageSelectionView(title: "I’m learning", selection: $state.targetLanguage,
                        choices: VipiLanguage.initial.filter { $0.id != state.knownLanguage }, localName: true)
                } label: { languageLabel(state.targetLanguage) }
                    .accessibilityLabel("I’m learning")
                    .accessibilityValue(VipiLanguage.named(state.targetLanguage).localizedName)
            }
            ConversationPreview(source:state.knownLanguage,target:state.targetLanguage,scrolling:scrolling,modelsReady:preparation.prepared,
                onVoiceState: { voiceState = $0; voiceProblem = $1 })
                .id("\(state.knownLanguage)-\(state.targetLanguage)-\(voiceRetry)")
            if voiceState == .unavailable, let voiceProblem {
                Text(voiceProblem).font(.body).foregroundStyle(VipiDesign.secondary)
                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("language-voice-problem")
                Button("Try again") { voiceRetry += 1 }.accessibilityIdentifier("language-voice-retry")
            } else if preparation.prepared && voiceState == .preparing {
                HStack { ProgressView(); Text("Preparing voices") }.font(.body).foregroundStyle(VipiDesign.secondary)
            }
            Text(ChatReadingState.gestureDescription(target:state.targetLanguage,hasAlternateScript:state.chatReading.hasAlternateScript && !state.chatReading.nativeScript,incremental:state.immersionMode == .incremental))
                .font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
                .accessibilityLabel(Text(ChatReadingState.actionDescription(showingMeaning:state.chatReading.showingMeaning,nativeScript:state.chatReading.nativeScript,hasAlternateScript:state.chatReading.hasAlternateScript,incremental:state.immersionMode == .incremental)))
                .accessibilityIdentifier("language-preview-gesture-hint")
            if preparation.busy || preparation.availability == .checking {
                HStack { ProgressView(); Text("Preparing translation downloads…").font(.subheadline) }.foregroundStyle(VipiDesign.secondary)
            } else if !preparation.prepared {
                Text(preparation.availability == .unsupported ? "Translation isn’t supported for this language pair on this device." : "Translation needs a language download.")
                    .font(.subheadline).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
                Button("Try again") { Task { await preparation.refresh(.init(source:state.knownLanguage,target:state.targetLanguage)); preparation.prepare() } }
            }
            if let message = preparation.message { Text(message).font(.subheadline).foregroundStyle(VipiDesign.secondary) }
            if let request = preparation.request { LanguagePreparationTask(request:request,preparation:preparation).id(request.id) }
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
                Text("Free to use. No subscription.")
                    .font(.body.weight(.medium))
            }
            legalLinks
            if let signInError = authentication.errorMessage { Text(signInError).font(.subheadline).foregroundStyle(VipiDesign.destructive).accessibilityIdentifier("signInError") }
        }
    }

    private var legalLinks: some View {
        let layout = dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 20)) : AnyLayout(HStackLayout(spacing: 20))
        return layout {
                Link(destination: URL(string: "https://api.mambovipi.app/terms")!) { Text("Terms of Service").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                Link(destination: URL(string: "https://api.mambovipi.app/privacy")!) { Text("Privacy Policy").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
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
            }.disabled(state.onboarding == .language && (!preparation.prepared || voiceState == .preparing || voiceState == .unavailable))
        }.padding(.horizontal, dynamicTypeSize.isAccessibilitySize ? 0 : 26).padding(.top, 14).padding(.bottom, 12)
            .frame(maxWidth: 560).frame(maxWidth: .infinity).background(VipiDesign.canvas)
    }
    private func advance(_ step: OnboardingStep) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { state.onboarding = step }
    }
}
