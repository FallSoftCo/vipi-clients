import XCTest
@testable import VipiCore

final class ContextMappingTests: XCTestCase {
    func testTypographicApostrophesMatchWithoutChangingStoredText() {
        let result=ImmersionEngine().align(original:"I work today.",translation:"Je travaille aujourd'hui.",entries:[.init(source:"today",targets:["aujourd’hui"])],density:1,targetLanguage:"fr")
        XCTAssertEqual(result.spans.first?.translated,"aujourd'hui")
        XCTAssertEqual(result.translation,"Je travaille aujourd'hui.")
    }

    func testTargetParticlesRequireExplicitAttestedFormAndExactSourceContext() {
        let text="I read a book."
        let mapping=ContextMapping(id:"book-en",meaning:"reading material",sourceLanguage:"en",targetLanguage:"ko",
            parts:[.literal("I read a "),.focus("book"),.literal(".")],targets:["책"],readings:["책":["chaek"]],
            targetForms:[.init(surface:"책을",target:"책",start:0,end:1)])
        let entries=ContextMappingMatcher.entries(original:text,source:"en",target:"ko",mappings:[mapping])
        func align(_ translated:String,_ rows:[VocabularyEntry]? = nil)->ImmersionResult {
            ImmersionEngine().align(original:text,translation:translated,entries:rows ?? entries,density:1,targetLanguage:"ko",targetBoundaries:[0,2,translated.utf16.count])
        }
        XCTAssertEqual(align("책을 읽어요.").spans.first?.romanization,"chaek")
        XCTAssertEqual(align("책을 읽어요.").spans.first?.translated,"책")
        XCTAssertTrue(align("책상 위에 있어요.").spans.isEmpty)
        let unscoped=VocabularyEntry(source:"book",targets:["책"],romanizations:["책":["chaek"]],targetForms:mapping.targetForms)
        XCTAssertTrue(align("책을 읽어요.",[unscoped]).spans.isEmpty)
        let malformed=VocabularyEntry(source:"book",targets:["책"],romanizations:["책":["chaek"]],sourceScope:entries[0].sourceScope,
            targetForms:[.init(surface:"책을",target:"책",start:0,end:2)])
        XCTAssertTrue(align("책을 읽어요.",[malformed]).spans.isEmpty)
    }

    func testExactKoreanFocusPreservesParticleAndCannotEscapeItsContext() throws {
        let text="책을 읽고 있어요."
        let mapping=ContextMapping(id:"book-ko",meaning:"book as reading material",sourceLanguage:"ko",targetLanguage:"en",
            parts:[.focus("책"),.literal("을 읽고 있어요.")],targets:["book"])
        let entries=ContextMappingMatcher.entries(original:text,source:"ko",target:"en",mappings:[mapping])
        let engine=ImmersionEngine()
        let result=engine.align(original:text,translation:"I am reading a book.",entries:entries,density:1,targetLanguage:"en",sourceBoundaries:[0,2,text.utf16.count])
        XCTAssertEqual(result.speech(source:"ko",target:"en").map(\.text).joined(),"book을 읽고 있어요.")
        XCTAssertTrue(engine.align(original:text,translation:"I am reading a book.",entries:[.init(source:"책",targets:["book"])],density:1,targetLanguage:"en",sourceBoundaries:[0,2,text.utf16.count]).spans.isEmpty)
        XCTAssertTrue(engine.align(original:"책상 위에 있어요.",translation:"It is on the desk with a book.",entries:entries,density:1,targetLanguage:"en").spans.isEmpty)
        let malformed=VocabularyEntry(source:"책",targets:["book"],sourceScope:.init(original:text,start:0,end:2))
        XCTAssertTrue(engine.align(original:text,translation:"I am reading a book.",entries:[malformed],density:1,targetLanguage:"en").spans.isEmpty)
        let encoded=try JSONEncoder().encode(entries)
        XCTAssertNil(try JSONDecoder().decode([VocabularyEntry].self,from:encoded).first?.sourceScope)
    }

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
