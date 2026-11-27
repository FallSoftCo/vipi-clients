import AVFAudio
import XCTest
@testable import Vipi

@MainActor final class InlineVoiceComposerTests: XCTestCase {
    /// The file enters the regular native encoder/attachment store. No microphone is opened.
    private final class Capture: VoiceCapture {
        var phase = VoiceMessageRecorder.Phase.idle
        let currentTime = 0.9
        let level = 0.2
        var starts = 0
        var clip: URL?

        func begin() async {
            starts += 1
            phase = .recording
        }
        func stop() { phase = .review }
        func take() -> ChosenMedia? {
            guard phase == .review, let clip else { return nil }
            self.clip = nil
            return ChosenMedia(url: clip, kind: .voice)
        }
        func cancel() { phase = .idle }

        func supplyAudio() throws {
            let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
                .appendingPathExtension("m4a")
            let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 24_000, channels: 1))
            let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 24_000))
            buffer.frameLength = 24_000
            let channel = try XCTUnwrap(buffer.floatChannelData?[0])
            for frame in 0..<24_000 { channel[frame] = Float(0.1 * sin(2 * .pi * 440 * Double(frame) / 24_000)) }
            let audio = try AVAudioFile(
                forWriting: file,
                settings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC,
                    AVSampleRateKey: 24_000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 48_000
                ])
            try audio.write(from: buffer)
            clip = file
        }
    }
    private func waitFor(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async throws {
        let deadline = ContinuousClock.now + .seconds(5)
        while !condition(), ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertTrue(condition(), file: file, line: line)
    }

    func testTapCancelReleaseLockAndOfflineRecovery() async throws {
        let account = UUID(), peer = UUID(), user = "user_localmedia_voice_" + UUID().uuidString
        let transport = MediaOutboxTests.Transport(
            ChatProfile(id: account, username: "qa_voice", display_name: "Voice QA"))
        let bytes = try CiphertextTransport(endpoint: XCTUnwrap(URL(string: "http://127.0.0.1:1"))) { _ in
            throw URLError(.notConnectedToInternet)
        }
        let session = try ChatSession(api: transport, userID: user, media: bytes)
        let capture = Capture()
        defer {
            try? session.close()
            if let file = capture.clip { try? FileManager.default.removeItem(at: file) }
            let key = account.uuidString.lowercased()
            for (location, folder) in [
                (FileManager.SearchPathDirectory.applicationSupportDirectory, "Attachments"),
                (.applicationSupportDirectory, "Messages"), (.cachesDirectory, "Attachments")
            ] {
                let root = FileManager.default.urls(for: location, in: .userDomainMask)[0]
                try? FileManager.default.removeItem(at: root.appendingPathComponent(folder).appendingPathComponent(key))
            }
            KeychainStore.delete(account: "messages-" + key)
            KeychainStore.delete(account: "profile-" + user)
        }
        await session.start()
        XCTAssertTrue(session.ready)
        let voice = InlineVoiceComposer(recorder: capture)
        var commits = 0
        voice.bind(session, peer: peer) { commits += 1 }

        voice.begin()
        voice.release(held: 0.08)
        XCTAssertTrue(voice.showHandsFree)
        XCTAssertEqual(capture.starts, 0)
        voice.begin()
        try await waitFor { voice.phase == .holding }
        voice.move(dx: -90, dy: -5)
        voice.release(held: 1)
        XCTAssertFalse(voice.active)
        XCTAssertNil(try session.voiceDraft(peer: peer))
        XCTAssertEqual(transport.capabilityChecks, 0)

        // Releasing the original locked finger cannot send. A separate direct
        // Send consumes the clip once even if equivalent actions arrive twice.
        try capture.supplyAudio()
        voice.begin()
        try await waitFor { voice.phase == .holding }
        voice.move(dx: 0, dy: -80)
        voice.release(held: 1.2)
        XCTAssertEqual(voice.phase, .locked)
        XCTAssertTrue(try session.messages(peer).isEmpty)
        voice.finish(send: true)
        voice.finish(send: true)
        try await waitFor { commits == 1 }
        XCTAssertEqual(try session.messages(peer).count, 1)
        XCTAssertNil(try session.voiceDraft(peer: peer))

        // Offline capability lookup runs only after local capture finishes.
        transport.capabilityOffline = true
        let before = transport.capabilityChecks
        try capture.supplyAudio()
        voice.begin()
        try await waitFor { voice.phase == .holding }
        XCTAssertEqual(transport.capabilityChecks, before)
        voice.release(held: 1.3)
        try await waitFor { voice.phase == .preview && voice.notice != nil }
        let draft = try XCTUnwrap(session.voiceDraft(peer: peer))
        XCTAssertEqual(commits, 1)
        let reopened = InlineVoiceComposer(recorder: Capture())
        reopened.bind(session, peer: peer) { commits += 1 }
        XCTAssertEqual(reopened.draft?.id, draft.id)
        transport.capabilityOffline = false
        reopened.submit()
        reopened.submit()
        try await waitFor { commits == 2 }
        XCTAssertEqual(try session.messages(peer).count, 2)

        try capture.supplyAudio()
        let handsFree = InlineVoiceComposer(recorder: capture)
        handsFree.bind(session, peer: peer) { commits += 1 }
        handsFree.begin(lock: true)
        try await waitFor { handsFree.phase == .locked }
        handsFree.interruption()
        try await waitFor { handsFree.phase == .preview }
        XCTAssertNotNil(try session.voiceDraft(peer: peer))
        handsFree.discard()
        XCTAssertNil(try session.voiceDraft(peer: peer))
        XCTAssertEqual(commits, 2)
    }
}
