import XCTest
import AVFoundation
@preconcurrency import Translation
#if !targetEnvironment(simulator)
@preconcurrency import MLKitTranslate
#endif
@testable import Vipi

@MainActor final class LanguagePreparationTests: XCTestCase {
    private let spanish = TranslationPair(source: "en", target: "es")
    private let japanese = TranslationPair(source: "en", target: "ja")
    func testInstalledSDKCatalogMatchesEveryOfferedLanguage() throws {
        #if !targetEnvironment(simulator)
        XCTAssertEqual(Set(TranslateLanguage.allLanguages().map(\.rawValue)),LocalLanguageCatalog.codes)
        #else
        throw XCTSkip("Pinned ML Kit has no arm64 Simulator slice; real SDK inventory needs the iOS-on-Mac host")
        #endif
    }
    func testRecordNativeLanguageCapabilitiesWithoutDownloadsOrSynthesis() async throws {
        let nativeLanguages = await LanguageAvailability().supportedLanguages
        let voiceLanguages = Set(AVSpeechSynthesisVoice.speechVoices()
            .filter { !$0.voiceTraits.contains(.isNoveltyVoice) }.map { LocalLanguageCatalog.canonicalCode($0.language) })
        var rows: [[String:Any]] = []
        for language in VipiLanguage.initial {
            let pair = TranslationPair(source:language.id == "en" ? "es" : "en",target:language.id)
            let actual = await LocalTranslationCapability.resolve(pair)
            let reading = FullSentenceReadings.resolveDetailed(language.exampleGreeting,language:language.id)
            let readingState = FullSentenceReadings.state(text:language.exampleGreeting,language:language.id,reading:reading)
            rows.append(["language":language.id,"translation_provider":String(describing:actual.provider),
                "translation_state":String(describing:actual.availability),"native_voice_reported":voiceLanguages.contains(language.id),
                "existing_bundled_voice":language.id == "sw","greeting_reading_state":readingState.status.rawValue,
                "greeting_reading":reading?.text ?? ""])
        }
        let data: [String:Any] = ["scope":"Actual hosted iOS capability inventory. Does not qualify translation, pronunciation, model acquisition or synthesis.",
            "apple_identifiers":nativeLanguages.map(\.minimalIdentifier).sorted(),"languages":rows,
            "downloads_requested":false,"synthesis_requested":false,"translation_requested":false]
        let attachment = XCTAttachment(data:try JSONSerialization.data(withJSONObject:data,options:[.sortedKeys]),uniformTypeIdentifier:"public.json")
        attachment.name = "native-api-language-capabilities"; attachment.lifetime = .keepAlways; add(attachment)
        XCTAssertEqual(rows.count,59)
    }
    func testExpandedDownloadsRetainTheirResolvedLocalProvider() async throws {
        for (pair, provider) in [(TranslationPair(source:"en",target:"hi"),LocalTranslationProvider.apple),
                                 (TranslationPair(source:"en",target:"el"),LocalTranslationProvider.mlKit)] {
            let model = LanguagePreparation(status: { _ in .downloadable }, resolveProvider: { _ in provider })
            await model.refresh(pair); model.prepare()
            let request = try XCTUnwrap(model.request)
            XCTAssertEqual(request.pair,pair); XCTAssertEqual(request.provider,provider)
            XCTAssertTrue(model.busy)
            model.invalidate()
            model.finish(request,availability:.installed,prepared:true)
            XCTAssertFalse(model.prepared,"An abandoned provider must not finish another language's setup")
        }
    }
    func testChangingLanguagesDuringProviderDiscoveryCannotReplaceTheNewPair() async throws {
        var pending: CheckedContinuation<LocalTranslationProvider,Never>?
        let model = LanguagePreparation(status: { _ in .downloadable }, resolveProvider: { pair in
            if pair.target == "el" { return await withCheckedContinuation { pending = $0 } }
            return .apple
        })
        let old = Task { await model.refresh(.init(source:"en",target:"el")) }
        let deadline = Date().addingTimeInterval(5)
        while pending == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(pending)
        await model.refresh(japanese)
        completion.resume(returning:.mlKit); await old.value
        XCTAssertEqual(model.pair,japanese); XCTAssertEqual(model.provider,.apple)
        model.prepare(); XCTAssertEqual(model.request?.provider,.apple)
    }
    func testPlatformLanguageAliasesKeepTheSameUserSelection() {
        for (native, canonical) in [("nb-NO","no"),("iw-IL","he"),("in-ID","id"),("fil-PH","tl"),("zh-Hant","zh")] {
            XCTAssertEqual(LocalLanguageCatalog.canonicalCode(native),canonical)
            XCTAssertTrue(LocalLanguageCatalog.codes.contains(canonical))
        }
        XCTAssertEqual(TranslationPair(source:"no",target:"en").appleSource.languageCode?.identifier,"nb")
    }
    func testOnlyActualInstalledStatusReportsReadiness() async throws {
        let model = LanguagePreparation(status: { _ in .downloadable })
        await model.refresh(spanish); model.prepare()
        let request = try XCTUnwrap(model.request)
        XCTAssertTrue(model.busy)
        model.finish(request, availability: .downloadable, message: "Still downloading")
        XCTAssertEqual(model.availability, .downloadable); XCTAssertFalse(model.busy)
        model.prepare()
        let retry = try XCTUnwrap(model.request)
        XCTAssertNotEqual(retry.id, request.id)
        model.finish(retry, availability: .installed, prepared: true)
        XCTAssertEqual(model.availability, .installed); XCTAssertNil(model.message)
        model.prepare(); XCTAssertFalse(model.busy)
    }
    func testOldDownloadCannotFinishAfterChangingAwayAndBack() async throws {
        let model = LanguagePreparation(status: { _ in .downloadable })
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
        let model = LanguagePreparation(status: { _ in calls += 1; return .downloadable })
        for pair in [TranslationPair(source: "en", target: "en"), TranslationPair(source: "xx", target: "es")] {
            await model.refresh(pair); model.prepare()
            XCTAssertEqual(model.availability, .unsupported); XCTAssertFalse(model.busy); XCTAssertNil(model.request)
        }
        XCTAssertEqual(calls, 0)
    }
    func testLeavingInvalidatesAnOutstandingAvailabilityCheck() async throws {
        var continuation: CheckedContinuation<LocalLanguageAvailability, Never>?
        let model = LanguagePreparation(status: { _ in await withCheckedContinuation { continuation = $0 } })
        let check = Task { await model.refresh(spanish) }
        let deadline = Date().addingTimeInterval(5)
        while continuation == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(continuation)
        model.invalidate(); completion.resume(returning: .installed); await check.value
        XCTAssertEqual(model.availability, .checking); XCTAssertNil(model.request)
    }
    func testOlderAvailabilityCannotOverwriteNewSelection() async throws {
        var pending: CheckedContinuation<LocalLanguageAvailability, Never>?
        let model = LanguagePreparation(status: { pair in
            if pair.target == "es" { return await withCheckedContinuation { pending = $0 } }
            return .unsupported
        })
        let first = Task { await model.refresh(spanish) }
        let deadline = Date().addingTimeInterval(5)
        while pending == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(pending)
        await model.refresh(japanese)
        completion.resume(returning: .installed); await first.value
        XCTAssertEqual(model.pair, japanese); XCTAssertEqual(model.availability, .unsupported)
    }
    func testLeavingDuringRemovalCannotOverwriteTheNewLanguage() async throws {
        var pending: CheckedContinuation<Void, Never>?
        let model = LanguagePreparation(remove: { _ in
            await withCheckedContinuation { pending = $0 }
        }, status: { pair in pair.target == "sw" ? .installed : .unsupported }, resolveProvider: { _ in .mlKit })
        await model.refresh(.init(source: "en", target: "sw"))
        let removal = Task { await model.removeDownloads() }
        let deadline = Date().addingTimeInterval(5)
        while pending == nil && Date() < deadline { await Task.yield() }
        let completion = try XCTUnwrap(pending)
        XCTAssertTrue(model.busy)
        model.invalidate(); await model.refresh(japanese)
        completion.resume(); await removal.value
        XCTAssertEqual(model.pair, japanese); XCTAssertEqual(model.availability, .unsupported)
        XCTAssertFalse(model.busy); XCTAssertNil(model.message)
    }

}
