#if DEBUG
import SwiftUI
import UIKit
import Observation
import VipiCore

/// Curated native presentation QA with supplied target strings. It never sends
/// a message, changes a real conversation, or claims provider inference.
struct FullReadingQualificationView: View {
    private enum Fixture: String, CaseIterable {
        case local = "Local", authored = "Authored", unknown = "Unknown"
        func source(_ language: String) -> String {
            switch self {
            case .local: ["ko": "We go to school together.", "ja": "I sent a message to Zoë and José."][language] ?? "The bank manager is walking."
            case .authored: "I need water."
            case .unknown: "How do you read these characters?"
            }
        }
        func target(_ language: String) -> String {
            switch self {
            case .local: ["ko": "같이 학교에 갑니다.", "ja": "ZoëとJoséにメッセージを送った。"][language] ?? "银行行长正在走路。"
            case .authored: ["ko": "물이 필요해요.", "ja": "水が必要です。"][language] ?? "我需要水。"
            case .unknown: ["ko": "𠮷에게 메시지를 보내요.", "ja": "𠮷先生に会う。"][language] ?? "𠮷先生与𰻞字怎么读？"
            }
        }
    }
    @State private var fixture = Fixture.local
    @State private var reading: FullReading?
    @State private var ready = false
    @State private var mode = ReadingMode.translation
    @State private var speech = SpeechPlayback()
    @State private var cache = FullReadingCache(policy: FullSentenceReadings.policy) {
        FullSentenceReadings.resolve($0, language: $1)
    }
    private let language: String = {
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-vipi-korean-reading-fixture") { return "ko" }
        if args.contains("-vipi-japanese-reading-fixture") { return "ja" }
        return "zh"
    }()
    private var result: ImmersionPresentation {
        .complete(ImmersionEngine().align(original: fixture.source(language), translation: fixture.target(language), entries: [], density: 0))
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Reading QA · supplied target text").font(.footnote).foregroundStyle(VipiDesign.secondary)
                    Picker("Fixture", selection: $fixture) {
                        ForEach(Fixture.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented)
                    ImmersionBubble(result: result, mode: mode, speech: speech,
                        sourceLanguage: "en", targetLanguage: language, messageID: "reading-qa-" + fixture.rawValue,
                        fullReading: reading?.text, onModeChange: { mode = $0 })
                        .id(fixture)
                    Text(ready ? (reading?.provenance.rawValue ?? "unavailable") : "pending metadata").font(.footnote)
                        .accessibilityIdentifier("reading-qa-provenance")
                }.padding()
            }.background(VipiDesign.canvas).navigationTitle(["ko": "Korean reading", "ja": "Japanese reading"][language] ?? "Chinese reading")
        }
        .task { speech.prepare(source: "en", target: language, warmups: ["en": "Hello.", language: ["ko": "안녕하세요.", "ja": "こんにちは。"][language] ?? "你好。"]) }
        .task(id: fixture) {
            ready = false; reading = nil; mode = .translation
            let active = fixture
            let value = await cache.resolve(text: active.target(language), language: language)
            guard !Task.isCancelled, active == fixture else { return }
            reading = value; ready = true
        }
        .onDisappear { speech.stop(); cache.removeAll() }
    }
}
// DEBUG-only native interaction fixture. Explicit supplied translation/reading
// outcomes test UI arbitration, not model quality or acoustic playback.
private actor ReadingStatusUIGate {
    private var attempts = 0, translations = 0
    private var continuation:CheckedContinuation<FullReading?,Never>?
    private var resumed = false
    func translate(_ text:String,pair:TranslationPair) throws -> String {
        guard pair == TranslationPair(source:"en",target:"ja") else { throw CancellationError() }
        translations += 1
        switch text {
        case "The bank.": return "銀行"
        case "Add it.": return "追加"
        case "OK 🙂": return text
        default: throw CancellationError()
        }
    }
    func reading(_ text:String,language:String) async -> FullReading? {
        guard language == "ja" else { return nil }
        if text == "追加" { return .init(text:"",provenance:.localTransliteration,failure:.outputLimit) }
        guard text == "銀行" else { return nil }
        attempts += 1
        if attempts == 1 { return nil }
        guard attempts == 2,!resumed else { return nil }
        return await withCheckedContinuation { continuation = $0 }
    }
    func release() {
        guard let continuation else { return }
        self.continuation = nil; resumed = true
        continuation.resume(returning:.init(text:"ginkō",provenance:.localTransliteration))
    }
    func cancel() { continuation?.resume(returning:nil); continuation = nil }
    func snapshot()->[String:Int] { ["reader_attempts":attempts,"translation_calls":translations,"reader_held":continuation == nil ? 0:1,"reader_resumed":resumed ? 1:0] }
}

