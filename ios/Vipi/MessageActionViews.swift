import SwiftUI

extension ChatFeatures.Reply {
    static func quoting(id: UUID, sender: UUID, text: String, media: String? = nil) -> Self {
        let label: String
        switch media {
        case "photo": label = String(localized: "Photo")
        case "video": label = String(localized: "Video")
        case "voice": label = String(localized: "Voice message")
        default: label = text
        }
        let kind = media.flatMap { ["photo", "voice", "video"].contains($0) ? $0 : nil } ?? "text"
        return .init(message_id: id, sender_id: sender, kind: kind, excerpt: ChatFeatures.excerpt(label))
    }
}

/// Only used by a sender’s composer. Message rows can render a preview without
/// having any dependency on this request pipeline.
@MainActor @Observable final class MessageActionDraft {
    var reply: ChatFeatures.Reply?
    private(set) var preview: ChatFeatures.Preview?
    private(set) var loading = false
    private(set) var unavailable = false
    private var currentURL: URL?
    private var suppressed: URL?
    private var task: Task<Void, Never>?
    private let load: (URL) async throws -> ChatFeatures.Preview
    init(load: @escaping (URL) async throws -> ChatFeatures.Preview = SenderLinkPreview.load) { self.load = load }
    func composed(_ text: String) -> ChatFeatures? {
        ChatFeatures(reply: reply, link_preview: preview).validated(in: text)
    }
    func update(_ text: String, automatic: Bool) {
        let url = ChatFeatures.Preview.firstURL(in: text)
        if url != currentURL {
            task?.cancel()
            task = nil
            loading = false
            unavailable = false
            suppressed = nil
            if preview?.url != url?.absoluteString { preview = nil }
            currentURL = url
        }
        if automatic, let url, suppressed != url, preview == nil, !loading && !unavailable { fetch(url) }
    }
    func fetch(_ url: URL) {
        task?.cancel()
        currentURL = url
        loading = true
        unavailable = false
        suppressed = nil
        task = Task {
            do {
                let value = try await load(url)
                guard !Task.isCancelled, currentURL == url else { return }
                preview = value.validated(in: url.absoluteString)
                unavailable = preview == nil
            } catch {
                guard !Task.isCancelled, currentURL == url else { return }
                unavailable = true
            }
            loading = false
        }
    }
    func restoreSuppression(_ url: URL, text: String) {
        guard ChatFeatures.Preview.firstURL(in: text) == url else { return }
        currentURL = url
        suppressed = url
    }
    func removePreview() {
        task?.cancel()
        loading = false
        preview = nil
        suppressed = currentURL
        unavailable = false
    }
    func leave() {
        task?.cancel()
        loading = false
    }
    func reset() {
        leave()
        currentURL = nil
        suppressed = nil
        preview = nil
        reply = nil
        unavailable = false
    }
    func restore(_ features: ChatFeatures?) {
        reply = features?.reply
        preview = features?.link_preview
    }
}

