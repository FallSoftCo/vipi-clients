import CryptoKit
import Foundation
import Network
import SwiftUI
@preconcurrency import Translation
import XCTest
@testable import Vipi

/// Public/authored QA text only. Not a production private message cache.
final class TranslationPhraseTests: XCTestCase {
    @MainActor func testInstalledWholeAndPhraseTranslations() async throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Apple Translation execution requires the physical iPad")
        #else
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = try Data(contentsOf: documents.appendingPathComponent("phrase-protocol.json"))
        let protocolValue = try XCTUnwrap(JSONSerialization.jsonObject(with: input) as? [String: Any])
        XCTAssertEqual(protocolValue["schema"] as? String, "vipi-local-phrase-probe-1")
        let samples = try XCTUnwrap(protocolValue["samples"] as? [[String: Any]])
        let extents = try XCTUnwrap(protocolValue["window_extents"] as? [[Int]])
        let runID = protocolValue["qa_run_id"] as? String ?? "001"
        guard runID.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else { throw PhraseError.identityMismatch }
        let digest = SHA256.hash(data: input).map { String(format: "%02x", $0) }.joined()
        let identity = digest + ":AppleTranslation:" + UIDevice.current.systemVersion + ":qa-epoch-" + runID
        let stateURL = documents.appendingPathComponent("phrase-cache-apple-\(runID).json")
        let receiptURL = documents.appendingPathComponent("phrase-observations-apple-\(runID).json")
        let state = PhraseState(identity: identity, total: samples.count, digest: digest, cacheURL: stateURL, receiptURL: receiptURL)
        try state.restore()
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { path in
            let online = path.status == .satisfied
            Task { @MainActor in state.networkAvailable = online }
        }
        monitor.start(queue: DispatchQueue(label: "vipi-phrase-path"))
        defer { monitor.cancel() }
        let observedBy = Date().addingTimeInterval(15)
        while state.networkAvailable == nil && Date() < observedBy { try await Task.sleep(for: .milliseconds(100)) }
        _ = try XCTUnwrap(state.networkAvailable)
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first(where: \.isKeyWindow)
        let window = UIWindow(windowScene: scene); window.frame = scene.screen.bounds
        let host = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.isHidden = true; window.rootViewController = nil; previous?.makeKey() }
        var indicesByPair: [String: [Int]] = [:]; var pairs: [String] = []
        for (index, sample) in samples.enumerated() {
            let source = try XCTUnwrap(sample["source"] as? String), target = try XCTUnwrap(sample["target"] as? String)
            let pair = source + "-" + target
            if indicesByPair[pair] == nil { pairs.append(pair) }
            indicesByPair[pair, default: []].append(index)
        }
        for pair in pairs {
            let pending = indicesByPair[pair, default: []].filter { state.rows[String($0)] == nil }
            if pending.isEmpty { continue }
            let languages = pair.split(separator: "-").map(String.init)
            let source = languages[0], target = languages[1]
            let availability = await LanguageAvailability().status(from: .init(identifier: source), to: .init(identifier: target))
            guard availability == .installed else { throw PhraseError.notInstalled(pair) }
            state.pairFinished = false
            host.rootView = AnyView(PhraseSession(source: source, target: target) { session in
                do {
                    guard session.sourceLanguage?.languageCode?.identifier == source,
                          session.targetLanguage?.languageCode?.identifier == target else { throw PhraseError.wrongSession }
                    for index in pending {
                        try Task.checkCancellation()
                        let item = samples[index]
                        let original = try XCTUnwrap(item["original"] as? String)
                        let begin = try XCTUnwrap(item["start"] as? Int), end = try XCTUnwrap(item["end"] as? Int)
                        let focus = NSRange(location: begin, length: end-begin)
                        guard Range(focus, in: original) != nil,
                              (original as NSString).substring(with: focus) == item["source_word"] as? String else { throw PhraseError.invalidFocus }
                        let started = ProcessInfo.processInfo.systemUptime
                        let whole = try await state.translate(original, source: source, target: target, session: session)
                        let words = LocalImmersion.words(original, language: source)
                        let first = try XCTUnwrap(words.firstIndex { NSIntersectionRange($0,focus).length > 0 })
                        let last = try XCTUnwrap(words.lastIndex { NSIntersectionRange($0,focus).length > 0 })
                        var ranges = [focus]
                        for width in extents {
                            let left = max(0,first-width[0]), right = min(words.count-1,last+width[1])
                            let a = min(begin,words[left].location), b = max(end,NSMaxRange(words[right]))
                            let range = NSRange(location: a,length: b-a)
                            let text = (original as NSString).substring(with: range)
                            if right-left+1 <= 8 && range.length <= 192 && text.range(of: "[.!?。！？\\n]", options: .regularExpression) == nil && !ranges.contains(range) {
                                ranges.append(range)
                            }
                        }
                        let targetWords = LocalImmersion.words(whole, language: target)
                        var phrases: [[String: Any]] = []
                        for range in ranges {
                            let text = (original as NSString).substring(with: range)
                            let translated = try await state.translate(text, source: source, target: target, session: session)
                            var needle = translated.trimmingCharacters(in: .whitespacesAndNewlines)
                            while let character = needle.last, ".!?。！？".contains(character) { needle.removeLast() }
                            needle = needle.trimmingCharacters(in: .whitespacesAndNewlines)
                            var matches: [[String: Any]] = []
                            if !needle.isEmpty {
                                let full = whole as NSString; var offset = 0
                                while offset < full.length {
                                    let found = full.range(of: needle, options: [.caseInsensitive], range: NSRange(location: offset,length: full.length-offset))
                                    if found.location == NSNotFound { break }
                                    if targetWords.contains(where: { $0.location == found.location }) && targetWords.contains(where: { NSMaxRange($0) == NSMaxRange(found) }) {
                                        matches.append(["start": found.location,"end": NSMaxRange(found),"text": full.substring(with: found)])
                                    }
                                    offset = NSMaxRange(found)
                                }
                            }
                            phrases.append(["start": range.location,"end": NSMaxRange(range),"input": text,"translation": translated,
                                            "focus_only": range == focus,"whole_translation_matches": matches])
                        }
                        var row = item
                        row["translation"] = whole; row["phrases"] = phrases; row["status"] = "executed"
                        row["network_unavailable"] = state.networkAvailable == false
                        row["latency_ms"] = (ProcessInfo.processInfo.systemUptime-started)*1000
                        state.rows[String(index)] = row
                        try state.save()
                    }
                    try state.save(force: true)
                } catch { state.failure = error }
                state.pairFinished = true
            }.id(pair))
            let deadline = Date().addingTimeInterval(180)
            while !state.pairFinished && Date() < deadline { try await Task.sleep(for: .milliseconds(100)) }
            guard state.pairFinished else { throw PhraseError.timeout(pair) }
            if let failure = state.failure { throw failure }
            host.rootView = AnyView(EmptyView())
        }
        try state.save(force: true)
        XCTAssertEqual(state.rows.count, samples.count)
        #endif
    }
}

