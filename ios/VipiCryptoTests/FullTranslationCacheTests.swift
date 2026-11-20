import Foundation
import XCTest
import VipiCore
@testable import Vipi

/// Real encrypted MessageVault storage and production translation orchestration.
/// Controlled SDK completions qualify cache/lifetime behavior, not model quality.
@MainActor final class FullTranslationCacheTests: XCTestCase {
    private func store() throws -> MessageVault {
        let account = UUID()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("full-translation-" + UUID().uuidString)
        let value = try MessageVault(account:account,directory:root)
        addTeardownBlock {
            try? value.close()
            try? FileManager.default.removeItem(at:root)
            KeychainStore.delete(account:"messages-" + account.uuidString.lowercased())
        }
        return value
    }
    private func owner(_ store:MessageVault, target:String = "es") async -> ConversationImmersion {
        let value = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await value.configure(pair:.init(source:"en",target:target),mode:.fullMessages); value.attachCache(store)
        return value
    }
    private func request(_ owner:ConversationImmersion) async throws -> ConversationImmersion.Request {
        let deadline = ContinuousClock.now.advanced(by:.seconds(2))
        while owner.request == nil && ContinuousClock.now < deadline { await Task.yield() }
        return try XCTUnwrap(owner.request,"Production owner must request an actual SDK completion")
    }
    private func complete(_ owner:ConversationImmersion,id:String,text:String,target:String) async throws -> FullMessageTranslation {
        let identity = owner.identity(messageID:id,text:text)
        let task = Task { await owner.translatedMessage(for:identity) }
        let pending = try await request(owner)
        XCTAssertEqual(pending.text,text)
        await owner.finish(pending,translation:target)
        let returned = await task.value
        return try XCTUnwrap(returned)
    }
    func testCompleteResultSurvivesOwnerAndVaultReopenWithoutAnotherSDKRequest() async throws {
        let original = "A completely unseen purple bicycle.", store = try store()
        let first = await owner(store)
        let value = try await complete(first,id:"durable",text:original,target:"Una bicicleta morada completamente nueva.")
        let url = store.url, account = store.account
        XCTAssertEqual(try store.transaction { try store.ids("full-message-translation").count },1)
        first.close(); try store.close()
        let reopened = try MessageVault(account:account,directory:url.deletingLastPathComponent().deletingLastPathComponent())
        defer { try? reopened.close() }
        let second = await owner(reopened); defer { second.close() }
        let received = await second.translatedMessage(for:second.identity(messageID:"durable",text:original))
        XCTAssertEqual(received,value); XCTAssertNil(second.request)
        XCTAssertTrue(second.lastOutcome?.cacheHit == true)
        // SQLite must not contain the original or derivative cleartext.
        for file in [url,URL(fileURLWithPath:url.path + "-wal")] where FileManager.default.fileExists(atPath:file.path) {
            let bytes = try Data(contentsOf:file)
            XCTAssertNil(bytes.range(of:Data(original.utf8)))
            XCTAssertNil(bytes.range(of:Data(value.practiceText.utf8)))
        }
    }
    func testDifferentAccountPairAndExactSourceBytesCannotReuseCompletedResult() async throws {
        let store = try store(), other = try self.store()
        let first = await owner(store)
        _ = try await complete(first,id:"same-id",text:"café",target:"café traducido")
        first.close()
        for (vault,target,text) in [(other,"es","café"),(store,"fr","café"),(store,"es","cafe\u{301}")] {
            let current = await owner(vault,target:target)
            let task = Task { await current.translatedMessage(for:current.identity(messageID:"same-id",text:text)) }
            let pending = try await request(current)
            XCTAssertEqual(pending.pair.target,target)
            XCTAssertTrue(pending.text.utf8.elementsEqual(text.utf8))
            XCTAssertNil(current.translation(for:current.identity(messageID:"same-id",text:text)))
            current.close(); let result = await task.value; XCTAssertNil(result)
        }
    }
    func testMalformedEncryptedCacheIsMissAndReplacedOnlyAfterCompleteResult() async throws {
        let store = try store(), first = await owner(store)
        _ = try await complete(first,id:"corrupt",text:"Keep my original.",target:"Conserva mi original.")
        first.close()
        let key = try XCTUnwrap(store.transaction { try store.ids("full-message-translation").first })
        try store.transaction { try store.put("full-message-translation",key,Data("invalid cache payload".utf8)) }
        let second = await owner(store); defer { second.close() }
        let task = Task { await second.translatedMessage(for:second.identity(messageID:"corrupt",text:"Keep my original.")) }
        let pending = try await request(second)
        XCTAssertEqual(try store.transaction { try store.get("full-message-translation",key) },Data("invalid cache payload".utf8))
        await second.finish(pending,translation:"Guarda mi mensaje original.")
        let result = await task.value
        XCTAssertEqual(result?.practiceText,"Guarda mi mensaje original.")
        XCTAssertNotEqual(try store.transaction { try store.get("full-message-translation",key) },Data("invalid cache payload".utf8))
    }
    func testCloseAndPairReplacementRejectLateCompletionWithoutDurableWrite() async throws {
        for changePair in [false,true] {
            let store = try store(), current = await owner(store)
            let old = current.identity(messageID:"late",text:"Do not save after logout.")
            let task = Task { await current.translatedMessage(for:old) }
            let pending = try await request(current)
            if changePair { await current.configure(pair:.init(source:"en",target:"fr"),mode:.fullMessages); current.attachCache(store) }
            else { current.close() }
            await current.finish(pending,translation:"No guardar después de salir.")
            let result = await task.value
            XCTAssertNil(result); XCTAssertNil(current.translation(for:old))
            XCTAssertEqual(try store.transaction { try store.ids("full-message-translation") },[])
            current.close()
        }
    }
    func testForgetRemovesAllPairCachesCancelsPendingAndPreservesOtherMessageAndAccount() async throws {
        let store = try store(), other = try self.store()
        for target in ["es","fr"] {
            let current = await owner(store,target:target)
            _ = try await complete(current,id:"deleted",text:"Delete this message.",target:"A real supplied model output.")
            current.close()
        }
        let preserved = await owner(store)
        _ = try await complete(preserved,id:"keep",text:"Keep this friend message.",target:"Conserva este mensaje.")
        let otherOwner = await owner(other)
        _ = try await complete(otherOwner,id:"deleted",text:"Other account private message.",target:"Otro mensaje privado.")
        otherOwner.close()
        let pendingTask = Task { await preserved.translatedMessage(for:preserved.identity(messageID:"pending-delete",text:"Pending private message.")) }
        let pending = try await request(preserved)
        try preserved.forget(messageIDs:["deleted","pending-delete"])
        await preserved.finish(pending,translation:"Must never persist")
        let cancelled = await pendingTask.value; XCTAssertNil(cancelled)
        XCTAssertEqual(try store.transaction { try store.ids("full-message-translation").count },1)
        XCTAssertEqual(try other.transaction { try other.ids("full-message-translation").count },1)
        let kept = await preserved.translatedMessage(for:preserved.identity(messageID:"keep",text:"Keep this friend message."))
        XCTAssertEqual(kept?.practiceText,"Conserva este mensaje."); XCTAssertNil(preserved.request)
        preserved.close()
    }
    func testDisappearingWaiterCannotCancelSharedTranslationOrWarmCompletion() async throws {
        let store = try store(), current = await owner(store); defer { current.close() }
        let identity = current.identity(messageID:"offscreen",text:"Translate while my row is offscreen.")
        let row = Task { await current.translatedMessage(for:identity) }
        let pending = try await request(current)
        row.cancel()
        let remaining = Task { await current.translatedMessage(for:identity) }
        await current.finish(pending,translation:"Traduce mientras mi mensaje está fuera de pantalla.")
        let cancelled = await row.value, completed = await remaining.value
        XCTAssertNil(cancelled); XCTAssertNotNil(completed)
        XCTAssertEqual(try store.transaction { try store.ids("full-message-translation").count },1)
        current.warm([(id:"inactive-chat",text:"A new message in another chat.")])
        let offscreen = try await request(current)
        XCTAssertEqual(offscreen.text,"A new message in another chat.")
        await current.finish(offscreen,translation:"Un mensaje nuevo en otro chat.")
        let deadline = ContinuousClock.now.advanced(by:.seconds(2))
        while current.translation(for:current.identity(messageID:"inactive-chat",text:offscreen.text)) == nil && ContinuousClock.now < deadline { await Task.yield() }
        XCTAssertNotNil(current.translation(for:current.identity(messageID:"inactive-chat",text:offscreen.text)))
    }
    func testEncryptedHistoryReplayIsBoundedAndKeepsMountedMessageReady() async throws {
        let store = try store(), writer = await owner(store)
        for index in 0..<6 {
            _ = try await complete(writer,id:"history-\(index)",text:"Stored source \(index)",target:"Traducción \(index)")
        }
        writer.close()
        let reader = ConversationImmersion(modelStatus:{_ in .installed},memoryCacheLimit:2,identify:{_ in nil})
        await reader.configure(pair:.init(source:"en",target:"es"),mode:.fullMessages); reader.attachCache(store)
        defer { reader.close() }
        let visible = reader.identity(messageID:"history-0",text:"Stored source 0")
        reader.retainVisible(visible)
        let displayed = await reader.translatedMessage(for:visible)
        XCTAssertEqual(displayed?.practiceText,"Traducción 0")
        for index in 1..<6 {
            await reader.prepareStoredMessage(id:"history-\(index)",text:"Stored source \(index)")
            XCTAssertNil(reader.request,"Encrypted replay must reuse complete results")
            XCTAssertLessThanOrEqual(reader.memoryCacheCount,2)
            XCTAssertEqual(reader.translation(for:visible),displayed,"Background replay must not replace a mounted row with Preparing")
            XCTAssertEqual(reader.phase(for:visible),.ready)
        }
        reader.releaseVisible(visible)
        await reader.prepareStoredMessage(id:"history-1",text:"Stored source 1")
        XCTAssertLessThanOrEqual(reader.memoryCacheCount,2)
        XCTAssertNil(reader.translation(for:visible))
        reader.retainVisible(visible)
        let restored = await reader.translatedMessage(for:visible)
        XCTAssertEqual(restored,displayed); XCTAssertNil(reader.request)
        reader.releaseVisible(visible)
    }

