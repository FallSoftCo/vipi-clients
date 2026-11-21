import CryptoKit
import SwiftUI
import VipiCore
import XCTest
@testable import Vipi

@MainActor final class SwahiliConversationCoverageTests: XCTestCase {
    func testSwahiliTurnUsesSelectedModeAndKeepsAuthoredOriginal() async throws {
        let pair = TranslationPair(source: "sw", target: "en")
        let original = "maji!"
        var requests: [String] = []
        let owner = ConversationImmersion(modelStatus: { requested in
            XCTAssertEqual(requested, pair)
            return .installed
        }, nativeTranslation: { text, requested in
            XCTAssertEqual(requested, pair)
            requests.append(text)
            switch text {
            case original: return "Water!"
            case "maji": return "water"
            default: XCTFail("Unexpected SDK input \(text)"); throw ConversationImmersion.ProviderError.unavailable
            }
        })
        defer { owner.close() }
        for mode in [ImmersionMode.incremental, .fullMessages] {
            await owner.configure(pair: pair, mode: mode)
            owner.selectInputLanguage("sw", for: "turn")
            let identity = owner.identity(messageID: "turn", text: original)
            let received = await owner.translatedMessage(for: identity)
            let value = try XCTUnwrap(received)
            XCTAssertEqual(value.original, original)
            XCTAssertEqual(value.meaningText, original)
            XCTAssertEqual(value.practiceLanguage, "en")
            if mode == .incremental {
                XCTAssertEqual(value.words?.map(\.source), ["maji"])
                XCTAssertEqual(value.practiceText, "water!")
                XCTAssertEqual(value.practiceSpeech.map(\.text), ["water"])
            } else {
                XCTAssertNil(value.words)
                XCTAssertEqual(value.practiceText, "Water!")
                XCTAssertEqual(value.practiceSpeech.map(\.text), ["Water!"])
            }
        }
        XCTAssertEqual(requests, ["maji", original])
    }

    func testFrozenTurnsThroughInstalledProvidersInBothModes() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["VIPI_SWAHILI_CORPUS"] == "1",
                          "Run test-ipad-swahili-coverage.sh with the frozen AfriWOZ corpus and installed models")
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let bytes = try Data(contentsOf: documents.appendingPathComponent("afriwoz-probe-001.json"))
        let output = documents.appendingPathComponent("swahili-conversation-modes-001.json")
        guard !FileManager.default.fileExists(atPath: output.path) else {
            throw CocoaError(.fileWriteFileExists)
        }
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let frozenDigest = "3886fca840451c66767748a6afdd1a317d1dba917e89c9bf4d9bc56842c54ba0"
        let verifiedDigest = try XCTUnwrap(digest == frozenDigest ? digest : nil, "Expected the frozen 241-turn AfriWOZ test split")
        let corpus = try JSONDecoder().decode(Corpus.self, from: bytes)
        let targets = ["en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko"]
        XCTAssertEqual(corpus.schema, "vipi-afriwoz-probe-1")
        XCTAssertEqual(corpus.targets, targets)
        XCTAssertFalse(corpus.cases.isEmpty)
        XCTAssertEqual(Set(corpus.cases.map(\.id)).count, corpus.cases.count)

        let owner = ConversationImmersion()
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previousWindow = scene.windows.first(where: \.isKeyWindow)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = UIHostingController(rootView: ConversationTranslationTask(immersion: owner))
        window.makeKeyAndVisible()
        defer { owner.close(); window.isHidden = true; previousWindow?.makeKeyAndVisible() }
        var rows: [Row] = []
        for target in targets {
            let pair = TranslationPair(source: "sw", target: target)
            let capability = await LocalTranslationCapability.resolve(pair)
            let provider = try XCTUnwrap(capability.availability == .installed ? capability.provider : nil,
                                         "Preinstall the local sw → \(target) provider before evaluating the corpus")
            for mode in [ImmersionMode.incremental, .fullMessages] {
                await owner.configure(pair: pair, mode: mode)
                for turn in corpus.cases {
                    let original = try XCTUnwrap(turn.text["sw"])
                    owner.selectInputLanguage("sw", for: turn.id)
                    let id = owner.identity(messageID: turn.id, text: original)
                    let begin = ContinuousClock.now
                    let received = await owner.translatedMessage(for: id)
                    let value = try XCTUnwrap(received, "\(turn.id), sw → \(target), \(mode)")
                    XCTAssertEqual(value.original, original)
                    XCTAssertEqual(value.meaningText, original)
                    XCTAssertEqual(value.inputLanguage, "sw")
                    XCTAssertEqual(value.practiceLanguage, target)
                    XCTAssertFalse(value.practiceText.isEmpty)
                    XCTAssertEqual(value.words == nil, mode == .fullMessages)
                    for word in value.words ?? [] where FullReadingRequirement.needsReading(word.target) {
                        XCTAssertFalse(word.reading?.isEmpty ?? true, "Missing reading for an introduced word")
                    }
                    let duration = begin.duration(to: .now).components
                    rows.append(Row(id: turn.id, target: target, mode: mode.rawValue,
                                    provider: String(describing: provider), value: value,
                                    identifierIntegrity: TranslationIntegrity.preservesIdentifiers(
                                        original: original, translation: value.practiceText),
                                    elapsedMilliseconds: Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15))
                }
            }
        }
        XCTAssertEqual(rows.count, corpus.cases.count * targets.count * 2)
        let report = Report(corpusSHA256: verifiedDigest, rows: rows)
        try JSONEncoder().encode(report).write(to: output, options: .withoutOverwriting)
    }

    private struct Corpus: Decodable {
        struct Turn: Decodable { let id: String; let text: [String: String] }
        let schema: String
        let targets: [String]
        let cases: [Turn]
    }

    private struct Row: Encodable {
        let id, target, mode, provider: String
        let value: FullMessageTranslation
        let identifierIntegrity: Bool
        let elapsedMilliseconds: Double
    }

    private struct Report: Encodable {
        let schema = "vipi-swahili-conversation-modes-1"
        let platform = "ios"
        let semanticAcceptance = false
        let corpusSHA256: String
        let rows: [Row]
    }
}
