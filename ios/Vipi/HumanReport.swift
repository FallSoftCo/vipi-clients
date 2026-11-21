import SwiftUI
import CryptoKit
import UIKit
import UIKit.UIGestureRecognizerSubclass
import Observation

enum HumanReportReason: String, Codable, CaseIterable, Identifiable {
    case spam, harassment, harmful, other
    var id: String { rawValue }
    var title: String { switch self { case .spam: "Spam"; case .harassment: "Harassment"; case .harmful: "Harmful content"; case .other: "Something else" } }
}
struct HumanReportBody: Codable, Equatable {
    let report_id: UUID
    let reported_user_id: UUID
    let message_id: UUID?
    let reason: HumanReportReason
    let selected_text: String?
    let consent_version: String
    enum CodingKeys: String, CodingKey { case report_id, reported_user_id, message_id, reason, selected_text, consent_version }
    func encode(to encoder: Encoder) throws {
        var value = encoder.container(keyedBy: CodingKeys.self)
        try value.encode(report_id, forKey: .report_id); try value.encode(reported_user_id, forKey: .reported_user_id)
        try value.encode(message_id, forKey: .message_id); try value.encode(reason, forKey: .reason)
        try value.encode(selected_text, forKey: .selected_text); try value.encode(consent_version, forKey: .consent_version)
    }
}
struct HumanReportReply: Decodable { let reported: Bool; let report_id: UUID }
struct SavedHumanReport: Codable {
    let key: String
    let body: HumanReportBody
    let createdAt: Date
    var reported: Bool
}
enum HumanReportStore {
    /// Called only after the explicit disclosure confirmation. The original
    /// received journal record is authoritative, never the translated rendering.
    static func prepare(vault: MessageVault, peer: UUID, message: ChatItem?, reason: HumanReportReason) throws -> SavedHumanReport {
        try vault.transaction {
            guard peer != vault.account else { throw MessageJournal.Failure.invalidMessage }
            var text: String?
            if let message {
                guard !message.outgoing, message.state != "imported", message.peer == peer,
                      let bytes = try vault.get("incoming", message.id.uuidString.lowercased()) else { throw MessageJournal.Failure.invalidMessage }
                let original = try JSONDecoder().decode(StoredChat.self, from: bytes)
                guard original.envelope.id == message.id, original.envelope.sender == peer,
                      original.envelope.recipient == vault.account, original.text == message.text,
                      !original.text.isEmpty, original.text.utf8.count <= 32768 else { throw MessageJournal.Failure.invalidMessage }
                text = original.text
            }
            // Excludes the random request ID, so reopening/retrying the same
            // confirmed report reuses its durable body after an uncertain POST.
            let semantic = HumanReportBody(report_id: UUID(uuidString: "00000000-0000-0000-0000-000000000000")!,
                reported_user_id: peer, message_id: message?.id, reason: reason, selected_text: text, consent_version: "report-v1")
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            let key = SHA256.hash(data: try encoder.encode(semantic)).map { String(format: "%02x", $0) }.joined()
            if let bytes = try vault.get("human-report", key) {
                return try JSONDecoder().decode(SavedHumanReport.self, from: bytes)
            }
            let value = SavedHumanReport(key: key, body: HumanReportBody(report_id: UUID(), reported_user_id: peer,
                message_id: message?.id, reason: reason, selected_text: text, consent_version: "report-v1"), createdAt: Date(), reported: false)
            try vault.put("human-report", key, encoder.encode(value))
            return value
        }
    }
    static func complete(vault: MessageVault, report: SavedHumanReport) throws {
        try vault.transaction {
            guard let bytes = try vault.get("human-report", report.key) else { throw MessageJournal.Failure.missingMessage }
            var saved = try JSONDecoder().decode(SavedHumanReport.self, from: bytes)
            guard saved.body == report.body else { throw MessageJournal.Failure.conflict }
            saved.reported = true
            try vault.put("human-report", report.key, JSONEncoder().encode(saved))
        }
    }
}

