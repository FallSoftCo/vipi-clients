import XCTest
import VipiCore
@testable import Vipi

@MainActor final class ManualTranslationTests: XCTestCase {
    private func pending(_ owner:ConversationImmersion) async throws -> ConversationImmersion.Request {
        for _ in 0..<200 {if let value=owner.request{return value};try await Task.sleep(for:.milliseconds(10))}
        throw NSError(domain:"ManualTranslationTests",code:1)
    }
    func testArbitrarySelectionDoesNotRequireImmersionAndGetsLivePinyin() async throws {
        let owner=ConversationImmersion(modelStatus:{_ in .installed},sourceUnits:nil)
        await owner.configure(pair:.init(source:"en",target:"zh"),density:0)
        defer{owner.close()}
        let request=owner.makeManualRequest(messageID:"message",originalText:"The marmot hums.",startUTF16:4,endUTF16:10,generation:1)
        let task=Task{await owner.manualTranslation(request)}
        let provider=try await pending(owner)
        XCTAssertEqual(provider.text,"The marmot hums.")
        await owner.finish(provider,translation:"音乐")
        let outcome=await task.value
        XCTAssertEqual(outcome.status,.ready)
        XCTAssertEqual(outcome.result?.originalSlice,"marmot")
        XCTAssertEqual(outcome.result?.sourceContextText,"The marmot hums.")
        XCTAssertEqual(outcome.result?.contextExpanded,true)
        XCTAssertEqual(outcome.result?.sourceContextStartUTF16,0)
        XCTAssertEqual(outcome.result?.sourceContextEndUTF16,16)
        XCTAssertEqual(outcome.result?.targetText,"音乐")
        XCTAssertEqual(outcome.result?.reading?.text,"yīnyuè")
        XCTAssertEqual(outcome.result?.targetLanguage,"zh")
        XCTAssertEqual(outcome.result?.request,request)
        XCTAssertNil(owner.lastOutcome)
        XCTAssertEqual(owner.lexicalPreparation,"unmeasured")
        let warm=await owner.manualTranslation(owner.makeManualRequest(messageID:"message",originalText:"The marmot hums.",startUTF16:4,endUTF16:10,generation:2))
        XCTAssertEqual(warm.status,.ready);XCTAssertNil(owner.request)
        owner.selectInputLanguage("en",for:"message")
        let stale=await owner.manualTranslation(request)
        XCTAssertEqual(stale.status,.stale)
    }
    func testSupersedingSelectionCannotPublishOldCompletion() async throws {
        var readinessCalls=0
        let owner=ConversationImmersion(modelStatus:{_ in readinessCalls+=1;return .installed},sourceUnits:nil)
        await owner.configure(pair:.init(source:"en",target:"zh"),density:0)
        defer{owner.close()}
        let first=Task{await owner.manualTranslation(owner.makeManualRequest(messageID:"message",originalText:"first",startUTF16:0,endUTF16:5,generation:1))}
        let active=try await pending(owner)
        let second=Task{await owner.manualTranslation(owner.makeManualRequest(messageID:"message",originalText:"second",startUTF16:0,endUTF16:6,generation:2))}
        for _ in 0..<200 {if readinessCalls>=2{break};try await Task.sleep(for:.milliseconds(1))}
        XCTAssertEqual(readinessCalls,2)
        await owner.finish(active,translation:"音乐")
        let firstValue=await first.value
        XCTAssertEqual(firstValue.status,.stale)
        let next=try await pending(owner)
        XCTAssertEqual(next.text,"second")
        await owner.finish(next,translation:"银行")
        let secondValue=await second.value
        XCTAssertEqual(secondValue.status,.ready)
        XCTAssertEqual(secondValue.result?.reading?.text,"yínháng")
    }
}
