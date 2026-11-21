import SwiftUI
import CryptoKit
import UIKit
import VipiCore

private extension NSAttributedString.Key {
    static let vipiOriginalRange = NSAttributedString.Key("co.fallsoft.vipi.original-range")
    static let vipiWordID = NSAttributedString.Key("co.fallsoft.vipi.word-id")
}

/// A native inline attachment reserves the same geometry for every word face.
/// Its visible text remains available to accessibility and selection/copy.
final class ImmersionWordAttachment: NSTextAttachment {
    let displayed: String
    let forms: [String]
    let font: UIFont
    let ink: UIColor
    let fill: UIColor
    let spokenFill: UIColor
    let spokenInk: UIColor
    let trailingWidth: CGFloat
    let copySlotID: Int?
    let copyShowsOriginal: Bool
    let copyRun: ImmersionCopyRun
    var playingRange:NSRange?
    @MainActor init(displayed: String, forms: [String], font: UIFont, ink: UIColor, trailingWidth: CGFloat = 0, copySlotID: Int? = nil, copyShowsOriginal: Bool = true, copyRun: ImmersionCopyRun? = nil, fill:UIColor? = nil, spokenFill:UIColor? = nil, spokenInk:UIColor? = nil) {
        self.displayed = displayed; self.forms = forms; self.font = font; self.ink = ink
        self.fill = fill ?? VipiPalette.uiColor(.practiceFill)
        self.spokenFill = spokenFill ?? VipiPalette.uiColor(.spokenFill)
        self.spokenInk = spokenInk ?? VipiPalette.uiColor(.spokenInk)
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
            fill.setFill()
            UIBezierPath(roundedRect: CGRect(origin: .zero, size: bounds.size), cornerRadius: 2.5).fill()
            let text = NSMutableAttributedString(string:displayed,attributes:attributes)
            if let range = playingRange,range.location >= 0,range.length > 0,NSMaxRange(range) <= text.length {
                text.addAttributes([.backgroundColor:spokenFill,.foregroundColor:spokenInk],range:range)
            }
            text.draw(with:CGRect(x:4,y:2,width:max(1,bounds.width-8),height:bounds.height-4),options:[.usesLineFragmentOrigin,.usesFontLeading],context:nil)
        }
    }
}

@MainActor private final class ImmersionPlainWordTap: UITapGestureRecognizer {
    override func canPrevent(_ preventedGestureRecognizer: UIGestureRecognizer) -> Bool { false }
    override func canBePrevented(by preventingGestureRecognizer: UIGestureRecognizer) -> Bool { false }
}

