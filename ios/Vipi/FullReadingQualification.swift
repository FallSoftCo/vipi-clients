#if DEBUG
import SwiftUI
import VipiCore

/// Curated native presentation QA with supplied target strings. It never sends
/// a message, changes a real conversation, or claims provider inference.
struct FullReadingQualificationView: View {
    private enum Fixture: String, CaseIterable {
        case local = "Local", authored = "Authored", unknown = "Unknown"
        func source(_ language: String) -> String {
            switch self {
            case .local: language == "ko" ? "We go to school together." : "The bank manager is walking."
            case .authored: "I need water."
            case .unknown: "How do you read these characters?"
            }
        }
        func target(_ language: String) -> String {
            switch self {
            case .local: language == "ko" ? "같이 학교에 갑니다." : "银行行长正在走路。"
            case .authored: language == "ko" ? "물이 필요해요." : "我需要水。"
            case .unknown: language == "ko" ? "𠮷에게 메시지를 보내요." : "𠮷先生与𰻞字怎么读？"
            }
        }
    }
    @State private var fixture = Fixture.local
    @State private var reading: FullReading?
    @State private var ready = false
    @State private var mode = ReadingMode.translation
    @State private var speech = SpeechPlayback()
    @State private var cache = FullReadingCache(policy: FullSentenceReadings.policy) {
        FullSentenceReadings.resolve($0, language: $1)
    }
    private let language = ProcessInfo.processInfo.arguments.contains("-vipi-korean-reading-fixture") ? "ko" : "zh"
    private var result: ImmersionPresentation {
        .complete(ImmersionEngine().align(original: fixture.source(language), translation: fixture.target(language), entries: [], density: 0))
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Reading QA · supplied target text").font(.footnote).foregroundStyle(VipiDesign.secondary)
                    Picker("Fixture", selection: $fixture) {
                        ForEach(Fixture.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented)
                    ImmersionBubble(result: result, mode: mode, speech: speech,
                        sourceLanguage: "en", targetLanguage: language, messageID: "reading-qa-" + fixture.rawValue,
                        fullReading: reading?.text, onModeChange: { mode = $0 })
                        .id(fixture)
                    Text(ready ? (reading?.provenance.rawValue ?? "unavailable") : "pending metadata").font(.footnote)
                        .accessibilityIdentifier("reading-qa-provenance")
                }.padding()
            }.background(VipiDesign.canvas).navigationTitle(language == "ko" ? "Korean reading" : "Chinese reading")
        }
        .task { speech.prepare(source: "en", target: language, warmups: ["en": "Hello.", language: language == "ko" ? "안녕하세요." : "你好。"]) }
        .task(id: fixture) {
            ready = false; reading = nil; mode = .translation
            let active = fixture
            let value = await cache.resolve(text: active.target(language), language: language)
            guard !Task.isCancelled, active == fixture else { return }
            reading = value; ready = true
        }
        .onDisappear { speech.stop(); cache.removeAll() }
    }
}
#endif
