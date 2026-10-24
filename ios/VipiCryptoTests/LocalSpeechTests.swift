import XCTest
@testable import Vipi

@MainActor final class LocalSpeechTests: XCTestCase {
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
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: directory.appendingPathComponent("speech-001.json"), options: .atomic)
        }
        for language in languages {
            var row: [String: Any] = ["language": language]
            do {
                let voice = try LocalVoice(language: language)
                row["voice"] = voice.voice.identifier
                let start = Date()
                let audio = try await voice.render(samples[language]!, to: directory.appendingPathComponent(language + ".caf"))
                row["render_ms"] = Date().timeIntervalSince(start) * 1000
                row["audio_ms"] = audio.milliseconds
                row["sample_rate"] = audio.sampleRate
                row["channels"] = audio.channels
                row["status"] = "synthesized"
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
