import SwiftUI
import UIKit
import VipiCore

private extension NSAttributedString.Key {
    static let vipiOriginalRange = NSAttributedString.Key("co.fallsoft.vipi.original-range")
}

/// A native inline attachment reserves the same geometry for every word face.
/// Its visible text remains available to accessibility and selection/copy.
final class ImmersionWordAttachment: NSTextAttachment {
    let displayed: String
    let forms: [String]
    let font: UIFont
    let ink: UIColor
    let trailingWidth: CGFloat
    let copySlotID: Int?
    let copyShowsOriginal: Bool
    let copyRun: ImmersionCopyRun
    @MainActor init(displayed: String, forms: [String], font: UIFont, ink: UIColor, trailingWidth: CGFloat = 0, copySlotID: Int? = nil, copyShowsOriginal: Bool = true, copyRun: ImmersionCopyRun? = nil) {
        self.displayed = displayed; self.forms = forms; self.font = font; self.ink = ink
        self.trailingWidth = trailingWidth
        self.copySlotID = copySlotID; self.copyShowsOriginal = copyShowsOriginal
        self.copyRun = copyRun ?? .init(text: displayed, slotID: copySlotID, showsOriginal: copyShowsOriginal)
        super.init(data: nil, ofType: nil)
        accessibilityLabel = displayed
    }
    required init?(coder: NSCoder) { return nil }
    private var attributes: [NSAttributedString.Key: Any] {
        let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center; paragraph.lineBreakMode = .byWordWrapping
        return [.font: font, .foregroundColor: ink, .paragraphStyle: paragraph]
    }
    override func attachmentBounds(for textContainer: NSTextContainer?, proposedLineFragment lineFrag: CGRect, glyphPosition position: CGPoint, characterIndex charIndex: Int) -> CGRect {
        let available = max(1, (textContainer?.size.width ?? lineFrag.width) - 2 * (textContainer?.lineFragmentPadding ?? 0))
        let natural = forms.map { ($0 as NSString).size(withAttributes: [.font: font]).width }.max() ?? 0
        // Keep immediate closing punctuation on the attachment's line even
        // when a complete phrase needs several lines inside its stable block.
        let width = min(available - min(available * 0.25, trailingWidth), ceil(natural) + 8)
        let height = forms.map { ($0 as NSString).boundingRect(with: CGSize(width: max(1, width - 8), height: .greatestFiniteMagnitude), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attributes, context: nil).height }.max() ?? font.lineHeight
        return CGRect(x: 0, y: font.descender - 2, width: width, height: ceil(height) + 4)
    }
    override func image(forBounds bounds: CGRect, textContainer: NSTextContainer?, characterIndex charIndex: Int) -> UIImage? {
        guard bounds.width > 0, bounds.height > 0 else { return nil }
        return UIGraphicsImageRenderer(size: bounds.size).image { _ in
            ink.withAlphaComponent(0.11).setFill()
            UIBezierPath(roundedRect: CGRect(origin: .zero, size: bounds.size), cornerRadius: 2.5).fill()
            (displayed as NSString).draw(with: CGRect(x: 4, y: 2, width: max(1, bounds.width - 8), height: bounds.height - 4), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attributes, context: nil)
        }
    }
}

@MainActor final class ImmersionAccessibilityElement: UIAccessibilityElement {
    var activate: (() -> Void)?
    var frame: (() -> CGRect)?
    override func accessibilityActivate() -> Bool { guard let activate else { return false }; activate(); return true }
    override var accessibilityFrame: CGRect {
        get { frame?() ?? .zero }
        set { }
    }
}

