import AVFAudio
import XCTest
@testable import Vipi

@MainActor final class InlineVoiceNoteTests: XCTestCase {
    private func waitFor(_ condition: () -> Bool) async throws {
        let deadline = ContinuousClock.now + .seconds(5)
        while !condition() {
            if .now >= deadline { throw NSError(domain: "InlineVoiceNoteTests", code: 1) }
            try await Task.sleep(for: .milliseconds(15))
        }
    }

    private func writeClip(at url: URL) throws {
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 8_000, channels: 1))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16_000))
        buffer.frameLength = buffer.frameCapacity
        let samples = try XCTUnwrap(buffer.floatChannelData)[0]
        for index in 0..<Int(buffer.frameLength) {
            samples[index] = Float(0.05 * sin(2 * .pi * 220 * Double(index) / 8_000))
        }
        let clip = try AVAudioFile(forWriting: url, settings: format.settings)
        try clip.write(from: buffer)
    }

    func testBadDecodedFileIsDeletedAndExplicitRetryOpensFreshClip() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let invalid = folder.appendingPathComponent("invalid.m4a")
        let valid = folder.appendingPathComponent("good.caf")
        try Data("Invalid recording".utf8).write(to: invalid)
        try writeClip(at: valid)
        let note = VoiceNotePlayer()
        defer {
            note.clear()
            try? FileManager.default.removeItem(at: folder)
        }
        note.toggle { invalid }
        try await waitFor { note.state == .failed }
        XCTAssertFalse(FileManager.default.fileExists(atPath: invalid.path))
        XCTAssertFalse(VoiceAudioHandoff.owns(note))

        note.toggle { valid }
        try await waitFor { note.state == .playing && note.elapsed > 0.05 }
        XCTAssertEqual(note.duration, 2, accuracy: 0.05)
        note.yieldPlayback()
        XCTAssertTrue(note.state == .paused && note.elapsed > 0)
        XCTAssertFalse(FileManager.default.fileExists(atPath: valid.path))
        XCTAssertFalse(VoiceAudioHandoff.owns(note))
    }

    func testLateFileAfterAnotherOwnerTakesAudioIsDeletedWithoutPlaying() async throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try Data([1]).write(to: temporary)
        let note = VoiceNotePlayer()
        let next = NSObject()
        var loading: CheckedContinuation<URL, Never>?
        defer {
            loading?.resume(returning: temporary)
            note.clear()
            VoiceAudioHandoff.release(next)
            try? FileManager.default.removeItem(at: temporary)
        }
        note.toggle { await withCheckedContinuation { loading = $0 } }
        try await waitFor { loading != nil }
        VoiceAudioHandoff.claim(next) {}
        XCTAssertTrue(note.state == .idle)
        loading?.resume(returning: temporary)
        loading = nil
        try await waitFor { !FileManager.default.fileExists(atPath: temporary.path) }
        XCTAssertTrue(note.state == .idle)
        XCTAssertTrue(VoiceAudioHandoff.owns(next))
    }
}
