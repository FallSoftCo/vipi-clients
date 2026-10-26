import XCTest
@testable import Vipi

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
        try await awaitState(.ready)
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
        try await awaitState(.ready)
        let spans = ImmersionPreview.result.speech(source: "en", target: "es").map { (text: $0.text, language: $0.language) }
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
                let voice = try LocalVoice(language: language)
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
        XCTAssertEqual(rows.count, 10)
    }
}
