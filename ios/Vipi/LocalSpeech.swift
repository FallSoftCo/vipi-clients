import AVFoundation
import CryptoKit
import Foundation
import VipiCore

/// An erased generation is never recreated by a new account or voice pair.
/// Late synthesis/join callbacks retain their old directory and cannot publish
/// private audio into the new generation after account deletion.
@MainActor enum MessageSpeechCache {
    private static let key = "vipi-private-speech-generation"
    private static var generation: UUID = {
        if let value = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: value) { return id }
        let id = UUID(); UserDefaults.standard.set(id.uuidString, forKey: key); return id
    }()
    private static var parent: URL { FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("vipi-speech", isDirectory: true) }
    static var directory: URL { parent.appendingPathComponent(generation.uuidString.lowercased(), isDirectory: true) }
    static func erase() throws {
        generation = UUID(); UserDefaults.standard.set(generation.uuidString, forKey: key)
        if FileManager.default.fileExists(atPath: parent.path) { try FileManager.default.removeItem(at: parent) }
    }
}

enum LocalSpeechError: Error { case missingVoice(String), invalidAudio, unavailable, formatMismatch, notPrepared, timedOut }

struct RenderedSpeech: Sendable {
    let file: URL
    let milliseconds: Double
    let sampleRate: Double
    let channels: UInt32
    var marks: [SpeechMark] = []
    var boundaryFrames: [Int] = []
}

struct SpeechMark: Codable, Sendable {
    let start: Int
    let length: Int
    let byteSampleOffset: Int
    var source:String? = nil
    var endByteSampleOffset:Int? = nil
}

/// AVSpeechSynthesizer invokes buffer callbacks outside the main actor.
/// This object confines AVAudioFile access and continuation completion to a lock.
private final class SpeechFileWriter: @unchecked Sendable {
    private let lock = NSLock()
    private var file: AVAudioFile?
    private var frames: AVAudioFramePosition = 0
    private var continuation: CheckedContinuation<RenderedSpeech, Error>?
    private let url: URL
    private var marks: [SpeechMark] = []

    init(url: URL, continuation: CheckedContinuation<RenderedSpeech, Error>) {
        self.url = url; self.continuation = continuation
    }
    func accept(_ buffer: AVAudioBuffer) {
        lock.lock(); defer { lock.unlock() }
        guard let continuation else { return }
        do {
            guard let pcm = buffer as? AVAudioPCMBuffer else { throw LocalSpeechError.invalidAudio }
            if pcm.frameLength == 0 {
                guard let file, frames > 0 else { throw LocalSpeechError.invalidAudio }
                let result = RenderedSpeech(file: url, milliseconds: Double(frames) * 1000 / file.processingFormat.sampleRate,
                    sampleRate: file.processingFormat.sampleRate, channels: file.processingFormat.channelCount, marks: marks)
                self.file = nil; self.continuation = nil
                continuation.resume(returning: result)
            } else {
                if file == nil {
                    file = try AVAudioFile(forWriting: url, settings: pcm.format.settings,
                        commonFormat: pcm.format.commonFormat, interleaved: pcm.format.isInterleaved)
                }
                guard file!.processingFormat == pcm.format else { throw LocalSpeechError.formatMismatch }
                try file!.write(from: pcm); frames += AVAudioFramePosition(pcm.frameLength)
            }
        } catch {
            self.file = nil; self.continuation = nil
            continuation.resume(throwing: error)
        }
    }
    func fail(_ error: Error) {
        lock.lock(); defer { lock.unlock() }
        file = nil
        continuation?.resume(throwing: error); continuation = nil
    }
    func acceptMarkers(_ values: [AVSpeechSynthesisMarker]) {
        lock.lock(); defer { lock.unlock() }
        for value in values where value.mark == .word {
            marks.append(SpeechMark(start: value.textRange.location, length: value.textRange.length, byteSampleOffset: value.byteSampleOffset))
        }
    }
}

private final class ConverterInput: @unchecked Sendable {
    private let lock = NSLock()
    private let buffer: AVAudioPCMBuffer
    private var supplied = false
    init(_ buffer: AVAudioPCMBuffer) { self.buffer = buffer }
    func next(_ state: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
        lock.lock(); defer { lock.unlock() }
        if supplied { state.pointee = .endOfStream; return nil }
        supplied = true; state.pointee = .haveData; return buffer
    }
}

