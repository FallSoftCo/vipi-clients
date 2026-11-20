import XCTest
import CryptoKit
import VipiCore
@testable import Vipi

@MainActor final class ImmersionModeTests: XCTestCase {
    private let pair = TranslationPair(source:"en",target:"es")
    private func store() throws -> MessageVault {
        let account = UUID(),root = FileManager.default.temporaryDirectory.appendingPathComponent("mode-"+UUID().uuidString)
        let vault = try MessageVault(account:account,directory:root)
        addTeardownBlock { try? vault.close(); try? FileManager.default.removeItem(at:root); KeychainStore.delete(account:"messages-"+account.uuidString.lowercased()) }
        return vault
    }
    func testFreshDefaultAndPersistedModeAreIndependentOfIdentityAndLanguage() {
        let name = "mode-default-"+UUID().uuidString
        let defaults = UserDefaults(suiteName:name)!
        defer { defaults.removePersistentDomain(forName:name) }
        let state = AppState(defaults:defaults)
        XCTAssertEqual(state.immersionMode,.incremental)
        let before = (state.knownLanguage,state.targetLanguage,state.invitationUsername)
        state.immersionMode = .fullMessages
        let reopened = AppState(defaults:defaults)
        XCTAssertEqual(reopened.immersionMode,.fullMessages)
        XCTAssertEqual(reopened.knownLanguage,before.0); XCTAssertEqual(reopened.targetLanguage,before.1); XCTAssertEqual(reopened.invitationUsername,before.2)
    }
    func testFullModeKeepsIncrementalPlanAndVocabularyAcrossToggleAndReopen() async throws {
        let vault = try store(); var calls:[String] = []
        func make() -> ConversationImmersion { ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},nativeTranslation:{text,_ in
            calls.append(text); return text == "water bread" ? "agua y pan" : text == "water" ? "agua" : "pan"
        }) }
        let owner = make(); await owner.configure(pair:pair); owner.attachCache(vault)
        let first = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        let incremental = try XCTUnwrap(first); XCTAssertEqual(incremental.words?.count,1)
        let plans = try vault.transaction{try vault.ids("message-word-plan").map{try vault.get("message-word-plan",$0)}}
        await owner.configure(pair:pair,mode:.fullMessages)
        let whole = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        XCTAssertEqual(whole?.practiceText,"agua y pan"); XCTAssertNil(whole?.words)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},1)
        XCTAssertEqual(try vault.transaction{try vault.ids("message-word-plan").map{try vault.get("message-word-plan",$0)}},plans)
        await owner.configure(pair:pair)
        let restored = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        XCTAssertEqual(restored,incremental); XCTAssertEqual(calls.count,2); owner.close()
        let reopened = make(); await reopened.configure(pair:pair,mode:.fullMessages); reopened.attachCache(vault)
        let cached = await reopened.translatedMessage(for:reopened.identity(messageID:"one",text:"water bread"))
        XCTAssertEqual(cached,whole); XCTAssertEqual(calls.count,2); reopened.close()
    }
    func testTransientIncrementalPlanSurvivesFullModeAndLateOldResultCannotCommit() async throws {
        var calls = 0
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},nativeTranslation:{text,_ in calls += 1; return "translated "+text})
        await owner.configure(pair:pair)
        let first = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        await owner.configure(pair:pair,mode:.fullMessages)
        _ = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        await owner.configure(pair:pair)
        let restored = await owner.translatedMessage(for:owner.identity(messageID:"one",text:"water bread"))
        XCTAssertEqual(restored,first); XCTAssertEqual(calls,2); owner.close()
        let vault = try store(); var reply:CheckedContinuation<String,Never>?
        let delayed = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},nativeTranslation:{_,_ in await withCheckedContinuation{reply = $0}})
        await delayed.configure(pair:pair); delayed.attachCache(vault)
        let task = Task{await delayed.translatedMessage(for:delayed.identity(messageID:"pending",text:"water"))}
        while reply == nil { await Task.yield() }
        await delayed.configure(pair:pair,mode:.fullMessages); reply?.resume(returning:"agua")
        let result = await task.value; XCTAssertNil(result)
        XCTAssertEqual(try vault.transaction{try vault.ids("introduced-word").count},0)
        XCTAssertEqual(try vault.transaction{try vault.ids("message-word-plan").count},0); delayed.close()
    }
    func testAmbiguousShortLatinKeepsChosenSourceWithActualNativeDetection() async throws {
        let text = "Water, water!"
        let detected = try await MessageLanguage().identify(text)
        let note = XCTAttachment(string:"Native NLLanguageRecognizer for synthetic English input: "+(detected ?? "unidentified")); note.name = "short-ambiguous-native-detection"; note.lifetime = .keepAlways; add(note)
        var directions:[TranslationPair] = []
        let owner = ConversationImmersion(modelStatus:{_ in .installed},nativeTranslation:{_,pair in directions.append(pair); return "agua, agua!"})
        await owner.configure(pair:pair,mode:.fullMessages)
        let value = await owner.translatedMessage(for:owner.identity(messageID:"short-ambiguous",text:text))
        XCTAssertEqual(value?.practiceText,"agua, agua!"); XCTAssertEqual(value?.meaningText,text); XCTAssertEqual(directions,[pair]); owner.close()
        // Deterministically exercise the advisory third-language branch as well.
        let controlled = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "nl"},nativeTranslation:{_,direction in XCTAssertEqual(direction,self.pair); return "agua, agua!"})
        await controlled.configure(pair:pair,mode:.fullMessages)
        let result = await controlled.translatedMessage(for:controlled.identity(messageID:"shared-latin",text:text))
        XCTAssertEqual(result?.practiceText,"agua, agua!"); controlled.close()
    }
    func testStableMessageIDSeedCoversEveryEligiblePositionAndPreservesContentPriority() async throws {
        let text = "water bread coffee"
        var seen = Set<String>()
        for index in 0..<18 {
            let id = "stable-position-"+String(index)
            let tokens = IncrementalWords.tokens(text,language:"en")
            var used = Set<String>(); let distinct = tokens.filter{used.insert($0.key).inserted}
            let preferred = distinct.filter(\.preferred), eligible = preferred.isEmpty ? distinct : preferred
            let seed = SHA256.hash(data:Data(id.lowercased().utf8)).prefix(4).reduce(UInt32(0)){($0 << 8)|UInt32($1)}
            let expected = eligible[Int(seed % UInt32(eligible.count))].text
            let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},nativeTranslation:{word,_ in "mapped "+word})
            await owner.configure(pair:pair)
            let result = await owner.translatedMessage(for:owner.identity(messageID:id,text:text))
            XCTAssertEqual(result?.words?.first?.source,expected); seen.insert(try XCTUnwrap(result?.words?.first?.source)); owner.close()
        }
        XCTAssertEqual(seen,Set(["water","bread","coffee"]))
    }
    func testAdjacentPracticeWordsShareProsodyWhileDisjointWordsRemainSeparate() {
        let value = FullMessageTranslation(original:"water bread and coffee",practiceText:"agua pan and café",meaningText:"water bread and coffee",inputLanguage:"en",practiceLanguage:"es",meaningLanguage:"en",words:[
            .init(start:0,length:5,source:"water",target:"agua",reading:nil),.init(start:6,length:5,source:"bread",target:"pan",reading:nil),.init(start:16,length:6,source:"coffee",target:"café",reading:nil)])
        XCTAssertEqual(value.practiceSpeech.map(\.text),["agua pan","café"])
        let sentence = String(repeating:"This uninterrupted sentence contains many words ",count:6)+"and finishes here."
        XCTAssertEqual(SpeechChunks.sentencePlan([(sentence,"en")]).count,1)
    }
}
