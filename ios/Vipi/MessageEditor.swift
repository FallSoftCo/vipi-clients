import SwiftUI
import UIKit

/// Keep rejected pastes out of the native editor as well as the saved draft.
/// Rejecting only a SwiftUI Binding write leaves the field's editing buffer
/// showing text that was never accepted by the model.
struct MessageEditor: UIViewRepresentable {
    @Binding var text: String
    let placeholder: String
    let focus: Binding<Bool>
    let maximumBytes: Int
    let rejected: () -> Void
    @Environment(\.isEnabled) private var enabled
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> DraftTextView {
        let view = DraftTextView(frame: .zero, textContainer: nil)
        view.delegate = context.coordinator
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.isScrollEnabled = true
        view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.autocapitalizationType = .sentences
        return view
    }
    func updateUIView(_ view: DraftTextView, context: Context) {
        context.coordinator.parent = self
        view.font = .preferredFont(forTextStyle: .body)
        view.textColor = .label
        view.tintColor = UIColor(VipiDesign.highlight)
        view.placeholder.text = placeholder
        view.placeholder.font = view.font
        view.placeholder.textColor = UIColor(VipiDesign.secondary)
        view.accessibilityLabel = placeholder
        view.isEditable = enabled
        if view.text != text, view.markedTextRange == nil {
            view.text = text
        }
        view.updatePlaceholder()
        if focus.wrappedValue && enabled && !view.isFirstResponder { view.becomeFirstResponder() }
        else if !focus.wrappedValue && view.isFirstResponder { view.resignFirstResponder() }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: DraftTextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width > 0 else { return nil }
        let line = uiView.font?.lineHeight ?? 22
        let measured = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        // Large text and a software keyboard still need room for the native
        // navigation bar and a visible validation message. The draft scrolls
        // inside the editor rather than pushing controls off the screen.
        let lines: CGFloat = verticalSizeClass == .compact ? 2 : typeSize.isAccessibilitySize ? 3 : 6
        return CGSize(width: width, height: min(max(line, measured.height), line * lines))
    }

    @MainActor final class Coordinator: NSObject, UITextViewDelegate {
        var parent: MessageEditor
        init(_ parent: MessageEditor) { self.parent = parent }
        func textView(_ textView: UITextView, shouldChangeTextIn range: NSRange, replacementText text: String) -> Bool {
            let current = textView.text ?? ""
            guard let range = Range(range, in: current) else { return false }
            let proposed = current.replacingCharacters(in: range, with: text)
            guard proposed.utf8.count <= parent.maximumBytes else {
                parent.rejected()
                return false
            }
            return true
        }
        func textViewDidChange(_ textView: UITextView) {
            parent.text = textView.text
            (textView as? DraftTextView)?.updatePlaceholder()
            textView.invalidateIntrinsicContentSize()
        }
        func textViewDidBeginEditing(_ textView: UITextView) { parent.focus.wrappedValue = true }
        func textViewDidEndEditing(_ textView: UITextView) { parent.focus.wrappedValue = false }
    }
}

@MainActor final class DraftTextView: UITextView {
    let placeholder = UILabel()
    override init(frame: CGRect, textContainer: NSTextContainer?) {
        super.init(frame: frame, textContainer: textContainer)
        placeholder.isUserInteractionEnabled = false
        placeholder.isAccessibilityElement = false
        addSubview(placeholder)
    }
    required init?(coder: NSCoder) { fatalError("Use the native message editor initializer") }
    func updatePlaceholder() { placeholder.isHidden = !text.isEmpty; setNeedsLayout() }
    override func layoutSubviews() {
        super.layoutSubviews()
        placeholder.frame = CGRect(x: textContainerInset.left, y: textContainerInset.top,
            width: bounds.width - textContainerInset.left - textContainerInset.right,
            height: font?.lineHeight ?? 22)
    }
}
