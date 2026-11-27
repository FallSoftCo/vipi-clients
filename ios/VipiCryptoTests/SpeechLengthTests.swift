import XCTest
@testable import Vipi

@MainActor final class SpeechLengthTests: XCTestCase {
    func testMeasureParagraphBufferingLatency() async throws {
        let fixture =
            try JSONSerialization.jsonObject(
                with: Data(
                    contentsOf: Bundle(for: Self.self).url(forResource: "speech-lengths", withExtension: "json")!))
            as! [String: Any]
        let base = (fixture["spans"] as! [[String: String]]).map { (text: $0["text"]!, language: $0["language"]!) }
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("speech-qa")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let pair = try LocalSpeechPair(source: "en", target: "es", root: directory.appendingPathComponent("lengths"))
        defer { pair.stop() }
        try await pair.prepare(warmups: ["en": "Hello.", "es": "Hola."])
        var rows: [[String: Any]] = []
        for count in [1, 3, 8] {
            let spans = (0..<count).flatMap { _ in base }
            let start = Date()
            let result = try await pair.render(spans)
            rows.append([
                "characters": spans.reduce(0) { $0 + $1.text.utf16.count }, "segments": spans.count,
                "render_ms": Date().timeIntervalSince(start) * 1000, "audio_ms": result.milliseconds
            ])
            try JSONSerialization.data(
                withJSONObject: ["evidence": "prepared_pair_paragraph_render_timing_not_player_latency", "cases": rows],
                options: [.prettyPrinted, .sortedKeys]
            )
            .write(to: directory.appendingPathComponent("lengths-001.json"), options: .atomic)
        }
    }
}
