import Foundation
import XCTest
import VipiCore
@testable import Vipi

/// Controlled translation responses exercise growth and encrypted persistence.
/// These tests do not approve any language, pronunciation or transliteration.
@MainActor final class IncrementalConversationTests: XCTestCase {
    private func store() throws -> MessageVault {
        let account = UUID(), root = FileManager.default.temporaryDirectory.appendingPathComponent("incremental-"+UUID().uuidString)
        let value = try MessageVault(account:account,directory:root)
        addTeardownBlock {
            try? value.close(); try? FileManager.default.removeItem(at:root)
            KeychainStore.delete(account:"messages-"+account.uuidString.lowercased())
        }
        return value
    }
    private func owner(_ vault:MessageVault,target:String = "es",translate:@escaping(String,TranslationPair) async throws -> String) async -> ConversationImmersion {
        let value = ConversationImmersion(modelStatus:{_ in .installed},memoryCacheLimit:2,identify:{_ in nil},nativeTranslation:translate)
        await value.configure(pair:.init(source:"en",target:target)); value.attachCache(vault)
        return value
    }
    private func message(_ owner:ConversationImmersion,_ id:String,_ text:String) async throws -> FullMessageTranslation {
        let result = await owner.translatedMessage(for:owner.identity(messageID:id,text:text))
        return try XCTUnwrap(result)
    }
    func testEachMessageAddsOneNewWordAndRepeatsOldWordsWithoutRewritingSource() async throws {
        let vault = try store(); var calls: [String] = []
        let value = await owner(vault) { text,_ in calls.append(text); return ["water":"agua","bread":"pan"][text] ?? "mapped" }
        defer { value.close() }
        let first = try await message(value,"one","water, water!")
        XCTAssertEqual(first.original,"water, water!"); XCTAssertEqual(first.practiceText,"agua, agua!")
        XCTAssertEqual(calls,["water"])
        let second = try await message(value,"two","water and bread")
        XCTAssertEqual(second.practiceText,"agua and pan"); XCTAssertEqual(calls,["water","bread"])
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},2)
        XCTAssertEqual(second.practiceSpeech.map(\.text),["agua","pan"])
        XCTAssertTrue(second.practiceSpeech.allSatisfy{$0.language == "es"})
    }
    func testConcurrentMessagesAndDuplicateWaitersDoNotIntroduceSameWordTwice() async throws {
        let vault = try store(); var calls: [String] = []
        let value = await owner(vault) { text,_ in calls.append(text); await Task.yield(); return "translated "+text }
        defer { value.close() }
        let a = Task { try await self.message(value,"one","water bread") }
        let duplicate = Task { try await self.message(value,"one","water bread") }
        let b = Task { try await self.message(value,"two","water bread") }
        let first = try await a.value, same = try await duplicate.value, second = try await b.value
        XCTAssertEqual(first,same); XCTAssertEqual(calls.count,2); XCTAssertEqual(Set(calls),Set(["water","bread"]))
        XCTAssertEqual(first.words?.count,1); XCTAssertEqual(second.words?.count,2)
    }
    func testReopenAndEvictionKeepMessagePlanAndGrowthHasNoHundredWordLimit() async throws {
        let vault = try store(); var calls = 0
        let value = await owner(vault) { text,_ in calls += 1; return "translated "+text }
        for index in 0..<105 {
            let suffix = String(UnicodeScalar(97+index/26)!)+String(UnicodeScalar(97+index%26)!)
            _ = try await message(value,"m\(index)","vocabulary"+suffix)
        }
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},105)
        XCTAssertEqual(calls,105); value.close()
        let reopened = await owner(vault) { _,_ in XCTFail("Completed plans must not call the model after reopening"); return "unexpected" }
        defer { reopened.close() }
        let restored = try await message(reopened,"m0","vocabularyaa")
        XCTAssertEqual(restored.words?.count,1)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},105)
    }
    func testFailedTranslationDoesNotLearnAndExplicitRetryCommitsOnlyOnce() async throws {
        let vault = try store(); var calls = 0
        let value = await owner(vault) { _,_ in calls += 1; if calls == 1 { throw ConversationImmersion.ProviderError.unavailable }; return "agua" }
        defer { value.close() }
        let identity = value.identity(messageID:"retry",text:"water")
        let failure = await value.translatedMessage(for:identity)
        XCTAssertNil(failure); XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},0)
        value.retry(identity)
        let success = await value.translatedMessage(for:identity)
        XCTAssertEqual(success?.practiceText,"agua")
        _ = await value.translatedMessage(for:identity)
        XCTAssertEqual(calls,2); XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
    }
    func testNoWordMessagesDoNotInventProgressAndLiteralsRemainExact() async throws {
        let vault = try store(); var calls = 0
        let value = await owner(vault) { _,_ in calls += 1; return "agua" }
        defer { value.close() }
        let text = "👋 123 @friend `water` https://example.com/water"
        let result = try await message(value,"literal",text)
        XCTAssertEqual(result.practiceText,text); XCTAssertEqual(result.words,[])
        XCTAssertEqual(calls,0); XCTAssertTrue(result.practiceSpeech.isEmpty)
    }
    func testLanguagePairsAndAccountsHaveSeparateVocabulary() async throws {
        let one = try store(), two = try store(); var calls = 0
        for (vault,target) in [(one,"es"),(one,"fr"),(two,"es")] {
            let value = await owner(vault,target:target) { _,pair in calls += 1; return pair.target == "es" ? "agua" : "eau" }
            _ = try await message(value,"same","water"); value.close()
        }
        XCTAssertEqual(calls,3)
        XCTAssertEqual(try one.transaction{try one.ids("introduced-word").count},2)
        XCTAssertEqual(try two.transaction{try two.ids("introduced-word").count},1)
        let bytes = try Data(contentsOf:one.url)
        XCTAssertNil(bytes.range(of:Data("water".utf8)))
    }
    func testClosingOwnerWhileTranslationRunsCannotCommitProgress() async throws {
        let vault = try store()
        var continuation: CheckedContinuation<String,Never>?
        let value = await owner(vault) { _,_ in await withCheckedContinuation { continuation = $0 } }
        let task = Task { await value.translatedMessage(for:value.identity(messageID:"late",text:"water")) }
        while continuation == nil { await Task.yield() }
        value.close(); continuation?.resume(returning:"agua")
        let result = await task.value
        XCTAssertNil(result); XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},0)
    }
    func testUnchangedEquivalentDoesNotPreventAnotherWordBeingIntroduced() async throws {
        let vault = try store(); var calls: [String] = []
        let value = await owner(vault) { text,_ in calls.append(text); return text == "taxi" ? "taxi" : "pan" }
        defer { value.close() }
        let result = try await message(value,"loanword","taxi bread")
        XCTAssertEqual(calls,["taxi","bread"]); XCTAssertEqual(result.practiceText,"taxi pan")
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
    }
    func testWordsAlreadyIntroducedKeepRepeatingWithoutNewModelCalls() async throws {
        let vault = try store(); var calls = 0
        let value = await owner(vault) { _,_ in calls += 1; return "agua" }
        defer { value.close() }
        _ = try await message(value,"first","water")
        let second = try await message(value,"second","water!")
        XCTAssertEqual(second.practiceText,"agua!"); XCTAssertEqual(calls,1)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
    }
    func testClearingDerivativeCacheKeepsExactOriginalPlanAfterLaterLearning() async throws {
        let vault = try store()
        let first = await owner(vault) { text,_ in text == "water" ? "agua" : "pan" }
        let original = try await message(first,"one","water bread")
        XCTAssertEqual(original.words?.count,1)
        _ = try await message(first,"two","water bread")
        first.close()
        try vault.transaction {
            for id in try vault.ids("full-message-translation") { try vault.remove("full-message-translation",id) }
        }
        let reopened = await owner(vault) { _,_ in XCTFail("Cache loss must not introduce another word"); return "unexpected" }
        defer { reopened.close() }
        let restored = try await message(reopened,"one","water bread")
        XCTAssertEqual(restored,original)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},2)
        XCTAssertEqual(try vault.transaction{try vault.ids("message-word-plan").count},2)
    }
    func testCorruptPlanDoesNotFallBackToSelectingAnotherWordEvenWithValidCache() async throws {
        let vault = try store()
        let first = await owner(vault) { _,_ in "agua" }
        _ = try await message(first,"one","water bread"); first.close()
        try vault.transaction {
            for id in try vault.ids("message-word-plan") { try vault.put("message-word-plan",id,Data("broken".utf8)) }
        }
        var calls = 0
        let reopened = await owner(vault) { _,_ in calls += 1; return "pan" }
        defer { reopened.close() }
        let identity = reopened.identity(messageID:"one",text:"water bread")
        let result = await reopened.translatedMessage(for:identity)
        XCTAssertNil(result); XCTAssertEqual(reopened.phase(for:identity),.failed)
        reopened.retry(identity)
        let retried = await reopened.translatedMessage(for:identity)
        XCTAssertNil(retried); XCTAssertEqual(calls,0)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
    }
    func testMissingPlanWordCannotSilentlyAdvanceVocabulary() async throws {
        let vault = try store()
        let first = await owner(vault) { _,_ in "agua" }
        _ = try await message(first,"one","water bread"); first.close()
        try vault.transaction {
            for kind in ["full-message-translation","introduced-word"] {
                for id in try vault.ids(kind) { try vault.remove(kind,id) }
            }
        }
        var calls = 0
        let reopened = await owner(vault) { _,_ in calls += 1; return "pan" }
        defer { reopened.close() }
        let identity = reopened.identity(messageID:"one",text:"water bread")
        let result = await reopened.translatedMessage(for:identity)
        XCTAssertNil(result); XCTAssertEqual(reopened.phase(for:identity),.failed)
        XCTAssertEqual(calls,0)
    }
    func testConversationDeletionRemovesMessagePlansButRetainsLearnedVocabulary() async throws {
        let vault = try store()
        let value = await owner(vault) { _,_ in "agua" }
        defer { value.close() }
        _ = try await message(value,"one","water")
        _ = try await message(value,"two","water!")
        try value.forget(messageIDs:["one"])
        XCTAssertEqual(try vault.transaction{try vault.ids("message-word-plan").count},1)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
        XCTAssertEqual(try vault.transaction{try vault.ids("full-message-translation").count},1)
    }

    func testRestoredHistoryRepeatsKnownWordsWithoutIntroducingUnseenOnes() async throws {
        let vault = try store()
        var calls: [String] = []
        let value = await owner(vault) { word,_ in calls.append(word); return "agua" }
        defer { value.close() }
        let empty = UUID(), repeatOnly = UUID()
        func importMessage(_ id: UUID) throws {
            let record = HistoryBackupMessage(id:id, peer:UUID(), outgoing:false, createdAt:0, text:"water bread")
            try vault.transaction { try vault.put("imported",id.uuidString.lowercased(),JSONEncoder().encode(record)) }
        }
        try importMessage(empty)
        let restored = try await message(value,empty.uuidString,"water bread")
        XCTAssertEqual(restored.practiceText,"water bread")
        XCTAssertTrue(calls.isEmpty)
        _ = try await message(value,"new","water")
        try importMessage(repeatOnly)
        let repeated = try await message(value,repeatOnly.uuidString,"water bread")
        XCTAssertEqual(repeated.practiceText,"agua bread")
        let collision = await value.translatedMessage(for:value.identity(messageID:empty.uuidString,text:"wrong text"))
        XCTAssertNil(collision)
        XCTAssertEqual(calls,["water"])
    }
}
