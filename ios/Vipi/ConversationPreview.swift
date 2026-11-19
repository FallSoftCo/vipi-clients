import SwiftUI

/// A localized source greeting goes through the same native translation service
/// as chats. No authored target text, dictionary or pretranslated preview asset.
struct ConversationPreview: View {
    let source: String
    let target: String
    var scrolling = false
    var modelsReady = false
    var onVoiceState: (SpeechState, String?) -> Void = { _, _ in }
    @Environment(AppState.self) private var state
    @State private var immersion = ConversationImmersion()
    @State private var speech = SpeechPlayback()
    private var sentence: String { VipiLanguage.named(source).exampleGreeting }
    private var pair: TranslationPair { .init(source: source, target: target) }
    var body: some View {
        Group {
        if immersion.pair == pair && immersion.inputLanguage(for: "language-preview") == source {
        ConversationImmersionText(text:sentence,id:"language-preview",immersion:immersion,speech:speech,
            paused:scrolling,metadata:AnyView(EmptyView()),onVoiceHelp:{
                speech.prepare(source:target,target:target,warmups:[target:VipiLanguage.named(target).localName])
            })
        } else {
            ProgressView().frame(maxWidth: .infinity, minHeight: 64)
        }
        }
            .background(VipiDesign.surface,in:RoundedRectangle(cornerRadius:18))
            .background { ConversationTranslationTask(immersion:immersion) }
            .background { ChatReadingGestureSurface(reading:state.chatReading) }
            .onChange(of: speech.state, initial: true) { _, value in onVoiceState(value, speech.error) }
            .task(id:"\(source)-\(target)-\(modelsReady)") {
                onVoiceState(.preparing, nil)
                immersion.close(); immersion = state.translationServices.makeOwner()
                await Self.configure(immersion, pair: pair)
                speech.close(); speech.prepare(source:target,target:target,warmups:[target:VipiLanguage.named(target).localName])
            }
            .onDisappear { immersion.close(); speech.close(); onVoiceState(.preparing, nil) }
    }
    static func configure(_ owner: ConversationImmersion, pair: TranslationPair) async {
        await owner.configure(pair: pair)
        // We authored this input, so its language is known. The example must
        // not ask a classifier to choose an unprepared third-language route.
        owner.selectInputLanguage(pair.source, for: "language-preview")
    }
}