struct HumanReportSelection: Identifiable {
    let id = UUID()
    let message: ChatItem?
}
struct HumanReportView: View {
    @Environment(\.dismiss) private var dismiss
    let chat: ChatSession
    let peer: UUID
    let message: ChatItem?
    @State private var reason = HumanReportReason.spam
    @State private var attempted = false
    @State private var busy = false
    @State private var reported = false
    @State private var notice: String?
    var body: some View {
        NavigationStack {
            Form {
                if reported {
                    Section { Label("Report received", systemImage: "checkmark.circle") }
                    Section { Text("You can also block this person from the conversation menu.") }
                } else {
                    Section(message == nil ? "Person to report" : "Original message to share") {
                        Text(chat.name(peer))
                        if let message { Text(message.text).textSelection(.enabled).accessibilityIdentifier("human-report-original") }
                    }
                    Section("Reason") {
                        Picker("Reason", selection: $reason) {
                            ForEach(HumanReportReason.allCases) { Text(LocalizedStringKey($0.title)).tag($0) }
                        }.disabled(attempted || busy)
                    }
                    Section {
                        Text(LocalizedStringKey(message == nil
                            ? "Send this person’s account identifier and your reason to Fallible Software, Co. (FallSoft) for review. No messages are shared."
                            : "Send only the original message shown above, the account identifiers and your reason to Fallible Software, Co. (FallSoft) for review. This shares the selected text outside your encrypted chat."))
                        Text("Reports are stored encrypted for up to 30 days. A report does not automatically block anyone or guarantee a response.")
                            .font(.footnote).foregroundStyle(VipiDesign.secondary)
                        Link("Privacy and reporting", destination: URL(string: "https://mambovipi.app/privacy.html")!)
                        Button(LocalizedStringKey(attempted ? "Retry this report" : "Send report to FallSoft")) { submit() }
                            .disabled(busy).accessibilityIdentifier("human-report-submit")
                        if busy { ProgressView("Sending report") }
                    }
                }
                if let notice { Section { Text(notice).accessibilityIdentifier("human-report-notice") } }
            }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle(message == nil ? "Report person" : "Report message").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(reported ? "Done" : "Cancel") { dismiss() }.disabled(busy) } }
                .interactiveDismissDisabled(busy)
        }
    }
    private func submit() {
        guard !busy else { return }; attempted = true; busy = true; notice = nil
        Task {
            defer { busy = false }
            do { try await chat.report(peer: peer, message: message, reason: reason); reported = true }
            catch { notice = String(localized: "We couldn’t confirm this report. Retrying sends the same report without creating a duplicate.") }
        }
    }
}

/// Touch reporting stays reachable without overloading the meaning-reveal gesture.
/// Selecting only opens the existing explicit review; it never sends a report.
struct ReportMessageChoice: Identifiable {
    let id: String
    let original: String
}
struct ReportMessagePicker: View {
    let choices: [ReportMessageChoice]
    let select: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List(choices) { item in
                Button { select(item.id); dismiss() } label: {
                    Text(verbatim:item.original).font(.body).foregroundStyle(.primary)
                        .fixedSize(horizontal:false,vertical:true).frame(maxWidth:.infinity,minHeight:44,alignment:.leading)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("report-message-choice-" + item.id)
            }
            .navigationTitle("Report a message").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }
}

// The chooser owns immutable raw message values, never translated/revealed text.
struct CopyOriginalChoice: Identifiable {
    let id: String
    let original: String
}
struct CopyOriginalPicker: View {
    let choices: [CopyOriginalChoice]
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List(choices) { item in
                Button {
                    UIPasteboard.general.string = item.original
                    dismiss()
                } label: {
                    Text(verbatim:item.original).font(.body).foregroundStyle(.primary)
                        .fixedSize(horizontal:false,vertical:true)
                        .frame(maxWidth:.infinity,minHeight:44,alignment:.leading)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityIdentifier("copy-original-choice-" + item.id)
            }
            .navigationTitle("Copy original message").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.cancellationAction) {
                Button("Cancel") { dismiss() }.accessibilityIdentifier("copy-original-cancel")
            } }
        }
    }
}

