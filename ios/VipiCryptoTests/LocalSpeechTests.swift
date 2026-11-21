import AVFoundation
import XCTest
@testable import Vipi

/// Apple’s voice catalog can cold-start before synthesis is available. Measure
/// that separately from render, playback, and cancellation deadlines.
@MainActor func waitForNativeVoicePreparation(_ player: SpeechPlayback,
    file: StaticString = #filePath, line: UInt = #line) async throws {
    let start = ProcessInfo.processInfo.systemUptime
    while player.state == .preparing && ProcessInfo.processInfo.systemUptime - start < 150 {
        try await Task.sleep(for: .milliseconds(20))
    }
    print("VIPI_NATIVE_VOICE_PREPARATION seconds=\(ProcessInfo.processInfo.systemUptime - start) state=\(player.state)")
    guard player.state == .ready else {
        XCTFail(player.error ?? "Native speech preparation remained \(player.state)", file: file, line: line)
        throw LocalSpeechError.unavailable
    }
}

@MainActor final class LocalSpeechTests: XCTestCase {
    func testProgressiveParagraphCompletesWithoutUnderruns() async throws {
        let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: Bundle(for: Self.self).url(forResource: "speech-lengths", withExtension: "json")!)) as! [String: Any]
        let spans = (fixture["spans"] as! [[String: String]]).map { (text: $0["text"]!, language: $0["language"]!) }
        let controller = SpeechPlayback()
        defer { controller.close() }
        func awaitState(_ state: SpeechState) async throws {
            let deadline = Date().addingTimeInterval(45)
            while controller.state != state {
                if let error = controller.error { XCTFail(error); throw LocalSpeechError.unavailable }
                guard Date() < deadline else { throw LocalSpeechError.unavailable }
                try await Task.sleep(for: .milliseconds(20))
            }
        }
        controller.prepare(source: "en", target: "es", warmups: ["en": "Hello.", "es": "Hola."])
        try await waitForNativeVoicePreparation(controller)
        let start = Date()
        controller.toggle(message: "paragraph", spans: spans)
        try await awaitState(.playing)
        let latency = Date().timeIntervalSince(start) * 1000
        try await awaitState(.ready)
        let report: [String: Any] = ["evidence": "progressive_native_output_not_acoustic_or_listening_acceptance",
            "request_to_player_started_ms": latency, "completion": "passed", "output_underruns": controller.outputUnderruns]
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("speech-qa")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: root.appendingPathComponent("progressive-001.json"), options: .atomic)
        XCTAssertEqual(controller.outputUnderruns, 0)
    }

    func testChunkPlanningPreservesUnicodeAndLanguages() {
        let spans = [(text: String(repeating: "Meet me by the river 🌊. ", count: 30), language: "en"), (text: "明日はコーヒーを飲みましょう。", language: "ja")]
        let chunks = SpeechChunks.plan(spans)
        XCTAssertGreaterThan(chunks.count, 1)
        XCTAssertEqual(chunks.flatMap { $0 }.map(\.text).joined(), spans.map(\.text).joined())
        XCTAssertTrue(chunks.allSatisfy { $0.reduce(0) { $0 + $1.text.count } <= 160 })
        XCTAssertEqual(chunks.last?.last?.language, "ja")
    }

    func testErasedAudioGenerationCannotBeRepopulatedByInFlightSynthesis() async throws {
        let oldRoot = MessageSpeechCache.directory
        let pair = try LocalSpeechPair(source: "en", target: "sw", root: oldRoot)
        try await pair.prepare(warmups: ["en": "Hello", "sw": "Habari"])
        let render = Task { try await pair.render([(text: String(repeating: "Habari rafiki yangu. ", count: 150), language: "sw"), (text: "This is private speech.", language: "en")]) }
        await Task.yield()
        render.cancel(); pair.stop()
        try MessageSpeechCache.erase()
        let newRoot = MessageSpeechCache.directory
        try FileManager.default.createDirectory(at: newRoot, withIntermediateDirectories: true)
        _ = await render.result
        XCTAssertNotEqual(oldRoot, newRoot)
        XCTAssertFalse(FileManager.default.fileExists(atPath: oldRoot.path))
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: newRoot.path).isEmpty)
    }

    func testActualPlayerCompletionAndCancellation() async throws {
        let controller = SpeechPlayback()
        defer { controller.close() }
        var report: [String: Any] = ["evidence": "actual_player_callbacks_not_acoustic_or_listening_acceptance"]
        func awaitState(_ expected: SpeechState) async throws {
            let deadline = Date().addingTimeInterval(15)
            while controller.state != expected {
                if let error = controller.error { XCTFail(error); throw LocalSpeechError.unavailable }
                guard Date() < deadline else { XCTFail("Player timed out"); throw LocalSpeechError.unavailable }
                try await Task.sleep(for: .milliseconds(20))
            }
        }
        controller.prepare(source: "en", target: "es", warmups: ["en": "Hello.", "es": "Hola."])
        try await waitForNativeVoicePreparation(controller)
        let spans = [(text:"A new message.",language:"en"),(text:"Un mensaje nuevo.",language:"es")]
        var start = Date()
        controller.toggle(message: "mixed", spans: spans)
        try await awaitState(.playing)
        report["request_to_player_started_ms"] = Date().timeIntervalSince(start) * 1000
        try await awaitState(.ready)
        report["completion"] = "passed"
        controller.toggle(message: "cancel-before-render", spans: spans); controller.stop()
        try await Task.sleep(for: .milliseconds(500))
        XCTAssertEqual(controller.state, .ready); XCTAssertNil(controller.activeMessage)
        report["cancel_before_render"] = "passed"
        controller.toggle(message: "replay", spans: spans)
        try await awaitState(.playing)
        start = Date(); controller.stop()
        report["stop_return_ms"] = Date().timeIntervalSince(start) * 1000
        try await Task.sleep(for: .milliseconds(500))
        XCTAssertEqual(controller.state, .ready)
        report["cancel_during_playback"] = "passed"
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("speech-qa")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: directory.appendingPathComponent("player-001.json"), options: .atomic)
    }

    func testTemporaryDuckingAcrossCompletionStopSwitchAndRendererFailures() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pair = try LocalSpeechPair(source: "en", target: "en", root: directory)
        let renderer = FailingAfterFirstChunk(pair)
        let speaker = SpeechPlayback { _, _, _ in renderer }
        defer { speaker.close(); try? FileManager.default.removeItem(at: directory) }
        func mark(_ phase: String) { print("VIPI_DUCK \(Date().timeIntervalSince1970) \(phase)") }
        func awaitState(_ state: SpeechState) async throws {
            let deadline = Date().addingTimeInterval(12)
            while speaker.state != state {
                guard Date() < deadline else { XCTFail("Speech did not reach the expected state"); throw LocalSpeechError.timedOut }
                try await Task.sleep(for: .milliseconds(20))
            }
        }
        let phrase = [(text: "The train to Cambridge leaves at seven.", language: "en")]
        speaker.prepare(source: "en", target: "en", warmups: ["en": "Ready."])
        try await waitForNativeVoicePreparation(speaker)
        mark("ready")
        speaker.start(message: "finish", spans: phrase)
        try await awaitState(.playing); mark("playing")
        let session = AVAudioSession.sharedInstance()
        XCTAssertEqual(session.category, .playback)
        XCTAssertTrue(session.categoryOptions.contains(.duckOthers))
        XCTAssertFalse(session.categoryOptions.contains(.interruptSpokenAudioAndMixWithOthers))
        try await awaitState(.ready)
        XCTAssertEqual(speaker.lastCompletion?.succeeded, true); mark("finished")
        speaker.start(message: "first", spans: phrase)
        try await awaitState(.playing)
        speaker.start(message: "replacement", spans: phrase)
        try await awaitState(.playing)
        XCTAssertEqual(speaker.activeMessage, "replacement")
        mark("replaced")
        speaker.stop()
        XCTAssertEqual(speaker.state, .ready); mark("stopped")
        for cancellation in [false, true] {
            renderer.failOnNextChunk = false
            renderer.nextError = cancellation ? CancellationError() : LocalSpeechError.invalidAudio
            speaker.start(message: cancellation ? "cancel" : "failure", spans: phrase + phrase, pauseBetweenSpans: true)
            try await awaitState(.playing)
            renderer.failOnNextChunk = true
            try await awaitState(.ready)
            XCTAssertEqual(speaker.lastCompletion?.succeeded, false)
            XCTAssertNil(speaker.activeMessage)
            mark(cancellation ? "cancelled" : "failed")
        }
    }

    @MainActor private final class FailingAfterFirstChunk: PreparedSpeechPair {
        let pair: LocalSpeechPair
        var nextError: Error?
        var failOnNextChunk = false
        private var firstChunk = true
        init(_ pair: LocalSpeechPair) { self.pair = pair }
        func prepare(warmups: [String: String]) async throws { try await pair.prepare(warmups: warmups) }
        func render(_ spans: [(text: String, language: String)]) async throws -> RenderedSpeech {
            if let nextError {
                if firstChunk { firstChunk = false }
                else {
                    while !failOnNextChunk { try await Task.sleep(for: .milliseconds(10)) }
                    self.nextError = nil; firstChunk = true
                    throw nextError
                }
            }
            return try await pair.render(spans)
        }
        func stop() { pair.stop() }
    }

    func testRecordNativeVoicesAndPreparedPair() async throws {
        let fixture = Bundle(for: Self.self).url(forResource: "corpus", withExtension: "json")!
        let corpus = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as! [String: Any]
        let languages = corpus["languages"] as! [String]
        let samples = (corpus["cases"] as! [[String: Any]])[0]["text"] as! [String: String]
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("speech-qa")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var rows: [[String: Any]] = []
        var report: [String: Any] = ["evidence": "simulator_synthesis_not_offline_network_or_listening_acceptance"]
        func save() throws {
            report["languages"] = rows
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: directory.appendingPathComponent("speech-002.json"), options: .atomic)
        }
        for language in languages {
            var row: [String: Any] = ["language": language]
            do {
                let voice = try await LocalVoice(language: language)
                row["voice"] = voice.identifier
                let start = Date()
                let audio = try await voice.render(samples[language]!, to: directory.appendingPathComponent(language + ".caf"))
                row["render_ms"] = Date().timeIntervalSince(start) * 1000
                row["audio_ms"] = audio.milliseconds
                row["sample_rate"] = audio.sampleRate
                row["channels"] = audio.channels
                row["status"] = "synthesized"
                row["word_markers"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(audio.marks))
            } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
            rows.append(row); try save()
        }
        var pairReport: [String: Any] = [:]
        do {
            let pair = try LocalSpeechPair(source: "en", target: "es", root: directory.appendingPathComponent("pair"))
            var start = Date()
            try await pair.prepare(warmups: ["en": "Hello.", "es": "Hola."])
            pairReport["prepare_ms"] = Date().timeIntervalSince(start) * 1000
            let spans = [(text: "Coffee ", language: "en"), (text: "mañana", language: "es"),
                (text: "? I know a little place by the ", language: "en"), (text: "río", language: "es")]
            start = Date()
            let audio = try await pair.render(spans)
            pairReport["first_render_ms"] = Date().timeIntervalSince(start) * 1000
            start = Date()
            let replay = try await pair.render(spans)
            pairReport["cached_render_ms"] = Date().timeIntervalSince(start) * 1000
            pairReport["audio_ms"] = audio.milliseconds
            pairReport["status"] = "single_pcm_file_rendered"
            XCTAssertEqual(audio.file, replay.file)
        } catch { pairReport["status"] = "failed"; pairReport["error"] = String(describing: error) }
        report["en_es_pair"] = pairReport; try save()
        XCTAssertEqual(rows.count, languages.count)
        XCTAssertEqual(rows.filter { $0["status"] as? String == "synthesized" }.count, languages.count)
        XCTAssertEqual(pairReport["status"] as? String, "single_pcm_file_rendered")
    }
}
