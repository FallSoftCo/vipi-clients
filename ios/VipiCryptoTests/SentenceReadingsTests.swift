import XCTest
@testable import Vipi

@MainActor final class SentenceReadingsTests: XCTestCase {
    func testMarkedChineseWordsAndExactOnboardingPreview() throws {
        let file = try XCTUnwrap(Bundle.main.url(forResource: "chinese-ordinary", withExtension: "json"))
        let reader = try ChineseFullReading(data: Data(contentsOf: file))
        for (source, expected) in [("音乐", "yīnyuè"), ("音樂", "yīnyuè"), ("银行", "yínháng"), ("銀行", "yínháng"),
                                   ("重庆", "Chóngqìng"), ("重慶", "Chóngqìng"), ("銀行行長", "yínháng hángzhǎng"),
                                   ("妈妈", "māma"), ("媽媽", "māma"), ("什麼", "shénme"), ("孩子", "háizi"),
                                   ("女儿", "nǚ'ér"), ("綠色", "lǜsè"), ("牛奶", "niúnǎi"),
                                   ("José 银行 café", "José yínháng café")] {
            let result = try reader.resolve(source)
            XCTAssertEqual(result.reading, expected, source)
            XCTAssertEqual(result.pieces.map(\.source).joined(), source)
        }
        let preview = try XCTUnwrap(ConversationExamples.examples?.languages["zh"])
        XCTAssertEqual(preview.words["coffee"]?.reading, "kāfēi")
        XCTAssertEqual(preview.words["tomorrow"]?.reading, "míngtiān")
        XCTAssertEqual(preview.words["river"]?.reading, "hé")
        XCTAssertEqual(preview.reading, "Míngtiān yīqǐ hē kāfēi ma? Wǒ zhīdào hébiān yǒu ge xiǎo dìfang.")
        XCTAssertEqual(SentenceReadings.reading("你好。", language: "zh"), "Nǐ hǎo.")
    }

    func testAllAuthoredReadingsAndUnknownClauseAbstention() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "sentence-readings", withExtension: "json"))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let entries = try XCTUnwrap(root["entries"] as? [[String: String]])
        XCTAssertEqual(entries.count, 423)
        for entry in entries {
            let language = try XCTUnwrap(entry["language"]), native = try XCTUnwrap(entry["text"]), reading = try XCTUnwrap(entry["latin"])
            XCTAssertEqual(SentenceReadings.reading(native, language: language), reading)
            XCTAssertEqual(SentenceReadings.reading(native + "\n" + native, language: language), reading + "\n" + reading)
            XCTAssertNil(SentenceReadings.reading(native + "\nUnknown new sentence.", language: language))
            XCTAssertNil(SentenceReadings.reading(native, language: "sw"))
            XCTAssertTrue(reading.range(of: #"^[\p{Latin}\p{M}\p{N}\s.,?!'’\-]+$"#, options: .regularExpression) != nil)
            XCTAssertFalse(reading.unicodeScalars.contains { (0x0250...0x02FF).contains($0.value) || (0x1D00...0x1DBF).contains($0.value) })
        }
        XCTAssertEqual(SentenceReadings.reading("私は音楽が好きです。駅はどこですか。", language: "ja"), "Watashi wa ongaku ga suki desu. Eki wa doko desu ka.")
        XCTAssertNil(SentenceReadings.reading("私は新しい音楽が好きです。", language: "ja"))
        XCTAssertNil(SentenceReadings.reading("أنا أحب هذه الموسيقى.", language: "ar"))
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("sentence-readings-009.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        try JSONSerialization.data(withJSONObject: ["exact_readings":entries.count,"languages":4,"unknown_clause_abstention":true,"independent_linguistic_acceptance":false], options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .withoutOverwriting)
    }
}
