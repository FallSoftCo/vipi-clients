import XCTest
import VipiCore
import CryptoKit
import NaturalLanguage
import Darwin
@testable import Vipi

private actor FullReadingInvocationQA {
    private(set) var count = 0
    private(set) var ranOnMainThread = false
    func record() { count += 1; ranOnMainThread = ranOnMainThread || Thread.isMainThread }
}

private actor DelayedFullReadingQA {
    private var waiter: CheckedContinuation<Void, Never>?
    private var opened = false
    private(set) var started = false
    func hold() async {
        started = true
        if opened { return }
        await withCheckedContinuation { waiter = $0 }
    }
    func release() { opened = true; waiter?.resume(); waiter = nil }
}

/// Hash-pinned research pack. This producer is in the test target, never in the
/// shipping app bundle. It receives source text only, not a target translation.
@MainActor private final class StarterSourceUnitQA {
    static let sha = "67f041f3024c0e3679d54de9afa2debcebba1ad42e0a79b7bb0e4aacb90f2f60"
    static let version = "reviewed-source-starter-en-v002"
    struct Entry: Decodable {
        let id: String, source: String, target: String, category: String, pos: String
        let trainRank: Int, sourceTokens: [String]
        let guardValue: String?, following: [String]?, reading: String?
        enum CodingKeys: String, CodingKey {
            case id, source, target, category, pos, following, reading
            case trainRank = "train_rank", sourceTokens = "source_tokens", guardValue = "guard"
        }
    }
    struct Pack: Decodable {
        struct Pair: Decodable { let entries: [Entry] }
        struct Context: Decodable { let determiners: [String], prepositions: [String], objectVerbs: [String], copulas: [String]
            enum CodingKeys: String, CodingKey { case determiners, prepositions, copulas; case objectVerbs = "object_verbs" }
        }
        let schema: String, production: Bool, packVersion: String, pairs: [String: Pair], sourceContextSets: Context
        enum CodingKeys: String, CodingKey { case schema, production, pairs; case packVersion = "pack_version", sourceContextSets = "source_context_sets" }
    }
    enum Invalid: Error { case fixture }
    let pack: Pack
    var trace: [[String: Any]] = []
    private let words = try! NSRegularExpression(pattern: #"[\p{L}\p{Nl}\p{No}]+(?:['’][\p{L}\p{Nl}\p{No}]+)*"#)
    private let protected = try! NSRegularExpression(pattern: #"https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`"#)
    static func digest(_ value: Data) -> String { SHA256.hash(data: value).map { String(format: "%02x", $0) }.joined() }
    init(data: Data) throws {
        guard Self.digest(data) == Self.sha else { throw Invalid.fixture }
        pack = try JSONDecoder().decode(Pack.self, from: data)
        guard pack.schema == "vipi-reviewed-source-unit-native-candidate-2", !pack.production,
              pack.packVersion == Self.version, pack.pairs["en-sw"]?.entries.count == 109,
              pack.pairs["en-ja"]?.entries.count == 46, pack.pairs["en-es"]?.entries.count == 43 else { throw Invalid.fixture }
    }
    private func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
    }
    func partial(_ original: String, pair: TranslationPair, density: Double) throws -> PartialImmersionResult? {
        guard pair.source == "en", density.isFinite, density > 0, original.utf16.count <= 16_384,
              let entries = pack.pairs["en-" + pair.target]?.entries else { return nil }
        let text = original as NSString, range = NSRange(location: 0, length: original.utf16.count)
        let tokens = words.matches(in: original, range: range).map(\.range)
        let keys = tokens.map { fold(text.substring(with: $0)).replacingOccurrences(of: "’", with: "'") }
        let native = LocalImmersion.words(original, language: "en")
        guard let basis = NativeSourceTokenBasis(original: original, wordRanges: native), basis.count > 0 else { return nil }
        let budget = max(1, Int(Double(basis.count) * min(density, 1)))
        let protectedRanges = protected.matches(in: original, range: range).map(\.range)
        let leftContexts = Set(pack.sourceContextSets.determiners + pack.sourceContextSets.prepositions + pack.sourceContextSets.objectVerbs)
        let copulas = Set(pack.sourceContextSets.copulas)
        struct Candidate { let entry: Entry, range: NSRange, cost: Int, ordinal: Int }
        var found: [Candidate] = []
        func gap(_ from: Int, _ to: Int) -> String { text.substring(with: NSRange(location: from, length: to-from)) }
        for (i, token) in tokens.enumerated() {
            for entry in entries {
                let j = i + entry.sourceTokens.count
                guard j <= tokens.count, Array(keys[i..<j]) == entry.sourceTokens else { continue }
                let unit = NSRange(location: token.location, length: NSMaxRange(tokens[j-1])-token.location)
                let source = text.substring(with: unit), first = text.substring(with: token)
                var prefix = text.substring(to: token.location).trimmingCharacters(in: .whitespacesAndNewlines)
                while let last = prefix.last, "\"'“”‘’".contains(last) { prefix.removeLast() }
                let initial = prefix.isEmpty || ".!?".contains(prefix.last!)
                var reason: String?
                if protectedRanges.contains(where: { NSIntersectionRange($0, unit).length > 0 }) { reason = "protected_identifier_or_code" }
                else if keys[i] != "i", first.count > 1, first == first.uppercased(), first != first.lowercased() { reason = "uppercase_identifier" }
                else if keys[i] != "i", first.first?.isUppercase == true, !initial { reason = "mid_sentence_capital" }
                else if entry.guardValue == "interrogative" {
                    if !initial { reason = "question_not_sentence_initial" }
                    else if j >= keys.count || !(entry.following ?? []).contains(keys[j]) { reason = "question_right_context_absent" }
                    else if (i..<j).contains(where: { k in
                        !gap(NSMaxRange(tokens[k]), tokens[k+1].location).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    }) { reason = "noncontiguous_question_context" }
                } else if entry.guardValue == "ordinary_noun_context" {
                    let left = i > 0 && gap(NSMaxRange(tokens[i-1]), token.location).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? keys[i-1] : ""
                    let right = j < keys.count ? keys[j] : ""
                    if !leftContexts.contains(left) && !(initial && copulas.contains(right)) { reason = "noun_context_absent" }
                }
                let touched = native.filter { NSIntersectionRange($0, unit).length > 0 }
                let cost = basis.cost(for: unit)
                if reason == nil && (cost == nil || touched.first?.location != unit.location || touched.last.map(NSMaxRange) != NSMaxRange(unit)) {
                    reason = "partial_native_word"
                }
                if reason == nil && fold(source.precomposedStringWithCompatibilityMapping) == fold(entry.target.precomposedStringWithCompatibilityMapping) { reason = "unchanged_normalized_face" }
                if reason == nil && pair.target == "ja" && (entry.reading?.isEmpty ?? true) { reason = "missing_reading" }
                if reason == nil && (cost ?? Int.max) > budget { reason = "native_density_budget" }
                let ordinal = trace.count
                trace.append(["entry_id": entry.id, "source": source, "target": entry.target,
                    "source_range_utf16": [unit.location, NSMaxRange(unit)], "native_source_tokens": cost as Any? ?? NSNull(),
                    "budget": budget, "reason": reason as Any? ?? NSNull(), "selected": false])
                if reason == nil, let cost { found.append(.init(entry: entry, range: unit, cost: cost, ordinal: ordinal)) }
            }
        }
        found.sort {
            if ($0.entry.category == "content") != ($1.entry.category == "content") { return $0.entry.category == "content" }
            if $0.entry.trainRank != $1.entry.trainRank { return $0.entry.trainRank < $1.entry.trainRank }
            if $0.entry.sourceTokens.count != $1.entry.sourceTokens.count { return $0.entry.sourceTokens.count > $1.entry.sourceTokens.count }
            return $0.range.location < $1.range.location
        }
        guard let chosen = found.first else { return nil }
        let unit = SourceReferenceUnit(range: chosen.range, original: text.substring(with: chosen.range),
            translated: chosen.entry.target, reading: chosen.entry.reading,
            referenceID: Self.version + ":" + chosen.entry.id, catalogSHA256: Self.sha, nativeSourceTokens: chosen.cost)
        let partial = SourceReferencePresentation.create(original: original, target: pair.target, units: [unit],
            density: density, nativeSourceTokenCount: basis.count)
        trace[chosen.ordinal]["selected"] = partial != nil
        if partial == nil { trace[chosen.ordinal]["reason"] = "source_reference_validation" }
        return partial
    }
}

@MainActor final class ConversationImmersionTests: XCTestCase {

