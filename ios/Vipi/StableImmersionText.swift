import SwiftUI
import UIKit
import VipiCore

/// Native shaping, links, selection and copy. Natural paragraph forms share a
/// reserved bubble height, without blank padding around individual vocabulary.
@MainActor final class ImmersionNativeTextView: UITextView {
    var variants: [NSAttributedString] = []
    var reserveKey = ""
    var reserveHeight: CGFloat = 0
    var contentIdentity = ""
    var measurementContext = ""
    let measurer: UITextView = {
        let view = UITextView(); view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0; view.isScrollEnabled = false
        return view
    }()
    func reservedSize(width: CGFloat) -> CGSize {
        let key = "\(width)|\(variants.map(\.string))|\(variants.map { $0.length > 0 ? ($0.attribute(.font, at: 0, effectiveRange: nil) as? UIFont)?.pointSize ?? 0 : 0 })|\(traitCollection.preferredContentSizeCategory.rawValue)"
        let context = "\(width)|\(contentIdentity)|\(variants.first.flatMap { $0.length > 0 ? $0.attribute(.font, at: 0, effectiveRange: nil) as? UIFont : nil }?.pointSize ?? 0)"
        if context != measurementContext { measurementContext = context; reserveHeight = 0; reserveKey = "" }
        if reserveKey != key {
            reserveKey = key
            reserveHeight = max(reserveHeight, variants.map { variant in
                measurer.attributedText = variant
                return measurer.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude)).height
            }.max() ?? 0)
        }
        return CGSize(width: width, height: ceil(max(reserveHeight, sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude)).height)))
    }
}

struct StableImmersionText: UIViewRepresentable {
    let result: ImmersionResult
    let revealed: Set<Int>
    let script: Bool
    let onWord: (Int) -> Void
    let onSelection: (Bool) -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var scheme
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> ImmersionNativeTextView {
        let view = ImmersionNativeTextView()
        view.backgroundColor = .clear; view.isEditable = false; view.isSelectable = true; view.isScrollEnabled = false
        view.textContainerInset = .zero; view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.delegate = context.coordinator
        view.accessibilityIdentifier = "immersionText"
        view.linkTextAttributes = [:]
        return view
    }
    func updateUIView(_ view: ImmersionNativeTextView, context: Context) {
        context.coordinator.onWord = onWord; context.coordinator.onSelection = onSelection
        context.coordinator.updating = true
        defer { context.coordinator.updating = false }
        let category: UIContentSizeCategory
        switch typeSize {
        case .xSmall: category = .extraSmall
        case .small: category = .small
        case .medium: category = .medium
        case .large: category = .large
        case .xLarge: category = .extraLarge
        case .xxLarge: category = .extraExtraLarge
        case .xxxLarge: category = .extraExtraExtraLarge
        case .accessibility1: category = .accessibilityMedium
        case .accessibility2: category = .accessibilityLarge
        case .accessibility3: category = .accessibilityExtraLarge
        case .accessibility4: category = .accessibilityExtraExtraLarge
        default: category = .accessibilityExtraExtraExtraLarge
        }
        let font = UIFont.preferredFont(forTextStyle: .body, compatibleWith: UITraitCollection(preferredContentSizeCategory: category))
        let color = UIColor(VipiDesign.highlight).resolvedColor(with: view.traitCollection)
        view.contentIdentity = String(describing: result)
        let current = render(revealed: revealed, script: script, font: font, color: color)
        view.variants = [render(revealed: Set(result.spans.map(\.id)), script: false, font: font, color: color),
                         render(revealed: [], script: false, font: font, color: color),
                         render(revealed: [], script: true, font: font, color: color), current]
        var seen = Set<String>()
        view.variants = view.variants.filter { seen.insert($0.string).inserted }
        if !view.attributedText.isEqual(to: current) {
            let selection = view.selectedRange
            let sameText = view.attributedText.string == current.string
            view.attributedText = current
            if sameText && NSMaxRange(selection) <= current.length { view.selectedRange = selection }
        }
        view.accessibilityLabel = current.string
        view.accessibilityHint = "Words switch automatically. Use Reading options to pause or show the original."
        view.accessibilityCustomActions = result.spans.map { word in
            UIAccessibilityCustomAction(name: "Switch \(word.original) and \(word.displayedTarget)") { _ in onWord(word.id); return true }
        }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView view: ImmersionNativeTextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width > 0 else { return nil }
        return view.reservedSize(width: width)
    }
    private func render(revealed: Set<Int>, script: Bool, font: UIFont, color: UIColor) -> NSAttributedString {
        let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 5; paragraph.baseWritingDirection = .natural
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.label, .paragraphStyle: paragraph]
        let descriptor = font.fontDescriptor.addingAttributes([.traits: [UIFontDescriptor.TraitKey.weight: UIFont.Weight.semibold]])
        let emphasis = UIFont(descriptor: descriptor, size: font.pointSize)
        let text = NSMutableAttributedString(string: "")
        let original = result.original as NSString
        var cursor = 0
        for word in result.spans {
            if word.range.location > cursor { text.append(NSAttributedString(string: original.substring(with: NSRange(location: cursor, length: word.range.location - cursor)), attributes: attributes)) }
            let value = revealed.contains(word.id) ? word.original : (script ? word.translated : word.displayedTarget)
            var style = attributes
            style[.font] = emphasis; style[.foregroundColor] = color
            style[.link] = URL(string: "vipi-reveal://word/\(word.id)")!
            text.append(NSAttributedString(string: value, attributes: style))
            cursor = NSMaxRange(word.range)
        }
        if cursor < original.length { text.append(NSAttributedString(string: original.substring(from: cursor), attributes: attributes)) }
        return text
    }
    @MainActor final class Coordinator: NSObject, UITextViewDelegate {
        var updating = false
        var selectionActive = false
        var onWord: ((Int) -> Void)?
        var onSelection: ((Bool) -> Void)?
        func textViewDidChangeSelection(_ textView: UITextView) {
            guard !updating else { return }
            let selected = textView.selectedRange.length > 0
            guard selected != selectionActive else { return }
            selectionActive = selected; onSelection?(selected)
        }
        func textView(_ textView: UITextView, shouldInteractWith URL: URL, in characterRange: NSRange, interaction: UITextItemInteraction) -> Bool {
            guard URL.scheme == "vipi-reveal", let id = Int(URL.lastPathComponent) else { return false }
            onWord?(id); return false
        }
    }
}
