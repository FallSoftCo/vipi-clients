import AVFoundation
import Foundation
import Observation
import VipiCore

enum SpeechState { case preparing, ready, rendering, playing, unavailable }

/// One owner per open chat, retaining its practice voice and one audio player.
@MainActor @Observable final class SpeechPlayback: NSObject {
    private var pair: (any PreparedSpeechPair)?
    private let pairFactory: (String,String,URL) throws -> any PreparedSpeechPair
    init(pairFactory: @escaping (String,String,URL) throws -> any PreparedSpeechPair = { try LocalSpeechPair(source:$0,target:$1,root:$2) }) {
        self.pairFactory = pairFactory; super.init()
    }
    private var player: AVAudioPlayerNode?
    private var engine: AVAudioEngine?
    private var scheduled: [UUID: AVAudioFile] = [:]
    private var schedulingFinished = false
    private(set) var outputUnderruns = 0
    private var preparation: Task<Void, Never>?
    private var preparationID = UUID()
    private var rendering: Task<Void, Never>?
    struct ActiveWord: Equatable { let range:NSRange; let text:String }
    private(set) var activeWord: ActiveWord?
    private struct TimedWord { let range:NSRange; let text:String; let start:Int64; var end:Int64 }
    private var timedWords:[TimedWord] = []
    private var wordTracking:Task<Void,Never>?
    private var scheduledFrames:Int64 = 0
    private func trackWords(request:Int) {
        guard wordTracking == nil else { return }
        wordTracking = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self,request == self.epoch,let node = self.player else { return }
                if let time = node.lastRenderTime.flatMap({node.playerTime(forNodeTime:$0)}) {
                    let sample = time.sampleTime
                    let word = self.timedWords.first{sample >= $0.start && sample < $0.end}
                    let next = word.map{ActiveWord(range:$0.range,text:$0.text)}
                    if self.activeWord != next {
                        self.activeWord = next
                        #if DEBUG
                        LiveImmersionQualification.recordFirstMonthSpeechOutput(["event":"speech_active_word","message_id":self.activeMessage ?? "",
                            "source":"synthesis_metadata_and_player_sample_time","sample_time":sample,
                            "start":next?.range.location ?? -1,"length":next?.range.length ?? 0])
                        #endif
                    }
                }
                do { try await Task.sleep(for:.milliseconds(20)) } catch { return }
            }
        }
    }
    private var observers: [NSObjectProtocol] = []
    private var epoch = 0
    private var ready = false
    private var sessionActive = false
    @ObservationIgnored var onUnavailable: (() -> Void)?
    @ObservationIgnored var onInterruption: (() -> Void)?
    private(set) var state: SpeechState = .preparing {
        didSet { if state == .unavailable { onUnavailable?() } }
    }
    private(set) var error: String?
    private(set) var activeMessage: String?
    private(set) var activeFace: ImmersionTextFace?
    private(set) var activePracticeWordID: Int?
    func matchesDisplayedFace(_ face: ImmersionTextFace?) -> Bool { activeFace == face }
    private(set) var autoplayOwned = false
    struct Completion: Equatable { let serial:UInt64; let message:String; let succeeded:Bool }
    private(set) var playbackSerial: UInt64 = 0
    private(set) var lastCompletion: Completion?
    private func completed(_ message:String,succeeded:Bool) {
        lastCompletion = .init(serial:playbackSerial,message:message,succeeded:succeeded); stop()
    }
    #if DEBUG
    /// Component-only preparation failure injection; no account or audio state.
    var qualificationPrepare: (() async throws -> Void)?
    #endif
    private func prepareVoices(source: String, target: String, warmups: [String: String]) async throws {
        #if DEBUG
        if let qualificationPrepare { try await qualificationPrepare(); return }
        #endif
        let next = try pairFactory(source,target,MessageSpeechCache.directory)
        pair = next
        try await next.prepare(warmups: warmups)
    }

    func prepare(source: String, target: String, warmups: [String: String]) {
        guard !ready, preparation == nil else { return }
        state = .preparing; error = nil
        if observers.isEmpty {
            for name in [AVAudioSession.interruptionNotification, AVAudioSession.routeChangeNotification, AVAudioSession.mediaServicesWereResetNotification] {
                observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] note in
                    if name == AVAudioSession.routeChangeNotification,
                       (note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt) != AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue { return }
                    if name == AVAudioSession.interruptionNotification,
                       (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) != AVAudioSession.InterruptionType.began.rawValue { return }
                    Task { @MainActor [weak self] in
                        guard let self else { return }
                        self.onInterruption?()
                        self.stop()
                    }
                })
            }
        }
        let preparationID = UUID(); self.preparationID = preparationID
        preparation = Task { [weak self] in
            guard let self else { return }
            defer { if self.preparationID == preparationID { self.preparation = nil } }
            do {
                try await self.prepareVoices(source: source, target: target, warmups: warmups)
                try Task.checkCancellation()
                guard self.preparationID == preparationID else { return }
                self.ready = true; self.state = .ready
            } catch is CancellationError {
                guard self.preparationID == preparationID, !Task.isCancelled else { return }
                self.error = String(localized: "Voices couldn’t get ready. Try again."); self.state = .unavailable
            }
            catch LocalSpeechError.missingVoice(let language) {
                guard self.preparationID == preparationID else { return }
                self.error = String(localized: "Add a \(VipiLanguage.named(language).localizedName) voice in Settings → Accessibility → Spoken Content → Voices, then retry.")
                self.state = .unavailable
            } catch {
                guard self.preparationID == preparationID else { return }
                self.error = String(localized: "Voices couldn’t get ready. Try again."); self.state = .unavailable
            }
        }
    }

    /// Start or replace practice playback without toggling the selected item off.
    func start(message: String, spans: [(text: String, language: String)], autoplay: Bool = false, pauseBetweenSpans: Bool = false, face: ImmersionTextFace? = nil, wordID: Int? = nil) {
        if activeMessage == message { stop() }
        toggle(message:message,spans:spans,pauseBetweenSpans:pauseBetweenSpans,face:face,wordID:wordID)
        if activeMessage == message { autoplayOwned = autoplay }
    }

    func toggle(message: String, spans: [(text: String, language: String)], pauseBetweenSpans: Bool = false, face: ImmersionTextFace? = nil, wordID: Int? = nil) {
        guard ready, let pair else { return }
        if activeMessage == message { stop(); return }
        #if DEBUG
        LiveImmersionQualification.recordSpeech(message, spans: spans)
        #endif
        let previous = rendering
        stop()
        let request = epoch
        playbackSerial &+= 1
        activeMessage = message; activeFace = face; activePracticeWordID = wordID; state = .rendering; error = nil
        rendering = Task { [weak self] in
            // Await cancellation cleanup before reusing AVSpeechSynthesizer.
            await previous?.value
            guard let self, !Task.isCancelled, request == self.epoch else { return }
            do {
                guard spans.reduce(0, { $0 + $1.text.utf8.count }) <= FullMessageBudget.recordBytes else { throw LocalSpeechError.unavailable }
                let planning = Task.detached(priority:.userInitiated) {
                    if pauseBetweenSpans { return try spans.flatMap{try SpeechChunks.plan([$0],checkCancellation:{try Task.checkCancellation()})} }
                    try Task.checkCancellation()
                    return SpeechChunks.sentencePlan(spans)
                }
                let chunks = try await withTaskCancellationHandler { try await planning.value } onCancel: { planning.cancel() }
                try Task.checkCancellation()
                guard !chunks.isEmpty else { throw LocalSpeechError.unavailable }
                self.schedulingFinished = false; self.outputUnderruns = 0
                var renderedAny = false, textOffset = 0
                let spokenText = spans.map(\.text).joined() as NSString
                var boundary = 0
                let pauseOffsets = Set(spans.dropLast().map{span -> Int in boundary += span.text.utf16.count; return boundary})
                for chunk in chunks {
                    // A punctuation-only native utterance can return zero PCM.
                    // Treat it as silence; do not abort later pronounceable text.
                    guard chunk.contains(where:{SpeechChunks.hasSpokenContent($0.text)}) else { textOffset += chunk.reduce(0){$0+$1.text.utf16.count}; continue }
                    renderedAny = true
                    while self.scheduled.count >= 3 { try await Task.sleep(for: .milliseconds(20)) }
                    let audio = try await pair.render(chunk)
                    try Task.checkCancellation()
                    guard request == self.epoch else { return }
                    let file = try AVAudioFile(forReading: audio.file)
                    if self.player == nil {
                        let session = AVAudioSession.sharedInstance()
                        try session.setCategory(.playback, mode: .spokenAudio)
                        try session.setActive(true); self.sessionActive = true
                        let engine = AVAudioEngine(); let node = AVAudioPlayerNode()
                        engine.attach(node); engine.connect(node, to: engine.mainMixerNode, format: file.processingFormat)
                        self.engine = engine; self.player = node
                        engine.prepare(); try engine.start()
                    }
                    guard let node = self.player else { throw LocalSpeechError.unavailable }
                    if pauseBetweenSpans,pauseOffsets.contains(textOffset),
                       let silence = AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:AVAudioFrameCount(file.processingFormat.sampleRate * 0.16)) {
                        silence.frameLength = silence.frameCapacity
                        for buffer in UnsafeMutableAudioBufferListPointer(silence.mutableAudioBufferList) {
                            if let bytes = buffer.mData { memset(bytes,0,Int(buffer.mDataByteSize)) }
                        }
                        node.scheduleBuffer(silence,completionHandler:nil)
                        self.scheduledFrames += Int64(silence.frameLength)
                    }
                    let bytesPerFrame = max(1,Int(file.processingFormat.streamDescription.pointee.mBytesPerFrame))
                    let ordered = audio.marks.sorted{$0.byteSampleOffset < $1.byteSampleOffset}
                    let chunkLength = chunk.reduce(0){$0+$1.text.utf16.count}
                    for (index,mark) in ordered.enumerated() {
                        guard mark.start >= 0,mark.start <= chunkLength,mark.length > 0,mark.length <= chunkLength-mark.start else { continue }
                        let range = NSRange(location:textOffset+mark.start,length:mark.length)
                        guard range.location >= 0,range.length > 0,NSMaxRange(range) <= spokenText.length else { continue }
                        let start = self.scheduledFrames + Int64(mark.byteSampleOffset / bytesPerFrame)
                        let end = self.scheduledFrames + (index+1 < ordered.count ? Int64(ordered[index+1].byteSampleOffset / bytesPerFrame) : file.length)
                        guard end > start else { continue }
                        self.timedWords.append(.init(range:range,text:spokenText.substring(with:range),start:start,end:end))
                    }
                    textOffset += chunk.reduce(0){$0+$1.text.utf16.count}
                    self.scheduledFrames += file.length
                    let id = UUID()
                    self.scheduled[id] = file
                    #if DEBUG
                    LiveImmersionQualification.recordFirstMonthSpeechOutput(["event": "speech_file_scheduled",
                        "message_id": message, "audio_file": audio.file.lastPathComponent,
                        "frames": file.length, "sample_rate": file.processingFormat.sampleRate])
                    #endif
                    node.scheduleFile(file, at: nil, completionCallbackType: .dataPlayedBack) { [weak self] _ in
                        Task { @MainActor [weak self] in
                            guard let self, request == self.epoch else { return }
                            #if DEBUG
                            let sampleTime = self.player.flatMap { player in
                                player.lastRenderTime.flatMap { player.playerTime(forNodeTime: $0)?.sampleTime }
                            } ?? 0
                            LiveImmersionQualification.recordFirstMonthSpeechOutput(["event": "speech_file_played_back",
                                "message_id": message, "audio_file": audio.file.lastPathComponent,
                                "frames": file.length, "sample_rate": file.processingFormat.sampleRate,
                                "node_sample_time": sampleTime, "engine_running": self.engine?.isRunning == true,
                                "callback": "dataPlayedBack", "epoch_matches": true])
                            #endif
                            self.scheduled.removeValue(forKey: id)
                            if self.scheduled.isEmpty {
                                if self.schedulingFinished { self.completed(message,succeeded:true) }
                                else { self.outputUnderruns += 1 }
                            }
                        }
                    }
                    if !node.isPlaying { node.play(); self.state = .playing; self.trackWords(request:request) }
                }
                guard renderedAny else { throw LocalSpeechError.invalidAudio }
                self.schedulingFinished = true
                if self.scheduled.isEmpty { self.completed(message,succeeded:true) }
            } catch is CancellationError { }
            catch {
                if request == self.epoch { self.completed(message,succeeded:false); self.error = String(localized: "This message couldn’t play. Try again.") }
            }
        }
    }
    func stop() {
        epoch += 1
        wordTracking?.cancel(); wordTracking = nil; activeWord = nil; timedWords.removeAll(); scheduledFrames = 0
        rendering?.cancel()
        // Keep the task reference until the next request has awaited its cleanup.
        player?.stop(); engine?.stop(); player = nil; engine = nil; scheduled.removeAll()
        if sessionActive { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation); sessionActive = false }
        activeMessage = nil; activeFace = nil; activePracticeWordID = nil; autoplayOwned = false
        if ready { state = .ready }
    }
    func close() {
        stop(); preparationID = UUID(); preparation?.cancel(); preparation = nil; pair?.stop(); pair = nil; ready = false
        observers.forEach(NotificationCenter.default.removeObserver); observers.removeAll()
    }
}