    func testFrozenJapaneseNativeGuardCapture() throws {
        struct Input: Decodable {
            struct Row: Decodable { let id: String, text: String, group: String }
            let schema: String, cases: [Row]
        }
        struct Observation: Encodable { let result: JapaneseFullReading.Result, milliseconds: Double }
        struct Row: Encodable { let id: String, source: String, group: String; let first: Observation, warm: Observation }
        struct Report: Encodable {
            let schema = "vipi-apple-japanese-reading-native-1"
            let platform = "iOS Simulator native CF tokenizer; no translation provider or acoustic claim"
            let inputSHA256: String, os: String, policy: String, lexicalSchemes: [String]
            let requestedAssets = false, generatedAudio = false
            let peakRSSBytes: Int64, cases: [Row]
        }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let bytes = try Data(contentsOf: documents.appendingPathComponent("japanese-reading-qa-inputs.json"))
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hash, "4da6c97e071b604f11a069648d172a7c58c2e3ae1460e354747192d434193b80")
        let input = try JSONDecoder().decode(Input.self, from: bytes)
        XCTAssertEqual(input.schema, "vipi-japanese-guard-input-1"); XCTAssertEqual(input.cases.count, 32)
        let output = documents.appendingPathComponent("apple-japanese-reading-native-r01.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path), "Inspect the original capture before any rerun")
        guard !FileManager.default.fileExists(atPath: output.path) else { return }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]
        func observe(_ text: String) -> Observation {
            let start = ProcessInfo.processInfo.systemUptime
            let result = JapaneseFullReading.resolve(text)
            return .init(result: result, milliseconds: (ProcessInfo.processInfo.systemUptime - start) * 1000)
        }
        var rows: [Row] = []
        for item in input.cases {
            let first = observe(item.text), warm = observe(item.text)
            XCTAssertEqual(try encoder.encode(first.result), try encoder.encode(warm.result), item.id)
            let text = item.text as NSString
            if text.length <= 16_384 {
                var end = 0
                for piece in first.result.pieces {
                    XCTAssertEqual(piece.startUTF16, end, item.id)
                    XCTAssertEqual(Array(text.substring(with: NSRange(location: piece.startUTF16, length: piece.endUTF16-piece.startUTF16)).utf16), Array(piece.source.utf16), item.id)
                    end = piece.endUTF16
                }
                XCTAssertEqual(end, text.length, item.id)
            }
            rows.append(.init(id: item.id, source: item.text, group: item.group, first: first, warm: warm))
        }
        var usage = rusage(); _ = getrusage(RUSAGE_SELF, &usage)
        let report = Report(inputSHA256: hash, os: ProcessInfo.processInfo.operatingSystemVersionString,
            policy: JapaneseFullReading.policy,
            lexicalSchemes: NLTagger.availableTagSchemes(for: .word, language: .japanese).map(\.rawValue).sorted(),
            peakRSSBytes: Int64(usage.ru_maxrss), cases: rows)
        try encoder.encode(report).write(to: output, options: .atomic)
    }

    func testJapaneseDefaultReadingCachesMetadataAndKeepsOriginalSpeech() async throws {
        XCTAssertEqual(FullSentenceReadings.resolve("水が必要です。", language: "ja"),
            .init(text: "Mizu ga hitsuyō desu.", provenance: .authored))
        XCTAssertNil(FullSentenceReadings.resolve("𠮷先生に会う。", language: "ja"))
        XCTAssertEqual(FullSentenceReadings.resolve("JoséとZoëに会った。", language: "ja")?.text, "José to Zoë ni atta。")
        let calls = FullReadingInvocationQA()
        let owner = ConversationImmersion(modelStatus: { _ in .installed }, fullTranslationTimeout: .seconds(2),
            fullReadingProducer: { text, language in await calls.record(); return FullSentenceReadings.resolve(text, language: language) })
        defer { owner.close() }
        await owner.configure(pair: .init(source: "en", target: "ja"), density: 0.25)
        let source = "I sent a message to Zoë and José.", target = "ZoëとJoséにメッセージを送った。"
        owner.selectInputLanguage("en", for: "japanese-reading-cache")
        let identity = owner.identity(messageID: "japanese-reading-cache", text: source)
        let task = Task { await owner.fullTranslation(for: identity) }
        let request = try await pending(owner)
        // Supplied target qualifies metadata/cache/speech routing, not inference.
        await owner.finish(request, translation: target)
        let completion = await task.value; let result = try XCTUnwrap(completion?.result)
        let reading = try await awaitReading(owner, result: result, identity: identity)
        XCTAssertEqual(reading, .init(text: "Zoë to José ni messēji wo okutta。", provenance: .localTransliteration))
        for _ in 0..<100 { XCTAssertEqual(owner.fullReading(for: result, identity: identity), reading) }
        _ = await owner.fullTranslation(for: identity)
        let count = await calls.count; XCTAssertEqual(count, 1)
        XCTAssertEqual(result.speech(mode: .fullTarget, source: "en", target: "ja"), [.init(text: target, language: "ja")])
        XCTAssertEqual(result.speech(mode: .original, source: "en", target: "ja"), [.init(text: source, language: "en")])
    }