struct ReplyExcerptView: View {
    let author: String
    let excerpt: String
    var body: some View {
        HStack(spacing: 8) {
            Capsule().fill(VipiDesign.focus).frame(width: 3)
            VStack(alignment: .leading, spacing: 2) {
                Text(author).font(.caption.weight(.semibold))
                Text(excerpt).font(.subheadline).lineLimit(2)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
    }
}

struct EmbeddedLinkCard: View {
    let preview: ChatFeatures.Preview
    var body: some View {
        HStack(spacing: 10) {
            if let data = preview.thumbnail_jpeg, let image = UIImage(data: data) {
                Image(uiImage: image).resizable().scaledToFill().frame(width: 48, height: 48).clipShape(
                    RoundedRectangle(cornerRadius: 7)
                ).accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                if !preview.title.isEmpty { Text(preview.title).font(.subheadline.weight(.semibold)).lineLimit(2) }
                if let host = URL(string: preview.url)?.host {
                    Text(host).font(.caption).lineLimit(1).truncationMode(.middle)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "arrow.up.right").font(.caption).accessibilityHidden(true)
        }.padding(9).background(.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
            .accessibilityElement(children: .combine)
    }
}

struct MessageComposerContext: View {
    let draft: MessageActionDraft
    let text: String
    let name: (UUID) -> String
    let vault: MessageVault?
    let conversation: String
    @State private var automatic = false
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let reply = draft.reply {
                HStack {
                    ReplyExcerptView(author: name(reply.sender_id), excerpt: reply.excerpt)
                    Button {
                        draft.reply = nil
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .frame(minWidth: 44, minHeight: 44).accessibilityLabel("Cancel reply")
                }
            }
            if let preview = draft.preview {
                HStack {
                    EmbeddedLinkCard(preview: preview)
                    Button {
                        if let url = draft.preview?.url, let vault {
                            try? vault.transaction {
                                try vault.put("compose-preview-muted", conversation, Data(url.utf8))
                            }
                        }
                        draft.removePreview()
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .frame(minWidth: 44, minHeight: 44).accessibilityLabel("Remove preview")
                }
            } else if let url = ChatFeatures.Preview.firstURL(in: text) {
                HStack {
                    Button {
                        draft.fetch(url)
                    } label: {
                        Label("Add preview", systemImage: "link")
                    }
                    .frame(minHeight: 44).disabled(draft.loading)
                    if draft.loading { ProgressView().accessibilityLabel("Loading preview") }
                    if draft.unavailable { Text("Preview unavailable").font(.footnote) }
                }
            }
        }.padding(.horizontal, 12)
            .task(id: vault?.account) {
                guard let vault else { return }
                if let data = try? vault.transaction({ try vault.get("compose-preview-muted", conversation) }),
                    let url = URL(string: String(decoding: data, as: UTF8.self))
                {
                    draft.restoreSuppression(url, text: text)
                }
                automatic =
                    (try? vault.transaction { try vault.get("privacy", "automatic-link-previews") == Data([1]) })
                    == true
                draft.update(text, automatic: automatic)
            }
            .onChange(of: text, initial: true) { _, value in draft.update(value, automatic: automatic) }
            .onChange(of: automatic) { _, value in draft.update(text, automatic: value) }
            .onChange(of: draft.reply) { _, _ in persist() }
            .onChange(of: draft.preview) { _, _ in persist() }
            .onDisappear { draft.leave() }
    }
    private func persist() {
        guard let vault else { return }
        try? vault.transaction {
            if draft.reply != nil || draft.preview != nil {
                let features = ChatFeatures(reply: draft.reply, link_preview: draft.preview)
                try vault.put("compose-features", conversation, JSONEncoder().encode(features))
            } else {
                try vault.remove("compose-features", conversation)
            }
        }
    }
    static func saved(_ vault: MessageVault?, conversation: String) -> ChatFeatures? {
        guard let vault else { return nil }
        return try? vault.transaction {
            try vault.get("compose-features", conversation).map {
                try JSONDecoder().decode(ChatFeatures.self, from: $0)
            }
        }
    }
}

struct MessageActionTarget: Identifiable, Equatable {
    let id: UUID
    let sender: UUID
    let quote: ChatFeatures.Reply
}

struct MessageActionFooter<Metadata: View>: View {
    let target: MessageActionTarget
    let account: UUID
    let entries: [MessageReactions.Entry]
    let allowReaction: Bool
    let metadataLabel: String
    let name: (UUID) -> String
    let reply: () -> Void
    let react: (String?) async throws -> Void
    @Binding var selected: UUID?
    @ViewBuilder let metadata: () -> Metadata
    @State private var showingPeople = false
    @State private var more = false
    @State private var input = ""
    @State private var busy = false
    @State private var error: String?
    private let choices = ["❤️", "👍", "😂", "😮", "😢"]
    private var active: [MessageReactions.Entry] { entries.filter { $0.emoji != nil } }
    private var mine: String? { active.first { $0.actor == account }?.emoji }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                selected = target.id
            } label: {
                HStack(spacing: 6) {
                    metadata()
                    Image(systemName: "ellipsis").font(.caption)
                }
                .frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityLabel("Message actions").accessibilityValue(metadataLabel)
                .accessibilityIdentifier("message-actions-" + target.id.uuidString.lowercased())
                .popover(isPresented: Binding(get: { selected == target.id }, set: { if !$0 { selected = nil } })) {
                    menu
                }
            if !active.isEmpty {
                Button {
                    showingPeople = true
                } label: {
                    HStack(spacing: 4) {
                        Text(Array(Set(active.compactMap(\.emoji))).sorted().prefix(3).joined())
                        Text(active.count.formatted()).monospacedDigit()
                    }.font(.caption.weight(.semibold)).padding(.horizontal, 8).padding(.vertical, 3)
                        .background(.primary.opacity(0.07), in: Capsule()).frame(minHeight: 44)
                }.accessibilityLabel("Reactions").accessibilityValue(active.count.formatted())
            }
        }
        .sheet(isPresented: $showingPeople) {
            NavigationStack {
                List {
                    ForEach(active.sorted { $0.actor.uuidString < $1.actor.uuidString }, id: \.actor) { entry in
                        HStack {
                            Text(name(entry.actor))
                            Spacer()
                            Text(entry.emoji ?? "")
                        }
                    }
                    if allowReaction {
                        Button("Change reaction") {
                            showingPeople = false
                            selected = target.id
                        }
                    }
                }.navigationTitle("Reactions").toolbar { Button("Done") { showingPeople = false } }
            }.presentationDetents([.medium, .large])
        }
        .alert(
            "Couldn’t add this reaction", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(error ?? "")
        }
    }
    private var menu: some View {
        VStack(alignment: .leading, spacing: 6) {
            if allowReaction {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 0) { reactionButtons }.fixedSize()
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 44, maximum: 48), spacing: 0)], spacing: 0) {
                        reactionButtons
                    }
                }
                if more {
                    ReactionEmojiField(text: $input).frame(minHeight: 44)
                    Button("Use emoji") { apply(input) }.disabled(!valid(input) || busy)
                }
            }
            Button {
                selected = nil
                reply()
            } label: {
                Label("Reply", systemImage: "arrowshape.turn.up.left")
            }.frame(minHeight: 44)
        }.padding(12).presentationCompactAdaptation(.popover)
            .onDisappear {
                input = ""
                more = false
            }
    }
    @ViewBuilder private var reactionButtons: some View {
        ForEach(choices, id: \.self) { emoji in
            Button {
                apply(emoji)
            } label: {
                Text(emoji).font(.title3).frame(minWidth: 44, minHeight: 44)
                    .background(emoji == mine ? Color.primary.opacity(0.12) : .clear, in: Circle())
            }.disabled(busy)
        }
        Button {
            more.toggle()
        } label: {
            Image(systemName: "plus.circle").frame(minWidth: 44, minHeight: 44)
        }.accessibilityLabel("More reactions")
    }
    private func valid(_ value: String) -> Bool {
        ChatFeatures.Reaction(message_id: target.id, target_sender_id: target.sender, sequence: 1, emoji: value).valid
    }
    private func apply(_ value: String) {
        guard !busy, valid(value) else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                try await react(value == mine ? nil : value)
                selected = nil
            } catch {
                self.error = ChatSession.explanation(error)
                selected = nil
            }
        }
    }
}

