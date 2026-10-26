import SwiftUI
import VipiCore

enum ConversationExamples {
    struct Word: Decodable { let surface: String; let reading: String? }
    struct Language: Decodable { let text: String; let reading: String?; let words: [String: Word] }
    struct Examples: Decodable { let languages: [String: Language] }
    static let examples: Examples? = {
        guard let url = Bundle.main.url(forResource: "immersion-preview", withExtension: "json"), let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Examples.self, from: data)
    }()
    static func result(source: String, target: String) -> ImmersionResult? {
        guard source != target else { return nil }
        guard let from = examples?.languages[source], let to = examples?.languages[target] else { return nil }
        let entries = from.words.keys.sorted().compactMap { key -> VocabularyEntry? in
            guard let original = from.words[key], let destination = to.words[key] else { return nil }
            return VocabularyEntry(source: original.surface, targets: [destination.surface],
                romanizations: destination.reading.map { [destination.surface: [$0]] } ?? [:])
        }
        return LocalImmersion.align(original: from.text, translation: to.text, entries: entries, density: 0.5, source: source, target: target)
    }
}

struct ConversationPreview: View {
    let source: String
    let target: String
    var scrolling = false
    @State private var mode: ReadingMode = .immersed
    @State private var speech = SpeechPlayback()
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        if let result = ConversationExamples.result(source: source, target: target) {
            VStack(alignment: .leading, spacing: 10) {
                Text("CONVERSATION PREVIEW").font(.caption2.weight(.semibold)).tracking(1.2).foregroundStyle(VipiDesign.secondary)
                ImmersionBubble(result: result, mode: mode, speech: speech, sourceLanguage: source, targetLanguage: target,
                    messageID: "language-preview-\(source)-\(target)", interactionPaused: scrolling, fullReading: ConversationExamples.examples?.languages[target]?.reading)
                Text("A sample plan with a friend. Words keep switching; their meaning stays close.").font(.footnote).foregroundStyle(VipiDesign.secondary)
                Button(mode == .translation ? "Back to immersion" : "See the whole thought in \(VipiLanguage.named(target).name)") {
                    mode = mode == .translation ? .immersed : .translation
                }.font(.footnote.weight(.semibold)).frame(minHeight: 44)
                if let error = speech.error { Text(error).font(.footnote).foregroundStyle(VipiDesign.secondary) }
            }.padding(16).background(VipiDesign.outgoing.opacity(0.48), in: RoundedRectangle(cornerRadius: 28))
                .task { speech.prepare(source: source, target: target, warmups: [source: result.original, target: result.translation]) }
                .onDisappear { speech.close() }
                .onChange(of: scenePhase) { _, phase in if phase != .active { speech.stop() } }
        }
    }
}