    func testFrozenKoreanNativeGuardCapture() throws {
        struct Input: Decodable {
            struct Row: Decodable { let id: String, text: String, group: String, expected_guard: String }
            let schema: String, cases: [Row]
        }
        struct Observation: Encodable { let result: KoreanFullReading.Result, milliseconds: Double }
        struct Row: Encodable { let id: String, source: String, group: String; let first: Observation, warm: Observation }
        struct Report: Encodable {
            let schema = "vipi-apple-korean-reading-native-1"
            let platform = "iOS Simulator native CF tokenizer; no translation provider or acoustic claim"
            let inputSHA256: String, os: String, policy: String, lexicalSchemes: [String]
            let requestedAssets = false, generatedAudio = false
            let peakRSSBytes: Int64, cases: [Row]
        }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let bytes = try Data(contentsOf: documents.appendingPathComponent("korean-reading-qa-inputs.json"))
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hash, "b18de78e591117543a5475705e19a52e1707e45097f1c355bfd79ab856c8a155")
        let input = try JSONDecoder().decode(Input.self, from: bytes)
        XCTAssertEqual(input.schema, "vipi-korean-guard-input-1"); XCTAssertEqual(input.cases.count, 32)
        let output = documents.appendingPathComponent("apple-korean-reading-native-r01.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path), "Inspect the original capture before any rerun")
        guard !FileManager.default.fileExists(atPath: output.path) else { return }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]
        func observe(_ text: String) -> Observation {
            let start = ProcessInfo.processInfo.systemUptime
            let result = KoreanFullReading.resolve(text)
            return .init(result: result, milliseconds: (ProcessInfo.processInfo.systemUptime - start) * 1000)
        }
        var rows: [Row] = []
        for item in input.cases {
            let first = observe(item.text), warm = observe(item.text)
            XCTAssertEqual(try encoder.encode(first.result), try encoder.encode(warm.result), item.id)
            XCTAssertEqual(first.result.reading != nil, item.expected_guard == "reading", item.id)
            let text = item.text as NSString
            if text.length <= 16_384 {
                var end = 0
                for piece in first.result.pieces {
                    XCTAssertEqual(piece.startUTF16, end, item.id)
                    XCTAssertEqual(Array(text.substring(with: NSRange(location: piece.startUTF16, length: piece.endUTF16-piece.startUTF16)).utf16), Array(piece.source.utf16), item.id)
                    end = piece.endUTF16
                }
                XCTAssertEqual(end, text.length, item.id)
            }
            rows.append(.init(id: item.id, source: item.text, group: item.group, first: first, warm: warm))
        }
        var usage = rusage(); _ = getrusage(RUSAGE_SELF, &usage)
        let report = Report(inputSHA256: hash, os: ProcessInfo.processInfo.operatingSystemVersionString,
            policy: KoreanFullReading.policy,
            lexicalSchemes: NLTagger.availableTagSchemes(for: .word, language: .korean).map(\.rawValue).sorted(),
            peakRSSBytes: Int64(usage.ru_maxrss), cases: rows)
        try encoder.encode(report).write(to: output, options: .atomic)
    }

    func testKoreanDefaultReadingCachesMetadataAndKeepsOriginalSpeech() async throws {
        XCTAssertEqual(FullSentenceReadings.resolve("물이 필요해요.", language: "ko"),
            .init(text: "Muri piryohaeyo.", provenance: .authored))
        XCTAssertNil(FullSentenceReadings.resolve("𠮷에게 메시지를 보내요.", language: "ko"))
        XCTAssertEqual(FullSentenceReadings.resolve("José와 Zoë에게 보내요.", language: "ko")?.text, "José wa Zoë ege bonaeyo.")
        let calls = FullReadingInvocationQA()
        let owner = ConversationImmersion(modelStatus: { _ in .installed }, fullTranslationTimeout: .seconds(2),
            fullReadingProducer: { text, language in await calls.record(); return FullSentenceReadings.resolve(text, language: language) })
        defer { owner.close() }
        await owner.configure(pair: .init(source: "en", target: "ko"), density: 0.25)
        let source = "We go to school together.", target = "같이 학교에 갑니다."
        owner.selectInputLanguage("en", for: "korean-reading-cache")
        let identity = owner.identity(messageID: "korean-reading-cache", text: source)
        let task = Task { await owner.fullTranslation(for: identity) }
        let request = try await pending(owner)
        // Supplied target qualifies metadata/cache/speech routing, not inference.
        await owner.finish(request, translation: target)
        let completion = await task.value; let result = try XCTUnwrap(completion?.result)
        let reading = try await awaitReading(owner, result: result, identity: identity)
        XCTAssertEqual(reading, .init(text: "gat-i haggyoe gabnida.", provenance: .localTransliteration))
        for _ in 0..<100 { XCTAssertEqual(owner.fullReading(for: result, identity: identity), reading) }
        _ = await owner.fullTranslation(for: identity)
        let count = await calls.count; XCTAssertEqual(count, 1)
        XCTAssertEqual(result.speech(mode: .fullTarget, source: "en", target: "ko"), [.init(text: target, language: "ko")])
        XCTAssertEqual(result.speech(mode: .original, source: "en", target: "ko"), [.init(text: source, language: "en")])
    }

    private func awaitReading(_ owner: ConversationImmersion, result: ImmersionPresentation,
                              identity: ImmersionRequestIdentity) async throws -> FullReading {
        let deadline = ContinuousClock.now + .seconds(3)
        while ContinuousClock.now < deadline {
            if let reading = owner.fullReading(for: result, identity: identity) { return reading }
            try await Task.sleep(for: .milliseconds(5))
        }
        return try XCTUnwrap(owner.fullReading(for: result, identity: identity), "Reading metadata did not complete")
    }

    func testSlowReadingDoesNotDelayTranslationAudioOrAnotherRowAndCannotPublishAfterClose() async throws {
        let gate = DelayedFullReadingQA()
        let owner = ConversationImmersion(modelStatus: { _ in .unsupported }, fullReadingProducer: { text, language in
            if text == "我需要水。" { await gate.hold() }
            return SentenceReadings.reading(text, language: language).map { .init(text: $0, provenance: .authored) }
        })
        await owner.configure(pair: .init(source: "en", target: "zh"), density: 0.25)
        defer { owner.close(); Task { await gate.release() } }
        var completed = false
        var first: ImmersionPresentation?
        let request = Task { @MainActor in
            first = await owner.result(for: "I need water.", inputLanguage: "en")
            completed = true
        }
        let deadline = ContinuousClock.now + .seconds(5)
        while !completed && ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(5)) }
        // Release on failure before joining, so a regression cannot strand the
        // fixture's deliberate producer continuation or hang the test process.
        if !completed { await gate.release() }
        XCTAssertTrue(completed, "Optional reading work delayed a complete reference")
        await request.value
        let result = try XCTUnwrap(first)
        let identity = owner.identity(messageID: "slow-reading", text: "I need water.")
        XCTAssertEqual(result.translation, "我需要水。")
        XCTAssertEqual(result.speech(mode: .fullTarget, source: "en", target: "zh"), [.init(text: "我需要水。", language: "zh")])
        XCTAssertNil(owner.fullReading(for: result, identity: identity))
        let secondValue = await owner.result(for: "I like music.", inputLanguage: "en")
        let second = try XCTUnwrap(secondValue)
        let secondIdentity = owner.identity(messageID: "other-reading", text: "I like music.")
        _ = try await awaitReading(owner, result: second, identity: secondIdentity)
        let started = await gate.started; XCTAssertTrue(started)
        owner.close()
        await gate.release()
        try await Task.sleep(for: .milliseconds(30))
        XCTAssertNil(owner.fullReading(for: result, identity: identity))
        XCTAssertNil(owner.fullReading(for: second, identity: secondIdentity))
    }

    func testBundledFullReadingKeepsAuthoredPrecedenceAndOriginalSpeech() async throws {
        let file = try XCTUnwrap(Bundle.main.url(forResource: "chinese-ordinary", withExtension: "json"))
        let data = try Data(contentsOf: file)
        let reader = FullSentenceReadings(chinese: try ChineseFullReading(data: data))
        XCTAssertEqual(data.count, 773_812)
        XCTAssertEqual(FullSentenceReadings.resolve("银行行长正在走路。", language: "zh"),
                       .init(text: "yin hang hang zhang zheng zai zou lu。", provenance: .localTransliteration))
        let authored = "我需要水。"
        XCTAssertEqual(reader.reading(authored, language: "zh"),
                       .init(text: try XCTUnwrap(SentenceReadings.reading(authored, language: "zh")), provenance: .authored))
        XCTAssertNil(reader.reading("𠮷先生与𰻞字怎么读？", language: "zh"))
        XCTAssertNil(reader.reading("جملة جديدة غير معروفة.", language: "ar"))
        let literal = try XCTUnwrap(reader.reading("请打开https://例子.测试/中文?q=银行。", language: "zh"))
        XCTAssertTrue(literal.text.contains("https://例子.测试/中文?q=银行"))
        XCTAssertEqual(literal.provenance, .localTransliteration)
        let calls = FullReadingInvocationQA()
        let owner = ConversationImmersion(modelStatus: { _ in .installed }, fullTranslationTimeout: .seconds(2),
            fullReadingProducer: { text, language in await calls.record(); return reader.reading(text, language: language) })
        defer { owner.close() }
        await owner.configure(pair: .init(source: "en", target: "zh"), density: 0.25)
        let source = "I need water. Did you finish the report?", id = "candidate-full-reading"
        owner.selectInputLanguage("en", for: id)
        let partialValue = await owner.result(for: source, inputLanguage: "en", messageID: id)
        let partial = try XCTUnwrap(partialValue)
        let identity = owner.identity(messageID: id, text: source)
        XCTAssertNil(owner.fullReading(for: partial, identity: identity))
        let requestTask = Task { await owner.fullTranslation(for: identity) }
        let request = try await pending(owner)
        // Deliberately injected full translation for coordinator/reading QA;
        // this does not establish local Translation/ML Kit inference.
        let translated = "我需要水。你写完报告了吗？"
        await owner.finish(request, translation: translated)
        let completion = await requestTask.value
        let result = try XCTUnwrap(completion?.result)
        let expected = try XCTUnwrap(reader.reading(translated, language: "zh"))
        XCTAssertEqual(expected.provenance, .localTransliteration)
        let resolved = try await awaitReading(owner, result: result, identity: identity)
        XCTAssertEqual(resolved, expected)
        for _ in 0..<100 { XCTAssertEqual(owner.fullReading(for: result, identity: identity), expected) }
        _ = await owner.fullTranslation(for: identity)
        let count = await calls.count; XCTAssertEqual(count, 1)
        XCTAssertEqual(result.spans, partial.spans)
        XCTAssertEqual(result.original, source); XCTAssertEqual(result.translation, translated)
        XCTAssertEqual(result.speech(mode: .fullTarget, source: "en", target: "zh"), [.init(text: translated, language: "zh")])
        XCTAssertEqual(result.speech(mode: .original, source: "en", target: "zh"), [.init(text: source, language: "en")])
    }

    func testFullAuthoredReadingIsResolvedOnceOutsideRenderingAndClearedWithIdentity() async throws {
        let calls = FullReadingInvocationQA()
        let owner = ConversationImmersion(modelStatus: { _ in .unsupported }, fullReadingProducer: { text, language in
            await calls.record()
            return SentenceReadings.reading(text, language: language).map { FullReading(text: $0, provenance: .authored) }
        })
        await owner.configure(pair: .init(source: "en", target: "zh"), density: 0.25)
        defer { owner.close() }
        let text = "I need water.", id = "authored-reading-cache"
        let result = await owner.result(for: text, inputLanguage: "en")
        let value = try XCTUnwrap(result), translation = try XCTUnwrap(value.translation)
        let identity = owner.identity(messageID: id, text: text)
        let expected = try XCTUnwrap(SentenceReadings.reading(translation, language: "zh"))
        _ = try await awaitReading(owner, result: value, identity: identity)
        for _ in 0..<100 {
            XCTAssertEqual(owner.fullReading(for: value, identity: identity), .init(text: expected, provenance: .authored))
        }
        _ = await owner.result(for: text, inputLanguage: "en")
        let count = await calls.count, main = await calls.ranOnMainThread
        XCTAssertEqual(count, 1); XCTAssertFalse(main)
        XCTAssertEqual(value.speech(mode: .fullTarget, source: "en", target: "zh")?.map(\.text), [translation])
        owner.selectInputLanguage("en", for: id)
        XCTAssertNil(owner.fullReading(for: value, identity: identity))
        // Input-language changes invalidate metadata. A retained full-reference
        // cache hit repopulates it exactly once for the new identity.
        _ = await owner.result(for: text, inputLanguage: "en", messageID: id)
        let fresh = owner.identity(messageID: id, text: text)
        _ = try await awaitReading(owner, result: value, identity: fresh)
        XCTAssertEqual(owner.fullReading(for: value, identity: fresh)?.text, expected)
        let refreshed = await calls.count; XCTAssertEqual(refreshed, 2)
        owner.close(); XCTAssertNil(owner.fullReading(for: value, identity: fresh))
    }

    func testSourceUnitStarterBaseline() async throws { try await captureSourceUnitStarter(candidate: false) }
    func testSourceUnitStarterCandidate() async throws { try await captureSourceUnitStarter(candidate: true) }
    func testStarterSourceOnlyNativeGuardsAndReadings() throws {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let starter = try StarterSourceUnitQA(data: Data(contentsOf: root.appendingPathComponent("reviewed-source-unit-native-candidate-r02.json")))
        let sw = TranslationPair(source: "en", target: "sw")
        for text in ["I'm", "`water`", "https://example.com/water", "water@example.com", "WATER", "Meet Water later"] {
            starter.trace = []
            let result = try starter.partial(text, pair: sw, density: 0.1)
            XCTAssertFalse(result?.spans.contains { ["I", "water", "Water", "WATER"].contains($0.original) } ?? false, text)
        }
        starter.trace = []
        let guarded = try starter.partial("What kind of music?", pair: sw, density: 0.1)
        XCTAssertFalse(guarded?.spans.contains { $0.original == "What kind" } ?? false)
        XCTAssertTrue(starter.trace.contains { ($0["source"] as? String) == "What kind" && ($0["reason"] as? String) == "native_density_budget" })
        let japanese = try starter.partial("or", pair: .init(source: "en", target: "ja"), density: 0.1)
        XCTAssertEqual(japanese?.spans.first?.translated, "または")
        XCTAssertEqual(japanese?.spans.first?.romanization, "matawa")
        XCTAssertNil(japanese?.completeTranslation, "A whole-source lexical face is not a fabricated full-reference translation")
        let cost = japanese?.references.first?.nativeSourceTokens
        XCTAssertEqual(cost, japanese?.nativeSourceTokenCount)
    }

    private func captureSourceUnitStarter(candidate: Bool) async throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("This bounded capture qualifies simulator lookup with truthful provider absence")
        #else
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let protocolData = try Data(contentsOf: documents.appendingPathComponent("source-unit-starter-native-protocol-r01.json"))
        guard StarterSourceUnitQA.digest(protocolData) == "fd89fd2bf9988b657fe3f8d689f23d5554364c9c5b73675ac80ebf6a6f2e3ec6" else { throw StarterSourceUnitQA.Invalid.fixture }
        struct ProtocolValue: Decodable {
            struct Case: Decodable { let id: String; let text: String; let source: String; let target: String }
            let cases: [Case]
        }
        let cases = try JSONDecoder().decode(ProtocolValue.self, from: protocolData).cases
        XCTAssertEqual(cases.count, 240)
        let starter = try StarterSourceUnitQA(data: Data(contentsOf: documents.appendingPathComponent("reviewed-source-unit-native-candidate-r02.json")))
        let arm = candidate ? "candidate" : "baseline"
        let destination = documents.appendingPathComponent("source-unit-starter-" + arm + "-r01.jsonl")
        let summary = documents.appendingPathComponent("source-unit-starter-" + arm + "-r01-summary.json")
        if candidate {
            let previous = try Data(contentsOf: documents.appendingPathComponent("source-unit-starter-baseline-r01-summary.json"))
            let value = try XCTUnwrap(JSONSerialization.jsonObject(with: previous) as? [String: Any])
            guard value["rows"] as? Int == 240, value["complete"] as? Bool == true,
                  value["candidate_sha256"] as? String == StarterSourceUnitQA.sha else { throw StarterSourceUnitQA.Invalid.fixture }
        }
        guard !FileManager.default.fileExists(atPath: destination.path), !FileManager.default.fileExists(atPath: summary.path) else {
            return XCTFail("Preserve prior native evidence before a new capture")
        }
        FileManager.default.createFile(atPath: destination.path, contents: nil)
        let file = try FileHandle(forWritingTo: destination); defer { try? file.close() }
        var owner: ConversationImmersion?, target: String?, observed = LocalLanguageAvailability.checking
        var count = 0, complete = true
        defer { owner?.close() }
        for value in cases {
            if target != value.target {
                owner?.close(); target = value.target
                let pair = TranslationPair(source: value.source, target: value.target)
                observed = await LanguagePreparation.nativeStatus(pair)
                // No provider host/injected output is installed by this test.
                // Stop honestly if the platform acquires inference capability.
                guard observed != .installed else { complete = false; break }
                let next = ConversationImmersion()
                if candidate {
                    next.qualifySourceUnits(version: StarterSourceUnitQA.version + ":" + StarterSourceUnitQA.sha) {
                        try starter.partial($0, pair: $1, density: $2)
                    }
                }
                await next.configure(pair: pair, density: 0.10); owner = next
            }
            let current = try XCTUnwrap(owner)
            current.selectInputLanguage("en", for: value.id)
            let nativeWords = LocalImmersion.words(value.text, language: "en")
            starter.trace = []
            var invocations: [[String: Any]] = []
            for phase in ["first", "immediate_repeat"] {
                let started = ProcessInfo.processInfo.systemUptime
                _ = await current.result(for: value.text, inputLanguage: "en", messageID: value.id)
                let elapsed = (ProcessInfo.processInfo.systemUptime - started) * 1000
                let outcome = try XCTUnwrap(current.lastOutcome)
                XCTAssertEqual(outcome.localTranslationCalls, 0, "Provider absence must not fabricate an inference")
                var record: [String: Any] = ["phase": phase, "elapsed_ms": elapsed,
                    "status": outcome.status.rawValue, "origin": outcome.origin?.rawValue as Any? ?? NSNull(),
                    "model_readiness_calls": outcome.modelReadinessCalls, "translation_calls": outcome.localTranslationCalls,
                    "heavy_alignment_calls": outcome.alignmentCalls, "cache_hit": outcome.cacheHit,
                    "full_translation": outcome.result?.translation as Any? ?? NSNull(),
                    "raw_full_provider_string_if_called": NSNull()]
                let spans = outcome.result?.spans ?? []
                record["spans"] = spans.map { ["original": $0.original, "target": $0.translated,
                    "range_utf16": [$0.range.location, NSMaxRange($0.range)],
                    "target_range_utf16": [$0.targetRange.location, NSMaxRange($0.targetRange)],
                    "reading": $0.romanization as Any? ?? NSNull()] as [String: Any] }
                let changed = nativeWords.filter { word in spans.contains { NSIntersectionRange(word, $0.range) == word } }.count
                record["changed_source_words"] = changed
                record["changed_depth"] = Double(changed) / Double(max(1, nativeWords.count))
                record["whole_source_lexical_face"] = changed > 0 && changed == nativeWords.count && outcome.result?.translation == nil
                if let result = outcome.result {
                    record["mixed_text"] = result.speech(source: "en", target: value.target).map(\.text).joined()
                    if case .partial(let partial) = result {
                        record["target_coordinate_basis"] = "each_reference_local"
                        record["references"] = partial.references.map { ["id": $0.referenceID,
                            "catalog_sha256": $0.catalogSHA256, "native_source_tokens": $0.nativeSourceTokens,
                            "original": $0.original, "target": $0.translated] as [String: Any] }
                        XCTAssertEqual(outcome.modelReadinessCalls, 0); XCTAssertEqual(outcome.alignmentCalls, 0)
                        if value.target == "ja" { XCTAssertTrue(partial.spans.allSatisfy { !($0.romanization?.isEmpty ?? true) }) }
                    }
                }
                invocations.append(record)
            }
            let row: [String: Any] = ["case_id": value.id, "source": value.source, "target": value.target,
                "exact_source": value.text, "arm": arm, "requested_density": 0.10,
                "native_source_word_ranges_utf16": nativeWords.map { [$0.location, NSMaxRange($0)] },
                "native_source_word_count": nativeWords.count, "actual_native_token_budget": max(1, Int(Double(nativeWords.count) * 0.10)),
                "pair_availability": String(describing: observed), "offline_network_observation": "not disabled; no model downloads or remote translation API",
                "source_candidate_diagnostics": starter.trace, "invocations": invocations]
            var bytes = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]); bytes.append(10)
            try file.write(contentsOf: bytes); try file.synchronize(); count += 1
        }
        try JSONSerialization.data(withJSONObject: ["arm": arm, "complete": complete && count == 240, "rows": count,
            "candidate_sha256": StarterSourceUnitQA.sha, "pack_version": StarterSourceUnitQA.version,
            "protocol_sha256": StarterSourceUnitQA.digest(protocolData), "injected_provider": false,
            "physical_device": false, "production_candidate_enabled": false], options: [.prettyPrinted, .sortedKeys])
            .write(to: summary, options: .withoutOverwriting)
        XCTAssertTrue(complete); XCTAssertEqual(count, 240)
        #endif
    }

    /// Actual simulator catalog/native boundary and availability execution. The
    /// separate core tests inject provider values; this receipt never does.
    func testSourceApprovedUnitsSatisfyAutomaticImmersion() async throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("This frozen control is specifically the simulator provider-absence audit")
        #else
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = try Data(contentsOf: documents.appendingPathComponent("source-unit-routing-fixtures-r01.json"))
        XCTAssertEqual(SHA256.hash(data: input).map { String(format: "%02x", $0) }.joined(),
                       "1a2e1d5974df1053fbda0901fe268f98a2c6fde99c8076cb23bf34db667deb74")
        let protocolValue = try XCTUnwrap(JSONSerialization.jsonObject(with: input) as? [String: Any])
        let fixtures = try XCTUnwrap(protocolValue["fixtures"] as? [[String: Any]])
        let output = documents.appendingPathComponent("source-unit-routing-native-r01.json")
        guard !FileManager.default.fileExists(atPath: output.path) else { return XCTFail("Preserve the previous routing receipt") }
        let pair = TranslationPair(source: "en", target: "sw")
        let availability = await LanguagePreparation.nativeStatus(pair)
        XCTAssertEqual(availability, .unsupported)
        guard availability == .unsupported else { return }
        let catalog = BundledImmersionCatalog(), language = MessageLanguage()
        var records: [[String: Any]] = []
        func describe(_ outcome: LookupFirstOutcome?) -> [String: Any] {
            guard let outcome else { return ["outcome": NSNull()] }
            var row: [String: Any] = ["status": outcome.status.rawValue,
                "fallback": outcome.fallbackStatus?.rawValue as Any? ?? NSNull(),
                "model_checks": outcome.modelReadinessCalls, "translation_calls": outcome.localTranslationCalls,
                "heavy_alignments": outcome.alignmentCalls, "cache_hit": outcome.cacheHit,
                "translation": outcome.result?.translation as Any? ?? NSNull()]
            row["spans"] = outcome.result?.spans.map { ["source": $0.original, "target": $0.translated,
                "source_start_utf16": $0.range.location, "source_end_utf16": NSMaxRange($0.range),
                "reading": $0.romanization as Any? ?? NSNull()] as [String: Any] } ?? []
            if case .partial(let partial)? = outcome.result {
                row["references"] = partial.references.map { ["id": $0.referenceID, "catalog_sha256": $0.catalogSHA256,
                    "source": $0.original, "translation": $0.translated] }
            }
            return row
        }
        for fixture in fixtures {
            let id = try XCTUnwrap(fixture["id"] as? String), text = try XCTUnwrap(fixture["text"] as? String)
            let kind = try XCTUnwrap(fixture["kind"] as? String)
            var checks = 0, translations = 0, alignments = 0, partialEvents = 0
            let controlStarted = ProcessInfo.processInfo.systemUptime
            let control = try await FrozenSourceUnitControl.resolve(.init(text: text, source: "en", target: "sw", inputLanguage: "en"),
                valid: { true }, reference: { original, source, target in
                    try await catalog.reference(original: original, pair: .init(source: source, target: target))
                }, identify: { try await language.identify($0) }, modelsReady: { source, target in
                    checks += 1
                    return await LanguagePreparation.nativeStatus(.init(source: source, target: target)) == .installed
                }, translate: { _, _, _ in
                    translations += 1
                    XCTFail("Unsupported simulator must never enqueue native inference")
                    throw CancellationError()
                }, align: { original, translation in
                    alignments += 1
                    let supplemental = try await BundledLexicalCatalog.shared.entries(original: original, translation: translation, pair: pair)
                    return try await catalog.result(original: original, translation: translation, pair: pair, density: 0.25, supplementalEntries: supplemental)
                }, partialReference: { original, source, target in
                    try await catalog.partial(original: original, pair: .init(source: source, target: target), density: 0.25)
                }, onPartial: { _ in partialEvents += 1 })
            var controlRecord = describe(control)
            controlRecord["model_checks"] = checks; controlRecord["translation_calls"] = translations
            controlRecord["heavy_alignments"] = alignments; controlRecord["partial_events"] = partialEvents
            controlRecord["seconds"] = ProcessInfo.processInfo.systemUptime - controlStarted
            let owner = ConversationImmersion()
            await owner.configure(pair: pair, density: 0.25); owner.selectInputLanguage("en", for: id)
            var candidateRecords: [[String: Any]] = []
            for phase in ["automatic", "warm_automatic", "explicit_full", "repeated_full"] {
                let started = ProcessInfo.processInfo.systemUptime
                let outcome: LookupFirstOutcome?
                if phase.contains("full") { outcome = await owner.fullTranslation(for: owner.identity(messageID: id, text: text)) }
                else { _ = await owner.result(for: text, inputLanguage: "en", messageID: id); outcome = owner.lastOutcome }
                var value = describe(outcome); value["phase"] = phase; value["seconds"] = ProcessInfo.processInfo.systemUptime - started
                candidateRecords.append(value)
                XCTAssertEqual(outcome?.localTranslationCalls, 0)
                if kind == "approved_partial" {
                    XCTAssertFalse(outcome?.result?.spans.isEmpty ?? true)
                    XCTAssertEqual(outcome?.alignmentCalls, 0)
                    XCTAssertEqual(outcome?.modelReadinessCalls, phase.contains("full") ? 1 : 0)
                    XCTAssertNil(outcome?.result?.translation)
                } else if kind == "complete_reference" { XCTAssertNotNil(outcome?.result?.translation) }
                else { XCTAssertNil(outcome?.result) }
            }
            records.append(["id": id, "text": text, "kind": kind, "control": controlRecord, "candidate": candidateRecords])
            owner.close()
        }
        try JSONSerialization.data(withJSONObject: ["fixture_sha256": "1a2e1d5974df1053fbda0901fe268f98a2c6fde99c8076cb23bf34db667deb74",
            "native_provider": "unsupported", "physical_device": false, "injected_provider": false,
            "control_source_sha256": "e3935b5c3addc8c80280c66f2cb16b86441e35629b205a8a34fda8ff2869b092", "records": records],
            options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .withoutOverwriting)
        #endif
    }


    /// Injected readiness and completion for coordinator races only. These are
    /// not Translation/ML Kit model or language-quality qualifications.
    func testSyntheticFullExtensionCoalescesAndPreservesApprovedSpans() async throws {
        var statusChecks = 0
        let owner = ConversationImmersion(modelStatus: { _ in statusChecks += 1; return .installed }, fullTranslationTimeout: .seconds(2))
        defer { owner.close() }
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 0.25)
        let text = "I need water. Did you finish the report?", id = "synthetic-coalescing"
        owner.selectInputLanguage("en", for: id)
        owner.selectInputLanguage("en", for: "independent-partial")
        let automaticValue = await owner.result(for: text, inputLanguage: "en", messageID: id)
        let automatic = try XCTUnwrap(automaticValue)
        XCTAssertFalse(automatic.spans.isEmpty); XCTAssertEqual(statusChecks, 0)
        let identity = owner.identity(messageID: id, text: text)
        let a = Task { await owner.fullTranslation(for: identity) }
        let b = Task { await owner.fullTranslation(for: identity) }
        let request = try await pending(owner)
        try await Task.sleep(for: .milliseconds(20))
        XCTAssertEqual(owner.request?.id, request.id); XCTAssertEqual(statusChecks, 1)
        let independent = await owner.result(for: "Did you finish the report? I need water.",
            inputLanguage: "en", messageID: "independent-partial")
        XCTAssertFalse(independent?.spans.isEmpty ?? true)
        XCTAssertEqual(owner.lastOutcome?.modelReadinessCalls, 0)
        XCTAssertEqual(owner.request?.id, request.id, "A pending full request must not block or consume another row's partial")
        XCTAssertEqual(statusChecks, 1)
        let syntheticTarget = "Ninahitaji maji. Je, umemaliza ripoti?"
        await owner.finish(request, translation: syntheticTarget)
        let first = await a.value, second = await b.value
        XCTAssertEqual(first?.result?.translation, syntheticTarget); XCTAssertEqual(second?.result?.translation, syntheticTarget)
        XCTAssertEqual(first?.result?.spans, automatic.spans); XCTAssertEqual(second?.result?.spans, automatic.spans)
        XCTAssertEqual(first?.alignmentCalls, 0); XCTAssertNil(owner.request)
        let cached = await owner.fullTranslation(for: identity)
        XCTAssertEqual(cached?.localTranslationCalls, 0); XCTAssertTrue(cached?.cacheHit ?? false)
        XCTAssertEqual(statusChecks, 1)
    }
    func testSyntheticFullExtensionTimeoutAndCancellationKeepPartial() async throws {
        let text = "I need water. Did you finish the report?", id = "synthetic-cancellation"
        let timed = ConversationImmersion(modelStatus: { _ in .installed }, fullTranslationTimeout: .milliseconds(60))
        await timed.configure(pair: .init(source: "en", target: "sw"), density: 0.25)
        timed.selectInputLanguage("en", for: id)
        let partial = await timed.result(for: text, inputLanguage: "en", messageID: id)
        let timedOutcome = await timed.fullTranslation(for: timed.identity(messageID: id, text: text))
        XCTAssertEqual(timedOutcome?.fallbackStatus, .error); XCTAssertEqual(timedOutcome?.result?.spans, partial?.spans)
        XCTAssertNil(timedOutcome?.result?.translation); XCTAssertNil(timed.request); timed.close()
        let owner = ConversationImmersion(modelStatus: { _ in .installed }, fullTranslationTimeout: .seconds(2))
        defer { owner.close() }
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 0.25)
        owner.selectInputLanguage("en", for: id)
        _ = await owner.result(for: text, inputLanguage: "en", messageID: id)
        let identity = owner.identity(messageID: id, text: text)
        let task = Task { await owner.fullTranslation(for: identity) }
        let old = try await pending(owner); task.cancel()
        let cancelled = await task.value; XCTAssertNil(cancelled); XCTAssertNil(owner.request)
        XCTAssertEqual(owner.cached(text, messageID: id)?.spans, partial?.spans)
        let retry = Task { await owner.fullTranslation(for: identity) }
        let current = try await pending(owner); XCTAssertNotEqual(current.id, old.id)
        await owner.finish(old, translation: "An ignored stale synthetic response")
        XCTAssertEqual(owner.request?.id, current.id)
        owner.selectInputLanguage("sw", for: id)
        let invalidated = await retry.value; XCTAssertNil(invalidated); XCTAssertNil(owner.request)
    }

    /// Functional routing evidence for the separately frozen live conversation.
    /// Missing simulator ML Kit is an observed result, never a replay provider.
    func testFrozenLivePeerSwahiliRoutingWritesActualOutcomes() async throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("This receipt is specifically the simulator capability control")
        #else
        let texts = ["I need water.", "I am drinking coffee now.", "Can you meet me after work?",
            "I will be home in twenty minutes.", "Do you want to listen to some music?",
            "I like music.", "Let's have lunch tomorrow.", "That sounds good. See you soon."]
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("live-peer-sw-routing-r01.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path), "Retain the prior receipt before rerunning")
        guard !FileManager.default.fileExists(atPath: output.path) else { return }
        let pair = TranslationPair(source: "en", target: "sw")
        let observedAvailability = await LanguagePreparation.nativeStatus(pair)
        XCTAssertEqual(observedAvailability, .unsupported)
        let owner = ConversationImmersion()
        await owner.configure(pair: pair, density: 0.25)
        defer { owner.close() }
        func presentation(_ value: ImmersionPresentation) -> [String: Any] {
            var record: [String: Any] = ["original": value.original,
                "full_translation": value.translation as Any? ?? NSNull(),
                "mixed_text": value.speech(source: "en", target: "sw").map(\.text).joined(),
                "mixed_speech_spans": value.speech(source: "en", target: "sw").map { ["text": $0.text, "language": $0.language] },
                "spans": value.spans.map { span -> [String: Any] in
                    ["source_range_utf16": [span.range.location, NSMaxRange(span.range)],
                     "source": span.original, "target": span.translated,
                     "target_range_utf16": [span.targetRange.location, NSMaxRange(span.targetRange)],
                     "romanization": span.romanization as Any? ?? NSNull()]
                }]
            switch value {
            case .complete:
                record["kind"] = "complete"
                record["target_range_basis"] = "full_translation"
            case .partial(let partial):
                record["kind"] = "partial"
                record["target_range_basis"] = "corresponding_reference_translated"
                record["native_source_token_count"] = partial.nativeSourceTokenCount
                record["references"] = partial.references.map { reference -> [String: Any] in
                    ["source": reference.original, "translated": reference.translated,
                     "source_range_utf16": [reference.range.location, NSMaxRange(reference.range)],
                     "reference_id": reference.referenceID, "catalog_sha256": reference.catalogSHA256,
                     "native_source_tokens": reference.nativeSourceTokens,
                     "reading": reference.reading as Any? ?? NSNull()]
                }
            }
            return record
        }
        var rows: [[String: Any]] = []
        let runStarted = ContinuousClock.now
        var timedOut = false
        for pass in ["first_in_owner", "warm_repeat"] {
            for (index, text) in texts.enumerated() {
                let started = ContinuousClock.now
                var partials: [[String: Any]] = []
                let task = Task { @MainActor in
                    await owner.result(for: text) { partial in partials.append(presentation(.partial(partial))) }
                }
                let watchdog = Task { @MainActor in
                    do { try await Task.sleep(for: .seconds(15)) }
                    catch { return }
                    timedOut = true
                    task.cancel()
                }
                let value = await task.value
                watchdog.cancel()
                let elapsed = started.duration(to: .now).components
                let outcome = owner.lastOutcome
                rows.append(["id": String(format: "live-sw-peer-r01-%02d", index + 1), "text": text,
                    "pass": pass, "input_language": "auto", "density": 0.25,
                    "elapsed_ms": Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15,
                    "availability_after": String(describing: owner.availability),
                    "lexical_preparation": owner.lexicalPreparation,
                    "status": outcome?.status.rawValue as Any? ?? NSNull(),
                    "origin": outcome?.origin?.rawValue as Any? ?? NSNull(),
                    "fallback_status": outcome?.fallbackStatus?.rawValue as Any? ?? NSNull(),
                    "local_translation_calls": outcome?.localTranslationCalls as Any? ?? NSNull(),
                    "cache_hit": outcome?.cacheHit as Any? ?? NSNull(),
                    "result": value.map(presentation) as Any? ?? NSNull(),
                    "partial_events": partials, "timed_out": timedOut])
                XCTAssertNil(owner.request, "Unsupported simulator must not enqueue a fabricated provider")
                XCTAssertEqual(outcome?.localTranslationCalls ?? 0, 0)
                if timedOut { break }
            }
            if timedOut { break }
        }
        let elapsed = runStarted.duration(to: .now).components
        var voices: [[String: Any]] = []
        for language in ["en", "sw"] {
            do {
                let voice = try LocalVoice(language: language)
                voices.append(["language": language, "identifier": voice.identifier, "synthesis_requested": false])
            } catch {
                voices.append(["language": language, "error": String(describing: error), "synthesis_requested": false])
            }
        }
        let speechRoot = MessageSpeechCache.directory
        let cachedURLs = (try? FileManager.default.contentsOfDirectory(at: speechRoot,
            includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey, .isRegularFileKey])) ?? []
        var cachedFiles: [[String: Any]] = []
        for file in cachedURLs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) where file.pathExtension.lowercased() == "caf" {
            let metadata = try file.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey, .isRegularFileKey])
            guard metadata.isRegularFile == true else { continue }
            var entry: [String: Any] = ["filename": file.lastPathComponent,
                "bytes": metadata.fileSize as Any? ?? NSNull(),
                "modified_unix": metadata.contentModificationDate?.timeIntervalSince1970 as Any? ?? NSNull()]
            if (metadata.fileSize ?? Int.max) <= 50 * 1024 * 1024 {
                let bytes = try Data(contentsOf: file, options: .mappedIfSafe)
                entry["sha256"] = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            } else { entry["hash_status"] = "larger_than_50MiB_read_bound" }
            cachedFiles.append(entry)
        }
        let report: [String: Any] = ["schema": "vipi-live-peer-sw-routing-1",
            "protocol_sha256": "4ccee4cd1b9e79a60e018902af278e85bc34377c75162eef066960b6aa4d0e6e",
            "provider_injection": false, "model_preparation_requested": false,
            "simulator": true, "native_pair_availability": String(describing: observedAvailability),
            "coverage_claim": false, "semantic_acceptance": false,
            "voices": voices, "existing_speech_cache_directory": speechRoot.path,
            "existing_speech_cache_files": cachedFiles,
            "speech_cache_observation": "Read-only enumeration and bounded hashing after routing; this test never renders or plays audio.",
            "timing_caveat": "First owner invocation is not a guaranteed process/model cold start; warm repeat retains conversation cache.",
            "elapsed_ms": Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15,
            "complete": rows.count == 16 && !timedOut, "rows": rows]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: output, options: .withoutOverwriting)
        XCTAssertFalse(timedOut)
        XCTAssertEqual(rows.count, 16)
        #endif
    }

    func testInputLanguageChoiceBelongsToMessageAndSurvivesRowRecreation() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        let text = "Ninapenda muziki."
        owner.selectInputLanguage("sw", for: "message-one")
        let value = await owner.result(for: text, inputLanguage: owner.inputLanguage(for: "message-one"))
        XCTAssertNotNil(value)
        XCTAssertEqual(owner.cached(text, messageID: "message-one"), value)
        XCTAssertNil(owner.cached(text, messageID: "message-two"))
        XCTAssertNil(owner.inputLanguage(for: "message-two"))
        owner.selectInputLanguage("de", for: "message-one")
        XCTAssertEqual(owner.inputLanguage(for: "message-one"), "sw")
        owner.selectInputLanguage(nil, for: "message-one")
        XCTAssertNil(owner.inputLanguage(for: "message-one"))
        owner.selectInputLanguage("sw", for: "message-one")
        owner.close()
        XCTAssertNil(owner.inputLanguage(for: "message-one"))
        XCTAssertNil(owner.cached(text, messageID: "message-one"))
    }
    func testLearningLanguageReferencesUseNativeBaselineWithoutChangingTargetText() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        defer { owner.close() }
        let result = await owner.result(for: "Ninapenda muziki.")
        let value = try XCTUnwrap(result)
        XCTAssertEqual(value.original, "I like music.")
        XCTAssertEqual(value.translation, "Ninapenda muziki.")
        XCTAssertEqual(value.speech(source: "en", target: "sw").map(\.text).joined(), "I like muziki.")
        let forced = await owner.result(for: "Ninapenda muziki.", inputLanguage: "sw")
        XCTAssertEqual(forced, value)
        let unsupported = await owner.result(for: "Ninapenda muziki.", inputLanguage: "de")
        XCTAssertNil(unsupported)
    }

    func testBundledClassifierRecognizesElevenNativeParagraphsAndRejectsShortInput() async throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Bundled ML Kit language identification requires physical arm64")
        #else
        let examples = try XCTUnwrap(ConversationExamples.examples)
        let identifier = MessageLanguage()
        var results: [String: String] = [:]
        for language in VipiLanguage.initial {
            let text = try XCTUnwrap(examples.languages[language.id]?.text)
            let guess = try await identifier.identify(text)
            results[language.id] = guess ?? "und"
            XCTAssertEqual(guess, language.id)
        }
        for text in ["ok", "no", "42", "🙂"] {
            let guess = try await identifier.identify(text); XCTAssertNil(guess)
        }
        let path = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("message-language-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: path.path))
        try JSONSerialization.data(withJSONObject: ["authored_paragraphs":results, "independent_accuracy":false], options: [.prettyPrinted, .sortedKeys]).write(to: path, options: .withoutOverwriting)
        #endif
    }

    func testUnseenSwahiliUsesActualReverseTranslatorAndKeepsNativeSentence() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        guard owner.availability == .installed else { throw XCTSkip("Requires explicitly prepared physical Swahili models") }
        defer { owner.close() }
        let task = Task { await owner.result(for: "Tunakunywa maji sasa.") }
        let request = try await pending(owner)
        XCTAssertEqual(request.pair.source, "sw"); XCTAssertEqual(request.pair.target, "en")
        await owner.translateSwahili(request)
        let result = await task.value
        let value = try XCTUnwrap(result)
        XCTAssertEqual(value.translation, "Tunakunywa maji sasa.")
        XCTAssertTrue(value.spans.contains { $0.original.lowercased() == "water" && $0.translated == "maji" })
        let short = await owner.result(for: "ok"); XCTAssertNil(short)
        let foreign = await owner.result(for: "Das ist ein langer deutscher Satz über unsere gemeinsame Reise.")
        XCTAssertNil(foreign)
    }

    private func pending(_ owner: ConversationImmersion) async throws -> ConversationImmersion.Request {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while ContinuousClock.now < deadline {
            if let request = owner.request { return request }
            try await Task.sleep(for: .milliseconds(10))
        }
        return try XCTUnwrap(owner.request, "The installed pair should enqueue local translation")
    }

    func testCancellationAndLanguageChangesNeverApplyStaleTranslation() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        guard owner.availability == .installed else { throw XCTSkip("Requires explicitly prepared physical-device Swahili models") }
        defer { owner.close() }
        let cancelled = Task { await owner.result(for: "We are drinking water now.") }
        let old = try await pending(owner)
        cancelled.cancel()
        let cancelledValue = await cancelled.value
        XCTAssertNil(cancelledValue)
        XCTAssertNil(owner.request)

        let current = Task { await owner.result(for: "We are drinking water now.") }
        let active = try await pending(owner)
        XCTAssertNotEqual(active.id, old.id)
        await owner.finish(old, translation: "Ninakunywa maji sasa.")
        XCTAssertEqual(owner.request?.id, active.id, "A cancelled reply must not finish the next request")
        await owner.finish(active, translation: "Tunakunywa maji sasa.")
        let value = await current.value
        XCTAssertEqual(value?.speech(source: "en", target: "sw").map(\.text).joined(), "We are drinking maji now.")

        let switching = Task { await owner.result(for: "They are drinking water now.") }
        let stale = try await pending(owner)
        await owner.configure(pair: .init(source: "en", target: "es"), density: 1)
        let switchedValue = await switching.value
        XCTAssertNil(switchedValue)
        await owner.finish(stale, translation: "Wanakunywa maji sasa.")
        XCTAssertNil(owner.request)
        let spanish = await owner.result(for: "I like music.")
        XCTAssertEqual(spanish?.translation, "Me gusta la música.")
    }

    func testLocalReferenceParagraphsWorkWithoutAnAttachedTranslationTask() async throws {
        let owner = ConversationImmersion()
        await owner.configure(pair: .init(source: "en", target: "sw"), density: 1)
        defer { owner.close() }
        let original = "I like music.\nI am drinking water now."
        let value = await owner.result(for: original)
        XCTAssertEqual(value?.translation, "Ninapenda muziki.\nNinakunywa maji sasa.")
        XCTAssertEqual(value?.original, original)
        XCTAssertNil(owner.request)
    }
}

