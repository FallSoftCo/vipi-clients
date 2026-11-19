import XCTest
import VipiCore
@testable import Vipi

/// Exercises production orchestration at the native SDK request boundary.
/// Supplied SDK responses do not qualify Apple/ML Kit execution or language quality.
@MainActor final class ConversationImmersionTests: XCTestCase {
    private func next(_ owner: ConversationImmersion, file: StaticString = #filePath, line: UInt = #line) async throws -> ConversationImmersion.Request {
        let deadline = ContinuousClock.now.advanced(by:.seconds(2))
        while owner.request == nil && ContinuousClock.now < deadline { await Task.yield() }
        return try XCTUnwrap(owner.request,"Expected actual native SDK request",file:file,line:line)
    }
    func testEveryMessageRequestsFullTranslationIncludingShortAndFormerReferenceHits() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es"))
        defer { owner.close() }
        for (index,text) in ["yes","OK","Coffee tomorrow?","A completely new sentence about the purple umbrella."].enumerated() {
            let id = "message-\(index)", identity = owner.identity(messageID:"message-\(index)",text:text)
            let task = Task { await owner.translatedMessage(for:identity) }
            let request = try await next(owner)
            XCTAssertEqual(request.text,text); XCTAssertEqual(request.pair,.init(source:"en",target:"es"))
            let supplied = "Respuesta completa \(index)."
            await owner.finish(request,translation:supplied)
            let received = await task.value
            let result = try XCTUnwrap(received)
            XCTAssertEqual(result.original,text); XCTAssertEqual(result.practiceText,supplied); XCTAssertEqual(result.meaningText,text)
            XCTAssertEqual(result.practiceLanguage,"es"); XCTAssertEqual(result.meaningLanguage,"en")
            XCTAssertEqual(owner.lastOutcome?.localTranslationCalls,1)
            XCTAssertTrue(result.presentation.spans.isEmpty,"No invented word correspondence")
            let cached = await owner.translatedMessage(for:owner.identity(messageID:id,text:text))
            XCTAssertEqual(cached,result); XCTAssertNil(owner.request); XCTAssertTrue(owner.lastOutcome?.cacheHit == true)
        }
    }
    func testDistinctIdenticalMessagesTranslateSeparatelyAndConcurrentSameMessageCoalesces() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es")); defer { owner.close() }
        let first = owner.identity(messageID:"first",text:"OK")
        let a = Task { await owner.translatedMessage(for:first) }, b = Task { await owner.translatedMessage(for:first) }
        let request = try await next(owner); await owner.finish(request,translation:"Vale")
        let firstValue = await a.value, secondValue = await b.value
        XCTAssertEqual(firstValue,secondValue); XCTAssertNil(owner.request)
        let second = owner.identity(messageID:"second",text:"OK")
        let c = Task { await owner.translatedMessage(for:second) }
        let nextRequest = try await next(owner); XCTAssertNotEqual(nextRequest.id,request.id)
        await owner.finish(nextRequest,translation:"De acuerdo")
        let other = await c.value; XCTAssertEqual(other?.practiceText,"De acuerdo")
    }
    func testPracticeInputRemainsExactPracticeAndGetsNativeMeaning() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "ja"})
        await owner.configure(pair:.init(source:"en",target:"ja")); defer { owner.close() }
        let original = "はい", identity = owner.identity(messageID:"incoming",text:"はい")
        let task = Task { await owner.translatedMessage(for:identity) }
        let request = try await next(owner)
        XCTAssertEqual(request.pair,.init(source:"ja",target:"en")); await owner.finish(request,translation:"Yes")
        let returned = await task.value
        let value = try XCTUnwrap(returned)
        XCTAssertEqual(value.original,original); XCTAssertEqual(value.practiceText,original); XCTAssertEqual(value.meaningText,"Yes")
        XCTAssertEqual(value.inputLanguage,"ja"); XCTAssertEqual(value.meaningLanguage,"en")
    }
    func testThirdLanguageGetsBothPracticeAndConfiguredNativeMeaning() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "es"})
        await owner.configure(pair:.init(source:"en",target:"ja")); defer { owner.close() }
        let original = "¿Dónde está la estación?", identity = owner.identity(messageID:"received",text:"¿Dónde está la estación?")
        let task = Task { await owner.translatedMessage(for:identity) }
        let practice = try await next(owner); XCTAssertEqual(practice.pair,.init(source:"es",target:"ja"))
        await owner.finish(practice,translation:"駅はどこですか？")
        let meaning = try await next(owner); XCTAssertEqual(meaning.pair,.init(source:"es",target:"en")); XCTAssertEqual(meaning.text,original)
        XCTAssertNil(owner.translation(for:identity),"Incomplete native meaning is not a completed cache entry")
        await owner.finish(meaning,translation:"Where is the station?")
        let returned = await task.value
        let value = try XCTUnwrap(returned)
        XCTAssertEqual(value.original,original); XCTAssertEqual(value.practiceText,"駅はどこですか？")
        XCTAssertEqual(value.meaningText,"Where is the station?"); XCTAssertEqual(value.meaningLanguage,"en")
        XCTAssertEqual(owner.lastOutcome?.localTranslationCalls,2)
    }
    func testMissingModelsAndFailedProviderRemainExplicitAndRetryable() async throws {
        var installed = false
        let owner = ConversationImmersion(modelStatus:{_ in installed ? .installed : .downloadable},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es")); defer { owner.close() }
        let identity = owner.identity(messageID:"sent",text:"A new message")
        let missing = await owner.translatedMessage(for:identity); XCTAssertNil(missing); XCTAssertEqual(owner.phase(for:identity),.needsDownload); XCTAssertNil(owner.cached(identity.text,messageID:identity.messageID))
        installed = true; owner.retry(identity)
        let first = Task { await owner.translatedMessage(for:identity) }
        await owner.finish(try await next(owner),translation:nil)
        let failure = await first.value; XCTAssertNil(failure); XCTAssertEqual(owner.phase(for:identity),.failed); XCTAssertNil(owner.cached(identity.text,messageID:identity.messageID))
        owner.retry(identity)
        let retry = Task { await owner.translatedMessage(for:identity) }
        await owner.finish(try await next(owner),translation:"Un mensaje nuevo")
        let retried = await retry.value; XCTAssertEqual(retried?.practiceText,"Un mensaje nuevo"); XCTAssertEqual(owner.phase(for:identity),.ready)
    }
    func testCloseCancelsPendingAndLateResultCannotPublishOrPlay() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es"))
        let identity = owner.identity(messageID:"late",text:"Please translate this")
        let task = Task { await owner.translatedMessage(for:identity) }
        let request = try await next(owner); owner.close()
        await owner.finish(request,translation:"Una respuesta tardía")
        let cancelled = await task.value; XCTAssertNil(cancelled); XCTAssertNil(owner.translation(for:identity)); XCTAssertNil(owner.request)
        XCTAssertNil(owner.cached(identity.text,messageID:identity.messageID))
    }
    func testUnchangedModelOutputIsRetainedAfterRealRequestRatherThanHeuristicallyRejected() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es")); defer { owner.close() }
        let original = "Ada 42 🙂", identity = owner.identity(messageID:"literal",text:"Ada 42 🙂")
        let task = Task { await owner.translatedMessage(for:identity) }
        let request = try await next(owner); await owner.finish(request,translation:original)
        let unchanged = await task.value; XCTAssertEqual(unchanged?.practiceText,original); XCTAssertEqual(owner.lastOutcome?.localTranslationCalls,1)
    }
    func testForegroundAndHistoryWaitersDoNotSilentlyRetryFailedMessage() async throws {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await owner.configure(pair:.init(source:"en",target:"es")); defer { owner.close() }
        let identity = owner.identity(messageID:"retry-required",text:"Keep this failure actionable.")
        let task = Task { await owner.translatedMessage(for:identity) }
        await owner.finish(try await next(owner),translation:nil)
        let failed = await task.value; XCTAssertNil(failed)
        XCTAssertEqual(owner.phase(for:identity),.failed)
        let foreground = await owner.translatedMessage(for:identity)
        await owner.prepareStoredMessage(id:identity.messageID,text:identity.text)
        XCTAssertNil(foreground); XCTAssertNil(owner.request)
        XCTAssertEqual(owner.phase(for:identity),.failed)
        owner.retry(identity)
        let retry = Task { await owner.translatedMessage(for:identity) }
        await owner.finish(try await next(owner),translation:"Mantén este error recuperable.")
        let received = await retry.value; XCTAssertNotNil(received)
        XCTAssertEqual(owner.phase(for:identity),.ready)
    }

}
