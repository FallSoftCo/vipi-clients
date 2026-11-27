import Foundation
import XCTest
@testable import Vipi

final class SwahiliTranslationTests: XCTestCase {
    @MainActor func testExplicitDownloadAndLocalTranslationInTwentyDirections() async throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["VIPI_SWAHILI_MODEL_DOWNLOAD"] == "1",
            "Run test-ipad-swahili.sh to explicitly prepare the physical-device ML Kit models")
        let texts = [
            "en": "I am drinking water now.", "es": "Estoy bebiendo agua ahora.",
            "fr": "Je bois de l’eau maintenant.", "de": "Ich trinke gerade Wasser.",
            "it": "Sto bevendo acqua adesso.", "pt": "Estou bebendo água agora.",
            "ar": "أنا أشرب الماء الآن.", "zh": "我正在喝水。", "ja": "今、水を飲んでいます。",
            "ko": "지금 물을 마시고 있어요.", "sw": "Ninakunywa maji sasa."
        ]
        var rows: [[String: Any]] = []
        for other in texts.keys.sorted() where other != "sw" {
            for pair in [TranslationPair(source: other, target: "sw"), TranslationPair(source: "sw", target: other)] {
                let translator = try SwahiliTranslation(pair: pair)
                try await translator.prepare()
                XCTAssertTrue(SwahiliTranslation.installed(pair))
                let original = try XCTUnwrap(texts[pair.source])
                let begin = ContinuousClock.now
                let output = try await translator.translate(original)
                let duration = begin.duration(to: .now).components
                XCTAssertFalse(output.isEmpty)
                rows.append([
                    "source": pair.source, "target": pair.target, "original": original,
                    "translation": output,
                    "elapsed_ms": Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15
                ])
            }
        }
        XCTAssertEqual(rows.count, 20)
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let output = root.appendingPathComponent("swahili-translations-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        try JSONSerialization.data(
            withJSONObject: [
                "schema": "vipi-swahili-translation-1",
                "provider": "Google ML Kit local iOS", "semantic_acceptance": false,
                "network_disabled": false, "rows": rows
            ], options: [.prettyPrinted, .sortedKeys]
        )
        .write(to: output, options: .withoutOverwriting)
    }
}
