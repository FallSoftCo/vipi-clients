import SwiftUI

extension EnvironmentValues {
    @Entry var tutorialShowsOriginal = false
}

/// An optional real local preview. It has no ChatSession, MessageVault or send
/// boundary; same-pair toggles keep only this transient owner's word plans.
struct ImmersionTutorialContent: View {
    var scrolling = false
    var demonstratesHold = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    private enum Finger { case hidden, approach, hold }
    @State private var finger: Finger = .hidden
    @State private var demonstrationEnded = false
    @State private var exampleVisible = false
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var immersion = ConversationImmersion()
    @State private var configuredPair: TranslationPair?
    @State private var speech = SpeechPlayback()
    @State private var preparation = LanguagePreparation()
    private var pair: TranslationPair { .init(source:state.knownLanguage,target:state.targetLanguage) }
    private var text: String { ImmersionTutorialSource.text(pair.source) }
    private var messageID: String { ImmersionTutorialSource.messageID(source:pair.source,target:pair.target) }
    private var translatedExample: Bool {
        let identity = immersion.identity(messageID: messageID, text: text)
        guard let translation = immersion.translation(for: identity) else { return false }
        return translation.practiceText != translation.meaningText
    }
    private var canDemonstrate: Bool {
        demonstratesHold && exampleVisible && !scrolling && !voiceOver && scenePhase == .active && translatedExample
    }
    private func stopDemonstrating() {
        if demonstratesHold { demonstrationEnded = true; finger = .hidden }
    }
    private func demonstrate() async {
        guard canDemonstrate, !demonstrationEnded, !reduceMotion else { return }
        do {
            try await Task.sleep(for: .milliseconds(450))
            guard !demonstrationEnded else { return }
            finger = .approach
            try await Task.sleep(for: .milliseconds(450))
            guard !demonstrationEnded else { return }
            finger = .hold
            try await Task.sleep(for: .milliseconds(1250))
            stopDemonstrating()
        } catch { finger = .hidden }
    }
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            Text("Immersion").font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("tutorial-title")
            VStack(alignment:.leading,spacing:8) {
                ImmersionModeChoices(mode:state.immersionMode) { choice in
                    stopDemonstrating()
                    guard choice != state.immersionMode else { return }
                    speech.stop(); state.chatReading.cancelInteractions(); state.immersionMode = choice
                }
                Text(state.immersionMode == .incremental ? String(localized:"One new word at a time") : String(localized:"The whole message"))
                    .foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
            }
            Group {
                if configuredPair == pair && immersion.inputLanguage(for:messageID) == pair.source {
                    ConversationImmersionText(text:text,id:messageID,immersion:immersion,speech:speech,
                        paused:scrolling,metadata:AnyView(EmptyView()),onVoiceHelp:prepareVoice,
                        onTranslationSetup:{ _ in preparation.prepare() })
                } else { ProgressView().frame(maxWidth:.infinity,minHeight:64) }
            }
            .environment(\.tutorialShowsOriginal, demonstratesHold && !reduceMotion && finger == .hold)
            .padding(.trailing, demonstratesHold ? 32 : 0)
            .overlay(alignment: .trailing) {
                if canDemonstrate, !demonstrationEnded, reduceMotion || finger != .hidden {
                    ZStack {
                        Circle().stroke(VipiDesign.highlight, lineWidth: 1.5)
                            .frame(width: 17, height: 17).offset(x: -4, y: -6)
                        Image(systemName: "hand.point.up.left.fill")
                            .font(.body).foregroundStyle(VipiDesign.highlight)
                    }.padding(.trailing, 8)
                    .scaleEffect(finger == .approach ? 1.1 : 1)
                    .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: finger)
                    .allowsHitTesting(false).accessibilityHidden(true)
                }
            }
            .onScrollVisibilityChange(threshold: 0.3) { exampleVisible = $0 }
            .task(id: canDemonstrate && !reduceMotion) { await demonstrate() }
            .background { RoundedRectangle(cornerRadius: 18).fill(VipiDesign.incomingBubble) }
            .accessibilityIdentifier("tutorial-message")
            .background { ConversationTranslationTask(immersion:immersion) }
            .background { ChatReadingGestureSurface(reading:state.chatReading, onTouch: { stopDemonstrating() }) }
            let preview = immersion.identity(messageID:messageID,text:text)
            if immersion.translation(for:preview) != nil || (immersion.phase(for:preview) == .translating && immersion.previousModeTranslation(for:preview) != nil) {
            VStack(alignment:.leading,spacing:6) {
                if speech.state == .ready || speech.state == .rendering || speech.state == .playing { Text("Tap to hear it") }
                Text("Hold to see the original")
                if state.chatReading.hasAlternateScript { Text("Double-tap to change script") }
            }.font(.body).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
            }
            if preparation.busy || preparation.availability == .checking {
                HStack(spacing:8) { ProgressView(); Text("Preparing translation…") }
                    .font(.subheadline).foregroundStyle(VipiDesign.secondary)
            }
            if let request = preparation.request { LanguagePreparationTask(request:request,preparation:preparation).id(request.id) }
            if speech.state == .preparing {
                Text("Preparing voice…").font(.subheadline).foregroundStyle(VipiDesign.secondary)
            } else if speech.state == .unavailable {
                if let error = speech.error { Text(error).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true) }
                Button("Try again",action:prepareVoice).frame(minHeight:44)
            }
        }
        .foregroundStyle(VipiDesign.ink)
        .task(id:pair) {
            immersion.close(); immersion = state.translationServices.makeOwner()
            preparation.invalidate(); preparation = state.translationServices.makePreparation()
            await immersion.configure(pair:pair,mode:state.immersionMode)
            immersion.selectInputLanguage(pair.source,for:messageID); configuredPair = pair
            prepareVoice()
            await preparation.refresh(pair)
            if !Task.isCancelled { preparation.prepare() }
        }
        .task(id:"\(configuredPair?.source ?? "")-\(configuredPair?.target ?? "")-\(state.immersionMode.rawValue)") {
            guard configuredPair == pair else { return }
            await immersion.configure(pair:pair,mode:state.immersionMode)
            immersion.selectInputLanguage(pair.source,for:messageID)
        }
        .onChange(of:preparation.prepared) { _,ready in if ready { immersion.retry(immersion.identity(messageID:messageID,text:text)) } }
        .onChange(of:state.chatReading.showingMeaning) { _,held in if held { speech.stop() } }
        .onChange(of:scrolling) { _,moving in if moving { speech.stop(); state.chatReading.cancelInteractions() } }
        .onChange(of:scenePhase) { _,phase in if phase != .active { speech.stop(); state.chatReading.cancelInteractions() } }
        .onDisappear { immersion.close(); configuredPair = nil; preparation.invalidate(); speech.close(); state.chatReading.cancelInteractions() }
    }
    private func prepareVoice() {
        speech.prepare(source:pair.target,target:pair.target,warmups:[pair.target:VipiLanguage.named(pair.target).localName])
    }
}

/// Existing users can revisit without navigating away from their account/chat.
struct ImmersionTutorialView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var scrolling = false
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:24) {
                ImmersionTutorialContent(scrolling:scrolling, demonstratesHold:true)
                if dynamicTypeSize.isAccessibilitySize { finish }
            }.padding(26).frame(maxWidth:560).frame(maxWidth:.infinity)
        }
        .clipped().background(VipiDesign.canvas)
        .onScrollPhaseChange { _,phase in scrolling = phase != .idle }
        .safeAreaInset(edge:.bottom) { if !dynamicTypeSize.isAccessibilitySize { finish.padding(26).background(VipiDesign.canvas) } }
        .navigationBarTitleDisplayMode(.inline)
    }
    private var finish: some View { PrimaryButton(title:"Continue") { dismiss() }.accessibilityIdentifier("tutorial-continue") }
}
