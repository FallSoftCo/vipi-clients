import SwiftUI
import UIKit

/// Keep the empty-state prompt in the same SwiftUI layer as the composer.
struct MessageEditor: View {
    @Binding var text: String
    let placeholder: String
    let focus: Binding<Bool>
    let maximumBytes: Int
    let rejected: () -> Void

    var body: some View {
        NativeMessageEditor(text: $text, placeholder: placeholder, focus: focus,
                            maximumBytes: maximumBytes, rejected: rejected)
            .overlay(alignment: .topLeading) {
                if text.isEmpty {
                    Text(verbatim: placeholder)
                        .font(.body).foregroundStyle(VipiDesign.secondary)
                        .lineLimit(1).allowsHitTesting(false).accessibilityHidden(true)
                }
            }
    }
}

/// Keep rejected pastes out of the native editor as well as the saved draft.
/// Rejecting only a SwiftUI Binding write leaves the field's editing buffer
/// showing text that was never accepted by the model.
struct NativeMessageEditor: UIViewRepresentable {
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
        let view = DraftTextView.messageEditor()
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
        view.textColor = VipiPalette.uiColor(.ink)
        view.tintColor = VipiPalette.uiColor(.focus)
        view.accessibilityLabel = placeholder
        view.isEditable = enabled
        if view.text != text, view.markedTextRange == nil {
            view.text = text
        }
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
        let desired = min(max(line, measured.height), line * lines)
        // VStack proposes the space left after wrapped validation/recovery
        // copy. Respect it so a longer error cannot push above navigation.
        let available = proposal.height.flatMap { $0.isFinite ? $0 : nil } ?? desired
        return CGSize(width: width, height: max(line, min(desired, available)))
    }

    @MainActor final class Coordinator: NSObject, UITextViewDelegate {
        var parent: NativeMessageEditor
        init(_ parent: NativeMessageEditor) { self.parent = parent }
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
            textView.invalidateIntrinsicContentSize()
        }
        func textViewDidBeginEditing(_ textView: UITextView) { parent.focus.wrappedValue = true }
        func textViewDidEndEditing(_ textView: UITextView) { parent.focus.wrappedValue = false }
    }
}

@MainActor final class DraftTextView: UITextView {
    static func messageEditor() -> DraftTextView {
        // UIKit's TextKit 2 viewport renders a long single paragraph blank at
        // large text sizes, even with a valid caret and retained native text.
        // The explicit compatibility constructor keeps bounded plain drafts
        // visible and editable. Do not trigger an implicit engine switch by
        // accessing layoutManager after editing has begun.
        DraftTextView(usingTextLayoutManager: false)
    }
}