@MainActor @Observable private final class ReadingStatusUIModel {
    static let messages = [("transient","The bank."),("permanent","Add it."),("literal","OK 🙂")]
    let run:UUID,defaults:UserDefaults,state:AppState,immersion:ConversationImmersion
    let cleaned:Bool
    let initiallyNativeScript:Bool
    private(set) var mountedNativeScript:Bool?
    var visibleMessages:[(String,String)] { initiallyNativeScript ? Self.messages.filter { $0.0 != "permanent" } : Self.messages }
    let speech = SpeechPlayback()
    private let gate:ReadingStatusUIGate
    private let playbackOwner = UUID()
    private(set) var counters:[String:Int] = [:]
    private(set) var audioIntents:[[String:String]] = []
    private(set) var samples:[[String:Any]] = []
    private(set) var captureFailure = false
    private var scriptTransitions = 0
    private var configured = false
    private(set) var readyToMount = false
    init() {
        let args = ProcessInfo.processInfo.arguments
        precondition(Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" && args.contains("-vipi-reading-status-ui-qa") &&
            !args.contains("-vipi-first-month-root-qa") && !args.contains("-vipi-deletion-root-qa"),"Owned row fixture only")
        guard let index = args.firstIndex(of:"-vipi-reading-status-run"),args.indices.contains(index+1),let run = UUID(uuidString:args[index+1]) else { preconditionFailure("Unique row run required") }
        self.run = run
        initiallyNativeScript = args.contains("-vipi-reading-status-start-native-script")
        let suite = "co.fallsoft.vipi.uxqa.reading-status."+run.uuidString.lowercased()
        let defaults = UserDefaults(suiteName:suite)!
        let cleanup = args.contains("-vipi-reading-status-cleanup")
        cleaned = cleanup
        if cleanup {
            if let domain = defaults.persistentDomain(forName:suite) {
                guard domain["owned_run"] as? String == run.uuidString.lowercased(),
                      Set(domain.keys).isSubset(of:["owned_run","knownLanguage","targetLanguage","full-message-gestures-v1-seen"]) else {
                    preconditionFailure("Preserve unexpected owned row defaults")
                }
                defaults.removePersistentDomain(forName:suite)
            }
        } else {
            precondition(defaults.persistentDomain(forName:suite) == nil,"Preserve previous owned row run")
            defaults.set(run.uuidString.lowercased(),forKey:"owned_run")
            defaults.set("en",forKey:"knownLanguage"); defaults.set("ja",forKey:"targetLanguage")
        }
        self.defaults = defaults; state = AppState(defaults:defaults)
        let gate = ReadingStatusUIGate(); self.gate = gate
        immersion = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "en"},
            nativeTranslation:{text,pair in try await gate.translate(text,pair:pair)},
            fullReadingProducer:{text,language in await gate.reading(text,language:language)})
        if initiallyNativeScript { state.chatReading.nativeScript = true }
    }
    func start() async {
        guard !cleaned,!configured else { return }; configured = true
        await immersion.configure(pair:.init(source:"en",target:"ja"))
        state.chatReading.bindPlayback(owner:playbackOwner) { [weak self] identity in
            guard let self,let value = immersion.translation(for:identity) else { return }
            // Observes production ChatReadingState command routing only. No
            // SpeechPlayback.prepare/start and no claim of synthesized audio.
            audioIntents.append(["id":identity.messageID,"text":value.practiceText,"language":value.practiceLanguage])
        }
        for (id,text) in Self.messages { _ = await immersion.translatedMessage(for:immersion.identity(messageID:id,text:text)) }
        mountedNativeScript = state.chatReading.nativeScript
        readyToMount = true
        await refresh()
    }
    func refresh() async { counters = await gate.snapshot() }
    func scriptChanged() async {
        scriptTransitions += 1
        // Explicit completion protocol: both physical script transitions must
        // happen while retry is held. No extra controls or timer completes it.
        if scriptTransitions == 2 { await gate.release() }
        await refresh()
    }
    func capture(_ phase:String) async {
        // Sample the actual UIKit buffers/paint after SwiftUI applies the face.
        await Task.yield()
        guard samples.count < 6,let window = UIApplication.shared.connectedScenes.compactMap({$0 as? UIWindowScene}).flatMap(\.windows).first(where:{$0.isKeyWindow}) else { captureFailure = true; return }
        window.layoutIfNeeded()
        var paragraphs:[[String:Any]] = []
        @MainActor func visit(_ view:UIView) {
            if let text = view as? UITextView,text.accessibilityIdentifier == "immersionText" {
                paragraphs.append(["text":text.attributedText.string,"frame":NSCoder.string(for:text.convert(text.bounds,to:window)),"hint":text.accessibilityHint ?? ""])
            }
            for child in view.subviews { visit(child) }
        }
        visit(window)
        let name = "reading-status-"+run.uuidString.lowercased()+"-"+String(samples.count)+"-"+phase+".png"
        let url = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent(name)
        var painted = false
        let image = UIGraphicsImageRenderer(bounds:window.bounds).image { _ in painted = window.drawHierarchy(in:window.bounds,afterScreenUpdates:true) }
        do {
            guard !FileManager.default.fileExists(atPath:url.path),let png = image.pngData() else { throw CancellationError() }
            try png.write(to:url,options:.withoutOverwriting)
            samples.append(["phase":phase,"holding":state.chatReading.holding,"native_script":state.chatReading.nativeScript,
                "painted":painted,"png":name,"paragraphs":paragraphs])
        } catch { captureFailure = true }
    }
    var proof:String {
        var rows:[[String:Any]] = []
        for (id,text) in Self.messages {
            let identity = immersion.identity(messageID:id,text:text),value = immersion.translation(for:identity)
            rows.append(["id":id,"ready":value != nil,"original":value?.original ?? "","practice":value?.practiceText ?? "",
                "reading":value?.practiceReading ?? "","status":value?.readingState?.status.rawValue ?? "pending",
                "can_retry":value?.readingState?.canRetry ?? false,"retry_pending":immersion.readingRetryPending(for:identity)])
        }
        let data:[String:Any] = ["run":run.uuidString.lowercased(),"controlled_sdk":true,"acoustic_proof":false,
            "rows":rows,"counters":counters,"audio_intents":audioIntents,"samples":samples,"capture_failure":captureFailure,
            "initial_native_script":initiallyNativeScript,"mounted_native_script":mountedNativeScript.map { $0 as Any } ?? NSNull(),
            "current_native_script":state.chatReading.nativeScript,
            "window_content_size":UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.flatMap(\.windows).first(where:{$0.isKeyWindow})?.traitCollection.preferredContentSizeCategory.rawValue ?? "missing"]
        return String(decoding:(try? JSONSerialization.data(withJSONObject:data,options:.sortedKeys)) ?? Data(),as:UTF8.self)
    }
    func close() {
        state.chatReading.unbindPlayback(owner:playbackOwner); immersion.close(); speech.close()
        Task { await gate.cancel() }
    }
}

