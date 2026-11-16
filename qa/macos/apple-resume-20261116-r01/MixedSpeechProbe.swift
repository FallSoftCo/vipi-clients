import AVFoundation
import Foundation

@main struct MixedSpeechProbe {
    @MainActor static func main() async throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        let words = ["en":"water", "es":"agua", "fr":"eau", "de":"Wasser", "it":"acqua", "pt":"água", "ar":"ماء", "zh":"水", "ja":"水", "ko":"물", "sw":"maji"]
        var rows: [[String: Any]] = []
        func save() throws {
            let result: [String:Any] = ["platform":"native macOS; not iOS", "network_disabled":false, "listening_review":false, "sample_basis":"authored water words; not emitted immersion spans", "results":rows]
            try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:root.appendingPathComponent("receipt.json"),options:.atomic)
        }
        for source in words.keys.sorted() {
            for target in words.keys.sorted() where source != target {
                var row: [String:Any] = ["source":source,"target":target]
                do {
                    let dir = root.appendingPathComponent("\(source)-\(target)")
                    let pair = try LocalSpeechPair(source:source,target:target,root:dir)
                    defer { pair.stop() }
                    let start = Date()
                    try await pair.prepare(warmups: [source:words[source]!, target:words[target]!])
                    let result = try await pair.render([(words[source]!, source), (words[target]!, target)])
                    let file = try AVAudioFile(forReading:result.file)
                    let buffer = AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:AVAudioFrameCount(file.length))!
                    try file.read(into:buffer)
                    guard let samples = buffer.floatChannelData else { throw LocalSpeechError.invalidAudio }
                    var peak:Float = 0
                    for i in 0..<Int(buffer.frameLength) { peak=max(peak,abs(samples[0][i])) }
                    guard peak.isFinite && peak > 0.001 && result.boundaryFrames.count == 1 else { throw LocalSpeechError.invalidAudio }
                    let player = try AVAudioPlayer(contentsOf:result.file)
                    guard player.play() else { throw LocalSpeechError.unavailable }
                    while player.isPlaying { try await Task.sleep(for:.milliseconds(100)) }
                    row["peak"] = peak; row["milliseconds"] = result.milliseconds
                    row["boundary_frames"] = result.boundaryFrames
                    row["elapsed_seconds"] = Date().timeIntervalSince(start)
                    row["playback_started_and_completed"] = true; row["status"] = "rendered"
                } catch { row["status"] = "failed"; row["error"] = String(describing:error) }
                rows.append(row); try save()
            }
        }
    }
}
