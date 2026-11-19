import SwiftUI
import UIKit
import VipiCore

// Retained mode names for native preview qualification; conversations use gestures.
enum ReadingMode: String, CaseIterable, Identifiable {
    case immersed = "Immersed", original = "Original", translation = "Translation"
    var id: String { rawValue }
    var label: String { self == .original ? String(localized:"Original message") : String(localized:"Full translation") }
}

/// Shared by visible and subsequently loaded rows, never by private message storage.
@MainActor @Observable final class ChatReadingState {
    private let defaults:UserDefaults
    private(set) var needsGestureHint:Bool
    init(defaults:UserDefaults = .standard) {
        self.defaults = defaults; needsGestureHint = !defaults.bool(forKey:"full-message-gestures-v1-seen")
    }
    private func learnedGesture() { if needsGestureHint { needsGestureHint = false; defaults.set(true,forKey:"full-message-gestures-v1-seen") } }
    var nativeScript = false
    var accessibleMeaning = false
    private(set) var holding = false
    var showingMeaning: Bool { holding || accessibleMeaning }
    struct Row {
        let identity: ImmersionRequestIdentity
        var frame: CGRect
        let activate: (Bool) -> Bool
        var hasAlternateScript = false
    }
    private(set) var hasAlternateScript = false
    @ObservationIgnored private var rows: [String:Row] = [:]
    @ObservationIgnored private var pendingPlayback: ImmersionRequestIdentity?
    @ObservationIgnored private var playbackOwner: UUID?
    @ObservationIgnored private var manualPlayback: ((ImmersionRequestIdentity)->Void)?
    @ObservationIgnored private var hintFrames:[UUID:CGRect] = [:]
    func setHintFrame(_ frame:CGRect,owner:UUID) {
        if frame.isNull || frame.isEmpty { hintFrames.removeValue(forKey:owner) }
        else { hintFrames[owner] = frame }
    }
    func removeHintFrame(owner:UUID) { hintFrames.removeValue(forKey:owner) }
    func bindPlayback(owner:UUID,play:@escaping(ImmersionRequestIdentity)->Void) { playbackOwner = owner; manualPlayback = play; pendingPlayback = nil }
    func unbindPlayback(owner:UUID) { if playbackOwner == owner { playbackOwner = nil; manualPlayback = nil; pendingPlayback = nil } }
    func cancelPendingPlayback() { pendingPlayback = nil }
    func register(_ row: Row) {
        rows[row.identity.messageID] = row
        refreshScriptAvailability()
        if pendingPlayback == row.identity, row.activate(true) { pendingPlayback = nil }
    }
    func remove(_ identity: ImmersionRequestIdentity) {
        if rows[identity.messageID]?.identity == identity { rows.removeValue(forKey:identity.messageID) }
        refreshScriptAvailability()
        if pendingPlayback == identity { pendingPlayback = nil }
    }
    private func refreshScriptAvailability() {
        let available = rows.values.contains { $0.hasAlternateScript }
        if available != hasAlternateScript { hasAlternateScript = available }
    }
    func activate(_ identity: ImmersionRequestIdentity, start: Bool = false) {
        learnedGesture()
        if let manualPlayback { pendingPlayback = nil; manualPlayback(identity); return }
        guard let row = rows[identity.messageID], row.identity == identity else { return }
        if pendingPlayback == identity && !start { pendingPlayback = nil; return }
        if row.activate(start) { pendingPlayback = nil } else { pendingPlayback = identity }
    }
    private func row(at point: CGPoint) -> Row? {
        rows.values.filter { $0.frame.contains(point) }.min { $0.frame.width*$0.frame.height < $1.frame.width*$1.frame.height }
    }
    func tap(at point: CGPoint) {
        // A scrolled row may extend behind the first-chat hint. Only visible
        // message content should respond to a playback tap in that area.
        guard !hintFrames.values.contains(where:{$0.contains(point)}) else { return }
        if let row = row(at:point) { activate(row.identity) }
    }
    func hold(at point: CGPoint) {
        learnedGesture(); holding = true
    }
    func releaseHold() { holding = false }
    func cancelInteractions() { holding = false; accessibleMeaning = false; pendingPlayback = nil }
    func toggleScript() { learnedGesture(); nativeScript.toggle() }
    func toggleMeaning() { learnedGesture(); accessibleMeaning.toggle() }
    /// Assistive activation uses native actions, not the physical touch grammar.
    static func actionDescription(showingMeaning:Bool = false,nativeScript:Bool = false,hasAlternateScript:Bool = true) -> String {
        var actions = [String(localized:"Play in practice language"),
                       showingMeaning ? String(localized:"Show practice text") : String(localized:"Show meanings")]
        if hasAlternateScript { actions.append(nativeScript ? String(localized:"Show transliteration") : String(localized:"Show native script")) }
        return actions.joined(separator:". ")
    }
    static func gestureDescription(source:String,target:String,hasAlternateScript:Bool) -> String {
        let basic = String(format:String(localized:"Tap to hear %1$@. Hold to read in %2$@."),VipiLanguage.named(target).localizedName,VipiLanguage.named(source).localizedName)
        return hasAlternateScript ? basic + " " + String(format:String(localized:"Double-tap to see %1$@ writing."),VipiLanguage.named(target).localizedName) : basic
    }
}

