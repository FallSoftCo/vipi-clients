import XCTest
@testable import Vipi

@MainActor final class LanguagePreparationTests: XCTestCase {
    private let spanish = TranslationPair(source: "en", target: "es")
    private let japanese = TranslationPair(source: "en", target: "ja")
    func testOnlyActualInstalledStatusReportsReadiness() async throws {
        let model = LanguagePreparation { _ in .downloadable }
        await model.refresh(spanish); model.prepare()
        let request = try XCTUnwrap(model.request)
        XCTAssertTrue(model.busy)
        model.finish(request, availability: .downloadable, message: "Still downloading")
        XCTAssertEqual(model.availability, .downloadable); XCTAssertFalse(model.busy)
        model.prepare()
        let retry = try XCTUnwrap(model.request)
        XCTAssertNotEqual(retry.id, request.id)
        model.finish(retry, availability: .installed)
        XCTAssertEqual(model.availability, .installed); XCTAssertNil(model.message)
        model.prepare(); XCTAssertFalse(model.busy)
    }
    func testOldDownloadCannotFinishAfterChangingAwayAndBack() async throws {
        let model = LanguagePreparation { _ in .downloadable }
        await model.refresh(spanish); model.prepare()
        let old = try XCTUnwrap(model.request)
        model.invalidate(); await model.refresh(japanese); await model.refresh(spanish); model.prepare()
        let current = try XCTUnwrap(model.request)
        model.finish(old, availability: .installed)
        XCTAssertTrue(model.busy); XCTAssertEqual(model.request?.id, current.id)
        XCTAssertEqual(model.availability, .downloadable)
        model.finish(current, availability: .installed); XCTAssertFalse(model.busy)
    }
    func testInvalidAndEqualLanguagesNeverStartAProviderOperation() async {
        var calls = 0
        let model = LanguagePreparation { _ in calls += 1; return .downloadable }
        for pair in [TranslationPair(source: "en", target: "en"), TranslationPair(source: "xx", target: "es")] {
            await model.refresh(pair); model.prepare()
            XCTAssertEqual(model.availability, .unsupported); XCTAssertFalse(model.busy); XCTAssertNil(model.request)
        }
        XCTAssertEqual(calls, 0)
    }
    func testLeavingInvalidatesAnOutstandingAvailabilityCheck() async throws {
        var continuation: CheckedContinuation<LocalLanguageAvailability, Never>?
        let model = LanguagePreparation { _ in await withCheckedContinuation { continuation = $0 } }
        let check = Task { await model.refresh(spanish) }
        let deadline = Date().addingTimeInterval(5)
        while continuation == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(continuation)
        model.invalidate(); completion.resume(returning: .installed); await check.value
        XCTAssertEqual(model.availability, .checking); XCTAssertNil(model.request)
    }
    func testOlderAvailabilityCannotOverwriteNewSelection() async throws {
        var pending: CheckedContinuation<LocalLanguageAvailability, Never>?
        let model = LanguagePreparation { pair in
            if pair.target == "es" { return await withCheckedContinuation { pending = $0 } }
            return .unsupported
        }
        let first = Task { await model.refresh(spanish) }
        let deadline = Date().addingTimeInterval(5)
        while pending == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(pending)
        await model.refresh(japanese)
        completion.resume(returning: .installed); await first.value
        XCTAssertEqual(model.pair, japanese); XCTAssertEqual(model.availability, .unsupported)
    }
}
