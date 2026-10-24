import Foundation
import Translation
import AVFoundation

/// Capability evidence only. No fabricated translations or inferred pair passes.
@main struct LanguageMatrix {
    static func main() async throws {
        let languages = ["en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko"]
        let availability = LanguageAvailability()
        var pairs: [[String: String]] = []
        for source in languages { for target in languages where source != target {
            let status = await availability.status(from: Locale.Language(identifier: source), to: Locale.Language(identifier: target))
            pairs.append(["source": source, "target": target, "availability": String(describing: status), "execution": "not_run"])
        } }
        let voices = AVSpeechSynthesisVoice.speechVoices().filter { voice in
            languages.contains(voice.language.components(separatedBy: "-")[0])
        }.map { ["language": $0.language, "identifier": $0.identifier, "name": $0.name, "quality": String($0.quality.rawValue)] }
        let report: [String: Any] = ["platform": "macOS", "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "evidence": "availability_only_not_iOS_execution", "pairs": pairs, "voices": voices]
        let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        print(String(decoding: data, as: UTF8.self))
    }
}