    func testResidentByteBudgetIncludesDiskHitsAndPreservesVisibleCompletedFace() async throws {
        let vault = try store(), writer = await owner(vault)
        for index in 0..<5 {
            _ = try await complete(writer,id:"bytes-\(index)",text:"Source \(index)",target:String(repeating:"á",count:100))
        }
        writer.close()
        let reader = ConversationImmersion(modelStatus:{_ in .installed},memoryCacheLimit:128,
            memoryCacheByteLimit:800,identify:{_ in nil})
        await reader.configure(pair:.init(source:"en",target:"es"),mode:.fullMessages); reader.attachCache(vault)
        defer { reader.close() }
        let pinned = reader.identity(messageID:"bytes-0",text:"Source 0")
        reader.retainVisible(pinned)
        let originalFace = await reader.translatedMessage(for:pinned)
        for index in 1..<5 {
            await reader.prepareStoredMessage(id:"bytes-\(index)",text:"Source \(index)")
            XCTAssertLessThanOrEqual(reader.residentMemoryBytes,800)
            XCTAssertLessThanOrEqual(reader.residentStateCount,2)
            XCTAssertEqual(reader.translation(for:pinned),originalFace)
            XCTAssertNil(reader.request)
        }
        reader.releaseVisible(pinned)
    }

