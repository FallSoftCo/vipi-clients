import AVFoundation
import Foundation
import libespeak_ng

/// eSpeak has process-global state. All initialization, synthesis and callbacks
/// run on this one serial queue, never the UI actor. Only cancellation crosses it.
final class SwahiliSpeech: @unchecked Sendable {
    static let shared = SwahiliSpeech()
    static let identifier = "espeak-ng-fd28f646-sw"
    private let queue = DispatchQueue(label: "co.fallsoft.vipi.swahili-speech", qos: .userInitiated)
    private var initialized = false

    final class Job: @unchecked Sendable {
        private let lock = NSLock()
        private var cancelled = false
        // The rest is confined to SwahiliSpeech.queue, including C callbacks.
        var file: AVAudioFile?
        var frames: AVAudioFramePosition = 0
        var error: Error?
        func cancel() { lock.lock(); cancelled = true; lock.unlock() }
        var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
        func accept(_ samples: UnsafeMutablePointer<Int16>?, count: Int32) -> Int32 {
            if isCancelled { return 1 }
            guard let samples, count > 0 else { return 0 }
            do {
                guard let file, let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat,
                    frameCapacity: AVAudioFrameCount(count)), let channel = buffer.floatChannelData?[0] else {
                    throw LocalSpeechError.invalidAudio
                }
                buffer.frameLength = AVAudioFrameCount(count)
                for i in 0..<Int(count) { channel[i] = Float(samples[i]) / 32768 }
                try file.write(from: buffer); frames += AVAudioFramePosition(count)
                return 0
            } catch { self.error = error; return 1 }
        }
    }

    func render(_ text: String, to url: URL, job: Job) async throws -> RenderedSpeech {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async {
                    do { continuation.resume(returning: try self.synthesize(text, to: url, job: job)) }
                    catch { try? FileManager.default.removeItem(at: url); continuation.resume(throwing: error) }
                }
            }
        } onCancel: { job.cancel() }
    }

    private func synthesize(_ text: String, to url: URL, job: Job) throws -> RenderedSpeech {
        guard !job.isCancelled else { throw CancellationError() }
        if !initialized {
            // This resource is compiled from the exact eSpeak revision linked by
            // the app and verified during every build. It is read-only in the app
            // bundle, avoiding stale or incomplete installed-data caches.
            guard let resources = Bundle.main.resourceURL else { throw LocalSpeechError.unavailable }
            let root = resources.appendingPathComponent("vipi-speech-699e7969", isDirectory: true)
            let data = root.appendingPathComponent("espeak-ng-data", isDirectory: true)
            for path in ["sw_dict", "phondata", "phonindex", "phontab", "intonations", "lang/bnt/sw"] {
                guard FileManager.default.isReadableFile(atPath: data.appendingPathComponent(path).path) else {
                    throw LocalSpeechError.unavailable
                }
            }
            root.path.withCString { espeak_ng_InitializePath($0) }
            guard espeak_ng_Initialize(nil) == ENS_OK,
                  espeak_ng_InitializeOutput(ENOUTPUT_MODE_SYNCHRONOUS, 0, nil) == ENS_OK else {
                throw LocalSpeechError.unavailable
            }
            espeak_SetSynthCallback { samples, count, events in
                guard let pointer = events?.pointee.user_data else { return 1 }
                return Unmanaged<Job>.fromOpaque(pointer).takeUnretainedValue().accept(samples, count: count)
            }
            initialized = true
        }
        guard !job.isCancelled else { throw CancellationError() }
        guard espeak_ng_SetVoiceByName("sw") == ENS_OK else { throw LocalSpeechError.missingVoice("sw") }
        _ = espeak_ng_SetParameter(espeakRATE, 155, 0)
        let rate = Double(espeak_ng_GetSampleRate())
        guard rate > 0, let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1) else {
            throw LocalSpeechError.invalidAudio
        }
        job.file = try AVAudioFile(forWriting: url, settings: format.settings)
        defer { job.file = nil }
        let pointer = Unmanaged.passUnretained(job).toOpaque()
        // Literal user text, UTF-8 byte count including NUL. SSML is deliberately
        // disabled so messages cannot inject synthesis commands.
        let status = text.utf8CString.withUnsafeBufferPointer { bytes in
            espeak_ng_Synthesize(bytes.baseAddress, bytes.count, 0, POS_CHARACTER, 0,
                UInt32(espeakCHARS_UTF8), nil, pointer)
        }
        _ = espeak_ng_Synchronize()
        if job.isCancelled { throw CancellationError() }
        if let error = job.error { throw error }
        guard status == ENS_OK, job.frames > 0 else { throw LocalSpeechError.invalidAudio }
        return RenderedSpeech(file: url, milliseconds: Double(job.frames)*1000/rate, sampleRate: rate, channels: 1)
    }
}