private struct MessagePan: UIGestureRecognizerRepresentable {
    let rtl: Bool
    let changed: (CGFloat) -> Void
    let finish: (Bool?) -> Void
    func makeCoordinator(converter: CoordinateSpaceConverter) -> Delegate { Delegate() }
    final class Pan: UIPanGestureRecognizer {
        var startedAt: TimeInterval = 0
        override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent) {
            startedAt = ProcessInfo.processInfo.systemUptime
            super.touchesBegan(touches, with: event)
        }
    }
    final class Delegate: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? Pan, let view = pan.view,
                ProcessInfo.processInfo.systemUptime - pan.startedAt < 0.35
            else { return false }
            let velocity = pan.velocity(in: view)
            return abs(velocity.x) > 1.8 * abs(velocity.y)
        }
        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
        ) -> Bool { true }
    }
    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = Pan()
        pan.maximumNumberOfTouches = 1
        pan.delegate = context.coordinator
        pan.cancelsTouchesInView = false
        return pan
    }
    func handleUIGestureRecognizerAction(_ pan: UIPanGestureRecognizer, context: Context) {
        let p = pan.translation(in: pan.view), dx = rtl ? -p.x : p.x
        switch pan.state {
        case .began, .changed: changed(abs(p.y) * 1.8 < abs(dx) ? dx : 0)
        case .ended: finish(abs(dx) >= 64 && abs(p.y) * 1.8 < abs(dx) ? dx > 0 : nil)
        case .cancelled, .failed: finish(nil)
        default: break
        }
    }
}
struct MessageSwipeActions: ViewModifier {
    @Environment(\.layoutDirection) private var direction
    @State private var distance: CGFloat = 0
    @State private var crossed = false
    let reply: () -> Void
    let actions: () -> Void
    func body(content: Content) -> some View {
        content.overlay(alignment: distance > 0 ? .leading : .trailing) {
            if abs(distance) > 20 {
                Image(systemName: distance > 0 ? "arrowshape.turn.up.left.fill" : "face.smiling")
                    .padding(8).background(.regularMaterial, in: Circle()).allowsHitTesting(false).accessibilityHidden(
                        true)
            }
        }.gesture(
            MessagePan(
                rtl: direction == .rightToLeft,
                changed: { value in
                    distance = value
                    if !crossed && abs(value) >= 64 {
                        crossed = true
                        UISelectionFeedbackGenerator().selectionChanged()
                    }
                },
                finish: { action in
                    distance = 0
                    crossed = false
                    if let action { action ? reply() : actions() }
                })
        )
        .accessibilityAction(named: "Reply", reply)
        .accessibilityAction(named: "React", actions)
    }
}

/// Request the user's installed system emoji keyboard and retain their normal
/// keyboard switcher for dictation, hardware input, and accessibility.
private struct ReactionEmojiField: UIViewRepresentable {
    @Binding var text: String
    final class Field: UITextField {
        override var textInputContextIdentifier: String? { "vipi.reaction" }
        override var textInputMode: UITextInputMode? {
            UITextInputMode.activeInputModes.first { $0.primaryLanguage == "emoji" } ?? super.textInputMode
        }
    }
    final class Coordinator: NSObject {
        var owner: ReactionEmojiField
        init(_ owner: ReactionEmojiField) { self.owner = owner }
        @objc func changed(_ input: UITextField) { owner.text = input.text ?? "" }
    }
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> Field {
        let field = Field()
        field.placeholder = String(localized: "Emoji")
        field.accessibilityLabel = field.placeholder
        field.font = .preferredFont(forTextStyle: .body)
        field.adjustsFontForContentSizeCategory = true
        field.borderStyle = .roundedRect
        field.addTarget(context.coordinator, action: #selector(Coordinator.changed(_:)), for: .editingChanged)
        DispatchQueue.main.async { [weak field] in field?.becomeFirstResponder() }
        return field
    }
    func updateUIView(_ view: Field, context: Context) {
        context.coordinator.owner = self
        if view.text != text { view.text = text }
    }
}
