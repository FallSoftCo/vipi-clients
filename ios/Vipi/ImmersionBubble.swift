import SwiftUI
import VipiCore

enum ReadingMode: String, CaseIterable, Identifiable {
    case immersed = "Immersed", original = "Original", translation = "Translation"
    var id: String { rawValue }
}

struct ImmersionBubble: View {
    let result: ImmersionResult
    var outgoing = false
    var mode: ReadingMode = .immersed
    var speech: SpeechPlayback?
    var sourceLanguage = "en"
    var targetLanguage = "es"
    @State private var revealed = Set<Int>()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var attributed: AttributedString {
        if mode == .original { return AttributedString(result.original) }
        if mode == .translation { return AttributedString(result.translation) }
        var text = AttributedString()
        let ns = result.original as NSString
        var cursor = 0
        for span in result.spans {
            if span.range.location > cursor { text += AttributedString(ns.substring(with: NSRange(location: cursor, length: span.range.location - cursor))) }
            var word = AttributedString(revealed.contains(span.id) ? span.original : span.displayedTarget)
            word.foregroundColor = VipiDesign.highlight
            word.font = .body.weight(.semibold)
            word.underlineStyle = .single
            word.link = URL(string: "vipi-reveal://word/\(span.id)")
            text += word
            cursor = NSMaxRange(span.range)
        }
        if cursor < ns.length { text += AttributedString(ns.substring(from: cursor)) }
        return text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(attributed).font(.body).lineSpacing(5)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let speech {
                HStack {
                    Spacer()
                    let active = speech.activeMessage == "onboarding-example"
                    Button {
                        let spans: [(text: String, language: String)]
                        switch mode {
                        case .original: spans = [(result.original, sourceLanguage)]
                        case .translation: spans = [(result.translation, targetLanguage)]
                        case .immersed: spans = result.speech(source: sourceLanguage, target: targetLanguage, revealed: revealed).map { ($0.text, $0.language) }
                        }
                        speech.toggle(message: "onboarding-example", spans: spans)
                    } label: {
                        HStack(spacing: 7) {
                            if speech.state == .preparing || (active && speech.state == .rendering) { ProgressView().controlSize(.small) }
                            else { Image(systemName: active ? "stop.fill" : "speaker.wave.2") }
                            Text(active ? "Stop" : speech.state == .preparing ? "Preparing voices" : "Listen")
                        }.font(.footnote.weight(.medium)).frame(minWidth: 44, minHeight: 44)
                    }.disabled(speech.state == .preparing || speech.state == .unavailable)
                        .accessibilityIdentifier("messageListen")
                }
            }
        }.padding(.horizontal, 20).padding(.top, 20).padding(.bottom, speech == nil ? 20 : 6)
            .background(outgoing ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
            .environment(\.openURL, OpenURLAction { url in
                guard url.scheme == "vipi-reveal", let id = Int(url.lastPathComponent), result.spans.contains(where: { $0.id == id }) else { return .systemAction }
                speech?.stop()
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.15)) {
                    if revealed.contains(id) { revealed.remove(id) } else { revealed.insert(id) }
                }
                return .handled
            })
            .onChange(of: result) { revealed.removeAll(); speech?.stop() }
            .onChange(of: mode) { speech?.stop() }
            .accessibilityHint(mode == .immersed ? "Activate an underlined word to reveal its meaning in place." : "")
    }
}

enum ImmersionPreview {
    // An original authored onboarding example. Not a downloaded production pack.
    static let result = ImmersionEngine().align(
        original: "Coffee tomorrow? I know a little place by the river.",
        translation: "¿Café mañana? Conozco un pequeño lugar junto al río.",
        entries: [.init(source: "Coffee", targets: ["Café"]), .init(source: "tomorrow", targets: ["mañana"]), .init(source: "river", targets: ["río"])],
        density: 0.3)
}