    func testFailedStatesAreBoundedAndRequireExplicitRetryAfterOwnerReopen() async throws {
        let vault = try store()
        let first = ConversationImmersion(modelStatus:{_ in .installed},memoryCacheLimit:2,identify:{_ in nil})
        await first.configure(pair:.init(source:"en",target:"es"),mode:.fullMessages); first.attachCache(vault)
        for index in 0..<5 {
            let identity = first.identity(messageID:"failed-\(index)",text:"Private failed source \(index)")
            let work = Task { await first.translatedMessage(for:identity) }
            let pending = try await request(first)
            await first.finish(pending,translation:nil)
            let result = await work.value
            XCTAssertNil(result)
            XCTAssertLessThanOrEqual(first.residentStateCount,2)
        }
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation-failure").count },5)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation").count },0)
        first.close()
        let second = await owner(vault); defer { second.close() }
        let identity = second.identity(messageID:"failed-0",text:"Private failed source 0")
        let unchanged = await second.translatedMessage(for:identity)
        XCTAssertNil(unchanged); XCTAssertEqual(second.phase(for:identity),.failed); XCTAssertNil(second.request)
        second.retry(identity)
        let retried = try await complete(second,id:identity.messageID,text:identity.text,target:"Resultado completo.")
        XCTAssertEqual(retried.practiceText,"Resultado completo.")
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation-failure").count },4)
        try second.forget(messageIDs:["failed-1"])
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation-failure").count },3)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation").count },1)
    }

    func testCancellationAndPreparationStateAreNotDurableTranslationFailures() async throws {
        for failure in [ConversationImmersion.ProviderError.cancelled,.modelNotReady,.unsupported,.preparation] {
            let vault = try store(), first = await owner(vault)
            let identity = first.identity(messageID:"transient",text:"Retry when the real model becomes ready.")
            let work = Task { await first.translatedMessage(for:identity) }
            let pending = try await request(first)
            await first.finish(pending,translation:nil,failure:failure)
            let result = await work.value; XCTAssertNil(result)
            XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation-failure").count },0)
            first.close()
            let second = await owner(vault)
            _ = try await complete(second,id:identity.messageID,text:identity.text,target:"Traducción después de preparar el modelo.")
            second.close()
        }
    }

    func testExpandedCompleteFacesAndReadingSurviveEncryptedCacheWithoutTailTruncation() async throws {
        let vault = try store()
        let source = String(repeating:"a",count:32_768)
        let practice = String(repeating:"汉",count:23_000) + "👩🏽‍💻END"
        let reading = String(repeating:"hàn ",count:23_000) + "👩🏽‍💻END"
        let writer = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},fullReadingProducer:{_,_ in
            .init(text:reading,provenance:.localTransliteration)
        })
        await writer.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); writer.attachCache(vault)
        let value = try await complete(writer,id:"expanded",text:source,target:practice)
        XCTAssertTrue(value.original.utf8.elementsEqual(source.utf8))
        XCTAssertEqual(value.practiceText,practice); XCTAssertEqual(value.practiceReading,reading)
        writer.close()
        let reader = ConversationImmersion(modelStatus:{_ in XCTFail("Complete encrypted hit must not reprepare models"); return .unsupported},identify:{_ in nil})
        await reader.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); reader.attachCache(vault)
        defer { reader.close() }
        let saved = await reader.translatedMessage(for:reader.identity(messageID:"expanded",text:source))
        XCTAssertEqual(saved,value); XCTAssertNil(reader.request)
        XCTAssertEqual(try vault.transaction{try vault.ids("full-message-translation").count},1)
    }

    func testDurableWarmReferencesLoadOnlyWhenReachedAndForgetRejectsQueuedWork() async throws {
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil})
        await current.configure(pair:.init(source:"en",target:"es"),mode:.fullMessages); defer { current.close() }
        var loaded:[String] = []
        current.warmStored(id:"first") { loaded.append("first"); return "First committed source." }
        let first = try await request(current)
        current.warmStored(id:"deleted") { loaded.append("deleted"); return "Must never load a deleted message." }
        current.warmStored(id:"second") { loaded.append("second"); return "Second committed source." }
        XCTAssertEqual(loaded,["first"],"Pending durable work must retain IDs/loaders, not load every plaintext body")
        try current.forget(messageIDs:["deleted"])
        await current.finish(first,translation:"Primero.")
        let second = try await request(current)
        XCTAssertEqual(second.text,"Second committed source."); XCTAssertEqual(loaded,["first","second"])
        current.close(); await current.finish(second,translation:"Late result rejected.")
        XCTAssertNil(current.translation(for:current.identity(messageID:"second",text:"Second committed source.")))
    }
    func testFullReadingByteEvictionKeepsExpandedUnicodeTail() async throws {
        let cache = FullReadingCache(policy:"owner-byte-regression",byteLimit:900) { text,_ in
            .init(text:text + " café\u{301} 👩🏽‍💻 tail",provenance:.localTransliteration)
        }
        for index in 0..<8 {
            let original = String(repeating:"字",count:60) + "\(index)"
            let result = await cache.resolve(text:original,language:"zh")
            XCTAssertEqual(result?.text,original + " café\u{301} 👩🏽‍💻 tail")
            XCTAssertLessThanOrEqual(cache.residentBytes,900)
        }
    }

    func testUnavailableGuidePersistsAndExplicitRetryNeverRetranslates() async throws {
        let vault = try store(), probe = ReadingStatusProbe([nil, .init(text:"míngtiān",provenance:.localTransliteration)])
        func make() async -> ConversationImmersion {
            let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
                fullReadingProducer:{text,language in await probe.read(text,language)})
            await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault)
            return current
        }
        let first = await make()
        let value = try await complete(first,id:"guide-retry",text:"Tomorrow",target:"明天")
        XCTAssertEqual(value.readingState?.status,.unavailable)
        XCTAssertEqual(value.practiceText,"明天"); XCTAssertEqual(first.phase(for:first.identity(messageID:"guide-retry",text:"Tomorrow")),.ready)
        first.close()
        let second = await make(), identity = second.identity(messageID:"guide-retry",text:"Tomorrow")
        let saved = await second.translatedMessage(for:identity)
        XCTAssertEqual(saved,value); XCTAssertNil(second.request)
        let callsBefore = await probe.count; XCTAssertEqual(callsBefore,1)
        let retry = try XCTUnwrap(second.retryReading(identity))
        XCTAssertNil(second.retryReading(identity)) // repeated tap shares the same pending work
        await retry.value
        XCTAssertFalse(second.readingRetryPending(for:identity))
        let updated = try XCTUnwrap(second.translation(for:identity))
        XCTAssertEqual(updated.readingState?.status,.available); XCTAssertEqual(updated.practiceReading,"míngtiān")
        XCTAssertEqual(updated.practiceText,value.practiceText); XCTAssertEqual(updated.original,value.original)
        XCTAssertEqual(updated.meaningText,value.meaningText); XCTAssertNil(second.request)
        let callsAfter = await probe.count; XCTAssertEqual(callsAfter,2)
        second.close()
        let third = await make(); defer { third.close() }
        let reopened = await third.translatedMessage(for:third.identity(messageID:"guide-retry",text:"Tomorrow"))
        XCTAssertEqual(reopened,updated); XCTAssertNil(third.request)
        let callsReopened = await probe.count; XCTAssertEqual(callsReopened,2)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation").count },1)
    }

    func testLegacyReadingRefreshKeepsExactTranslationCacheKeyAndOriginal() async throws {
        XCTAssertEqual(FullSentenceReadings.translationCacheCompatibilitySuffix,"live-full-text-2-byte-contract:pinyin-pro-3.29.5-marked-native-2:ec2f31077ea4aa2f531e0711366bb3d07af495c8ab53f144f32a5b231ed3f35c:cf-hangul-orthographic-guard-1:cf-japanese-guard-sokuon-1:cf-arabic-latin")
        XCTAssertNotEqual(FullSentenceReadings.translationCacheCompatibilitySuffix,FullSentenceReadings.policy,"Reading expansion must not invalidate stored full translations")
        let vault = try store(), first = await owner(vault,target:"zh")
        _ = try await complete(first,id:"old-guide",text:"Tomorrow",target:"明天")
        first.close()
        let key = try XCTUnwrap(vault.transaction { try vault.ids("full-message-translation").first })
        let bytes = try XCTUnwrap(vault.transaction { try vault.get("full-message-translation",key) })
        var record = try XCTUnwrap(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
        var value = try XCTUnwrap(record["value"] as? [String:Any])
        value.removeValue(forKey:"readingState"); value["practiceReading"] = "stale guide"
        record["value"] = value
        try vault.transaction { try vault.put("full-message-translation",key,JSONSerialization.data(withJSONObject:record)) }
        let probe = ReadingStatusProbe([.init(text:"míngtiān",provenance:.localTransliteration)])
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{text,language in await probe.read(text,language)})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let updated = await current.translatedMessage(for:current.identity(messageID:"old-guide",text:"Tomorrow"))
        XCTAssertEqual(updated?.practiceReading,"míngtiān"); XCTAssertEqual(updated?.readingState?.status,.available)
        XCTAssertEqual(updated?.original,"Tomorrow"); XCTAssertEqual(updated?.practiceText,"明天")
        XCTAssertNil(current.request); XCTAssertEqual(current.lastOutcome?.localTranslationCalls,0)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation") },[key])
        let calls = await probe.count; XCTAssertEqual(calls,1)
    }

    func testMalformedReadingMetadataRefreshesWithoutDiscardingTranslation() async throws {
        let vault = try store(), first = await owner(vault,target:"zh")
        _ = try await complete(first,id:"invalid-guide",text:"Tomorrow",target:"明天")
        first.close()
        let key = try XCTUnwrap(vault.transaction { try vault.ids("full-message-translation").first })
        let bytes = try XCTUnwrap(vault.transaction { try vault.get("full-message-translation",key) })
        var record = try XCTUnwrap(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
        var value = try XCTUnwrap(record["value"] as? [String:Any])
        value["readingState"] = ["status":"future-unknown-status", "failure":"future-reason", "policy":"future-version"]
        value["practiceReading"] = 42
        record["value"] = value
        try vault.transaction { try vault.put("full-message-translation",key,JSONSerialization.data(withJSONObject:record)) }
        let probe = ReadingStatusProbe([.init(text:"míngtiān",provenance:.localTransliteration)])
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{text,language in await probe.read(text,language)})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let updated = await current.translatedMessage(for:current.identity(messageID:"invalid-guide",text:"Tomorrow"))
        XCTAssertEqual(updated?.practiceReading,"míngtiān"); XCTAssertEqual(updated?.readingState?.status,.available)
        XCTAssertEqual(updated?.original,"Tomorrow"); XCTAssertEqual(updated?.practiceText,"明天")
        XCTAssertNil(current.request); XCTAssertEqual(current.lastOutcome?.localTranslationCalls,0)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation") },[key])
        let calls = await probe.count; XCTAssertEqual(calls,1)
    }

    func testLatinAndProtectedLiteralOutputNeedsNoReadingProvider() async throws {
        let vault = try store(), probe = ReadingStatusProbe([])
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{text,language in await probe.read(text,language)})
        await current.configure(pair:.init(source:"en",target:"ja"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let value = try await complete(current,id:"literal-guide",text:"Keep the link",target:"cafe\u{301} `日本語` https://example.com/日本 42 👩🏽‍💻")
        XCTAssertEqual(value.readingState?.status,.notNeeded); XCTAssertNil(value.practiceReading)
        let calls = await probe.count; XCTAssertEqual(calls,0)
    }

    func testPartialNativeReadingDoesNotClaimCompleteLatinGuide() async throws {
        let vault = try store(), probe = ReadingStatusProbe([.init(text:"míng 天",provenance:.localTransliteration)])
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{text,language in await probe.read(text,language)})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let value = try await complete(current,id:"partial-guide",text:"Tomorrow",target:"明天")
        XCTAssertEqual(value.readingState?.status,.unavailable); XCTAssertNil(value.practiceReading)
        XCTAssertEqual(value.readingState?.failure,.unresolved); XCTAssertFalse(value.readingState?.canRetry ?? true)
        XCTAssertNil(current.retryReading(current.identity(messageID:"partial-guide",text:"Tomorrow")))
        XCTAssertEqual(value.practiceText,"明天"); XCTAssertEqual(value.meaningText,"Tomorrow")
        XCTAssertEqual(current.phase(for:current.identity(messageID:"partial-guide",text:"Tomorrow")),.ready)
    }

    func testStaticGuideFailurePersistsWithoutRetryOrTranslationReplay() async throws {
        let cases:[(String,FullReading,FullMessageReadingState.Failure)] = [
            ("oversized",.init(text:String(repeating:"x",count:FullMessageBudget.recordBytes+1),provenance:.localTransliteration),.outputLimit),
            ("record-overhead",.init(text:String(repeating:"x",count:FullMessageBudget.recordBytes-1),provenance:.localTransliteration),.outputLimit),
            ("empty",.init(text:" \n",provenance:.localTransliteration),.unresolved),
            ("partial",.init(text:"míng 天",provenance:.localTransliteration),.unresolved)
        ]
        for (id,reading,reason) in cases {
            let vault = try store(), probe = ReadingStatusProbe([reading])
            func make() async -> ConversationImmersion {
                let value = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
                    fullReadingProducer:{text,language in await probe.read(text,language)})
                await value.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); value.attachCache(vault)
                return value
            }
            let first = await make(), identity = first.identity(messageID:id,text:"Tomorrow")
            let value = try await complete(first,id:id,text:"Tomorrow",target:"明天")
            XCTAssertEqual(value.readingState?.failure,reason); XCTAssertFalse(value.readingState?.canRetry ?? true)
            XCTAssertNil(value.practiceReading); XCTAssertNil(first.reading(for:value)); XCTAssertNil(first.retryReading(identity))
            XCTAssertEqual(first.phase(for:identity),.ready)
            // Practice text is still the complete immutable native audio payload.
            XCTAssertEqual(value.practiceText,"明天"); XCTAssertEqual(value.meaningText,"Tomorrow"); XCTAssertEqual(value.original,"Tomorrow")
            first.close()
            let second = await make(), secondIdentity = second.identity(messageID:id,text:"Tomorrow")
            let saved = await second.translatedMessage(for:secondIdentity)
            XCTAssertEqual(saved,value); XCTAssertNil(second.request); XCTAssertNil(second.retryReading(secondIdentity))
            XCTAssertEqual(second.lastOutcome?.localTranslationCalls,0)
            let count = await probe.count; XCTAssertEqual(count,1)
            XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation").count },1)
            second.close()
        }
    }
    func testCaughtReadingProducerThrowRemainsRetryableAndReady() async throws {
        let probe = ThrowingReadingStatusProbe(), vault = try store()
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{_,_ in try? await probe.read()})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let value = try await complete(current,id:"throw-guide",text:"Tomorrow",target:"明天")
        let identity = current.identity(messageID:"throw-guide",text:"Tomorrow")
        XCTAssertEqual(value.readingState?.failure,.producerUnavailable); XCTAssertTrue(value.readingState?.canRetry == true)
        XCTAssertEqual(current.phase(for:identity),.ready); XCTAssertEqual(value.practiceText,"明天")
        let retry = try XCTUnwrap(current.retryReading(identity)); await retry.value
        XCTAssertEqual(current.translation(for:identity)?.readingState?.failure,.producerUnavailable)
        XCTAssertNil(current.request)
        let count = await probe.count; XCTAssertEqual(count,2)
    }
    func testDetailedNativeFailureNeverLeaksIntoCompatibilityReading() {
        // Cyrillic in a Korean reading is explicitly untranscribed by the real
        // adapter before tokenization; this is not a supplied reading success.
        let source = "Ж"
        let detailed = FullSentenceReadings.resolveDetailed(source,language:"ko")
        XCTAssertEqual(detailed?.failure,.unresolved); XCTAssertEqual(detailed?.text,"")
        XCTAssertNil(FullSentenceReadings.resolve(source,language:"ko"))
        let missing = FullSentenceReadings(chinese:nil).detailedReading("明天",language:"zh")
        XCTAssertNil(missing)
        XCTAssertTrue(FullSentenceReadings.state(text:"明天",language:"zh",reading:missing).canRetry)
        let literalGuide = FullReading(text:"míngtiān 用户@例子.公司",provenance:.localTransliteration)
        XCTAssertEqual(FullSentenceReadings.state(text:"明天 用户@例子.公司",language:"zh",reading:literalGuide).status,.available)
    }
    func testForgetCancelsActualWarmLegacyCacheRefreshWithoutResurrectingDeletedText() async throws {
        let vault = try store()
        let removedID = "bot-68E21F9D-869E-4C46-890F-4E4957BFB472", retainedID = "retained-guide"
        let writer = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},fullReadingProducer:{text,_ in
            .init(text:text == "明天" ? "míngtiān" : "nǐ hǎo",provenance:.localTransliteration)
        })
        await writer.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); writer.attachCache(vault)
        _ = try await complete(writer,id:removedID,text:"Tomorrow",target:"明天")
        let removedKey = try XCTUnwrap(vault.transaction { try vault.ids("full-message-translation").first })
        let retained = try await complete(writer,id:retainedID,text:"Hello",target:"你好")
        let retainedKey = try XCTUnwrap(vault.transaction { try vault.ids("full-message-translation").first { $0 != removedKey } })
        let retainedBytes = try XCTUnwrap(vault.transaction { try vault.get("full-message-translation",retainedKey) })
        writer.close()
        // A genuine encrypted cache hit whose missing metadata forces reading-
        // only migration. No translator response is supplied during the warm run.
        let stored = try XCTUnwrap(vault.transaction { try vault.get("full-message-translation",removedKey) })
        var record = try XCTUnwrap(JSONSerialization.jsonObject(with:stored) as? [String:Any])
        var value = try XCTUnwrap(record["value"] as? [String:Any])
        value.removeValue(forKey:"readingState"); record["value"] = value
        try vault.transaction { try vault.put("full-message-translation",removedKey,JSONSerialization.data(withJSONObject:record)) }
        let gate = LegacyWarmReadingGate()
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},fullReadingProducer:{_,_ in await gate.read()})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault); defer { current.close() }
        let retainedIdentity = current.identity(messageID:retainedID,text:"Hello")
        let restored = await current.translatedMessage(for:retainedIdentity)
        XCTAssertEqual(restored,retained); XCTAssertNil(current.request)
        let removedIdentity = current.identity(messageID:removedID,text:"Tomorrow")
        let warm = try XCTUnwrap(current.warm([(id:removedID,text:"Tomorrow")]))
        let deadline = ContinuousClock.now.advanced(by:.seconds(3))
        while !(await gate.waiting) && ContinuousClock.now < deadline { await Task.yield() }
        let waiting = await gate.waiting
        guard waiting else {
            XCTFail("Actual owner.warm cache-hit refresh must enter the explicit reading gate")
            current.close(); await gate.release(); await warm.value; return
        }
        XCTAssertNil(current.request,"Legacy guide migration must not request model translation")
        do { try current.forget(messageIDs:[removedID]) }
        catch { current.close(); await gate.release(); await warm.value; throw error }
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation") },[retainedKey])
        XCTAssertNil(current.translation(for:removedIdentity))
        XCTAssertEqual(current.translation(for:retainedIdentity),retained)
        // Release and await the exact already-started owner feeder. This proves
        // late work is quiescent before checking durable deletion, not just hidden.
        await gate.release(); await warm.value
        XCTAssertNil(current.translation(for:removedIdentity)); XCTAssertNil(current.request)
        XCTAssertEqual(current.translation(for:retainedIdentity),retained)
        XCTAssertEqual(current.phase(for:retainedIdentity),.ready); XCTAssertEqual(current.memoryCacheCount,1)
        XCTAssertEqual(try vault.transaction { try vault.ids("full-message-translation") },[retainedKey])
        XCTAssertTrue(try vault.transaction { try vault.ids("full-message-translation-failure").isEmpty })
        let retainedAfter = try XCTUnwrap(vault.transaction { try vault.get("full-message-translation",retainedKey) })
        XCTAssertEqual(retainedAfter,retainedBytes)
        let readCount = await gate.count; XCTAssertEqual(readCount,1)
        let stillRetained = await current.translatedMessage(for:retainedIdentity)
        XCTAssertEqual(stillRetained,retained); XCTAssertNil(current.request)
        XCTAssertEqual(current.lastOutcome?.localTranslationCalls,0)
    }

    func testClosingOwnerRejectsLateReadingRetryAndPreservesStoredMessage() async throws {
        let vault = try store(), gate = ReadingStatusGate()
        let current = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},
            fullReadingProducer:{_,_ in await gate.read()})
        await current.configure(pair:.init(source:"en",target:"zh"),mode:.fullMessages); current.attachCache(vault)
        let original = try await complete(current,id:"close-guide",text:"Tomorrow",target:"明天")
        let key = try XCTUnwrap(vault.transaction { try vault.ids("full-message-translation").first })
        let before = try vault.transaction { try vault.get("full-message-translation",key) }
        let identity = current.identity(messageID:"close-guide",text:"Tomorrow")
        let retry = try XCTUnwrap(current.retryReading(identity))
        let deadline = ContinuousClock.now.advanced(by:.seconds(3))
        while !(await gate.waiting) && ContinuousClock.now < deadline { await Task.yield() }
        let waiting = await gate.waiting
        XCTAssertTrue(waiting)
        current.close(); await gate.release(); await retry.value
        // A fresh owner must read the durable unavailable state without a model
        // call or a replay of the cancelled old owner's reading attempt.
        let reopened = await owner(vault,target:"zh"); defer { reopened.close() }
        let value = await reopened.translatedMessage(for:reopened.identity(messageID:"close-guide",text:"Tomorrow"))
        XCTAssertEqual(value,original); XCTAssertNil(reopened.request)
        XCTAssertEqual(try vault.transaction { try vault.get("full-message-translation",key) },before)
        XCTAssertNil(current.translation(for:identity))
    }

}


