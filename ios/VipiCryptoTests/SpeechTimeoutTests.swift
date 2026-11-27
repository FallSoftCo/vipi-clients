import XCTest
@testable import Vipi

@MainActor final class SpeechTimeoutTests: XCTestCase {
    func testNativeTimeoutAndCancellationRemainDistinctAndVoiceCanRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("vipi-timeout-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let voice = try await LocalVoice(language: "en")
        defer { voice.stop() }
        voice.qualificationStallTimeout = .milliseconds(40)
        let start = ProcessInfo.processInfo.systemUptime
        do {
            _ = try await voice.render("Hello.", to: root.appendingPathComponent("timeout.caf"))
            XCTFail("Stalled native callback must time out")
        } catch LocalSpeechError.timedOut { XCTAssertFalse(Task.isCancelled) } catch {
            XCTFail("Deadline must not masquerade as cancellation: \(error)")
        }
        XCTAssertLessThan(ProcessInfo.processInfo.systemUptime - start, 2)
        voice.qualificationStallTimeout = .seconds(2)
        let cancelled = Task { try await voice.render("Hello.", to: root.appendingPathComponent("cancelled.caf")) }
        await Task.yield()
        cancelled.cancel()
        do {
            _ = try await cancelled.value
            XCTFail("Cancelled task must not finish")
        } catch is CancellationError {} catch { XCTFail("Cancellation must remain cancellation: \(error)") }
        voice.qualificationStallTimeout = nil
        let audio = try await voice.render("Hello.", to: root.appendingPathComponent("retry.caf"))
        XCTAssertGreaterThan(audio.milliseconds, 0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: audio.file.path))
    }
    private func wait(_ state: SpeechState, on controller: SpeechPlayback) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + 2
        while controller.state != state {
            guard ProcessInfo.processInfo.systemUptime < deadline else {
                XCTFail("Preparation stuck at \(controller.state)")
                throw LocalSpeechError.unavailable
            }
            try await Task.sleep(for: .milliseconds(10))
        }
        await Task.yield()
    }
    func testPreparationTimeoutLeavesPreparingAndRetrySucceeds() async throws {
        let controller = SpeechPlayback()
        defer { controller.close() }
        controller.qualificationPrepare = { throw LocalSpeechError.timedOut }
        controller.prepare(source: "en", target: "es", warmups: [:])
        try await wait(.unavailable, on: controller)
        XCTAssertEqual(controller.error, "Voices couldn’t get ready. Try again.")
        controller.qualificationPrepare = {}
        controller.prepare(source: "en", target: "es", warmups: [:])
        try await wait(.ready, on: controller)
        XCTAssertNil(controller.error)
    }
    func testUnexpectedCancellationFailsButClosedPreparationCannotReturnReady() async throws {
        let controller = SpeechPlayback()
        controller.qualificationPrepare = { throw CancellationError() }
        controller.prepare(source: "en", target: "es", warmups: [:])
        try await wait(.unavailable, on: controller)
        XCTAssertNotNil(controller.error)
        var continuation: CheckedContinuation<Void, Never>?
        controller.qualificationPrepare = { await withCheckedContinuation { continuation = $0 } }
        controller.prepare(source: "en", target: "es", warmups: [:])
        while continuation == nil { await Task.yield() }
        controller.close()
        continuation?.resume()
        try await Task.sleep(for: .milliseconds(20))
        XCTAssertNil(controller.error)
        XCTAssertNotEqual(controller.state, .ready)
    }
}