@MainActor private final class ImmersionTouchObserver: UIGestureRecognizer {
    weak var owner: ImmersionNativeTextView?
    var selectionOnly = false
    private var observing = false
    override func canPrevent(_ preventedGestureRecognizer: UIGestureRecognizer) -> Bool { false }
    override func canBePrevented(by preventingGestureRecognizer: UIGestureRecognizer) -> Bool { false }
    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent) {
        observing = !selectionOnly || touches.contains { owner?.isSelectionHandleTouch($0) == true }
        if observing { owner?.beginSelectionGesture() }
        if selectionOnly { owner?.recordSelectionGesture("selection_window_began", observed: observing) }
    }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent) { }
    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent) { if selectionOnly { owner?.recordSelectionGesture("selection_window_ended", observed: observing) }; if observing { owner?.endSelectionGesture(cancelled: false) }; state = .recognized }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent) { if observing { owner?.endSelectionGesture(cancelled: true) }; state = .cancelled }
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
    var playbackControlRectInWindow = CGRect.null
    func isSelectionHandleTouch(_ touch: UITouch) -> Bool {
        guard selectedRange.length > 0, let selectedTextRange, let window else { return false }
        let point = touch.location(in: window)
        guard !playbackControlRectInWindow.contains(point) else { return false }
        for selection in selectionRects(for: selectedTextRange) {
            let rect = convert(selection.rect, to: window)
            let rtl = selection.writingDirection == .rightToLeft
            if selection.containsStart {
                let start = CGPoint(x: rtl ? rect.maxX : rect.minX, y: rect.minY)
                if CGRect(x: start.x - 24, y: start.y - 24, width: 48, height: 48).contains(point) { return true }
            }
            if selection.containsEnd {
                let end = CGPoint(x: rtl ? rect.minX : rect.maxX, y: rect.maxY)
                if CGRect(x: end.x - 24, y: end.y - 24, width: 48, height: 48).contains(point) { return true }
            }
        }
        return false
    }
    private var selectionWindowObservers: [ObjectIdentifier: ImmersionTouchObserver] = [:]
    private func clearSelectionObservers() {
        for observer in selectionWindowObservers.values { observer.view?.removeGestureRecognizer(observer) }
        selectionWindowObservers.removeAll()
    }
    override func didMoveToWindow() {
        super.didMoveToWindow(); clearSelectionObservers(); syncSelectionObservers()
    }
    private func syncSelectionObservers() {
        guard selectedRange.length > 0, let window else { clearSelectionObservers(); return }
        // Native grabbers can live in UIKit's separate selection window. Observe
        // this scene's windows, restricted to the actual endpoint hit regions.
        let windows = window.windowScene?.windows ?? [window]
        let current = Set(windows.map(ObjectIdentifier.init))
        for (key, observer) in selectionWindowObservers where !current.contains(key) {
            observer.view?.removeGestureRecognizer(observer); selectionWindowObservers.removeValue(forKey: key)
        }
        for candidate in windows where !candidate.isHidden {
            let key = ObjectIdentifier(candidate)
            guard selectionWindowObservers[key] == nil else { continue }
            let observer = ImmersionTouchObserver(); observer.owner = self; observer.selectionOnly = true
            observer.cancelsTouchesInView = false; observer.delaysTouchesBegan = false; observer.delaysTouchesEnded = false
            candidate.addGestureRecognizer(observer); selectionWindowObservers[key] = observer
        }
    }
    func recordSelectionGesture(_ event: String, observed: Bool) {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") else { return }
        LiveImmersionQualification.record(["event": event, "observed": observed, "finger_down": fingerDown,
            "selection_start": selectedRange.location, "selection_end": NSMaxRange(selectedRange),
            "first_responder": isFirstResponder, "selection_windows": selectionWindowObservers.count])
        #endif
    }
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
        selectionRevision += 1; selectionTask?.cancel(); selectionChangedDuringTouch = false; releasedUserSelection = false; onCopyRequested?()
        UIPasteboard.general.string = visibleText(in: selectedRange)
    }
    var originalMessage = ""
    var onPlainWord: ((NSRange, ImmersionNativeTextView) -> Void)?
    var onReleasedSelection: ((NSRange, ImmersionNativeTextView) -> Void)?
    var onSelectionGestureBegan: (() -> Void)?
    var onCopyRequested: (() -> Void)?
    var onWhitespace: ((ImmersionNativeTextView) -> Void)?
    var onPlayMessage: (() -> Void)?
    private var fingerDown = false
    private var selectionChangedDuringTouch = false
    private var selectionRevision = 0
    private var selectionTask: Task<Void, Never>?
    private var lastRelease = Date.distantPast
    private var releasedUserSelection = false
    func beginSelectionGesture() {
        fingerDown = true; selectionChangedDuringTouch = false; releasedUserSelection = false
        selectionRevision += 1; selectionTask?.cancel(); onSelectionGestureBegan?()
    }
    func endSelectionGesture(cancelled: Bool) {
        fingerDown = false; lastRelease = Date(); releasedUserSelection = !cancelled
        syncSelectionObservers()
        DispatchQueue.main.async { [weak self] in self?.syncSelectionObservers() }
        if cancelled { selectionTask?.cancel(); return }
        if selectionChangedDuringTouch { scheduleReleasedSelection() }
    }
    func userSelectionChanged() {
        syncSelectionObservers()
        DispatchQueue.main.async { [weak self] in self?.syncSelectionObservers() }
        recordSelectionGesture("native_selection_changed", observed: fingerDown)
        selectionRevision += 1; selectionTask?.cancel()
        if fingerDown { selectionChangedDuringTouch = true }
        else if releasedUserSelection && Date().timeIntervalSince(lastRelease) < 0.3 {
            // UIKit may publish the final handle range just after touchesEnded.
            selectionChangedDuringTouch = true; scheduleReleasedSelection()
        }
    }
    private func scheduleReleasedSelection() {
        guard selectedRange.length > 0, onReleasedSelection != nil else { return }
        let revision = selectionRevision; let selected = selectedRange
        selectionTask?.cancel()
        selectionTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(180))
            guard let self, !Task.isCancelled, !fingerDown, revision == selectionRevision,
                  selected == selectedRange, let original = originalRange(for: selected) else { return }
            releasedUserSelection = false; selectionChangedDuringTouch = false
            onReleasedSelection?(original, self)
        }
    }
    @objc func plainWordTapped(_ gesture: UITapGestureRecognizer) {
        guard gesture.state == .ended, selectedRange.length == 0 else { return }
        let point = gesture.location(in: self)
        let local = CGPoint(x: point.x - textContainerInset.left, y: point.y - textContainerInset.top)
        let glyph = layoutManager.glyphIndex(for: local, in: textContainer)
        guard glyph < layoutManager.numberOfGlyphs,
              layoutManager.boundingRect(forGlyphRange: NSRange(location: glyph, length: 1), in: textContainer).insetBy(dx: -2, dy: -2).contains(local) else { onWhitespace?(self); return }
        let offset = layoutManager.characterIndexForGlyph(at: glyph)
        guard offset < attributedText.length else { return }
        if let id = attributedText.attribute(.vipiWordID, at: offset, effectiveRange: nil) as? Int {
            onWordActivation?(id); return
        }
        guard let onPlainWord,
              let source = originalRange(for: NSRange(location: offset, length: 1)),
              let word = OriginalTextSelection.word(atUTF16: source.location, in: originalMessage) else { onWhitespace?(self); return }
        onPlainWord(word, self)
    }
    func selectTextFromMenu() {
        onCopyRequested?()
        selectionRevision += 1; selectionTask?.cancel(); selectionChangedDuringTouch = false; releasedUserSelection = false
        DispatchQueue.main.async { [weak self] in self?.becomeFirstResponder(); self?.selectAll(nil) }
    }
    func windowRect(forOriginalRange selection: NSRange) -> CGRect {
        var display: NSRange?
        attributedText.enumerateAttributes(in: NSRange(location: 0, length: attributedText.length)) { attributes, range, _ in
            guard let original = (attributes[.vipiOriginalRange] as? NSValue)?.rangeValue,
                  NSIntersectionRange(original, selection).length > 0 else { return }
            let hit = NSIntersectionRange(original, selection)
            let part = attributes[.attachment] != nil ? range : NSRange(location: range.location + hit.location - original.location, length: hit.length)
            display = display.map { NSUnionRange($0, part) } ?? part
        }
        let glyph = layoutManager.glyphRange(forCharacterRange: display ?? NSRange(location: 0, length: attributedText.length), actualCharacterRange: nil)
        let local = layoutManager.boundingRect(forGlyphRange: glyph, in: textContainer).offsetBy(dx: textContainerInset.left, dy: textContainerInset.top)
        return convert(local, to: window)
    }
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
                  let id = attributes[.vipiWordID] as? Int else { return }
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
    var lastModeFace: ImmersionTextFace?
    var lastFaceFontSize: CGFloat = 0
    var currentFaceVariants: [NSAttributedString] = []
    var otherFaceVariants: [NSAttributedString] = []
    private var preferredWidthContext = ""
    private var preferredWidth: CGFloat = 0
    private lazy var widthMeasurer: UITextView = {
        let view = UITextView(usingTextLayoutManager: false)
        view.textContainerInset = .zero; view.textContainer.lineFragmentPadding = 0
        view.textContainer.widthTracksTextView = false; view.textContainer.heightTracksTextView = false
        view.isScrollEnabled = false
        return view
    }()
    /// The real TextKit attachments reserve source, target and reading forms.
    /// Measure those glyph boxes under the width cap, never the current ink face.
    func preferredContentWidth(maximumWidth: CGFloat) -> CGFloat {
        let font = attributedText.length > 0 ? attributedText.attribute(.font, at: 0, effectiveRange: nil) as? UIFont : nil
        let context = "\(maximumWidth)|\(contentIdentity)|\(font?.fontDescriptor.description ?? "")|\(traitCollection.preferredContentSizeCategory.rawValue)"
        if context != preferredWidthContext {
            preferredWidthContext = context
            var widest: CGFloat = 1
            for variant in variants {
                widthMeasurer.attributedText = variant
                widthMeasurer.textContainer.size = CGSize(width: maximumWidth, height: .greatestFiniteMagnitude)
                let layout = widthMeasurer.layoutManager
                layout.ensureLayout(for: widthMeasurer.textContainer)
                layout.enumerateLineFragments(forGlyphRange: NSRange(location: 0, length: layout.numberOfGlyphs)) { _, used, _, _, _ in
                    widest = max(widest, used.width)
                }
            }
            preferredWidth = min(maximumWidth, ceil(widest + 1))
        }
        return preferredWidth
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
struct ImmersionTextFace: Equatable {
    let scope: UUID
    let message: String
    let mode: ImmersionMode
}

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
    #if DEBUG
    private var lastQualificationGeometry = ""
    #endif
    override func layoutSubviews() {
        super.layoutSubviews(); textView.frame = bounds
        #if DEBUG
        guard LiveImmersionQualification.fullMessageGeometryEnabled else { return }
        let rect = textView.convert(textView.bounds,to:nil)
        let digest = SHA256.hash(data:Data(textView.attributedText.string.utf8)).map{String(format:"%02x",$0)}.joined()
        let key = "\(rect)|" + digest
        if key != lastQualificationGeometry {
            lastQualificationGeometry = key
            LiveImmersionQualification.recordFullMessageGeometry(["event":"full_message_paragraph_geometry",
                "text_sha256":digest,"frame":LiveImmersionQualification.frameFields(rect)])
        }
        #endif
    }
    func refreshAccessibility() {
        paragraph.activate = textView.onPlayMessage
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
    var onPlainWord: ((NSRange, ImmersionNativeTextView) -> Void)? = nil
    var onReleasedSelection: ((NSRange, ImmersionNativeTextView) -> Void)? = nil
    var onSelectionGestureBegan: (() -> Void)? = nil
    var onCopyRequested: (() -> Void)? = nil
    var onWhitespace: ((ImmersionNativeTextView) -> Void)? = nil
    var onPlayMessage: (() -> Void)? = nil
    var onReport: (() -> Void)? = nil
    var onNativeView: ((ImmersionNativeTextView) -> Void)? = nil
    var fitsContentWidth = false
    var reservedSentences: [String] = []
    var sentenceIdentity: String? = nil
    var transitionFace: ImmersionTextFace?
    var practiceWordActionsEnabled = true
    var fullMessage = false
    var incremental = false
    var playingRange:NSRange?
    var playingWordID:Int?
    var playingWordRange:NSRange?
    var onMeaning: (() -> Void)? = nil
    var showingMeaning = false
    var onScript: (() -> Void)? = nil
    var showingNativeScript = false
    var originalForCopy: String? = nil
    var accessibilityMessageContext: String? = nil
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var scheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.vipiOutgoingMessage) private var outgoingMessage
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
        let tap = ImmersionPlainWordTap(target: view, action: #selector(ImmersionNativeTextView.plainWordTapped(_:)))
        tap.cancelsTouchesInView = false; tap.delaysTouchesBegan = false; tap.delaysTouchesEnded = false
        view.addGestureRecognizer(tap)
        let observer = ImmersionTouchObserver(); observer.owner = view
        observer.cancelsTouchesInView = false; observer.delaysTouchesBegan = false; observer.delaysTouchesEnded = false
        view.addGestureRecognizer(observer)
        return container
    }
    func updateUIView(_ container: ImmersionTextContainer, context: Context) {
        let view = container.textView
        context.coordinator.onWord = onWord; context.coordinator.onSelection = onSelection
        view.onWordActivation = onWord
        view.onPlainWord = onPlainWord; view.onReleasedSelection = onReleasedSelection
        view.onSelectionGestureBegan = onSelectionGestureBegan; view.onCopyRequested = onCopyRequested
        view.onWhitespace = onWhitespace; view.onPlayMessage = onPlayMessage
        onNativeView?(view)
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
        let color = VipiPalette.uiColor(.practiceInk).resolvedColor(with:view.traitCollection)
        let bodyInk = VipiPalette.uiColor(outgoingMessage ? .outgoingInk:.ink).resolvedColor(with:view.traitCollection)
        let practiceFill = VipiPalette.uiColor(.practiceFill).resolvedColor(with:view.traitCollection)
        let spokenFill = VipiPalette.uiColor(.spokenFill).resolvedColor(with:view.traitCollection)
        let spokenInk = VipiPalette.uiColor(.spokenInk).resolvedColor(with:view.traitCollection)
        view.tintColor = VipiPalette.uiColor(outgoingMessage ? .outgoingFocus:.focus)
        view.originalMessage = result.original
        view.isSelectable = !fullMessage
        view.contentIdentity = sentenceIdentity ?? String(describing: result)
        let identity = "\(view.contentIdentity)|\(revealed.sorted())|\(script)|\(font.pointSize)|\(scheme)|\(contrast)|\(outgoingMessage)|\(String(describing:playingRange))|\(String(describing:playingWordID))|\(String(describing:playingWordRange))|" + Data(result.original.utf8).base64EncodedString()
        if view.renderingIdentity != identity {
            view.renderingIdentity = identity
            let current = NSMutableAttributedString(attributedString:render(revealed:revealed,script:script,font:font,color:color,bodyInk:bodyInk,practiceFill:practiceFill,spokenFill:spokenFill,spokenInk:spokenInk))
            if let range = playingRange,range.location >= 0,range.length > 0,NSMaxRange(range) <= current.length {
                current.addAttributes([.backgroundColor:spokenFill,.foregroundColor:spokenInk],range:range)
            }
            let selection = view.selectedRange
            let sameText = view.attributedText.string == current.string
            let previous = view.lastModeFace
            let sameMessage = transitionFace != nil && previous?.scope == transitionFace?.scope && previous?.message == transitionFace?.message
            let switched = sameMessage && previous?.mode != transitionFace?.mode
            if !sameMessage || view.lastFaceFontSize != font.pointSize {
                view.otherFaceVariants = []
            } else if switched {
                view.otherFaceVariants = view.currentFaceVariants
            }
            if !sameMessage || reduceMotion || voiceOver {
                view.layer.removeAnimation(forKey:"vipiModeFace")
            } else if switched && !view.attributedText.isEqual(to:current) && view.window != nil {
                // Animate the incoming ink only. Blending snapshots would show
                // two different sentences in the same glyph positions mid-switch.
                let ink = CABasicAnimation(keyPath:"opacity")
                ink.fromValue = 0.74; ink.toValue = 1.0
                let settle = CABasicAnimation(keyPath:"transform.translation.y")
                settle.fromValue = transitionFace?.mode == .fullMessages ? 3.0 : -3.0
                settle.toValue = 0.0
                let arrival = CAAnimationGroup()
                arrival.animations = [ink,settle]; arrival.duration = 0.22
                arrival.timingFunction = CAMediaTimingFunction(name:.easeOut)
                view.layer.add(arrival,forKey:"vipiModeFace")
            }
            view.lastModeFace = transitionFace; view.lastFaceFontSize = font.pointSize
            view.attributedText = current
            #if DEBUG
            if fullMessage, Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
               ProcessInfo.processInfo.arguments.contains("-vipi-full-translation-sdk-qa"),
               FirstMonthRootQualification.current != nil {
                LiveImmersionQualification.record(["event":"full_message_native_face",
                    "showing_meaning":showingMeaning,"showing_native_script":showingNativeScript,
                    "original_sha256":SHA256.hash(data:Data((originalForCopy ?? result.original).utf8)).map{String(format:"%02x",$0)}.joined(),
                    "displayed_sha256":SHA256.hash(data:Data(view.visibleText().utf8)).map{String(format:"%02x",$0)}.joined()])
            }
            #endif
            view.currentFaceVariants = reservedSentences.isEmpty ? [current] : reservedSentences.map { sentence in
                let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 5; paragraph.baseWritingDirection = .natural
                return NSAttributedString(string:sentence,attributes:[.font:font,.foregroundColor:bodyInk,.paragraphStyle:paragraph])
            }
            view.variants = view.currentFaceVariants + view.otherFaceVariants
            view.reserveKey = ""
            if sameText && NSMaxRange(selection) <= current.length { view.selectedRange = selection }
        }
        view.accessibilityLabel = view.visibleText()
        view.accessibilityValue = view.visibleText()
        if fullMessage {
            let actions = ChatReadingState.actionDescription(showingMeaning:showingMeaning,nativeScript:showingNativeScript,hasAlternateScript:onScript != nil,incremental:incremental)
            view.accessibilityHint = [accessibilityMessageContext,actions].compactMap { $0 }.joined(separator:". ")
        } else { view.accessibilityHint = voiceOver
            ? String(localized: "Automatic switching pauses while VoiceOver is on. Use the word actions to switch meanings. Reading options changes the language or script.")
            : String(localized: "Words switch automatically. Pause holds the current words. Reading options changes the pace or script.")
        }
        view.accessibilityCustomActions = (practiceWordActionsEnabled ? result.spans : []).map { word in
            let repeated = result.spans.filter { $0.original == word.original && $0.displayedTarget == word.displayedTarget }
            let name: String
            if fullMessage {
                name = String(localized:"Hear \(word.displayedTarget)")
            } else if repeated.count > 1 {
                let occurrence = (repeated.firstIndex(where: { $0.id == word.id }) ?? 0) + 1
                name = String(localized: "Switch \(word.original) and \(word.displayedTarget), occurrence \(occurrence)")
            } else { name = String(localized: "Switch \(word.original) and \(word.displayedTarget)") }
            return UIAccessibilityCustomAction(name: name) { _ in onWord(word.id); return true }
        }
        view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name: String(localized: "Copy displayed message")) { [weak view] _ in
            guard let view else { return false }; view.onCopyRequested?(); UIPasteboard.general.string = view.visibleText(); return true
        })
        if let onWhitespace {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name: String(localized: "Translate message")) { [weak view] _ in
                guard let view else { return false }; onWhitespace(view); return true
            })
        }
        if let onMeaning {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name:showingMeaning ? (incremental ? String(localized:"Show practice words") : String(localized:"Show practice text")) : String(localized:"Show original message")) { _ in onMeaning(); return true })
        }
        if let onScript {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name:showingNativeScript ? String(localized:"Show transliteration") : String(localized:"Show native script")) { _ in onScript(); return true })
        }
        if let originalForCopy {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name:String(localized:"Copy original message")) { _ in UIPasteboard.general.string = originalForCopy; return true })
        }
        if let onPlayMessage {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name: incremental ? String(localized:"Play practice words") : String(localized:"Play message")) { _ in onPlayMessage(); return true })
        }
        if let onReport {
            view.accessibilityCustomActions?.append(UIAccessibilityCustomAction(name: String(localized: "Report message")) { _ in onReport(); return true })
        }
        container.refreshAccessibility()
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView container: ImmersionTextContainer, context: Context) -> CGSize? {
        guard let width = proposal.width ?? (fitsContentWidth ? 520 : nil), width > 0 else { return nil }
        let fitted = fitsContentWidth && container.textView.attributedText.length > 0
            ? container.textView.preferredContentWidth(maximumWidth: width) : width
        return container.textView.reservedSize(width: fitted)
    }
    private func render(revealed:Set<Int>,script:Bool,font:UIFont,color:UIColor,bodyInk:UIColor,practiceFill:UIColor,spokenFill:UIColor,spokenInk:UIColor) -> NSAttributedString {
        let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 5; paragraph.baseWritingDirection = .natural
        let attributes: [NSAttributedString.Key: Any] = [.font:font,.foregroundColor:bodyInk,.paragraphStyle:paragraph]
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
            style[.vipiWordID] = word.id
            let suffix = original.substring(from: NSMaxRange(word.range)).prefix { ".,!?;:…؟。！？；，、)]}’”\"".contains($0) }.prefix(8)
            let trailing = suffix.isEmpty ? 0 : ceil((String(suffix) as NSString).size(withAttributes: [.font: font]).width) + 1
            let attachment = ImmersionWordAttachment(displayed: value, forms: [word.original, word.displayedTarget, word.translated], font: emphasis, ink: color, trailingWidth: trailing,
                copySlotID:word.id,copyShowsOriginal:revealed.contains(word.id),copyRun:copyRun,fill:practiceFill,spokenFill:spokenFill,spokenInk:spokenInk)
            if playingWordID == word.id { attachment.playingRange = playingWordRange ?? NSRange(location:0,length:value.utf16.count) }
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
            (textView as? ImmersionNativeTextView)?.userSelectionChanged()
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