/// Captures composer state before the existing header Menu interprets a touch.
/// Keyboard notifications are converted from screen into this window; a raw,
/// unconstrained UIWindow.keyboardLayoutGuide is not a visibility authority.
@MainActor @Observable final class CopyOriginalContext: NSObject {
    var presented = false
    private(set) var holdingLayout = false
    private(set) var choices: [CopyOriginalChoice] = []
    private(set) var captureStage = "none"
    private(set) var captureRevision:UInt64 = 0
    private(set) var capturedKeyboardVisible: Bool?
    private(set) var restoreOutcome = "none"
    private(set) var capturedTimelineScrolls = 0
    private(set) var menuGeneration:UInt64 = 0
    private(set) var menuSignalAttached = false
    @ObservationIgnored private(set) weak var anchor: UIView?
    #if DEBUG
    @ObservationIgnored private(set) var anchorRevision:UInt64 = 0
    #endif
    @ObservationIgnored private let editorID: String
    @ObservationIgnored private let timelineID: String
    @ObservationIgnored private var snapshot: Snapshot?
    @ObservationIgnored private var preparedMenu: Snapshot?
    @ObservationIgnored private var stagedTouch: Snapshot?
    @ObservationIgnored private weak var stagedTouchEvent: UITouch?
    @ObservationIgnored private weak var menuControl: UIControl?
    @ObservationIgnored private var frames: CADisplayLink?
    @ObservationIgnored private var attempts = 0
    @ObservationIgnored private var stableFrames = 0
    @ObservationIgnored private var keyboardMoving = false
    @ObservationIgnored private var keyboardFrame: CGRect?
    @ObservationIgnored private weak var keyboardScreen: UIScreen?
    @MainActor private final class Scroll {
        weak var view: UIScrollView?
        let offset: CGPoint
        init(_ view:UIScrollView) { self.view = view; offset = view.contentOffset }
    }
    @MainActor private final class Snapshot {
        weak var editor: UIView?
        let firstResponder: Bool
        let keyboardVisible: Bool?
        let selection: (Int,Int)?
        let scrolls: [Scroll]
        init(editor:UIView?,visibility:Bool?,scrolls:[Scroll]) {
            self.editor = editor; firstResponder = editor?.isFirstResponder ?? false
            keyboardVisible = visibility
            if let input = editor as? any UITextInput,let range = input.selectedTextRange {
                selection = (input.offset(from:input.beginningOfDocument,to:range.start),
                             input.offset(from:input.beginningOfDocument,to:range.end))
            } else { selection = nil }
            self.scrolls = scrolls
        }
    }
    init(editorID:String,timelineID:String = "conversation-timeline") {
        self.editorID = editorID; self.timelineID = timelineID; super.init()
        // Observe before any composer focus, not just after Copy was chosen.
        // Selector observers unregister automatically when their target dies.
        NotificationCenter.default.addObserver(self,selector:#selector(keyboardWillChange(_:)),name:UIResponder.keyboardWillChangeFrameNotification,object:nil)
        NotificationCenter.default.addObserver(self,selector:#selector(keyboardDidChange(_:)),name:UIResponder.keyboardDidChangeFrameNotification,object:nil)
    }
    func attachAnchor(_ view:UIView) {
        guard view.window != nil else { detachAnchor(view); return }
        guard anchor !== view else { return }
        anchor = view
        #if DEBUG
        anchorRevision &+= 1
        #endif
    }
    func detachAnchor(_ view:UIView) {
        // A superseded representable may detach after its replacement attached.
        // It must never clear that newer conversation anchor.
        guard anchor === view else { return }
        anchor = nil
        #if DEBUG
        anchorRevision &+= 1
        #endif
    }
    private func editorAndScrolls(in window:UIWindow)->(UIView?,[Scroll],Int) {
        var editor:UIView?, scrolls:[Scroll] = [], saved = Set<ObjectIdentifier>(), timeline = Set<ObjectIdentifier>()
        func save(_ scroll:UIScrollView,timelineScoped:Bool) {
            let id = ObjectIdentifier(scroll)
            if timelineScoped { timeline.insert(id) }
            if saved.insert(id).inserted { scrolls.append(Scroll(scroll)) }
        }
        func visit(_ view:UIView,inComposer:Bool = false,inTimeline:Bool = false) {
            guard !view.isHidden,view.alpha > 0 else { return }
            let composing = inComposer || view.accessibilityIdentifier == editorID
            let reading = inTimeline || view.accessibilityIdentifier == timelineID
            if composing,view is any UITextInput { editor = view }
            if let scroll = view as? UIScrollView,composing || reading { save(scroll,timelineScoped:reading) }
            // The SwiftUI identifier may be hosted inside the native scroll
            // view; only its nearest enclosing scroll is eligible, never all
            // scroll views in the app window or other navigation destinations.
            if view.accessibilityIdentifier == timelineID,!(view is UIScrollView) {
                var parent = view.superview
                while let current = parent {
                    if let scroll = current as? UIScrollView { save(scroll,timelineScoped:true); break }
                    parent = current.superview
                }
            }
            for child in view.subviews { visit(child,inComposer:composing,inTimeline:reading) }
        }
        // Search only the native controller owning this conversation anchor.
        // Never restore offsets in unrelated windows/navigation destinations.
        var responder:UIResponder? = anchor
        var root:UIView?
        while let current = responder {
            if let controller = current as? UIViewController { root = controller.view; break }
            responder = current.next
        }
        if let root,root.window === window { visit(root) }
        return (editor,scrolls,timeline.count)
    }
    #if DEBUG
    var anchorProof:[String:Any] {
        var value:[String:Any] = ["anchor_present":anchor != nil,
            "anchor_window_attached":anchor?.window != nil,"anchor_revision":anchorRevision]
        if let anchor,let window = anchor.window {
            let (editor,_,timelineCount) = editorAndScrolls(in:window)
            value["anchor_window_foreground"] = window.windowScene?.activationState == .foregroundActive
            value["anchor_descends_from_window"] = anchor.isDescendant(of:window)
            value["anchor_editor_present"] = editor?.window === window
            value["anchor_timeline_scrolls"] = timelineCount
        }
        return value
    }
    func selectionProof(in window:UIWindow)->[[String:Any]] {
        guard let view = editorAndScrolls(in:window).0,let input = view as? any UITextInput,
              let range = input.selectedTextRange else { return [] }
        return [["first_responder":view.isFirstResponder,
            "text":input.textRange(from:input.beginningOfDocument,to:input.endOfDocument).flatMap { input.text(in:$0) } ?? "",
            "start":input.offset(from:input.beginningOfDocument,to:range.start),
            "end":input.offset(from:input.beginningOfDocument,to:range.end)]]
    }
    #endif
    func keyboardVisible(in window:UIWindow)->Bool? {
        if let keyboardFrame,keyboardScreen == nil || keyboardScreen === window.screen {
            let local = window.convert(keyboardFrame,from:window.screen.coordinateSpace)
            let overlap = local.intersection(window.bounds)
            return !overlap.isNull && overlap.width > 0 && overlap.height > 0
        }
        // No software keyboard can belong to an unfocused composer. A focused
        // editor alone cannot distinguish software, hidden or hardware input.
        return editorAndScrolls(in:window).0?.isFirstResponder == true ? nil : false
    }
    func bindMenuControl(_ control:UIControl?) {
        if control == nil {
            menuControl = nil; menuSignalAttached = false
            preparedMenu = nil; stagedTouch = nil; stagedTouchEvent = nil; return
        }
        guard menuControl !== control else { return }
        menuControl = control; menuSignalAttached = true
        preparedMenu = nil; stagedTouch = nil; stagedTouchEvent = nil
    }
    private func takeSnapshot(in window:UIWindow)->Snapshot {
        let (editor,scrolls,_) = editorAndScrolls(in:window)
        return Snapshot(editor:editor,visibility:keyboardVisible(in:window),scrolls:scrolls)
    }
    func captureBeforeMenu(touch:UITouch) {
        guard !holdingLayout,let window = anchor?.window else { return }
        // Staging alone is never authoritative. A later public menu event must
        // contain this same current touch before it may consume this snapshot.
        stagedTouch = takeSnapshot(in:window); stagedTouchEvent = touch
    }
    func menuWillPresent(event:UIEvent?) {
        guard !holdingLayout,let window = anchor?.window,menuControl?.window === window else { return }
        // UIKit's menuActionTriggered precedes each presentation, including
        // hardware/programmatic activation. Replace cancelled-menu state here.
        preparedMenu = nil; menuGeneration &+= 1
        if event?.type == .touches,let touch = stagedTouchEvent,
           touch.phase != .cancelled,event?.allTouches?.contains(where:{$0 === touch}) == true,
           let stagedTouch {
            preparedMenu = stagedTouch; captureStage = "native-menu-current-touch"
        } else {
            preparedMenu = takeSnapshot(in:window); captureStage = "native-menu-before-presentation"
        }
        stagedTouch = nil; stagedTouchEvent = nil
        captureRevision &+= 1
        capturedKeyboardVisible = preparedMenu?.keyboardVisible
        capturedTimelineScrolls = editorAndScrolls(in:window).2
    }
    #if DEBUG
    var preparedSelectionForQualification:[Int] {
        guard let (start,end) = preparedMenu?.selection else { return [] }; return [start,end]
    }
    var preparedTimelineOffsetForQualification:CGPoint? {
        preparedMenu?.scrolls.first(where:{$0.view?.accessibilityIdentifier == timelineID})?.offset
    }
    var activeSelectionForQualification:[Int] {
        guard let (start,end) = snapshot?.selection else { return [] }; return [start,end]
    }
    #endif
    /// Both menu actions and controlled native cancellation tests use this same
    /// unconditional stop entry. Empty choices/no window still stop all intents.
    func open(_ choices:[CopyOriginalChoice],autoplay:ChatAutoplay,speech:SpeechPlayback,reading:ChatReadingState,fromMenu:Bool = false) {
        autoplay.stop(speech:speech); reading.cancelInteractions()
        guard !presented,!holdingLayout,let window = anchor?.window,!choices.isEmpty else { return }
        // Consume once. A bare touch cannot authorize an old saved snapshot.
        // Unsupported native menu implementations use current state explicitly.
        if fromMenu,menuSignalAttached,menuControl != nil,let preparedMenu { snapshot = preparedMenu }
        else {
            snapshot = takeSnapshot(in:window)
            captureStage = "action-fallback"; captureRevision &+= 1
            capturedKeyboardVisible = snapshot?.keyboardVisible
            capturedTimelineScrolls = editorAndScrolls(in:window).2
        }
        preparedMenu = nil; stagedTouch = nil; stagedTouchEvent = nil
        self.choices = choices; holdingLayout = true; restoreOutcome = "pending"
        // Remove retained hidden focus before UIKit presents a sheet, so its
        // own dismissal cannot reactivate that hidden software keyboard either.
        if snapshot?.keyboardVisible != true { _ = snapshot?.editor?.resignFirstResponder() }
        presented = true
    }
    func restore() {
        guard holdingLayout,let snapshot,let window = anchor?.window,
              window.windowScene?.activationState == .foregroundActive else { abandon(); return }
        if snapshot.keyboardVisible == true && snapshot.firstResponder {
            _ = snapshot.editor?.becomeFirstResponder()
        } else if snapshot.keyboardVisible == false {
            // A retained first responder with hidden IME must never reopen it.
            // Preserve text and selection, deliberately resign rather than
            // reactivate the native editor in this hidden-keyboard branch.
            if snapshot.editor?.isFirstResponder == true { _ = snapshot.editor?.resignFirstResponder() }
        }
        // Unknown visibility never calls becomeFirstResponder. Native tests
        // require a known notification-derived state for the visible case.
        attempts = 0; stableFrames = 0; frames?.invalidate()
        let frames = CADisplayLink(target:self,selector:#selector(restoreFrame))
        self.frames = frames; frames.add(to:.main,forMode:.common)
    }
    private func keyboardChanged(_ notification:Notification,moving:Bool) {
        if let screen = notification.object as? UIScreen,let window = anchor?.window,screen !== window.screen { return }
        guard let frame = (notification.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? NSValue)?.cgRectValue else { return }
        keyboardScreen = notification.object as? UIScreen; keyboardFrame = frame
        keyboardMoving = moving; stableFrames = 0
    }
    @objc private func keyboardWillChange(_ notification:Notification) { keyboardChanged(notification,moving:true) }
    @objc private func keyboardDidChange(_ notification:Notification) { keyboardChanged(notification,moving:false) }
    @objc private func restoreFrame() {
        guard let snapshot,let window = anchor?.window,
              window.windowScene?.activationState == .foregroundActive else { abandon(); return }
        attempts += 1; window.layoutIfNeeded()
        let visible = keyboardVisible(in:window)
        let visibilityMatches = snapshot.keyboardVisible.map { visible == $0 } ?? true
        if !keyboardMoving && visibilityMatches {
            if let input = snapshot.editor as? any UITextInput,let (start,end) = snapshot.selection,
               let a = input.position(from:input.beginningOfDocument,offset:start),
               let b = input.position(from:input.beginningOfDocument,offset:end) {
                input.selectedTextRange = input.textRange(from:a,to:b)
            }
            for saved in snapshot.scrolls where saved.view?.window === window {
                saved.view?.setContentOffset(saved.offset,animated:false)
            }
            stableFrames += 1
        } else { stableFrames = 0 }
        if stableFrames >= 2 { restoreOutcome = "complete"; finish() }
        else if attempts >= 120 { restoreOutcome = "timed-out"; finish() }
    }
    private func finish() {
        frames?.invalidate(); frames = nil; snapshot = nil
        preparedMenu = nil; stagedTouch = nil; stagedTouchEvent = nil
        holdingLayout = false; choices = []; presented = false
    }
    func abandon() { restoreOutcome = "abandoned"; finish() }
}
struct CopyOriginalAnchor: UIViewRepresentable {
    let context: CopyOriginalContext
    final class Probe:UIView {
        private weak var owner:CopyOriginalContext?
        func setOwner(_ value:CopyOriginalContext?) {
            if owner !== value { owner?.detachAnchor(self); owner = value }
            refreshAttachment()
        }
        private func refreshAttachment() {
            if window != nil { owner?.attachAnchor(self) }
            else { owner?.detachAnchor(self) }
        }
        override func didMoveToWindow() { super.didMoveToWindow(); refreshAttachment() }
        override func didMoveToSuperview() { super.didMoveToSuperview(); refreshAttachment() }
    }
    func makeUIView(context:Context)->Probe {
        let view = Probe(); view.isUserInteractionEnabled = false
        view.setOwner(self.context); return view
    }
    func updateUIView(_ view:Probe,context:Context) { view.setOwner(self.context) }
    static func dismantleUIView(_ view:Probe,coordinator:()) { view.setOwner(nil) }
}

/// Public, passive touch observation on the existing menu label. It never
/// recognizes a gesture, cancels/delays a touch or presents a second menu.
struct CopyOriginalMenuCapture: UIViewRepresentable {
    let context: CopyOriginalContext
    final class Probe: UIView {
        private(set) var owner:CopyOriginalContext?
        private weak var installedWindow:UIWindow?
        private weak var menuControl:UIControl?
        private var observer:TouchObserver?
        func setOwner(_ value:CopyOriginalContext) {
            if owner !== value {
                owner?.bindMenuControl(nil); owner = value
                value.bindMenuControl(menuControl); observer?.updateOwner(value)
            }
            refreshMenuBinding()
        }
        private func refreshMenuBinding() {
            var candidate:UIControl?, view = superview
            while let current = view {
                if let control = current as? UIControl,control.isContextMenuInteractionEnabled,control.showsMenuAsPrimaryAction {
                    candidate = control; break
                }
                view = current.superview
            }
            if window == nil { candidate = nil }
            guard menuControl !== candidate else { return }
            menuControl?.removeTarget(self,action:#selector(menuTriggered(_:forEvent:)),for:.menuActionTriggered)
            menuControl = candidate; owner?.bindMenuControl(candidate)
            candidate?.addTarget(self,action:#selector(menuTriggered(_:forEvent:)),for:.menuActionTriggered)
        }
        @objc private func menuTriggered(_ sender:UIControl,forEvent event:UIEvent?) {
            guard sender === menuControl else { return }; owner?.menuWillPresent(event:event)
        }
        override func layoutSubviews() { super.layoutSubviews(); refreshMenuBinding() }
        override func didMoveToSuperview() { super.didMoveToSuperview(); refreshMenuBinding() }
        override func didMoveToWindow() {
            super.didMoveToWindow(); refreshMenuBinding()
            if installedWindow !== window {
                if let observer { installedWindow?.removeGestureRecognizer(observer) }
                observer = nil; installedWindow = window
                if let window {
                    let observer = TouchObserver(label:self,owner:owner)
                    observer.cancelsTouchesInView = false; observer.delaysTouchesBegan = false; observer.delaysTouchesEnded = false
                    window.addGestureRecognizer(observer); self.observer = observer
                }
            }
        }
    }
    final class TouchObserver: UIGestureRecognizer {
        private weak var label:UIView?
        private weak var owner:CopyOriginalContext?
        init(label:UIView,owner:CopyOriginalContext?) { self.label = label; self.owner = owner; super.init(target:nil,action:nil) }
        @available(*,unavailable) required init?(coder:NSCoder) { return nil }
        func updateOwner(_ value:CopyOriginalContext) { owner = value }
        override func touchesBegan(_ touches:Set<UITouch>,with event:UIEvent) {
            if let label,let touch = touches.first,label.bounds.contains(touch.location(in:label)) { owner?.captureBeforeMenu(touch:touch) }
            state = .failed
        }
        override func canPrevent(_ preventedGestureRecognizer:UIGestureRecognizer)->Bool { false }
        override func canBePrevented(by preventingGestureRecognizer:UIGestureRecognizer)->Bool { false }
    }
    func makeUIView(context:Context)->Probe { let view = Probe(); view.setOwner(self.context); view.isUserInteractionEnabled = false; return view }
    func updateUIView(_ view:Probe,context:Context) { view.setOwner(self.context) }
}

#if DEBUG
/// Explicit synthetic root only. This observes actual UIKit/clipboard/audio
/// state; it does not mutate an editor, set a selection or fake playback.
struct CopyOriginalProof: View {
    let context: CopyOriginalContext
    let autoplay: ChatAutoplay
    let speech: SpeechPlayback
    var body: some View {
        if Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
           ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa"),
           ProcessInfo.processInfo.arguments.contains("-vipi-copy-original-root-qa"),
           !ProcessInfo.processInfo.arguments.contains("-vipi-draft-boundary-root-qa"),
           ProcessInfo.processInfo.environment["VIPI_COPY_CLIPBOARD_ISOLATED"] == "true" {
            TimelineView(.periodic(from:.now,by:0.1)) { _ in
                Text("Copy QA").font(.system(size:1)).frame(width:1,height:1)
                    .accessibilityIdentifier("copy-original-proof|" + proof)
                    .allowsHitTesting(false)
            }
        }
    }
    private var proof:String {
        var value:[String:Any] = ["holding_layout":context.holdingLayout,
            "autoplay":autoplay.enabled,"speech_state":String(describing:speech.state),
            "active_message":speech.activeMessage ?? "",
            "clipboard":UIPasteboard.general.string ?? ""]
        value.merge(context.anchorProof,uniquingKeysWith:{_,new in new})
        if let window = context.anchor?.window {
            value["keyboard_visible"] = context.keyboardVisible(in:window).map { $0 as Any } ?? NSNull()
            value["capture_stage"] = context.captureStage
            value["capture_revision"] = context.captureRevision
            value["menu_generation"] = context.menuGeneration
            value["menu_signal_attached"] = context.menuSignalAttached
            value["captured_keyboard_visible"] = context.capturedKeyboardVisible.map { $0 as Any } ?? NSNull()
            value["restore_outcome"] = context.restoreOutcome
            value["captured_timeline_scrolls"] = context.capturedTimelineScrolls
            value["selection"] = context.selectionProof(in:window)
        }
        return String(decoding:(try? JSONSerialization.data(withJSONObject:value,options:.sortedKeys)) ?? Data(),as:UTF8.self)
    }
}
extension View {
    @ViewBuilder func copyOriginalProof(context:CopyOriginalContext,autoplay:ChatAutoplay,speech:SpeechPlayback)->some View {
        overlay(alignment:.topLeading) { CopyOriginalProof(context:context,autoplay:autoplay,speech:speech) }
    }
}
#endif