/// Reserve the cue's current wrapped inset for this first open-chat lifetime.
/// Learning hides its ink/AX content without moving the held message; leaving
/// the conversation releases the inset. Subsequent chats need no cue.
struct ChatGestureCue: View {
    @Environment(AppState.self) private var state
    let reading:ChatReadingState
    let composing:Bool
    @State private var reservesHint:Bool
    @State private var hintOwner = UUID()
    init(reading:ChatReadingState,composing:Bool = false) {
        self.reading = reading; self.composing = composing; _reservesHint = State(initialValue:reading.needsGestureHint)
    }
    var body:some View {
        // The interactive preview teaches all three gestures. In a live chat,
        // remind the reader how to understand a message without a pinned lesson.
        let description = String(format:String(localized:"Hold to read in %1$@."),VipiLanguage.named(state.knownLanguage).localizedName)
        VStack(spacing:0) {
            if reservesHint && !composing {
                InertTextReservation(text:description,
                    minimumHeight:0,insets:UIEdgeInsets(top:18,left:30,bottom:12,right:30),fillsWidth:true)
                    .frame(maxWidth:560)
                    .overlay(alignment:.top) {
                        if reading.needsGestureHint {
                            Text(description)
                                .font(.subheadline).foregroundStyle(VipiDesign.secondary).fixedSize(horizontal:false,vertical:true)
                                .padding(12)
                                .padding(.horizontal,18).padding(.top,6).frame(maxWidth:560)
                                .accessibilityLabel(Text(ChatReadingState.actionDescription(showingMeaning:reading.showingMeaning,nativeScript:reading.nativeScript,hasAlternateScript:reading.hasAlternateScript)))
                                .accessibilityIdentifier("chat-gesture-hint").allowsHitTesting(false)
                        }
                    }
            }
        }
        .frame(maxWidth:.infinity).background(VipiDesign.canvas)
        .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { reading.setHintFrame($0,owner:hintOwner) }
        // Reset only when the whole cue host leaves. Hiding its conditional
        // text for the editor must not consume the first-chat reservation.
        .onDisappear { reservesHint = false; reading.removeHintFrame(owner:hintOwner) }
    }
}