private enum PhraseError: Error { case notInstalled(String), wrongSession, invalidFocus, timeout(String), identityMismatch }

@MainActor private final class PhraseState {
    let identity: String, total: Int, digest: String, cacheURL: URL, receiptURL: URL
    var networkAvailable: Bool?; var allCallsOffline = true
    var pairFinished = false; var failure: Error?
    var translations: [String: String] = [:]; var rows: [String: [String: Any]] = [:]
    var freshCalls = 0, cacheHits = 0, resumed = 0
    init(identity: String, total: Int, digest: String, cacheURL: URL, receiptURL: URL) {
        self.identity = identity; self.total = total; self.digest = digest; self.cacheURL = cacheURL; self.receiptURL = receiptURL
    }
    func restore() throws {
        guard FileManager.default.fileExists(atPath: cacheURL.path) else { return }
        let saved = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: cacheURL)) as? [String: Any])
        guard saved["identity"] as? String == identity else { throw PhraseError.identityMismatch }
        translations = try XCTUnwrap(saved["translations"] as? [String: String])
        rows = try XCTUnwrap(saved["rows"] as? [String: [String: Any]])
        allCallsOffline = saved["all_calls_offline"] as? Bool ?? false
        resumed = rows.count
    }
    func translate(_ text: String, source: String, target: String, session: TranslationSession) async throws -> String {
        let data = try JSONSerialization.data(withJSONObject: [source,target,text])
        let key = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        if let hit = translations[key] { cacheHits += 1; return hit }
        allCallsOffline = allCallsOffline && networkAvailable == false
        let response = try await session.translate(text)
        guard response.sourceText == text, response.sourceLanguage.languageCode?.identifier == source,
              response.targetLanguage.languageCode?.identifier == target else { throw PhraseError.wrongSession }
        allCallsOffline = allCallsOffline && networkAvailable == false
        translations[key] = response.targetText; freshCalls += 1
        return response.targetText
    }
    func save(force: Bool = false) throws {
        // Public QA observations only. Bounded checkpoints avoid repeatedly
        // serializing the entire growing capture for every sentence. A crash
        // may rerun at most 19 unfinished checkpoint cases; no synthetic hits.
        guard force || rows.count % 20 == 0 || rows.count == total else { return }
        try JSONSerialization.data(withJSONObject: ["identity":identity,"translations":translations,"rows":rows,
            "all_calls_offline":allCallsOffline], options: [.sortedKeys]).write(to:cacheURL, options:.atomic)
        let ordered = rows.keys.sorted { Int($0)! < Int($1)! }.compactMap { rows[$0] }
        let report: [String: Any] = ["schema":"vipi-local-phrase-observations-1","protocol_sha256":digest,
            "provider":"Apple Translation / iPadOS " + UIDevice.current.systemVersion,
            "cases_expected":total,"cases_completed":rows.count,"complete":rows.count == total,
            "fresh_calls_this_run":freshCalls,"cache_hits_this_run":cacheHits,"resumed_cases":resumed,
            "checkpoint_interval_cases":20,
            "network_absence_verified":allCallsOffline,"linguistic_acceptance":false,"runtime_integration":false,
            "model_identity_limit":"QA OS version and epoch; no provider model content hash","results":ordered]
        try JSONSerialization.data(withJSONObject:report, options:[.prettyPrinted,.sortedKeys]).write(to:receiptURL, options:.atomic)
    }
}

private struct PhraseSession: View {
    let source: String, target: String
    let execute: @MainActor (TranslationSession) async -> Void
    @State private var submitted = false
    var body: some View {
        Text("Preparing Vipi language evidence")
            .translationTask(source: .init(identifier:source),target: .init(identifier:target)) { session in
                guard !submitted else { return }; submitted = true
                await execute(session)
            }
    }
}
