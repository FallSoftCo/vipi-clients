import AVFoundation
import CryptoKit
import XCTest
@testable import Vipi

@MainActor final class SpeechPairMatrixTests: XCTestCase {
    func testBundledVoicesRenderCatalogGreetings() async throws {
        let expected = LocalLanguageCatalog.codes.subtracting(["gl", "tl", "ja"])
        XCTAssertEqual(BundledSpeech.availableLanguages, expected)
        XCTAssertNil(BundledSpeech.voice(for: "ja-JP"), "Mixed kanji and kana require a Japanese system voice")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".caf")
        defer { try? FileManager.default.removeItem(at: url) }
        for language in expected.sorted() {
            let voice = try XCTUnwrap(BundledSpeech.voice(for: language), language)
            let text = VipiLanguage.named(language).exampleGreeting
            let output = try await BundledSpeech.shared.render(text, voice: voice, to: url, job: .init())
            let audio = try AVAudioFile(forReading: output.file)
            let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: audio.processingFormat,
                                                         frameCapacity: AVAudioFrameCount(audio.length)))
            try audio.read(into: buffer)
            let channel = try XCTUnwrap(buffer.floatChannelData?[0])
            let samples = UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength))
            XCTAssertTrue(samples.contains { abs($0) > 0.001 }, "Silent bundled voice: " + language)
        }
    }

    /// Same frozen eleven ConversationExamples as Android's first voice audit.
    /// Simulator rendering is not a physical-device acoustic or offline proof.
    func testAuditAdvertisedElevenVoicesWithoutPreparingDownloads() async throws {
        let samples: [(String, String)] = [
            ("en", "Coffee tomorrow? I know a little place by the river."),
            ("es", "¿Tomamos un café mañana? Conozco un pequeño lugar junto al río."),
            ("fr", "Un café demain ? Je connais un petit endroit au bord de la rivière."),
            ("de", "Morgen einen Kaffee? Ich kenne ein kleines Café am Fluss."),
            ("it", "Un caffè domani? Conosco un posticino vicino al fiume."),
            ("pt", "Vamos tomar um café amanhã? Conheço um lugar pequeno perto do rio."),
            ("ja", "明日、コーヒーでもどう？川のそばに小さなお店を知っているよ。"),
            ("ko", "내일 커피 마실래? 강 옆에 작은 카페를 알고 있어."),
            ("zh", "明天一起喝咖啡吗？我知道河边有个小地方。"),
            ("ar", "هل نشرب القهوة غدًا؟ أعرف مكانًا صغيرًا قرب النهر."),
            ("sw", "Kahawa kesho? Ninajua sehemu ndogo karibu na mto."),
        ]
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("speech-availability-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        var rows: [[String: Any]] = []
        func save() throws {
            let receipt: [String: Any] = ["schema": "vipi-apple-voice-availability-1", "network_disabled": false,
                "downloads_requested": false, "physical_device": false,
                "scope": "Actual production voice selection and PCM synthesis in iOS Simulator; not acoustic review or verified offline networking",
                "languages": rows]
            try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
                .write(to: root.appendingPathComponent("receipt.json"), options: .atomic)
        }
        func inspect(_ output: RenderedSpeech) throws -> [String: Any] {
            let file = try AVAudioFile(forReading: output.file)
            guard file.length > 0, file.length < 2_000_000,
                  let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)) else {
                throw LocalSpeechError.invalidAudio
            }
            try file.read(into: buffer)
            guard let pcm = buffer.floatChannelData else { throw LocalSpeechError.invalidAudio }
            var peak: Float = 0
            for channel in 0..<Int(buffer.format.channelCount) {
                for frame in 0..<Int(buffer.frameLength) { peak = max(peak, abs(pcm[channel][frame])) }
            }
            guard peak > 0.001 else { throw LocalSpeechError.invalidAudio }
            let bytes = try Data(contentsOf: output.file)
            return ["file": output.file.lastPathComponent, "bytes": bytes.count,
                "sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
                "sample_rate": file.processingFormat.sampleRate, "channels": file.processingFormat.channelCount,
                "duration_ms": output.milliseconds, "peak": peak, "boundary_frames": output.boundaryFrames]
        }
        for (language, text) in samples {
            let started = Date()
            var row: [String: Any] = ["language": language, "text": text,
                "advertised": AVSpeechSynthesisVoice.speechVoices().filter { $0.language.components(separatedBy: "-")[0] == language }
                    .map { ["identifier": $0.identifier, "language": $0.language, "quality": $0.quality.rawValue] as [String: Any] }]
            do {
                let voice = try await LocalVoice(language: language); defer { voice.stop() }
                row["selected"] = voice.identifier
                let output = try await voice.render(text, to: root.appendingPathComponent(language + ".caf"))
                row["single"] = try inspect(output); row["status"] = "rendered"
                if language != "en" {
                    let pair = try LocalSpeechPair(source: "en", target: language, root: root.appendingPathComponent("pair-" + language))
                    defer { pair.stop() }
                    try await pair.prepare(warmups: ["en": "Hello.", language: text])
                    let mixed = try await pair.render([(text: "Hello.", language: "en"), (text: text, language: language), (text: "See you tomorrow.", language: "en")])
                    row["mixed"] = try inspect(mixed)
                }
            } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
            row["elapsed_ms"] = Date().timeIntervalSince(started) * 1000
            rows.append(row); try save()
        }
        XCTAssertEqual(rows.count, 11)
        XCTAssertEqual(rows.filter { $0["status"] as? String == "rendered" }.count, 11)
    }

    func testPrepareAndRenderAllCommonPracticeDirections() async throws {
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
        XCTAssertEqual(Set(languages), LocalLanguageCatalog.commonPractice)
        XCTAssertEqual(languages.count, LocalLanguageCatalog.commonPractice.count)
        let directionCount = languages.count * (languages.count - 1)
        XCTAssertEqual(rows.count, directionCount)
        XCTAssertEqual(rows.filter { $0["status"] as? String == "rendered" }.count, directionCount)
    }
}
