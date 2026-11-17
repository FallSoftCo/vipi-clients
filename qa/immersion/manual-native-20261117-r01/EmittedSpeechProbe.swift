import AVFoundation
import Foundation

@main struct EmittedSpeechProbe {
    @MainActor static func main() async throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let inputs = URL(fileURLWithPath: CommandLine.arguments[2])
        let output = root.appendingPathComponent("audio-results-r01.json")
        guard !FileManager.default.fileExists(atPath: output.path) else { fatalError("Inspect completed or partial original run") }
        let document = try JSONSerialization.jsonObject(with: Data(contentsOf: inputs)) as! [String: Any]
        let cases = document["cases"] as! [[String: Any]]
        let ids: Set<String> = ["zh-charger", "zh-tomorrow", "zh-whole", "ja-umbrella", "ja-whole", "ko-music"]
        let selected = cases.filter { ids.contains($0["id"] as? String ?? "") }
        guard selected.count == ids.count else { fatalError("Fixture selection mismatch") }
        var rows: [[String: Any]] = []
        func save(_ complete: Bool) throws {
            try JSONSerialization.data(withJSONObject: ["completed": complete,
                "scope": "Native macOS production LocalVoice file synthesis of exact previously emitted manual targets; no live iOS gesture or listening acceptance", "source_result": inputs.path,
                "romanization_passed_to_synthesis": false, "network_disabled": false,
                "results": rows], options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
        }
        for item in selected {
            let id = item["id"] as! String, language = item["target"] as! String, text = item["manual_target"] as! String
            var row: [String: Any] = ["id": id, "text": text, "language": language, "display_reading": item["reading"] ?? ""]
            let started = Date()
            do {
                let voice = try LocalVoice(language: language)
                defer { voice.stop() }
                row["voice"] = voice.identifier; row["locale"] = voice.voice?.language ?? "sw"
                let audio = try await voice.render(text, to: root.appendingPathComponent(id + ".caf"))
                let file = try AVAudioFile(forReading: audio.file)
                guard file.length > 0, file.length < 10_000_000,
                    let pcm = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)) else { throw LocalSpeechError.invalidAudio }
                try file.read(into: pcm)
                guard let channel = pcm.floatChannelData?[0] else { throw LocalSpeechError.invalidAudio }
                var peak: Float = 0
                for index in 0..<Int(pcm.frameLength) { peak = max(peak, abs(channel[index])) }
                guard peak.isFinite, peak > 0.001 else { throw LocalSpeechError.invalidAudio }
                row["status"] = "rendered"; row["peak"] = peak; row["milliseconds"] = audio.milliseconds
                row["sample_rate"] = audio.sampleRate; row["channels"] = audio.channels
            } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
            row["render_seconds"] = Date().timeIntervalSince(started); rows.append(row); try save(false)
        }
        try save(true)
    }
}