struct ReadingStatusUIQualificationView:View {
    @State private var model = ReadingStatusUIModel()
    var body:some View {
        Group {
        if model.cleaned { Text("Owned reading row defaults removed").accessibilityIdentifier("reading-status-ui-cleaned") }
        else {
        VStack(spacing:12) {
            if model.readyToMount {
            ForEach(model.visibleMessages,id:\.0) { message in
                let (id,text) = message
                ConversationImmersionText(text:text,id:id,immersion:model.immersion,speech:model.speech,paused:false,
                    metadata:AnyView(EmptyView()),onVoiceHelp:{})
                    .background(VipiDesign.surface,in:RoundedRectangle(cornerRadius:18))
                    .accessibilityIdentifier("reading-status-row-"+id)
            }
            }
            Spacer(minLength:0)
        }.padding(18).background(VipiDesign.canvas).preferredColorScheme(.light)
            .background { ChatReadingGestureSurface(reading:model.state.chatReading) }
            .environment(model.state)
            .safeAreaInset(edge:.bottom,spacing:0) {
                TimelineView(.periodic(from:.now,by:0.2)) { context in
                    Color.clear.frame(height:1).accessibilityElement(children:.ignore)
                        .accessibilityLabel("Local reading interaction evidence")
                        .accessibilityIdentifier("reading-status-ui-proof|"+model.proof)
                        .task(id:context.date) { await model.refresh() }
                }
            }
        }
        }
            .task { await model.start() }
            .onChange(of:model.state.chatReading.holding) { _,value in if value { Task { await model.capture("held") } } }
            .onChange(of:model.state.chatReading.nativeScript) { _,_ in Task { await model.capture("script"); await model.scriptChanged() } }
            .onDisappear { model.close() }
    }
}