@MainActor final class ImmersionNativeTextView: UITextView {
    var variants: [NSAttributedString] = []
    var reserveKey = ""
    var reserveHeight: CGFloat = 0
    var contentIdentity = ""
    var measurementContext = ""
    var renderingIdentity = ""
    let measurer: UITextView = {
        let view = UITextView(usingTextLayoutManager: false); view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0; view.isScrollEnabled = false
        return view
    }()
    func visibleText(in range: NSRange? = nil) -> String {
        let selected = attributedText.attributedSubstring(from: range ?? NSRange(location: 0, length: attributedText.length))
        var runs: [ImmersionCopyRun] = []
        selected.enumerateAttributes(in: NSRange(location: 0, length: selected.length)) { attributes, part, _ in
            if let word = attributes[.attachment] as? ImmersionWordAttachment {
                runs.append(word.copyRun)
            } else {
                runs.append(.init(text: (selected.string as NSString).substring(with: part)))
            }
        }
        return ImmersionCopyText.compose(runs)
    }
    override func copy(_ sender: Any?) {
        guard selectedRange.length > 0 else { return }
        UIPasteboard.general.string = visibleText(in: selectedRange)
    }
    var originalMessage = ""
    func originalRange(for selection: NSRange) -> NSRange? {
        var segments: [OriginalTextSegment] = []
        attributedText.enumerateAttributes(in: NSRange(location: 0, length: attributedText.length)) { attributes, displayed, _ in
            guard let source = attributes[.vipiOriginalRange] as? NSValue else { return }
            segments.append(.init(displayed: displayed, original: source.rangeValue, atomic: attributes[.attachment] != nil))
        }
        return OriginalTextSelection.range(for: selection, segments: segments, original: originalMessage)
    }
    var onWordActivation: ((Int) -> Void)?
    func wordAccessibility(in container: UIView) -> [ImmersionAccessibilityElement] {
        var links: [ImmersionAccessibilityElement] = []
        attributedText.enumerateAttributes(in: NSRange(location: 0, length: attributedText.length)) { attributes, range, _ in
            guard let word = attributes[.attachment] as? ImmersionWordAttachment,
                  let url = attributes[.link] as? URL, let id = Int(url.lastPathComponent) else { return }
            let element = ImmersionAccessibilityElement(accessibilityContainer: container)
            element.accessibilityLabel = word.displayed
            element.accessibilityIdentifier = "immersion-word-\(id)"
            element.accessibilityTraits = .link
            element.activate = { [weak self] in self?.onWordActivation?(id) }
            element.frame = { [weak self] in
                guard let self else { return .zero }
                let glyphs = layoutManager.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
                let local = layoutManager.boundingRect(forGlyphRange: glyphs, in: textContainer).offsetBy(dx: textContainerInset.left, dy: textContainerInset.top)
                return UIAccessibility.convertToScreenCoordinates(local, in: self)
            }
            links.append(element)
        }
        return links
    }
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

/// UITextView exposes attachment links without names. A standard UIKit
/// accessibility container supplies readable text and named native word actions.
@MainActor final class ImmersionTextContainer: UIView {
    let textView: ImmersionNativeTextView = {
        let storage = NSTextStorage(), layout = NSLayoutManager()
        storage.addLayoutManager(layout)
        let container = NSTextContainer(size: CGSize(width: 0, height: CGFloat.greatestFiniteMagnitude))
        layout.addTextContainer(container)
        return ImmersionNativeTextView(frame: .zero, textContainer: container)
    }()
    private lazy var paragraph = ImmersionAccessibilityElement(accessibilityContainer: self)
    private var accessibilityIdentity = ""
    override init(frame: CGRect) {
        super.init(frame: frame)
        isAccessibilityElement = false
        textView.accessibilityElementsHidden = true
        addSubview(textView)
    }
    required init?(coder: NSCoder) { return nil }
    override func layoutSubviews() { super.layoutSubviews(); textView.frame = bounds }
    func refreshAccessibility() {
        paragraph.accessibilityIdentifier = "immersionText"
        paragraph.accessibilityLabel = textView.visibleText()
        paragraph.accessibilityTraits = .staticText
        paragraph.accessibilityHint = textView.accessibilityHint
        paragraph.accessibilityCustomActions = textView.accessibilityCustomActions
        paragraph.frame = { [weak self] in
            guard let self else { return .zero }
            return UIAccessibility.convertToScreenCoordinates(textView.bounds, in: textView)
        }
        if accessibilityIdentity != textView.renderingIdentity {
            accessibilityIdentity = textView.renderingIdentity
            accessibilityElements = [paragraph] + textView.wordAccessibility(in: self)
        }
    }
}

struct StableImmersionText: UIViewRepresentable {
    let result: ImmersionPresentation
    let revealed: Set<Int>
    let script: Bool
    let onWord: (Int) -> Void
    let onSelection: (Bool) -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> ImmersionTextContainer {
        let container = ImmersionTextContainer(frame: .zero)
        let view = container.textView
        view.backgroundColor = .clear; view.isEditable = false; view.isSelectable = true; view.isScrollEnabled = false
        view.textContainerInset = .zero; view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.delegate = context.coordinator
        view.accessibilityIdentifier = "immersionText"
        view.linkTextAttributes = [:]
        return container
    }
    func updateUIView(_ container: ImmersionTextContainer, context: Context) {
        let view = container.textView
        context.coordinator.onWord = onWord; context.coordinator.onSelection = onSelection
        view.onWordActivation = onWord
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
        view.originalMessage = result.original
        view.contentIdentity = String(describing: result)
        let identity = "\(view.contentIdentity)|\(revealed.sorted())|\(script)|\(font.pointSize)|\(scheme)"
        if view.renderingIdentity != identity {
            view.renderingIdentity = identity
            let current = render(revealed: revealed, script: script, font: font, color: color)
            let selection = view.selectedRange
            let sameText = view.attributedText.string == current.string
            view.attributedText = current
            view.variants = [current]
            view.reserveKey = ""
            if sameText && NSMaxRange(selection) <= current.length { view.selectedRange = selection }
        }
        view.accessibilityLabel = view.visibleText()
        view.accessibilityValue = view.visibleText()
        view.accessibilityHint = voiceOver
            ? String(localized: "Automatic switching pauses while VoiceOver is on. Use the word actions to switch meanings. Reading options changes the language or script.")
            : String(localized: "Words switch automatically. Pause holds the current words. Reading options changes the pace or script.")
        view.accessibilityCustomActions = result.spans.map { word in
            UIAccessibilityCustomAction(name: String(localized: "Switch \(word.original) and \(word.displayedTarget)")) { _ in onWord(word.id); return true }
        }
        view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name: String(localized: "Copy displayed message")) { [weak view] _ in
            guard let view else { return false }; UIPasteboard.general.string = view.visibleText(); return true
        })
        container.refreshAccessibility()
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView container: ImmersionTextContainer, context: Context) -> CGSize? {
        guard let width = proposal.width, width > 0 else { return nil }
        return container.textView.reservedSize(width: width)
    }
    private func render(revealed: Set<Int>, script: Bool, font: UIFont, color: UIColor) -> NSAttributedString {
        let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 5; paragraph.baseWritingDirection = .natural
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.label, .paragraphStyle: paragraph]
        let descriptor = font.fontDescriptor.addingAttributes([.traits: [UIFontDescriptor.TraitKey.weight: UIFont.Weight.semibold]])
        let emphasis = UIFont(descriptor: descriptor, size: font.pointSize)
        let text = NSMutableAttributedString(string: "")
        let original = result.original as NSString
        var cursor = 0
        func appendOriginal(_ range: NSRange) {
            var style = attributes
            style[.vipiOriginalRange] = NSValue(range: range)
            text.append(NSAttributedString(string: original.substring(with: range), attributes: style))
        }
        for word in result.spans {
            if word.range.location > cursor { appendOriginal(NSRange(location: cursor, length: word.range.location - cursor)) }
            let copyRun = ImmersionCopyText.run(for: word, in: result, showingOriginal: revealed.contains(word.id), script: script)
            let value = copyRun.text
            var style = attributes
            style[.font] = emphasis; style[.foregroundColor] = color
            style[.vipiOriginalRange] = NSValue(range: word.range)
            style[.link] = URL(string: "vipi-reveal://word/\(word.id)")!
            let suffix = original.substring(from: NSMaxRange(word.range)).prefix { ".,!?;:…؟。！？；，、)]}’”\"".contains($0) }.prefix(8)
            let trailing = suffix.isEmpty ? 0 : ceil((String(suffix) as NSString).size(withAttributes: [.font: font]).width) + 1
            let attachment = ImmersionWordAttachment(displayed: value, forms: [word.original, word.displayedTarget, word.translated], font: emphasis, ink: color, trailingWidth: trailing,
                copySlotID: word.id, copyShowsOriginal: revealed.contains(word.id), copyRun: copyRun)
            let token = NSMutableAttributedString(attachment: attachment)
            token.addAttributes(style, range: NSRange(location: 0, length: token.length))
            text.append(token)
            cursor = NSMaxRange(word.range)
        }
        if cursor < original.length { appendOriginal(NSRange(location: cursor, length: original.length - cursor)) }
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
            guard interaction == .invokeDefaultAction, URL.scheme == "vipi-reveal", let id = Int(URL.lastPathComponent) else { return false }
            onWord?(id); return false
        }
    }
}