// Frozen routing control e3935b5c; only enum visibility/name changed. No alternate catalog or provider.
private enum FrozenSourceUnitControl {
    @MainActor static func resolve(
        _ request: LookupFirstRequest, valid: () -> Bool,
        reference: (String, String, String) async throws -> String?,
        identify: (String) async throws -> String?,
        modelsReady: (String, String) async throws -> Bool,
        translate: (String, String, String) async throws -> String,
        align: (String, String) async throws -> ImmersionResult,
        partialReference: (String, String, String) async throws -> PartialImmersionResult? = { _, _, _ in nil },
        onPartial: (PartialImmersionResult) -> Void = { _ in }
    ) async throws -> LookupFirstOutcome {
        var calls = 0
        var origin: ImmersionOrigin?
        var partial: PartialImmersionResult?
        func stop(_ status: ImmersionStatus) -> LookupFirstOutcome {
            if let partial, valid(), status != .stale {
                return .init(result: .partial(partial), origin: .sourceReferencePartial, status: .partial,
                             localTranslationCalls: calls, fallbackStatus: status)
            }
            return .init(result: nil, origin: origin, status: status, localTranslationCalls: calls, fallbackStatus: nil)
        }
        guard valid() else { return stop(.stale) }
        let text = request.text, source = request.source, target = request.target, input = request.inputLanguage
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf16.count <= 16_384,
              source != target, input == nil || input == source || input == target else { return stop(.invalidInput) }
        do {
            let forward = input != target ? try await reference(text, source, target) : nil
            guard valid() else { return stop(.stale) }
            let reverse = forward == nil && input != source ? try await reference(text, target, source) : nil
            guard valid() else { return stop(.stale) }
            let sourcePartial = forward == nil && reverse == nil && input != target
                ? try await partialReference(text, source, target) : nil
            guard valid() else { return stop(.stale) }
            let detected: String?
            if forward != nil { detected = source }
            else if reverse != nil { detected = target }
            else if let input { detected = input }
            else { detected = try await identify(text) }
            guard valid() else { return stop(.stale) }
            guard detected == source || detected == target else { return stop(.invalidLanguage) }
            if detected == source, let sourcePartial {
                guard sourcePartial.original == text,
                      SourceReferencePresentation.validPartial(sourcePartial, target: target) else { return stop(.invalidResult) }
                partial = sourcePartial; onPartial(sourcePartial)
            }
            guard valid() else { return stop(.stale) }
            let reversed = detected == target
            let known = forward ?? reverse
            let from = reversed ? target : source, to = reversed ? source : target
            if known == nil {
                let ready = try await modelsReady(from, to)
                guard valid() else { return stop(.stale) }
                guard ready else { return stop(.modelNotReady) }
            }
            guard valid() else { return stop(.stale) }
            origin = known != nil ? .lookupReference : .localFullContext
            let translated: String
            if let known { translated = known }
            else { calls += 1; translated = try await translate(text, from, to) }
            guard valid() else { return stop(.stale) }
            guard !translated.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  translated.utf16.count <= 32_768,
                  TranslationIntegrity.preservesIdentifiers(original: text, translation: translated) else { return stop(.invalidResult) }
            let original = reversed ? translated : text
            let targetText = reversed ? text : translated
            let result = try await align(original, targetText)
            guard valid() else { return stop(.stale) }
            guard result.original == original, result.translation == targetText, anchored(result) else { return stop(.invalidResult) }
            if let partial {
                return .init(result: .partial(partial.withCompleteTranslation(targetText)), origin: .sourceReferencePartial,
                             status: .partial, localTranslationCalls: calls, fallbackStatus: .ready)
            }
            return .init(result: .complete(result), origin: origin, status: .ready,
                         localTranslationCalls: calls, fallbackStatus: nil)
        } catch is CancellationError { throw CancellationError() }
        catch { return stop(valid() ? .error : .stale) }
    }

    private static func anchored(_ result: ImmersionResult) -> Bool {
        let source = result.original as NSString, target = result.translation as NSString
        var end = 0
        for span in result.spans {
            guard span.range.location >= end, span.range.location <= source.length,
                  span.range.length > 0, span.range.length <= source.length-span.range.location,
                  span.targetRange.location >= 0, span.targetRange.location <= target.length,
                  span.targetRange.length > 0, span.targetRange.length <= target.length-span.targetRange.location,
                  Range(span.range, in: result.original) != nil, Range(span.targetRange, in: result.translation) != nil,
                  source.substring(with: span.range) == span.original,
                  target.substring(with: span.targetRange) == span.translated else { return false }
            end = NSMaxRange(span.range)
        }
        return true
    }
}
