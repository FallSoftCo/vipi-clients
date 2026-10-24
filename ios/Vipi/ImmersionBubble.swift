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
            var word = AttributedString(revealed.contains(span.id) ? span.original : span.translated)
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
        Text(attributed).font(.body).lineSpacing(5)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
            .background(outgoing ? VipiDesign.outgoing : VipiDesign.surface, in: RoundedRectangle(cornerRadius: 23))
            .environment(\.openURL, OpenURLAction { url in
                guard url.scheme == "vipi-reveal", let id = Int(url.lastPathComponent), result.spans.contains(where: { $0.id == id }) else { return .systemAction }
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.15)) {
                    if revealed.contains(id) { revealed.remove(id) } else { revealed.insert(id) }
                }
                return .handled
            })
            .onChange(of: result.original) { revealed.removeAll() }
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