private actor ReadingStatusProbe {
    private var results:[FullReading?]
    private(set) var count = 0
    init(_ results:[FullReading?]) { self.results = results }
    func read(_ text:String,_ language:String) -> FullReading? {
        count += 1
        return results.isEmpty ? nil : results.removeFirst()
    }
}
private actor ReadingStatusGate {
    private var count = 0
    private var continuation:CheckedContinuation<FullReading?,Never>?
    var waiting:Bool { continuation != nil }
    func read() async -> FullReading? {
        count += 1
        if count == 1 { return nil }
        return await withCheckedContinuation { continuation = $0 }
    }
    func release() { continuation?.resume(returning:.init(text:"míngtiān",provenance:.localTransliteration)); continuation = nil }
}

private actor ThrowingReadingStatusProbe {
    enum Failure:Error { case unavailable }
    private(set) var count = 0
    func read() throws -> FullReading? { count += 1; throw Failure.unavailable }
}

private actor LegacyWarmReadingGate {
    private(set) var count = 0
    private var released = false
    private var continuation:CheckedContinuation<FullReading?,Never>?
    var waiting:Bool { continuation != nil }
    func read() async -> FullReading? {
        count += 1
        if released { return .init(text:"míngtiān",provenance:.localTransliteration) }
        return await withCheckedContinuation { continuation = $0 }
    }
    func release() {
        released = true
        continuation?.resume(returning:.init(text:"míngtiān",provenance:.localTransliteration)); continuation = nil
    }
}
