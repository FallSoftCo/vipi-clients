import AVFoundation
import Foundation
import XCTest
@testable import Vipi

final class SwahiliSpeechTests: XCTestCase {
    @MainActor func testLocalSwahiliAndEnglishJoinIntoOnePCMFile() async throws {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let output = root.appendingPathComponent("swahili-speech-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        let begin = ContinuousClock.now
        let pair = try LocalSpeechPair(source: "en", target: "sw", root: root.appendingPathComponent("swahili-speech-001"))
        try await pair.prepare(warmups: ["en": "Hello", "sw": "Habari"])
        let prepared = begin.duration(to: .now).components
        let renderStart = ContinuousClock.now
        let rendered = try await pair.render([(text: "I am drinking ", language: "en"),
            (text: "maji", language: "sw"), (text: " now.", language: "en")])
        let duration = renderStart.duration(to: .now).components
        XCTAssertGreaterThan(rendered.milliseconds, 500)
        XCTAssertEqual(rendered.sampleRate, 24_000)
        XCTAssertEqual(rendered.channels, 1)
        let voice = try LocalVoice(language: "sw")
        let swahili = try await voice.render("Habari! Ninakunywa maji sasa. Tutakutana kesho.",
            to: root.appendingPathComponent("swahili-speech-001.caf"))
        XCTAssertGreaterThan(swahili.milliseconds, 500)
        try JSONSerialization.data(withJSONObject: ["schema": "vipi-swahili-speech-1", "voice": voice.identifier,
            "prepare_ms": Double(prepared.seconds)*1000 + Double(prepared.attoseconds)/1e15,
            "render_ms": Double(duration.seconds)*1000 + Double(duration.attoseconds)/1e15,
            "mixed_file": rendered.file.lastPathComponent, "mixed_duration_ms": rendered.milliseconds,
            "swahili_duration_ms": swahili.milliseconds, "sample_rate": rendered.sampleRate,
            "channels": rendered.channels, "listening_acceptance": false], options: [.prettyPrinted, .sortedKeys])
            .write(to: output, options: .withoutOverwriting)
    }
}