/// One prepared system synthesizer per language; no romanized text sent to it.
@MainActor final class LocalVoice {
    let language: String
    let voice: AVSpeechSynthesisVoice?
    var identifier: String { voice?.identifier ?? SwahiliSpeech.identifier }
    private let synth = AVSpeechSynthesizer()
    private var active: SpeechFileWriter?
    private var swahiliJob: SwahiliSpeech.Job?
    private var renderID = UUID()
    #if DEBUG
    /// Controlled stalled callback qualification; never enabled by app UI.
    var qualificationStallTimeout: Duration?
    #endif

    private static var voiceInventory: Task<[AVSpeechSynthesisVoice],Never>?
    fileprivate static func installedVoices() async -> [AVSpeechSynthesisVoice] {
        if let voiceInventory { return await voiceInventory.value }
        // First use can wait on the OS speech catalog for minutes. Share only
        // the in-flight query so a later foreground visit sees newly added voices.
        let task = Task.detached(priority:.userInitiated) {
            AVSpeechSynthesisVoice.speechVoices().filter { !$0.voiceTraits.contains(.isNoveltyVoice) }
        }
        voiceInventory = task
        let voices = await task.value
        voiceInventory = nil
        return voices
    }
    static func availableLanguageCodes() async -> Set<String> {
        let voices = await installedVoices()
        var codes = Set(voices.compactMap { LocalLanguageCatalog.practiceVoiceCode($0.language) })
        if SwahiliSpeech.packagedRoot != nil { codes.insert("sw") } else { codes.remove("sw") }
        return codes
    }
    convenience init(language: String) async throws {
        let available = language.components(separatedBy:"-")[0] == "sw" ? [] : await Self.installedVoices()
        try Task.checkCancellation()
        try self.init(language:language,available:available)
    }
    fileprivate init(language: String, available: [AVSpeechSynthesisVoice]) throws {
        self.language = language
        let code = LocalLanguageCatalog.canonicalCode(language)
        if code == "sw" { voice = nil; return }
        let preferred = ["en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "it": "it-IT", "pt": "pt-BR",
            "ar": "ar-001", "zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR"][language] ?? language
        let matching = available.filter {
            LocalLanguageCatalog.practiceVoiceCode($0.language) == code
        }.sorted {
            // An explicitly selected dialect takes precedence. For a language
            // without a region, prefer its best installed natural voice.
            if language.contains("-"), ($0.language == preferred) != ($1.language == preferred) { return $0.language == preferred }
            if $0.quality != $1.quality { return $0.quality.rawValue > $1.quality.rawValue }
            if ($0.language == preferred) != ($1.language == preferred) { return $0.language == preferred }
            if $0.identifier.hasPrefix("com.apple.voice.") != $1.identifier.hasPrefix("com.apple.voice.") { return $0.identifier.hasPrefix("com.apple.voice.") }
            return $0.identifier < $1.identifier
        }
        guard let voice = matching.first else { throw LocalSpeechError.missingVoice(language) }
        self.voice = voice
    }

    func render(_ text: String, to url: URL) async throws -> RenderedSpeech {
        try Task.checkCancellation()
        guard active == nil, swahiliJob == nil, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= FullMessageBudget.recordBytes else { throw LocalSpeechError.unavailable }
        if language.components(separatedBy: "-")[0] == "sw" {
            let job = SwahiliSpeech.Job(); swahiliJob = job
            defer { swahiliJob = nil }
            return try await SwahiliSpeech.shared.render(text, to: url, job: job)
        }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = voice
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        utterance.preUtteranceDelay = 0
        utterance.postUtteranceDelay = 0
        let request = UUID(); renderID = request
        var deadline: Duration = .seconds(30)
        #if DEBUG
        if let qualificationStallTimeout { deadline = qualificationStallTimeout }
        #endif
        let timeout = Task { @MainActor [weak self] in
            do {
                try await Task.sleep(for: deadline)
                try Task.checkCancellation()
                self?.finish(request: request, error: LocalSpeechError.timedOut)
            } catch { }
        }
        defer { timeout.cancel(); if renderID == request { active = nil } }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                let writer = SpeechFileWriter(url: url, continuation: continuation)
                active = writer
                #if DEBUG
                if qualificationStallTimeout != nil { return }
                #endif
                synth.write(utterance, toBufferCallback: { buffer in writer.accept(buffer) },
                    toMarkerCallback: { markers in writer.acceptMarkers(markers) })
            }
        } onCancel: { Task { @MainActor [weak self] in self?.finish(request: request, error: CancellationError()) } }
    }
    private func finish(request: UUID, error: Error) {
        guard renderID == request else { return }
        renderID = UUID()
        active?.fail(error); active = nil
        synth.stopSpeaking(at: .immediate)
    }
    func stop() {
        swahiliJob?.cancel()
        finish(request: renderID, error: CancellationError())
    }
}