/// A decorative sizing view with no rendered text, action or AX subtree.
/// The measurement UILabel is never installed in a view hierarchy. This reserves
/// current wrapped geometry even when a failed row first arrives in native script
/// or a learned cue receives a new width or Dynamic Type proposal.
private struct InertTextReservation: UIViewRepresentable {
    let text:String
    let minimumHeight:CGFloat
    var insets:UIEdgeInsets = .zero
    var fillsWidth:Bool = false
    func makeUIView(context:Context)->Measure { Measure(frame:.zero) }
    func updateUIView(_ view:Measure,context:Context) {
        let category:UIContentSizeCategory
        switch context.environment.dynamicTypeSize {
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
        case .accessibility5: category = .accessibilityExtraExtraExtraLarge
        @unknown default: category = .large
        }
        view.configure(text:text,font:.preferredFont(forTextStyle:.subheadline,
            compatibleWith:UITraitCollection(preferredContentSizeCategory:category)),minimumHeight:minimumHeight,insets:insets,fillsWidth:fillsWidth)
    }
    func sizeThatFits(_ proposal:ProposedViewSize,uiView:Measure,context:Context)->CGSize? {
        uiView.sizeThatFits(CGSize(width:proposal.width ?? CGFloat.greatestFiniteMagnitude,height:CGFloat.greatestFiniteMagnitude))
    }
    @MainActor final class Measure:UIView {
        private let measurement = UILabel()
        private var minimumHeight:CGFloat = 0
        private var insets:UIEdgeInsets = .zero
        private var fillsWidth = false
        override init(frame:CGRect) {
            super.init(frame:frame)
            backgroundColor = .clear; isOpaque = false; isUserInteractionEnabled = false
            isAccessibilityElement = false; accessibilityElementsHidden = true
            measurement.numberOfLines = 0; measurement.lineBreakMode = .byWordWrapping
        }
        required init?(coder:NSCoder) { fatalError("Not a storyboard view") }
        func configure(text:String,font:UIFont,minimumHeight:CGFloat,insets:UIEdgeInsets,fillsWidth:Bool) {
            measurement.text = text; measurement.font = font; self.minimumHeight = minimumHeight
            self.insets = insets; self.fillsWidth = fillsWidth
            isAccessibilityElement = false; accessibilityElementsHidden = true
            invalidateIntrinsicContentSize()
        }
        override var intrinsicContentSize:CGSize { sizeThatFits(CGSize(width:CGFloat.greatestFiniteMagnitude,height:CGFloat.greatestFiniteMagnitude)) }
        override func sizeThatFits(_ size:CGSize)->CGSize {
            let available = max(0,size.width)
            let horizontal = insets.left + insets.right
            let measured = measurement.sizeThatFits(CGSize(width:max(0,available-horizontal),height:CGFloat.greatestFiniteMagnitude))
            return CGSize(width:fillsWidth ? available : min(available,measured.width+horizontal),
                height:max(minimumHeight,measured.height+insets.top+insets.bottom))
        }
    }
}

