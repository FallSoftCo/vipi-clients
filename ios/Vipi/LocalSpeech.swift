import AVFoundation
import CryptoKit
import Foundation

enum LocalSpeechError: Error { case missingVoice(String), invalidAudio, unavailable, formatMismatch, notPrepared }

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

    init(language: String) throws {
        self.language = language
        let code = language.components(separatedBy: "-")[0]
        if code == "sw" { voice = nil; return }
        let preferred = ["en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "it": "it-IT", "pt": "pt-BR",
            "ar": "ar-001", "zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR"][language] ?? language
        let available = AVSpeechSynthesisVoice.speechVoices().filter {
            $0.language.components(separatedBy: "-")[0] == code && !$0.voiceTraits.contains(.isNoveltyVoice)
        }.sorted {
            if ($0.language == preferred) != ($1.language == preferred) { return $0.language == preferred }
            if $0.quality != $1.quality { return $0.quality.rawValue > $1.quality.rawValue }
            if $0.identifier.hasPrefix("com.apple.voice.") != $1.identifier.hasPrefix("com.apple.voice.") { return $0.identifier.hasPrefix("com.apple.voice.") }
            return $0.identifier < $1.identifier
        }
        guard let voice = available.first else { throw LocalSpeechError.missingVoice(language) }
        self.voice = voice
    }

    func render(_ text: String, to url: URL) async throws -> RenderedSpeech {
        guard active == nil, swahiliJob == nil, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf16.count <= 16_384 else { throw LocalSpeechError.unavailable }
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
        let timeout = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .seconds(30)); self?.stop() } catch { }
        }
        defer { timeout.cancel(); active = nil }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                let writer = SpeechFileWriter(url: url, continuation: continuation)
                active = writer
                synth.write(utterance, toBufferCallback: { buffer in writer.accept(buffer) },
                    toMarkerCallback: { markers in writer.acceptMarkers(markers) })
            }
        } onCancel: { Task { @MainActor [weak self] in self?.stop() } }
    }
    func stop() {
        swahiliJob?.cancel()
        active?.fail(CancellationError()); active = nil
        synth.stopSpeaking(at: .immediate)
    }
}

/// Initial full-buffer experiment. One output file means one playback instance.
/// Streaming is selected only if measured first-play latency warrants it.
@MainActor final class LocalSpeechPair {
    private let root: URL
    private let voices: [String: LocalVoice]
    private var prepared = false
    private var busy = false

    init(source: String, target: String, root: URL) throws {
        guard source != target else { throw LocalSpeechError.unavailable }
        self.root = root
        voices = [source: try LocalVoice(language: source), target: try LocalVoice(language: target)]
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    func prepare(warmups: [String: String]) async throws {
        if prepared { return }
        guard !busy else { throw LocalSpeechError.unavailable }
        busy = true; defer { busy = false }
        for (language, voice) in voices {
            guard let text = warmups[language] else { throw LocalSpeechError.unavailable }
            let file = root.appendingPathComponent("warm-\(UUID()).caf")
            defer { try? FileManager.default.removeItem(at: file) }
            _ = try await voice.render(text, to: file)
        }
        prepared = true
    }
    func render(_ spans: [(text: String, language: String)]) async throws -> RenderedSpeech {
        guard prepared else { throw LocalSpeechError.notPrepared }
        guard !busy, !spans.isEmpty, spans.reduce(0, { $0 + $1.text.utf16.count }) <= 16_384 else { throw LocalSpeechError.unavailable }
        busy = true; defer { busy = false }
        for span in spans {
            guard voices[span.language] != nil else { throw LocalSpeechError.missingVoice(span.language) }
        }
        let normalized = SpeechChunks.coalesced(spans)
        let identity = normalized.map { $0.language + "\0" + voices[$0.language]!.identifier + "\0" + $0.text }.joined(separator: "\0")
        let hash = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        let output = root.appendingPathComponent(hash + ".caf")
        if FileManager.default.fileExists(atPath: output.path) { return try Self.inspect(output) }
        var parts: [URL] = []
        defer { for part in parts { try? FileManager.default.removeItem(at: part) } }
        for span in normalized {
            let part = root.appendingPathComponent("span-\(UUID()).caf")
            parts.append(part)
            _ = try await voices[span.language]!.render(span.text, to: part)
        }
        // Disk IO and standard AVAudioConverter resampling happen off the UI actor.
        let inputs = parts
        return try await Task.detached { [inputs, output] in
            let result = try Self.join(inputs, to: output)
            Self.pruneCache(in: output.deletingLastPathComponent(), keeping: output)
            return result
        }.value
    }
    func stop() { for voice in voices.values { voice.stop() } }

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
            do { try FileManager.default.removeItem(at: file.url); total -= file.bytes } catch { }
        }
    }

    private nonisolated static func inspect(_ url: URL) throws -> RenderedSpeech {
        let file = try AVAudioFile(forReading: url)
        guard file.length > 0 else { throw LocalSpeechError.invalidAudio }
        return RenderedSpeech(file: url, milliseconds: Double(file.length) * 1000 / file.processingFormat.sampleRate,
            sampleRate: file.processingFormat.sampleRate, channels: file.processingFormat.channelCount)
    }
    private nonisolated static func join(_ parts: [URL], to output: URL) throws -> RenderedSpeech {
        let temporary = output.deletingLastPathComponent().appendingPathComponent("joined-\(UUID()).caf")
        defer { try? FileManager.default.removeItem(at: temporary) }
        let format = AVAudioFormat(standardFormatWithSampleRate: 24_000, channels: 1)!
        var destination: AVAudioFile? = try AVAudioFile(forWriting: temporary, settings: format.settings)
        var frames = 0
        var boundaries: [Int] = []
        for part in parts {
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
            try destination!.write(from: converted)
            frames += Int(converted.frameLength)
        }
        destination = nil
        try FileManager.default.moveItem(at: temporary, to: output)
        var result = try inspect(output)
        result.boundaryFrames = boundaries
        return result
    }
}