/// SDK seam retains the production native synthesizer/file pipeline. Tests can
/// forward through a pair in their own directory without altering user audio.
@MainActor protocol PreparedSpeechPair: AnyObject {
    func prepare(warmups:[String:String]) async throws
    func render(_ spans:[(text:String,language:String)]) async throws -> RenderedSpeech
    func render(_ spans:[(text:String,language:String)], estimateWordTiming:Bool) async throws -> RenderedSpeech
    func stop()
}

extension PreparedSpeechPair {
    func render(_ spans:[(text:String,language:String)], estimateWordTiming:Bool) async throws -> RenderedSpeech {
        try await render(spans)
    }
}

@MainActor final class LocalSpeechPair: PreparedSpeechPair {
    private let root: URL
    private let languages: [String]
    private var voices: [String: LocalVoice] = [:]
    private var prepared = false
    private var busy = false
    #if DEBUG
    /// Simulate incomplete OS marker coverage without altering synthesized audio.
    var qualificationRetainNativeMarkers:Int?
    #endif

    init(source: String, target: String, root: URL) throws {
        self.root = root
        languages = source == target ? [source] : [source,target]
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    func prepare(warmups: [String: String]) async throws {
        if prepared { return }
        guard !busy else { throw LocalSpeechError.unavailable }
        busy = true; defer { busy = false }
        let installed = languages.contains(where:{ $0.components(separatedBy:"-")[0] != "sw" }) ? await LocalVoice.installedVoices() : []
        try Task.checkCancellation()
        var selected: [String:LocalVoice] = [:]
        for language in languages { selected[language] = try LocalVoice(language:language,available:installed) }
        voices = selected
        for (language, voice) in voices {
            guard let text = warmups[language] else { throw LocalSpeechError.unavailable }
            let file = root.appendingPathComponent("warm-\(UUID()).caf")
            defer { try? FileManager.default.removeItem(at: file) }
            _ = try await voice.render(text, to: file)
        }
        prepared = true
    }
    func render(_ spans: [(text: String, language: String)]) async throws -> RenderedSpeech {
        try await render(spans,estimateWordTiming:true)
    }
    func render(_ spans: [(text: String, language: String)], estimateWordTiming:Bool) async throws -> RenderedSpeech {
        guard prepared else { throw LocalSpeechError.notPrepared }
        guard !busy, !spans.isEmpty, spans.reduce(0, { $0 + $1.text.utf8.count }) <= FullMessageBudget.recordBytes else { throw LocalSpeechError.unavailable }
        busy = true; defer { busy = false }
        for span in spans {
            guard voices[span.language] != nil else { throw LocalSpeechError.missingVoice(span.language) }
        }
        let normalized = SpeechChunks.coalesced(spans)
        let identity = "native-phrase-pcm-4\0" + (estimateWordTiming ? "guided\0" : "native\0") + normalized.map { $0.language + "\0" + voices[$0.language]!.identifier + "\0" + $0.text }.joined(separator: "\0")
        let hash = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        let output = root.appendingPathComponent(hash + ".caf")
        let metadata = output.appendingPathExtension("words.json")
        // Older audio has no native timing metadata. Regenerate instead of
        // guessing word timing or showing a whole-message highlight.
        if FileManager.default.fileExists(atPath: output.path),
           let bytes = try? Data(contentsOf:metadata),let marks = try? JSONDecoder().decode([SpeechMark].self,from:bytes) {
            var result = try Self.inspect(output); result.marks = marks; return result
        }
        try? FileManager.default.removeItem(at:output)
        var parts: [URL] = [], temporary:[URL] = []
        var rendered: [RenderedSpeech] = [], lengths:[Int] = []
        defer { for part in temporary { try? FileManager.default.removeItem(at: part) } }
        for span in normalized {
            let part = root.appendingPathComponent("span-\(UUID()).caf"); temporary.append(part)
            var native = try await voices[span.language]!.render(span.text,to:part)
            let nativeFile = try AVAudioFile(forReading:part)
            let nativeBytesPerFrame = max(1,Int(nativeFile.processingFormat.streamDescription.pointee.mBytesPerFrame))
            native.marks = native.marks.filter{$0.byteSampleOffset >= 0 && $0.byteSampleOffset/nativeBytesPerFrame < Int(nativeFile.length)}
            #if DEBUG
            if let count = qualificationRetainNativeMarkers { native.marks = Array(native.marks.prefix(count)) }
            #endif
            // Word callbacks are optional. Resynthesizing words one at a time
            // changes the speaker’s cadence and loses punctuation context.
            // Derive missing visual timing from this same recording.
            if !SpeechChunks.marksCoverWords(native.marks,text:span.text,language:span.language) {
                let words = SpeechChunks.wordRanges(span.text,language:span.language)
                if words.count == 1, let word = words.first {
                    // This entire rendered file belongs to one practice word.
                    // Its measured start is sufficient even without a callback.
                    native.marks = [.init(start:word.location,length:word.length,byteSampleOffset:0,source:"measured_single_word_pcm")]
                } else if estimateWordTiming {
                    let marks=native.marks
                    native.marks=try await Task.detached(priority:.userInitiated) {
                        try Self.guidedMarks(file:part,text:span.text,language:span.language,marks:marks)
                    }.value
                } else {
                    native.marks.removeAll()
                }
            }
            parts.append(part)
            rendered.append(native)
            lengths.append(span.text.utf16.count)
        }
        // Disk IO and standard AVAudioConverter resampling happen off the UI actor.
        let inputs = parts, timings = rendered, textLengths = lengths
        return try await Task.detached { [inputs, output, timings, textLengths, metadata] in
            let result = try Self.join(inputs, timings:timings, lengths:textLengths, to: output)
            try JSONEncoder().encode(result.marks).write(to:metadata,options:.atomic)
            Self.pruneCache(in: output.deletingLastPathComponent(), keeping: output)
            return result
        }.value
    }
    func stop() { for voice in voices.values { voice.stop() } }

    private nonisolated static func guidedMarks(file url:URL,text:String,language:String,marks:[SpeechMark]) throws -> [SpeechMark] {
        let file=try AVAudioFile(forReading:url),format=file.processingFormat
        let frames=Int(file.length),window=max(1,Int(format.sampleRate*0.01))
        guard frames>0,frames<10_000_000,let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:AVAudioFrameCount(window*40)) else { throw LocalSpeechError.invalidAudio }
        var energy:[Float]=[]
        while file.framePosition<file.length {
            try Task.checkCancellation()
            try file.read(into:buffer)
            guard buffer.frameLength>0,let pcm=buffer.floatChannelData else { break }
            for start in stride(from:0,to:Int(buffer.frameLength),by:window) {
                let end=min(Int(buffer.frameLength),start+window)
                var sum:Float=0
                for i in start..<end { let value=pcm[0][i];sum+=value*value }
                energy.append(sqrt(sum/Float(end-start)))
            }
        }
        let voiced=SpeechWordTiming.regions(energy:energy,window:window,frames:frames,sampleRate:format.sampleRate)
        return SpeechWordTiming.interpolate(text:text,language:language,marks:marks,regions:voiced,
            frames:frames,bytesPerFrame:Int(format.streamDescription.pointee.mBytesPerFrame),sampleRate:format.sampleRate)
    }
    private nonisolated static func pruneCache(in root: URL, keeping output: URL) {
        let keys: Set<URLResourceKey> = [.fileSizeKey, .contentModificationDateKey]
        guard let files = try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys)) else { return }
        let cached = files.filter { $0.pathExtension == "caf" && $0.deletingPathExtension().lastPathComponent.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
            .compactMap { url -> (url: URL, bytes: Int, date: Date)? in
                guard let values = try? url.resourceValues(forKeys: keys) else { return nil }
                return (url, values.fileSize ?? 0, values.contentModificationDate ?? .distantPast)
            }.sorted { $0.date < $1.date }
        var total = cached.reduce(0) { $0 + $1.bytes }
        for file in cached where file.url != output {
            guard total > 64 * 1024 * 1024 else { break }
            do { try FileManager.default.removeItem(at: file.url); try? FileManager.default.removeItem(at:file.url.appendingPathExtension("words.json")); total -= file.bytes } catch { }
        }
    }

    private nonisolated static func inspect(_ url: URL) throws -> RenderedSpeech {
        let file = try AVAudioFile(forReading: url)
        guard file.length > 0 else { throw LocalSpeechError.invalidAudio }
        return RenderedSpeech(file: url, milliseconds: Double(file.length) * 1000 / file.processingFormat.sampleRate,
            sampleRate: file.processingFormat.sampleRate, channels: file.processingFormat.channelCount)
    }
    private nonisolated static func join(_ parts: [URL], timings:[RenderedSpeech], lengths:[Int], to output: URL) throws -> RenderedSpeech {
        let temporary = output.deletingLastPathComponent().appendingPathComponent("joined-\(UUID()).caf")
        defer { try? FileManager.default.removeItem(at: temporary) }
        let format = AVAudioFormat(standardFormatWithSampleRate: 24_000, channels: 1)!
        var destination: AVAudioFile? = try AVAudioFile(forWriting: temporary, settings: format.settings)
        var frames = 0
        var boundaries: [Int] = [], marks: [SpeechMark] = [], textOffset = 0
        for (index,part) in parts.enumerated() {
            let input = try AVAudioFile(forReading: part)
            guard input.length > 0, input.length < 10_000_000,
                  let buffer = AVAudioPCMBuffer(pcmFormat: input.processingFormat, frameCapacity: AVAudioFrameCount(input.length)) else { throw LocalSpeechError.invalidAudio }
            try input.read(into: buffer)
            guard let converter = AVAudioConverter(from: input.processingFormat, to: format),
                  let converted = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(ceil(Double(buffer.frameLength) * format.sampleRate / buffer.format.sampleRate)) + 64) else { throw LocalSpeechError.invalidAudio }
            let provider = ConverterInput(buffer)
            var error: NSError?
            let status = converter.convert(to: converted, error: &error) { _, state in
                return provider.next(state)
            }
            guard status != .error, error == nil, converted.frameLength > 0 else { throw error ?? LocalSpeechError.invalidAudio as NSError }
            if frames > 0 { boundaries.append(frames) }
            let bytesPerFrame = max(1,Int(input.processingFormat.streamDescription.pointee.mBytesPerFrame))
            for mark in timings[index].marks where mark.start >= 0 && mark.start <= lengths[index] && mark.length > 0 && mark.length <= lengths[index]-mark.start {
                let localFrame = Double(mark.byteSampleOffset) / Double(bytesPerFrame)
                let outputFrame = frames + Int((localFrame * format.sampleRate / input.processingFormat.sampleRate).rounded())
                guard outputFrame >= frames,outputFrame < frames + Int(converted.frameLength) else { continue }
                let outputBytes=Int(format.streamDescription.pointee.mBytesPerFrame)
                let end=mark.endByteSampleOffset.map { offset in
                    let local=Double(offset)/Double(bytesPerFrame)
                    return min(frames+Int(converted.frameLength),frames+Int((local*format.sampleRate/input.processingFormat.sampleRate).rounded()))*outputBytes
                }
                marks.append(.init(start:textOffset+mark.start,length:mark.length,byteSampleOffset:outputFrame*outputBytes,source:mark.source,endByteSampleOffset:end))
            }
            textOffset += lengths[index]
            try destination!.write(from: converted)
            frames += Int(converted.frameLength)
        }
        destination = nil
        try FileManager.default.moveItem(at: temporary, to: output)
        var result = try inspect(output)
        result.boundaryFrames = boundaries; result.marks = marks
        return result
    }
}
