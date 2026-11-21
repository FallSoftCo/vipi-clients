import SwiftUI
import UIKit
import VipiCore

// Retained mode names for native preview qualification; conversations use gestures.
enum ReadingMode: String, CaseIterable, Identifiable {
    case immersed = "Immersed", original = "Original", translation = "Translation"
    var id: String { rawValue }
    var label: String { self == .original ? String(localized:"Original message") : String(localized:"Full translation") }
}

/// The speech requested by a gesture belongs to the text the reader touched.
struct DisplayedPracticeAudio {
    let face: ImmersionTextFace?
    let spans: [(text:String, language:String)]
    let incremental: Bool
    var wordID: Int? = nil
}

/// Shared by visible and subsequently loaded rows, never by private message storage.
@MainActor @Observable final class ChatReadingState {
    #if DEBUG
    // Historical QA evidence only. Production coaching uses the account vault.
    private let defaults:UserDefaults
    private(set) var needsGestureHint:Bool
    init(defaults:UserDefaults = .standard) {
        self.defaults = defaults; needsGestureHint = !defaults.bool(forKey:"full-message-gestures-v1-seen")
    }
    private func learnedGesture() { if needsGestureHint { needsGestureHint = false; defaults.set(true,forKey:"full-message-gestures-v1-seen") } }
    #else
    init(defaults: UserDefaults = .standard) {}
    private func learnedGesture() {}
    #endif
    var nativeScript = false
    var accessibleMeaning = false
    private(set) var holding = false
    var showingMeaning: Bool { holding || accessibleMeaning }
    struct Row {
        let identity: ImmersionRequestIdentity
        var frame: CGRect
        let activate: (Bool) -> Bool
        var hasAlternateScript = false
        var audio: DisplayedPracticeAudio? = nil
        var visibleTranslation = false
    }
    @ObservationIgnored weak var revealVisit: RevealHintVisit?
    private(set) var hasVisibleTranslation = false
    private(set) var hasAlternateScript = false
    @ObservationIgnored private var rows: [String:Row] = [:]
    @ObservationIgnored private var pendingPlayback: ImmersionRequestIdentity?
    @ObservationIgnored private var playbackOwner: UUID?
    @ObservationIgnored private var manualPlayback: ((ImmersionRequestIdentity, DisplayedPracticeAudio?)->Void)?
    @ObservationIgnored private var hintFrames:[UUID:CGRect] = [:]
    func setHintFrame(_ frame:CGRect,owner:UUID) {
        if frame.isNull || frame.isEmpty { hintFrames.removeValue(forKey:owner) }
        else { hintFrames[owner] = frame }
    }
    func pointInHint(_ point: CGPoint) -> Bool { hintFrames.values.contains { $0.contains(point) } }
    func removeHintFrame(owner:UUID) { hintFrames.removeValue(forKey:owner) }
    func bindPlayback(owner:UUID,play:@escaping(ImmersionRequestIdentity, DisplayedPracticeAudio?)->Void) { playbackOwner = owner; manualPlayback = play; pendingPlayback = nil }
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
        let translated = rows.values.contains { $0.visibleTranslation }
        if translated != hasVisibleTranslation { hasVisibleTranslation = translated }
        let available = rows.values.contains { $0.hasAlternateScript }
        if available != hasAlternateScript { hasAlternateScript = available }
    }
    func activate(_ identity: ImmersionRequestIdentity, start: Bool = false, audio requested: DisplayedPracticeAudio? = nil) {
        learnedGesture()
        let row = rows[identity.messageID]
        if let requested, row?.identity != identity || row?.audio?.face != requested.face { return }
        if let manualPlayback {
            pendingPlayback = nil
            manualPlayback(identity,requested ?? (row?.identity == identity ? row?.audio : nil))
            return
        }
        guard let row = rows[identity.messageID], row.identity == identity else { return }
        if pendingPlayback == identity && !start { pendingPlayback = nil; return }
        if row.activate(start) { pendingPlayback = nil } else { pendingPlayback = identity }
    }
    func activateWord(_ identity: ImmersionRequestIdentity, audio: DisplayedPracticeAudio, local: () -> Void) {
        guard let row = rows[identity.messageID], row.identity == identity, row.audio?.face == audio.face else { return }
        if manualPlayback != nil { activate(identity,audio:audio) }
        else { learnedGesture(); local() }
    }
    private func row(at point: CGPoint) -> Row? {
        rows.values.filter { $0.frame.contains(point) }.min { $0.frame.width*$0.frame.height < $1.frame.width*$1.frame.height }
    }
    func tap(at point: CGPoint) {
        // A scrolled row may extend behind the first-chat hint. Only visible
        // message content should respond to a playback tap in that area.
        guard !pointInHint(point) else { return }
        if let row = row(at:point) { activate(row.identity) }
    }
    func hold(at point: CGPoint) {
        if hasVisibleTranslation && !showingMeaning { revealVisit?.revealed(keepSpace: true) }
        learnedGesture(); pendingPlayback = nil; holding = true
    }
    func releaseHold() { holding = false; revealVisit?.released() }
    func cancelInteractions() { holding = false; accessibleMeaning = false; pendingPlayback = nil }
    func toggleScript() { learnedGesture(); nativeScript.toggle() }
    func toggleMeaning() {
        if hasVisibleTranslation && !showingMeaning { revealVisit?.revealed(keepSpace: false) }
        learnedGesture(); accessibleMeaning.toggle()
    }
    /// Assistive activation uses native actions, not the physical touch grammar.
    static func actionDescription(showingMeaning:Bool = false,nativeScript:Bool = false,hasAlternateScript:Bool = true,incremental:Bool = true) -> String {
        var actions = [incremental ? String(localized:"Play practice words") : String(localized:"Play message"),
                       showingMeaning ? (incremental ? String(localized:"Show practice words") : String(localized:"Show practice text")) : String(localized:"Show original message")]
        if hasAlternateScript { actions.append(nativeScript ? String(localized:"Show transliteration") : String(localized:"Show native script")) }
        return actions.joined(separator:". ")
    }
    static func gestureDescription(target:String,hasAlternateScript:Bool,incremental:Bool = true) -> String {
        let basic = incremental ? String(format:String(localized:"Tap to hear %1$@ words. Hold to see the original message."),VipiLanguage.named(target).localizedName) : String(localized:"Tap a message to listen. Hold to see the original.")
        return hasAlternateScript ? basic + " " + String(format:String(localized:"Double-tap to see %1$@ writing."),VipiLanguage.named(target).localizedName) : basic
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
    var onTouch: (() -> Void)? = nil
    func makeUIView(context: Context) -> Capture { Capture(reading:reading) }
    func updateUIView(_ view: Capture, context: Context) { view.reading = reading; view.onTouch = onTouch }
    static func dismantleUIView(_ view: Capture, coordinator: ()) { view.detach() }
    @MainActor final class Capture: UIView, UIGestureRecognizerDelegate {
        var reading: ChatReadingState
        var onTouch: (() -> Void)?
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
            onTouch?()
            // VoiceOver owns its double tap. Equivalent named native actions remain available.
            if UIAccessibility.isVoiceOverRunning || reading.pointInHint(touch.location(in: window)) { return false }
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
    var incremental = false
    var transitionFace: ImmersionTextFace?
    @State private var localReading = ChatReadingState()
    @State private var frame = CGRect.zero
    @State private var visibleInScroll = false
    @State private var playbackAlignment:[FullSentenceReadings.Alignment] = []
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.vipiOutgoingMessage) private var outgoingMessage
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.tutorialShowsOriginal) private var tutorialShowsOriginal
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    private var controls: ChatReadingState { reading ?? localReading }
    private var binding: ImmersionRequestIdentity { identity ?? .init(messageID:messageID,text:originalMessage ?? result.original,source:sourceLanguage,target:targetLanguage,inputLanguage:inputLanguage,generation:UUID(uuidString:"00000000-0000-0000-0000-000000000000")!) }
    private var practice: String { result.translation ?? result.original }
    private var faces: [String] { [result.original,practice]+(fullReading.map { [$0] } ?? []) }
    private var displayed: String {
        if tutorialShowsOriginal || controls.showingMeaning || mode == .original { return result.original }
        return controls.nativeScript ? practice : (fullReading ?? practice)
    }
    private func play(start: Bool) -> Bool {
        guard scenePhase == .active, let speech else { return false }
        let span = playbackSpans
        guard !span.isEmpty else { return true }
        if speech.state == .unavailable { onVoiceHelp?(); return true }
        guard speech.state != .preparing else { return false }
        if start { speech.start(message:messageID,spans:span,pauseBetweenSpans:incremental,face:transitionFace) } else { speech.toggle(message:messageID,spans:span,pauseBetweenSpans:incremental,face:transitionFace) }
        return true
    }
    private var playbackSpans:[(text:String,language:String)] {
        if !incremental { return [(practice,targetLanguage)] }
        // Preserve natural adjacent target phrases; pause only across source
        // words omitted from practice speech.
        var spans:[(text:String,language:String)] = [], end:Int?
        let source = result.original as NSString
        for word in result.spans {
            let gap = end.map{NSRange(location:$0,length:max(0,word.range.location-$0))}
            if let gap,NSMaxRange(gap) <= source.length,
               source.substring(with:gap).allSatisfy({$0.isWhitespace || $0.isPunctuation}),!spans.isEmpty {
                spans[spans.count-1].text += source.substring(with:gap)+word.translated
            } else { spans.append((word.translated,targetLanguage)) }
            end = NSMaxRange(word.range)
        }
        return spans
    }
    private var playing:SpeechPlayback.ActiveWord? {
        guard !controls.showingMeaning,mode != .original,speech?.activeMessage == messageID, speech?.matchesDisplayedFace(transitionFace) == true else { return nil }
        return speech?.activeWord
    }
    private var hasAlternateScript: Bool { fullReading.map { !$0.isEmpty && $0 != practice } ?? false }
    private func register() { controls.register(.init(identity:binding,frame:frame,activate:play,hasAlternateScript:hasAlternateScript,
        audio:.init(face:transitionFace,spans:playbackSpans,incremental:incremental),
        visibleTranslation: visibleInScroll && mode != .original && (incremental ? result.spans.contains { $0.original != $0.translated } : practice != result.original))) }
    private var native: StableImmersionText {
        let revealed = tutorialShowsOriginal || controls.showingMeaning || mode == .original ? Set(result.spans.map(\.id)) : Set<Int>()
        var view = StableImmersionText(result:incremental ? result : .sourceOnly(original:displayed,target:targetLanguage),
            revealed:revealed,script:incremental ? controls.nativeScript : true,onWord:{ id in
                guard UIAccessibility.isVoiceOverRunning,let word = result.spans.first(where:{$0.id == id}) else { return }
                let audio = DisplayedPracticeAudio(face:transitionFace,spans:[(word.translated,targetLanguage)],incremental:true,wordID:id)
                controls.activateWord(binding,audio:audio) {
                    speech?.toggle(message:messageID,spans:audio.spans,face:transitionFace,wordID:id)
                }
            },onSelection:{_ in})
        view.transitionFace = transitionFace
        view.fitsContentWidth = embedded
        view.reservedSentences = incremental ? [] : faces
        view.sentenceIdentity = String(describing:binding)+"|"+faces.joined(separator:"\u{0}")
        view.fullMessage = true; view.incremental = incremental
        if let word = playing {
            if incremental {
                // Map the PCM marker through the exact practice speech spans
                // and the immutable replacement. Highlight the whole native word.
                let selected = speech?.activePracticeWordID
                let words = result.spans.filter { selected == nil || selected == $0.id }
                let spoken = (selected == nil ? playbackSpans.map(\.text) : words.map(\.translated)).joined() as NSString
                var cursor = 0
                for span in words {
                    let found = spoken.range(of:span.translated,options:.literal,range:NSRange(location:cursor,length:spoken.length-cursor))
                    guard found.location != NSNotFound else { break }
                    cursor = NSMaxRange(found)
                    guard NSIntersectionRange(found,word.range).length > 0 else { continue }
                    let native = NSIntersectionRange(found,word.range)
                    let local = NSRange(location:native.location-found.location,length:native.length)
                    let face = controls.nativeScript ? span.translated : span.displayedTarget
                    view.playingWordRange = FullSentenceReadings.displayedRange(local,text:span.translated,reading:face,
                        alignment:FullSentenceReadings.alignment(text:span.translated,reading:face,language:targetLanguage))
                    if view.playingWordRange != nil { view.playingWordID = span.id }
                    break
                }
            } else {
                view.playingRange = FullSentenceReadings.displayedRange(word.range,text:practice,reading:displayed,alignment:playbackAlignment)
            }
        }
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
                            .font(.subheadline).foregroundStyle(VipiDesign.messageSecondary(outgoingMessage))
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
        .animation(reduceMotion || voiceOver ? nil : .easeOut(duration:0.22),value:transitionFace)
        .onGeometryChange(for:CGRect.self) { $0.frame(in:.global) } action: { frame = $0; register() }
        .onScrollVisibilityChange(threshold: 0.1) { visible in visibleInScroll = visible; register() }
        .onAppear { register() }
        .task(id:practice+"\u{0}"+displayed+"\u{0}"+targetLanguage) {
            let text = practice, face = displayed, language = targetLanguage
            let value = await Task.detached{FullSentenceReadings.alignment(text:text,reading:face,language:language)}.value
            guard !Task.isCancelled else { return }; playbackAlignment = value
        }
        .onChange(of:controls.showingMeaning) { _,meaning in if meaning { speech?.stop() } }
        .onChange(of:binding) { old,_ in controls.remove(old); register() }
        .onChange(of:transitionFace) { register() }
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
    func manual(_ identity:ImmersionRequestIdentity,displayed:DisplayedPracticeAudio? = nil,immersion:ConversationImmersion,speech:SpeechPlayback,
                onModels:@escaping(TranslationPair)->Void,onVoiceHelp:@escaping()->Void) {
        bind(speech)
        guard identity == immersion.identity(messageID:identity.messageID,text:identity.text) else { return }
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
            let audio: DisplayedPracticeAudio
            if let displayed { audio = displayed }
            else {
                switch immersion.phase(for:identity) {
                case .failed,.timedOut: immersion.retry(identity)
                case .needsDownload,.unsupported: onModels(immersion.requiredPair(for:identity)); return
                default: break
                }
                guard let value = await immersion.translatedMessage(for:identity) else { return }
                audio = .init(face:.init(scope:immersion.displayGeneration,message:identity.messageID,mode:immersion.mode),
                    spans:value.practiceSpeech.map{($0.text,$0.language)},incremental:value.words != nil)
            }
            guard !audio.spans.isEmpty else { return }
            while speech.state == .preparing {
                guard !Task.isCancelled,active == epoch,selected == manualEpoch else { return }
                do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
            }
            guard speech.state != .unavailable else { onVoiceHelp(); return }
            guard !Task.isCancelled,active == epoch,selected == manualEpoch,
                  identity == immersion.identity(messageID:identity.messageID,text:identity.text) else { return }
            speech.start(message:identity.messageID,spans:audio.spans,pauseBetweenSpans:audio.incremental,face:audio.face,wordID:audio.wordID)
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
                guard !value.practiceSpeech.isEmpty else {
                    if queue.first?.id == next.id { queue.removeFirst() }
                    continue
                }
                while manualTask != nil || speech.state == .preparing || speech.activeMessage != nil {
                    guard !Task.isCancelled,epoch == active else { return }
                    do { try await Task.sleep(for:.milliseconds(30)) } catch { return }
                }
                guard !Task.isCancelled,epoch == active else { return }
                if consumed.contains(next.id) { if queue.first?.id == next.id { queue.removeFirst() }; continue }
                if speech.state == .unavailable { missingVoice(speech); return }
                speech.start(message:next.id,spans:value.practiceSpeech.map{($0.text,$0.language)},autoplay:true,pauseBetweenSpans:value.words != nil,
                    face:.init(scope:immersion.displayGeneration,message:next.id,mode:immersion.mode))
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
