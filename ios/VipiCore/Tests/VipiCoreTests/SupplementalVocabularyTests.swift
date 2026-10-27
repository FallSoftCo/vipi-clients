import XCTest
@testable import VipiCore

final class SupplementalVocabularyTests: XCTestCase {
    private let engine = ImmersionEngine()
    private func scoped(_ text: String, _ translated: String, _ word: String, _ target: String,
                        readings: [String:[String]] = [:]) -> VocabularyEntry {
        let a=(text as NSString).range(of:word), b=(translated as NSString).range(of:target)
        return .init(source:word,targets:[target],romanizations:readings,
            sourceScope:.init(original:text,start:a.location,end:NSMaxRange(a)),
            targetScope:.init(translation:translated,start:b.location,end:NSMaxRange(b)))
    }
    func testSupplementsFillGapsAndShareOneDensityBudget() {
        let text="Bring bread and milk.", translation="Trae pan y leche."
        let primary=[scoped(text,translation,"bread","pan")], extra=[scoped(text,translation,"milk","leche")]
        let result=engine.align(original:text,translation:translation,entries:primary,density:1,targetLanguage:"es",supplementalEntries:extra)
        XCTAssertEqual(result.spans.map(\.original),["bread","milk"])
        XCTAssertEqual(result.speech(source:"en",target:"es").map(\.text).joined(),"Bring pan and leche.")
        XCTAssertEqual(result.speech(source:"en",target:"es",revealed:Set(result.spans.map(\.id))).map(\.text).joined(),text)
        XCTAssertEqual(engine.align(original:text,translation:translation,entries:primary,density:0.25,targetLanguage:"es",supplementalEntries:extra).spans.count,1)
        XCTAssertTrue(engine.align(original:text,translation:translation,entries:primary,density:0,targetLanguage:"es",supplementalEntries:extra).spans.isEmpty)
    }
    func testAcceptedOwnershipSurvivesCompetingSourcesTargetsAndNestedWords() {
        let text="Bring the train ticket and milk.", translation="Trae el billete de tren y leche."
        let primary=[scoped(text,translation,"train ticket","billete de tren")]
        let extra=[scoped(text,translation,"train","tren"),scoped(text,translation,"milk","billete de tren"),
            scoped(text,translation,"train ticket","leche"),scoped(text,translation,"milk","leche")]
        let result=engine.align(original:text,translation:translation,entries:primary,density:1,targetLanguage:"es",supplementalEntries:extra)
        XCTAssertEqual(result.spans.map(\.original),["train ticket","milk"])
        XCTAssertEqual(result.spans.map(\.translated),["billete de tren","leche"])
    }
    func testRejectedPrimaryEvidenceAndNativeGuardsRemainEffective() {
        let text="Bring the train ticket and milk.", translation="Trae el billete de tren y leche."
        let primary=[VocabularyEntry(source:"train ticket",targets:[],protectInner:true),
            VocabularyEntry(source:"milk",targets:[],unresolvedNativeSenses:true)]
        XCTAssertTrue(engine.align(original:text,translation:translation,entries:primary,density:1,targetLanguage:"es",
            supplementalEntries:[scoped(text,translation,"train","tren"),scoped(text,translation,"milk","leche")]).spans.isEmpty)
        let collision=VocabularyEntry(source:"bread",targets:["pan"],requiresContext:true)
        XCTAssertTrue(engine.align(original:"bread loaf",translation:"pan",entries:[collision],density:1,targetLanguage:"es",
            supplementalEntries:[scoped("bread loaf","pan","loaf","pan")]).spans.isEmpty)
    }
    func testSupplementsRequireCurrentScopesAndKeepReadingAndIdentifierChecks() {
        let text="🙂 bread and milk", translation="🙂 パンと牛乳"
        let bread=scoped(text,translation,"bread","パン",readings:["パン":["pan"]])
        let milk=scoped(text,translation,"milk","牛乳")
        let result=engine.align(original:text,translation:translation,entries:[],density:1,targetLanguage:"ja",supplementalEntries:[bread,milk])
        XCTAssertEqual(result.spans.count,1);XCTAssertEqual(result.spans.first?.romanization,"pan")
        XCTAssertEqual(result.spans.first?.range.location,3)
        XCTAssertTrue(engine.align(original:"Other bread",translation:translation,entries:[],density:1,targetLanguage:"ja",supplementalEntries:[bread]).spans.isEmpty)
        XCTAssertTrue(engine.align(original:text,translation:"Different パン",entries:[],density:1,targetLanguage:"ja",supplementalEntries:[bread]).spans.isEmpty)
        let unscoped=VocabularyEntry(source:bread.source,targets:bread.targets,romanizations:bread.romanizations,targetScope:bread.targetScope)
        XCTAssertTrue(engine.align(original:text,translation:translation,entries:[],density:1,targetLanguage:"ja",supplementalEntries:[unscoped]).spans.isEmpty)
        let url="https://bread.example", other="https://pan.example"
        XCTAssertTrue(engine.align(original:url,translation:other,entries:[],density:1,targetLanguage:"es",
            supplementalEntries:[scoped(url,other,"bread","pan")]).spans.isEmpty)
    }
}
