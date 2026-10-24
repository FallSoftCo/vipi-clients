import AVFoundation
import XCTest
@testable import Vipi

@MainActor final class SpeechPairMatrixTests: XCTestCase {
    func testPrepareAndRenderAllNinetyDirections() async throws {
        let fixtureURL = Bundle(for: Self.self).url(forResource: "speech", withExtension: "json")!
        let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as! [String: Any]
        let languages = fixture["languages"] as! [String]
        let warmups = fixture["warmup"] as! [String: String]
        let coffee = fixture["coffee"] as! [String: String]
        let tomorrow = fixture["tomorrow"] as! [String: String]
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("speech-matrix-001")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var rows: [[String: Any]] = []
        func save() throws {
            try JSONSerialization.data(withJSONObject: ["evidence": "simulator_pair_rendering_not_offline_network_linguistic_or_listening_acceptance", "directions": rows], options: [.prettyPrinted, .sortedKeys])
                .write(to: directory.appendingPathComponent("report.json"), options: .atomic)
        }
        for source in languages { for target in languages where source != target {
            var row: [String: Any] = ["source": source, "target": target]
            do {
                let pair = try LocalSpeechPair(source: source, target: target, root: directory.appendingPathComponent("cache"))
                defer { pair.stop() }
                var start = Date()
                try await pair.prepare(warmups: warmups)
                row["prepare_ms"] = Date().timeIntervalSince(start) * 1000
                let spans = [(text: coffee[source]!, language: source), (text: tomorrow[target]!, language: target),
                    (text: tomorrow[source]!, language: source), (text: coffee[target]!, language: target)]
                start = Date()
                let rendered = try await pair.render(spans)
                row["render_ms"] = Date().timeIntervalSince(start) * 1000
                row["audio_ms"] = rendered.milliseconds
                row["boundary_frames"] = rendered.boundaryFrames
                let output = directory.appendingPathComponent("\(source)-\(target).caf")
                try? FileManager.default.removeItem(at: output)
                try FileManager.default.copyItem(at: rendered.file, to: output)
                let file = try AVAudioFile(forReading: rendered.file)
                let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))!
                try file.read(into: buffer)
                guard let pcm = buffer.floatChannelData, file.processingFormat.channelCount == 1 else { throw LocalSpeechError.invalidAudio }
                row["join_silence_ms_at_minus60db"] = rendered.boundaryFrames.map { boundary -> Double in
                    var left = boundary; var right = boundary
                    while left > 0 && abs(pcm[0][left - 1]) <= 0.001 { left -= 1 }
                    while right < Int(buffer.frameLength) && abs(pcm[0][right]) <= 0.001 { right += 1 }
                    return Double(right - left) * 1000 / buffer.format.sampleRate
                }
                start = Date(); _ = try await pair.render(spans)
                row["replay_ms"] = Date().timeIntervalSince(start) * 1000
                row["status"] = "rendered"
            } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
            rows.append(row); try save()
        } }
        XCTAssertEqual(rows.count, 90)
        XCTAssertEqual(rows.filter { $0["status"] as? String == "rendered" }.count, 90)
    }
}