/// A controlled rendering-only account/pair replacement check. No auth, vault,
/// SDK, speech or service request is created by this explicitly gated leaf host.
@MainActor @Observable private final class HomePreviewDisplayQualificationModel {
    let message = ChatItem(id:UUID(uuidString:"C9A1A1D1-3DDD-4A43-8D40-824CC39B692A")!,
        peer:UUID(uuidString:"BCE3860D-345A-435F-814A-982944EF8B53")!,text:"Original account message.",
        createdAt:1,outgoing:false,state:"received",cursor:"owned-preview")
    var expectedPair = TranslationPair(source:"en",target:"es")
    var owner:ConversationImmersion?
    private var oldOwner:ConversationImmersion?
    private var nextOwner:ConversationImmersion?
    private var held:CheckedContinuation<Void,Never>?
    private var retained:Task<FullMessageTranslation?,Never>?
    private var prepared = false
    private var oldCalls = 0
    private var newCalls = 0
    private var oldReturned = false
    private var replaced = false
    private var released = false
    private var oldTaskCompleted = false
    private var oldTaskCancelled = false
    private var oldTaskHasValue = false
    func prepare() async {
        guard !prepared else { return }; prepared = true
        let first = ConversationImmersion(modelStatus:{ _ in .installed },identify:{ _ in "en" },nativeTranslation:{ [weak self] text,pair in
            guard let self,text == message.text,pair == TranslationPair(source:"en",target:"es") else { throw CancellationError() }
            oldCalls += 1
            await withCheckedContinuation { held = $0 }
            oldReturned = true
            return "Resultado anterior del mensaje."
        })
        let second = ConversationImmersion(modelStatus:{ _ in .installed },identify:{ _ in "en" },nativeTranslation:{ [weak self] text,pair in
            guard let self,text == message.text,pair == TranslationPair(source:"en",target:"fr") else { throw CancellationError() }
            newCalls += 1
            return "Nouvelle traduction du compte."
        })
        await first.configure(pair:expectedPair); await second.configure(pair:.init(source:"en",target:"fr"))
        oldOwner = first; nextOwner = second; owner = first
    }
    func changeExpectedPair() { expectedPair = .init(source:"en",target:"fr") }
    func replaceAccountOwner() {
        guard !replaced,let oldOwner,let nextOwner,
              let task = oldOwner.pendingPairQualificationTasks.first(where:{$0.0.messageID == message.id.uuidString})?.1 else { return }
        retained = task
        oldOwner.close(); replaced = true; owner = nextOwner
    }
    func releaseOldResult() {
        guard replaced,!released,let held,let retained else { return }
        released = true; self.held = nil; held.resume()
        Task { @MainActor [weak self] in
            let value = await retained.value
            guard let self else { return }
            oldTaskHasValue = value != nil; oldTaskCancelled = retained.isCancelled; oldTaskCompleted = true
        }
    }
    var proof:String {
        let current = nextOwner.flatMap{$0.translation(for:$0.identity(messageID:message.id.uuidString,text:message.text))}
        let values:[String:Any] = ["controlled_render_only":true,"old_calls":oldCalls,"new_calls":newCalls,
            "old_held":held != nil,"old_returned":oldReturned,"replaced":replaced,"released":released,
            "old_task_completed":oldTaskCompleted,"old_task_cancelled":oldTaskCancelled,"old_task_has_value":oldTaskHasValue,
            "old_owner_closed":oldOwner?.pendingPairQualificationClosed ?? false,
            "new_cached_practice":current?.practiceText ?? "", "expected_target":expectedPair.target]
        return String(decoding:(try? JSONSerialization.data(withJSONObject:values,options:.sortedKeys)) ?? Data(),as:UTF8.self)
    }
    func close() {
        oldOwner?.close(); nextOwner?.close()
        if let held { self.held = nil; held.resume() }
    }
}

struct HomePreviewDisplayQualificationView: View {
    @State private var model = HomePreviewDisplayQualificationModel()
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:20) {
                    Text("Controlled preview rendering only").font(.caption)
                    HomeMessagePreview(owner:model.owner,message:model.message,expectedPair:model.expectedPair)
                    Button("Change expected practice pair") { model.changeExpectedPair() }.accessibilityIdentifier("preview-change-pair")
                    Button("Replace account owner") { model.replaceAccountOwner() }.accessibilityIdentifier("preview-replace-account")
                    Button("Release old provider result") { model.releaseOldResult() }.accessibilityIdentifier("preview-release-old")
                    TimelineView(.periodic(from:.now,by:0.2)) { _ in
                        Color.clear.frame(height:1).accessibilityElement(children:.ignore)
                            .accessibilityLabel("Local preview display evidence")
                            .accessibilityIdentifier("home-preview-proof|"+model.proof)
                    }
                }.padding()
            }.navigationTitle("Preview QA")
        }.task { await model.prepare() }.onDisappear { model.close() }
    }
}

#endif
