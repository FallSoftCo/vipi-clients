import AVFoundation
import Foundation
import libespeak_ng

/// eSpeak has process-global state. All initialization, synthesis and callbacks
/// run on this one serial queue, never the UI actor. Only cancellation crosses it.
final class BundledSpeech: @unchecked Sendable {
    static let shared = BundledSpeech()

    private struct Manifest: Decodable {
        struct Voice: Decodable {
            let voice: String
            let dictionary: String
        }
        let voices: [String: Voice]
    }

    private static let packagedRoot = Bundle.main.resourceURL?
        .appendingPathComponent("vipi-speech-699e7969", isDirectory: true)
    private static let voices: [String: Manifest.Voice] = {
        guard let root = packagedRoot, let data = try? Data(contentsOf: root.appendingPathComponent("manifest.json")),
            let manifest = try? JSONDecoder().decode(Manifest.self, from: data)
        else { return [:] }
        // The Japanese engine expects kana. The system voice handles arbitrary
        // mixed kanji and kana until this fallback has a matching native reader.
        return manifest.voices.filter { code, entry in
            code != "ja"
                && FileManager.default.isReadableFile(
                    atPath:
                        root
                        .appendingPathComponent("espeak-ng-data/\(entry.dictionary)_dict").path)
        }
    }()
    static var availableLanguages: Set<String> { Set(voices.keys) }
    static func voice(for language: String) -> String? { voices[LocalLanguageCatalog.canonicalCode(language)]?.voice }
    static func identifier(for voice: String) -> String { "espeak-ng-fd28f646-" + voice }

    private let queue = DispatchQueue(label: "co.fallsoft.vipi.bundled-speech", qos: .userInitiated)
    private var initialized = false

    final class Job: @unchecked Sendable {
        private let lock = NSLock()
        private var cancelled = false
        // The rest is confined to the synthesis queue, including C callbacks.
        var file: AVAudioFile?
        var frames: AVAudioFramePosition = 0
        var error: Error?
        var scalarOffsets: [Int] = []
        var marks: [SpeechMark] = []
        var sampleRate: Double = 0
        func acceptEvents(_ events: UnsafeMutablePointer<espeak_EVENT>?) {
            guard let events else { return }
            var index = 0
            while events[index].type != espeakEVENT_LIST_TERMINATED {
                let event = events[index]
                index += 1
                guard event.type == espeakEVENT_WORD, event.text_position > 0, event.length > 0 else { continue }
                let start = Int(event.text_position) - 1, end = start + Int(event.length)
                guard start >= 0, end < scalarOffsets.count else { continue }
                let range = NSRange(location: scalarOffsets[start], length: scalarOffsets[end] - scalarOffsets[start])
                let frame = Int((Double(event.audio_position) * sampleRate / 1000).rounded())
                marks.append(.init(start: range.location, length: range.length, byteSampleOffset: frame * 4))
            }
        }
        func cancel() {
            lock.lock()
            cancelled = true
            lock.unlock()
        }
        var isCancelled: Bool {
            lock.lock()
            defer { lock.unlock() }
            return cancelled
        }
        func accept(_ samples: UnsafeMutablePointer<Int16>?, count: Int32) -> Int32 {
            if isCancelled { return 1 }
            guard let samples, count > 0 else { return 0 }
            do {
                guard let file,
                    let buffer = AVAudioPCMBuffer(
                        pcmFormat: file.processingFormat,
                        frameCapacity: AVAudioFrameCount(count)), let channel = buffer.floatChannelData?[0]
                else {
                    throw LocalSpeechError.invalidAudio
                }
                buffer.frameLength = AVAudioFrameCount(count)
                for i in 0..<Int(count) { channel[i] = Float(samples[i]) / 32768 }
                try file.write(from: buffer)
                frames += AVAudioFramePosition(count)
                return 0
            } catch {
                self.error = error
                return 1
            }
        }
    }

    func render(_ text: String, voice: String, to url: URL, job: Job) async throws -> RenderedSpeech {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async {
                    do {
                        continuation.resume(returning: try self.synthesize(text, voice: voice, to: url, job: job))
                    } catch {
                        try? FileManager.default.removeItem(at: url)
                        continuation.resume(throwing: error)
                    }
                }
            }
        } onCancel: {
            job.cancel()
        }
    }

    private func synthesize(_ text: String, voice: String, to url: URL, job: Job) throws -> RenderedSpeech {
        guard !job.isCancelled else { throw CancellationError() }
        if !initialized {
            // This resource is compiled from the exact eSpeak revision linked by
            // the app and verified during every build. It is read-only in the app
            // bundle, avoiding stale or incomplete installed-data caches.
            guard let root = Self.packagedRoot else { throw LocalSpeechError.unavailable }
            root.path.withCString { espeak_ng_InitializePath($0) }
            guard espeak_ng_Initialize(nil) == ENS_OK,
                espeak_ng_InitializeOutput(ENOUTPUT_MODE_SYNCHRONOUS, 0, nil) == ENS_OK
            else {
                throw LocalSpeechError.unavailable
            }
            espeak_SetSynthCallback { samples, count, events in
                guard let pointer = events?.pointee.user_data else { return 1 }
                let job = Unmanaged<Job>.fromOpaque(pointer).takeUnretainedValue()
                job.acceptEvents(events)
                return job.accept(samples, count: count)
            }
            initialized = true
        }
        guard !job.isCancelled else { throw CancellationError() }
        guard espeak_ng_SetVoiceByName(voice) == ENS_OK else { throw LocalSpeechError.missingVoice(voice) }
        _ = espeak_ng_SetParameter(espeakRATE, 155, 0)
        let rate = Double(espeak_ng_GetSampleRate())
        guard rate > 0, let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1) else {
            throw LocalSpeechError.invalidAudio
        }
        job.scalarOffsets = [0]
        for scalar in text.unicodeScalars {
            job.scalarOffsets.append(job.scalarOffsets.last! + String(scalar).utf16.count)
        }
        job.marks = []
        job.sampleRate = rate
        job.file = try AVAudioFile(forWriting: url, settings: format.settings)
        defer { job.file = nil }
        let pointer = Unmanaged.passUnretained(job).toOpaque()
        // Literal user text, UTF-8 byte count including NUL. SSML is deliberately
        // disabled so messages cannot inject synthesis commands.
        let status = text.utf8CString.withUnsafeBufferPointer { bytes in
            espeak_ng_Synthesize(
                bytes.baseAddress, bytes.count, 0, POS_CHARACTER, 0,
                UInt32(espeakCHARS_UTF8), nil, pointer)
        }
        _ = espeak_ng_Synchronize()
        if job.isCancelled { throw CancellationError() }
        if let error = job.error { throw error }
        guard status == ENS_OK, job.frames > 0 else { throw LocalSpeechError.invalidAudio }
        return RenderedSpeech(
            file: url, milliseconds: Double(job.frames) * 1000 / rate, sampleRate: rate, channels: 1, marks: job.marks)
    }
}