/// One recognizer owner for the actual conversation viewport. UIKit arbitrates
/// tap/double-tap/hold before playback; native scrolling and editable controls win.
struct ChatReadingGestureSurface: UIViewRepresentable {
    let reading: ChatReadingState
    func makeUIView(context: Context) -> Capture { Capture(reading:reading) }
    func updateUIView(_ view: Capture, context: Context) { view.reading = reading }
    static func dismantleUIView(_ view: Capture, coordinator: ()) { view.detach() }
    @MainActor final class Capture: UIView, UIGestureRecognizerDelegate {
        var reading: ChatReadingState
        private weak var installedWindow: UIWindow?
        private lazy var single = UITapGestureRecognizer(target:self,action:#selector(tapped(_:)))
        private lazy var double = UITapGestureRecognizer(target:self,action:#selector(doubleTapped(_:)))
        private lazy var hold = UILongPressGestureRecognizer(target:self,action:#selector(held(_:)))
        init(reading: ChatReadingState) { self.reading = reading; super.init(frame:.zero); isUserInteractionEnabled = false }
        required init?(coder: NSCoder) { fatalError("Not a storyboard view") }
        override func didMoveToWindow() {
            super.didMoveToWindow(); detach()
            guard let window else { return }
            double.numberOfTapsRequired = 2; hold.minimumPressDuration = 0.35; hold.allowableMovement = 10
            single.require(toFail:double); single.require(toFail:hold); double.require(toFail:hold)
            for recognizer in [single,double,hold] { recognizer.delegate = self; recognizer.cancelsTouchesInView = false; window.addGestureRecognizer(recognizer) }
            installedWindow = window
        }
        func detach() {
            for recognizer in [single,double,hold] { installedWindow?.removeGestureRecognizer(recognizer) }
            installedWindow = nil; reading.releaseHold()
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
            guard let window, !isHidden, alpha > 0, bounds.width > 0, bounds.height > 0,
                  convert(bounds,to:window).contains(touch.location(in:window)) else { return false }
            // VoiceOver owns its double tap. Equivalent named native actions remain available.
            if UIAccessibility.isVoiceOverRunning { return false }
            var view = touch.view
            while let candidate = view {
                if candidate is UIControl || (candidate.isAccessibilityElement && candidate.accessibilityTraits.contains(.button)) || candidate is UINavigationBar || candidate is UIToolbar ||
                    (candidate as? UITextView)?.isEditable == true || candidate is UITextField { return false }
                view = candidate.superview
            }
            return true
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { false }
        @objc private func tapped(_ gesture: UITapGestureRecognizer) { if gesture.state == .ended, let window { reading.tap(at:gesture.location(in:window)) } }
        @objc private func doubleTapped(_ gesture: UITapGestureRecognizer) { if gesture.state == .ended { reading.toggleScript() } }
        @objc private func held(_ gesture: UILongPressGestureRecognizer) {
            switch gesture.state {
            case .began: if let window { reading.hold(at:gesture.location(in:window)) }
            case .ended,.cancelled,.failed: reading.releaseHold()
            default: break
            }
        }
    }
}

/// Actual full-message renderer. All available faces share one measured native
/// TextKit box, so hold/release/script changes do not move rows or scroll anchors.
struct ImmersionBubble: View {
    let result: ImmersionPresentation
    var outgoing = false
    var mode: ReadingMode = .immersed
    var speech: SpeechPlayback?
    var sourceLanguage = "en"
    var targetLanguage = "es"
    var messageID = "onboarding-example"
    var interactionPaused = false
    var fullReading: String? = nil
    var readingUnavailable = false
    var readingCanRetry = false
    var readingRetryPending = false
    var onReadingRetry: (() -> Void)? = nil
    var targetDwell: Duration = .seconds(4)
    var meaningDwell: Duration = .seconds(3)
    var embedded = false
    var onModeChange: ((ReadingMode)->Void)? = nil
    var metadata: AnyView? = nil
    var accessibilityMessageContext: String? = nil
    var onVoiceHelp: (() -> Void)? = nil
    var originalMessage: String? = nil
    var inputLanguage: String? = nil
    var onInputLanguage: ((String?)->Void)? = nil
    var onReport: (() -> Void)? = nil
    var rawSourceLanguage: String? = nil
    var reading: ChatReadingState? = nil
    var identity: ImmersionRequestIdentity? = nil
    @State private var localReading = ChatReadingState()
    @State private var frame = CGRect.zero
    @Environment(\.scenePhase) private var scenePhase
    private var controls: ChatReadingState { reading ?? localReading }
    private var binding: ImmersionRequestIdentity { identity ?? .init(messageID:messageID,text:originalMessage ?? result.original,source:sourceLanguage,target:targetLanguage,inputLanguage:inputLanguage,generation:UUID(uuidString:"00000000-0000-0000-0000-000000000000")!) }
    private var practice: String { result.translation ?? result.original }
    private var faces: [String] { [result.original,practice]+(fullReading.map { [$0] } ?? []) }
    private var displayed: String {
        if controls.showingMeaning || mode == .original { return result.original }
        return controls.nativeScript ? practice : (fullReading ?? practice)
    }
    private func play(start: Bool) -> Bool {
        guard scenePhase == .active, let speech else { return false }
        if speech.state == .unavailable { onVoiceHelp?(); return true }
        guard speech.state != .preparing else { return false }
        let span = [(text:practice,language:targetLanguage)]
        if start { speech.start(message:messageID,spans:span) } else { speech.toggle(message:messageID,spans:span) }
        return true
    }
    private var hasAlternateScript: Bool { fullReading.map { !$0.isEmpty && $0 != practice } ?? false }
    private func register() { controls.register(.init(identity:binding,frame:frame,activate:play,hasAlternateScript:hasAlternateScript)) }
    private var native: StableImmersionText {
        var view = StableImmersionText(result:.sourceOnly(original:displayed,target:targetLanguage),revealed:[],script:true,onWord:{_ in},onSelection:{_ in})
        view.fitsContentWidth = embedded
        view.reservedSentences = faces
        view.sentenceIdentity = String(describing:binding)+"|"+faces.joined(separator:"\u{0}")
        view.fullMessage = true
        view.onPlayMessage = { controls.activate(binding) }
        view.onMeaning = { controls.toggleMeaning() }
        view.showingMeaning = controls.showingMeaning
        if hasAlternateScript { view.onScript = { controls.toggleScript() } }
        view.showingNativeScript = controls.nativeScript
        view.accessibilityMessageContext = accessibilityMessageContext
        view.originalForCopy = originalMessage ?? result.original
        view.onReport = onReport
        return view
    }
    var body: some View {
        VStack(alignment:.leading,spacing:4) {
            native
            if readingUnavailable {
                let retryable = readingCanRetry && onReadingRetry != nil
                let notice = String(localized:"Reading guide unavailable.") + (retryable ? " " + String(localized:"Try again") : "")
                InertTextReservation(text:notice,minimumHeight:retryable ? 44 : 0)
                    .overlay(alignment:.topLeading) {
                        if !controls.showingMeaning && !controls.nativeScript && mode != .original {
                            Group {
                                if retryable, let onReadingRetry {
                                    Button(action:onReadingRetry) {
                                        (Text("Reading guide unavailable.") + Text(" ") + Text("Try again"))
                                            .frame(minHeight:44,alignment:.leading).contentShape(Rectangle())
                                    }.buttonStyle(.plain).disabled(readingRetryPending)
                                } else { Text("Reading guide unavailable.") }
                            }
                            .font(.subheadline).foregroundStyle(VipiDesign.secondary)
                            .fixedSize(horizontal:false,vertical:true)
                            .frame(maxWidth:.infinity,alignment:.leading)
                            .accessibilityIdentifier("message-reading-unavailable")
                        }
                    }
            }
            if let metadata { metadata }
        }
        .fixedSize(horizontal:false,vertical:true)
        .padding(.horizontal,15).padding(.vertical,12)
        .background(embedded ? Color.clear : VipiDesign.surface,in:RoundedRectangle(cornerRadius:18))
        .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame = $0; register() }
        .onAppear { register() }
        .onChange(of:result) { register() }
        .onChange(of:fullReading) { register() }
        .onChange(of:speech?.state) { register() }
        .onChange(of:interactionPaused) { if !$0 { register() } }
        .onDisappear { controls.remove(binding) }
        .onChange(of:scenePhase) { _,phase in if phase != .active { controls.cancelInteractions(); if speech?.activeMessage == messageID && speech?.autoplayOwned != true { speech?.stop() } } }
        .background { if reading == nil { ChatReadingGestureSurface(reading:localReading) } }
    }
}

/// Conversation-lifetime playback coordinator. Durable events supply future
/// messages in receive/send order; history snapshots are baseline only.
@MainActor @Observable final class ChatAutoplay {
    struct Message {
        let id:String; let load:@MainActor () -> String?; var eligible:Bool = true
        init(id:String,text:String,eligible:Bool = true) { self.id = id; self.load = {text}; self.eligible = eligible }
        init(id:String,load:@escaping @MainActor () -> String?,eligible:Bool = true) { self.id = id; self.load = load; self.eligible = eligible }
    }
    let ownerID = UUID()
    private(set) var enabled = false
    private(set) var voiceNotice: String?
    private var messageFailures: [String:String] = [:]
    func failure(for messageID:String) -> String? { messageFailures[messageID] }
    func voicesReady() { voiceNotice = nil }
    private func inspectCompletion(_ id:String,serial:UInt64,speech:SpeechPlayback) {
        guard let completed = speech.lastCompletion,completed.serial == serial,completed.message == id else { return }
        if completed.succeeded { messageFailures.removeValue(forKey:id) }
        else { messageFailures[id] = speech.error ?? String(localized:"This message couldn’t play. Try again.") }
    }
    private func missingVoice(_ speech:SpeechPlayback) {
        voiceNotice = speech.error ?? String(localized:"Voices couldn’t get ready. Try again."); stop(speech:speech)
    }
    private func bind(_ speech:SpeechPlayback) {
        // Each open conversation owns one coordinator and one player. These
        // callbacks distinguish OS/voice failures from a normal message ending.
        speech.onUnavailable = { [weak self,weak speech] in
            guard let self,let speech else { return }; self.missingVoice(speech)
        }
        speech.onInterruption = { [weak self,weak speech] in
            guard let self,let speech else { return }; self.stop(speech:speech)
        }
    }
    private var seen = Set<String>()
    private var consumed = Set<String>()
    private var queue: [Message] = []
    private var runner: Task<Void,Never>?
    private var manualTask: Task<Void,Never>?
    private var epoch = UUID()
    private var manualEpoch = UUID()
    private var pendingManualID: String?
    private var currentAutomaticID: String?
    #if DEBUG
    var pendingPairQualificationTasks: [String: Task<Void, Never>] {
        ["automatic": runner, "manual": manualTask].compactMapValues { $0 }
    }
    var pendingPairQualificationState: [String: Any] {
        ["owner": ownerID.uuidString, "enabled": enabled,
         "pending_manual_id": pendingManualID ?? "", "automatic_id": currentAutomaticID ?? "",
         "manual_task_present": manualTask != nil, "automatic_task_present": runner != nil,
         "queue_ids": queue.map(\.id)]
    }
    #endif
    func toggle(snapshot:[Message],immersion:ConversationImmersion,speech:SpeechPlayback) {
        bind(speech)
        if enabled { stop(speech:speech); return }
        guard speech.state != .unavailable else { missingVoice(speech); return }
        enabled = true; seen.formUnion(snapshot.map(\.id))
    }
    func arrived(_ message:Message,immersion:ConversationImmersion,speech:SpeechPlayback,foreground:Bool) {
        bind(speech)
        guard seen.insert(message.id).inserted else { return }
        immersion.warmStored(id:message.id,load:message.load)
        guard enabled,foreground,message.eligible else { return }
        queue.append(message); resume(immersion:immersion,speech:speech,foreground:foreground)
    }
    func manual(_ identity:ImmersionRequestIdentity,immersion:ConversationImmersion,speech:SpeechPlayback,
                onModels:@escaping(TranslationPair)->Void,onVoiceHelp:@escaping()->Void) {
        bind(speech)
        let sameAutomatic = currentAutomaticID == identity.messageID && pendingManualID == nil && (speech.activeMessage == nil || speech.activeMessage == identity.messageID)
        if speech.activeMessage == identity.messageID || pendingManualID == identity.messageID || sameAutomatic { stop(speech:speech); return }
        if let currentAutomaticID { consumed.insert(currentAutomaticID); queue.removeAll{$0.id == currentAutomaticID}; self.currentAutomaticID = nil }
        pendingManualID = identity.messageID
        consumed.insert(identity.messageID); queue.removeAll{$0.id == identity.messageID}
        manualEpoch = UUID(); let selected = manualEpoch, active = epoch
        manualTask?.cancel(); speech.stop()
        manualTask = Task { @MainActor [weak self,weak immersion,weak speech] in
            guard let self,let immersion,let speech else { return }
            defer { if manualEpoch == selected { manualTask = nil; pendingManualID = nil } }
            switch immersion.phase(for:identity) {
            case .failed,.timedOut: immersion.retry(identity)
            case .needsDownload,.unsupported: onModels(immersion.requiredPair(for:identity)); return
            default: break
            }
            guard let value = await immersion.translatedMessage(for:identity),!Task.isCancelled,
                  active == epoch,selected == manualEpoch else { return }
            while speech.state == .preparing {
                guard !Task.isCancelled,active == epoch,selected == manualEpoch else { return }
                do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
            }
            guard speech.state != .unavailable else { onVoiceHelp(); return }
            speech.start(message:identity.messageID,spans:[(value.practiceText,value.practiceLanguage)])
            let serial = speech.playbackSerial
            while speech.activeMessage == identity.messageID {
                guard !Task.isCancelled,active == epoch,selected == manualEpoch else { return }
                do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
            }
            guard !Task.isCancelled,active == epoch,selected == manualEpoch else { return }
            inspectCompletion(identity.messageID,serial:serial,speech:speech)
        }
    }
    func resume(immersion:ConversationImmersion,speech:SpeechPlayback,foreground:Bool) {
        bind(speech)
        guard enabled,foreground,runner == nil,!queue.isEmpty else { return }
        let active = epoch
        runner = Task { @MainActor [weak self,weak immersion,weak speech] in
            guard let self,let immersion,let speech else { return }
            defer { if epoch == active { runner = nil; currentAutomaticID = nil } }
            while enabled,epoch == active,!Task.isCancelled,let next = queue.first {
                currentAutomaticID = next.id
                guard let text = next.load() else { queue.removeFirst(); continue }
                let identity = immersion.identity(messageID:next.id,text:text)
                let value = await immersion.translatedMessage(for:identity)
                guard !Task.isCancelled,epoch == active else { return }
                if consumed.contains(next.id) { if queue.first?.id == next.id { queue.removeFirst() }; continue }
                guard let value else { if queue.first?.id == next.id { queue.removeFirst() }; continue }
                while manualTask != nil || speech.state == .preparing || speech.activeMessage != nil {
                    guard !Task.isCancelled,epoch == active else { return }
                    do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
                }
                guard !Task.isCancelled,epoch == active else { return }
                if consumed.contains(next.id) { if queue.first?.id == next.id { queue.removeFirst() }; continue }
                if speech.state == .unavailable { missingVoice(speech); return }
                speech.start(message:next.id,spans:[(value.practiceText,value.practiceLanguage)],autoplay:true)
                let serial = speech.playbackSerial
                while speech.activeMessage == next.id {
                    guard !Task.isCancelled,epoch == active else { return }
                    do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
                }
                inspectCompletion(next.id,serial:serial,speech:speech)
                if queue.first?.id == next.id { queue.removeFirst() }
            }
        }
    }
    func stop(speech:SpeechPlayback) {
        enabled = false; epoch = UUID(); manualEpoch = UUID()
        runner?.cancel(); runner = nil; manualTask?.cancel(); manualTask = nil
        queue.removeAll(); pendingManualID = nil; currentAutomaticID = nil; speech.stop()
    }
}
