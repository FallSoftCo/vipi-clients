import SwiftUI

/// An ordinary source sentence goes through the same native translation service
/// as chats. No authored target text, dictionary or pretranslated preview asset.
struct ConversationPreview: View {
    let source: String
    let target: String
    var scrolling = false
    var modelsReady = false
    @Environment(AppState.self) private var state
    @State private var immersion = ConversationImmersion()
    @State private var speech = SpeechPlayback()
    private let sentence = "Hello! How are you?"
    var body: some View {
        ConversationImmersionText(text:sentence,id:"language-preview",immersion:immersion,speech:speech,
            paused:scrolling,metadata:AnyView(EmptyView()),onVoiceHelp:{
                speech.prepare(source:target,target:target,warmups:[target:VipiLanguage.named(target).localName])
            })
            .background(VipiDesign.surface,in:RoundedRectangle(cornerRadius:18))
            .background { ConversationTranslationTask(immersion:immersion) }
            .background { ChatReadingGestureSurface(reading:state.chatReading) }
            .task(id:"\(source)-\(target)-\(modelsReady)") {
                immersion.close(); immersion = state.translationServices.makeOwner()
                await immersion.configure(pair:.init(source:source,target:target))
                speech.close(); speech.prepare(source:target,target:target,warmups:[target:VipiLanguage.named(target).localName])
            }
            .onDisappear { immersion.close(); speech.close() }
    }
}
