import XCTest
@testable import VipiCore

final class ContextMappingTests: XCTestCase {
    private func book(plural: Bool = false, meaning: String = "book as reading material", target: String = "es", readings: [String: [String]] = [:]) -> ContextMapping {
        ContextMapping(id: "book",meaning: meaning,sourceLanguage: "en",targetLanguage: target,
            parts: [.literal("Can "),.slot(["you","they","we"]),.literal(" bring "),.slot(["my","your","their","our"]),
                    .literal(" "),.focus(plural ? "books" : "book"),.literal("?")],
            targets: [target == "ja" ? "本" : plural ? "libros" : "libro"],readings: readings)
    }
    private func align(_ text: String, _ translation: String, records: [ContextMapping]? = nil) -> ImmersionResult {
        ImmersionEngine().align(original: text, translation: translation,
            entries: ContextMappingMatcher.entries(original: text,source: "en",target: "es",mappings: records ?? [book(),book(plural: true)]),density: 1,targetLanguage: "es")
    }
    func testPersonPossessionAndNumberRemainOutsideReplacement() {
        for (text, translation, expected) in [
            ("Can you bring my book?","¿Puedes traer mi libro?","Can you bring my libro?"),
            ("Can you bring your book?","¿Puedes traer tu libro?","Can you bring your libro?"),
            ("Can they bring their books?","¿Pueden traer sus libros?","Can they bring their libros?")
        ] {
            let result = align(text,translation)
            XCTAssertEqual(result.spans.count,1)
            XCTAssertEqual(result.speech(source: "en",target: "es").map(\.text).joined(),expected)
        }
    }
    func testUnknownContextWrongPairAndChangedNumberDoNotReuseExample() {
        XCTAssertTrue(align("Can you book my flight?","¿Puedes reservar mi vuelo?").spans.isEmpty)
        XCTAssertTrue(align("Can you bring her book?","¿Puedes traer su libro?").spans.isEmpty)
        XCTAssertTrue(align("Can you bring my books?","¿Puedes traer mis libros?",records:[book()]).spans.isEmpty)
        XCTAssertTrue(ContextMappingMatcher.entries(original:"Can you bring my book?",source:"es",target:"en",mappings:[book()]).isEmpty)
    }
    func testConflictingMeaningAndMissingTranslationEvidenceWithhold() {
        XCTAssertTrue(align("Can you bring my book?","¿Puedes traer mi libro?",records:[book(),book(meaning:"reservation")]).spans.isEmpty)
        XCTAssertTrue(align("Can you bring my book?","¿Puedes traer mi cuaderno?").spans.isEmpty)
    }
    func testNonRomanRequiresReadableTransliteration() {
        let text = "Can you bring my book?", translated = "私の本を持ってきてくれる？"
        func result(_ record: ContextMapping) -> ImmersionResult {
            ImmersionEngine().align(original:text,translation:translated,
                entries:ContextMappingMatcher.entries(original:text,source:"en",target:"ja",mappings:[record]),density:1,targetLanguage:"ja",
                targetBoundaries:[0,1,2,3,translated.utf16.count])
        }
        XCTAssertTrue(result(book(target:"ja")).spans.isEmpty)
        XCTAssertEqual(result(book(target:"ja",readings:["本":["hon"]])).spans.first?.romanization,"hon")
    }
    func testAmbiguousFocusParsingAndOversizedSlotReject() {
        let ambiguous = ContextMapping(id:"ambiguous",meaning:"fixture",sourceLanguage:"en",targetLanguage:"es",
            parts:[.literal("x"),.slot(["a","aa"]),.focus("a"),.slot(["a","aa"])],targets:["b"])
        XCTAssertTrue(ContextMappingMatcher.entries(original:"xaaaa",source:"en",target:"es",mappings:[ambiguous]).isEmpty)
        let oversized = ContextMapping(id:"oversized",meaning:"fixture",sourceLanguage:"en",targetLanguage:"es",
            parts:[.literal("Can "),.slot((0..<33).map(String.init)),.focus("book")],targets:["libro"])
        XCTAssertTrue(ContextMappingMatcher.entries(original:"Can 1book",source:"en",target:"es",mappings:[oversized]).isEmpty)
    }
}
