import Foundation
import XCTest
@testable import VipiCore

final class ContextFrameTests:XCTestCase {
    func testAttachedGrammarStaysOriginalWhileOnlyTheAssessedNounChanges() {
        for (original,translation,language,noun,suffix,target,reading) in [
            ("책을 가져왔어요.","I brought the book.","ko","책","을","book","chaek"),
            ("Tutakutana shuleni.","We will meet at school.","sw","shule","ni","school","")
        ] {
            let parts:[ContextPart]=[.focus(noun),.literal(suffix)]
            let frame=ContextFrame(id:"attached",meaning:"specific noun",sourceLanguage:language,targetLanguage:"en",
                sourceParts:parts,targetParts:[.focus(target)],targetUnit:true)
            let hit=ContextFrameHit(frame:frame,sourceWindows:[(original as NSString).range(of:noun+suffix)],
                targetWindows:[(translation as NSString).range(of:target)])
            let values=ContextFrameMatcher.entries(original:original,translation:translation,source:language,target:"en",hits:[hit])
            let result=ImmersionEngine().align(original:original,translation:translation,entries:values,density:1,targetLanguage:"en")
            XCTAssertEqual(result.spans.map(\.original),[noun])
            XCTAssertEqual(result.speech(source:language,target:"en").map(\.text).joined(),original.replacingOccurrences(of:noun,with:target))
            XCTAssertEqual(result.speech(source:language,target:"en",revealed:Set(result.spans.map(\.id))).map(\.text).joined(),original)
            let reverse=ContextFrame(id:"reverse",meaning:"specific noun",sourceLanguage:"en",targetLanguage:language,
                sourceParts:[.focus(target)],targetParts:parts,reading:reading,sourceUnit:true)
            let reverseHit=ContextFrameHit(frame:reverse,sourceWindows:hit.targetWindows,targetWindows:hit.sourceWindows)
            let reverseValues=ContextFrameMatcher.entries(original:translation,translation:original,source:"en",target:language,hits:[reverseHit])
            let reversed=ImmersionEngine().align(original:translation,translation:original,entries:reverseValues,density:1,targetLanguage:language)
            XCTAssertEqual(reversed.spans.map(\.translated),[noun])
            if language=="ko" {XCTAssertEqual(reversed.spans.first?.romanization,reading)}
            for targetUnit in [false,true] {
                let denied=ContextFrame(id:"denied",meaning:"specific noun",sourceLanguage:language,targetLanguage:"en",
                    sourceParts:targetUnit ? [.focus(noun),.literal("wrong")] : parts,targetParts:[.focus(target)],targetUnit:targetUnit)
                let deniedHit=ContextFrameHit(frame:denied,sourceWindows:hit.sourceWindows,targetWindows:hit.targetWindows)
                XCTAssertTrue(ContextFrameMatcher.entries(original:original,translation:translation,source:language,target:"en",hits:[deniedHit]).isEmpty)
            }
        }
    }
    func testFinitePossessorsRemainOutsideFocus() {
        let parts:[ContextPart]=[.slot(["my ","your ","their "]),.focus("dog")]
        XCTAssertEqual(ContextMappingMatcher.focus(in:"their dog",parts:parts),NSRange(location:6,length:3))
        XCTAssertNil(ContextMappingMatcher.focus(in:"her dog",parts:parts))
        XCTAssertNil(ContextMappingMatcher.focus(in:"dog",parts:[.focus("dog")]))
        XCTAssertNil(ContextMappingMatcher.focus(in:" dog",parts:[.slot([" ","\n"]),.focus("dog")]))
    }
    let original="🙂 I am reading a book now."
    let translation="🙂 Estoy leyendo un libro ahora. Otro libro."
    func frame(_ id:String="book",_ meaning:String="a book being read") -> ContextFrame {
        .init(id:id,meaning:meaning,sourceLanguage:"en",targetLanguage:"es",
            sourceParts:[.slot(["read","reading"]),.literal(" a "),.focus("book")],
            targetParts:[.literal("leyendo un "),.focus("libro")])
    }
    func hit(_ value:ContextFrame?=nil,_ targets:[NSRange]?=nil) -> ContextFrameHit {
        .init(frame:value ?? frame(),sourceWindows:[(original as NSString).range(of:"reading a book")],
            targetWindows:targets ?? [(translation as NSString).range(of:"leyendo un libro")])
    }
    func entries(_ hits:[ContextFrameHit]) -> [VocabularyEntry] {
        ContextFrameMatcher.entries(original:original,translation:translation,source:"en",target:"es",hits:hits)
    }
    func testBothMatchedContextsBindOnlyTheirLexicalFocus() {
        let values=entries([hit()]);XCTAssertEqual(values.count,1)
        let result=ImmersionEngine().align(original:original,translation:translation,entries:values,density:1,targetLanguage:"es")
        XCTAssertEqual(result.spans.count,1);XCTAssertEqual(result.spans.first?.original,"book")
        XCTAssertEqual(result.spans.first?.targetRange,(translation as NSString).range(of:"libro"))
        XCTAssertEqual(result.speech(source:"en",target:"es").filter{$0.language=="es"}.map(\.text),["libro"])
    }
    func testMissingTargetCannotEraseAContrarySourceMeaning() {
        XCTAssertTrue(entries([hit(nil,[])]).isEmpty)
        XCTAssertTrue(entries([hit(),hit(frame("rival","an unrelated sense"),[])]).isEmpty)
    }
    func testRepeatedMatchedTargetAndOverflowAbstain() {
        let repeated="leyendo un libro y leyendo un libro"
        let windows=[NSRange(location:0,length:16),NSRange(location:19,length:16)]
        let result=ContextFrameMatcher.entries(original:original,translation:repeated,source:"en",target:"es",
            hits:[.init(frame:frame(),sourceWindows:[(original as NSString).range(of:"reading a book")],targetWindows:windows)])
        XCTAssertTrue(result.isEmpty)
        XCTAssertTrue(entries((0...256).map{hit(frame("book-\($0)"))}).isEmpty)
    }
    func testAnIndexHitMustActuallyMatchTheBoundedPattern() {
        XCTAssertTrue(entries([.init(frame:frame(),sourceWindows:[NSRange(location:0,length:4)],targetWindows:[])]).isEmpty)
        XCTAssertTrue(entries([hit(nil,[NSRange(location:999,length:5)])]).isEmpty)
    }
    func testCompleteUnitNeedsExplicitScopeAndBothUniqueNativeForms() {
        let source="I lost my phone number.",target="Perdí mi número de teléfono."
        func unit(_ approved:Bool,_ id:String="phone",_ meaning:String="telephone contact number") -> ContextFrame {
            .init(id:id,meaning:meaning,sourceLanguage:"en",targetLanguage:"es",
                sourceParts:[.focus("phone number")],targetParts:[.focus("número de teléfono")],lexicalUnit:approved)
        }
        func hit(_ value:ContextFrame,_ targets:[NSRange]?=nil) -> ContextFrameHit {
            .init(frame:value,sourceWindows:[(source as NSString).range(of:"phone number")],
                targetWindows:targets ?? [(target as NSString).range(of:"número de teléfono")])
        }
        func result(_ hits:[ContextFrameHit]) -> [VocabularyEntry] {
            ContextFrameMatcher.entries(original:source,translation:target,source:"en",target:"es",hits:hits)
        }
        XCTAssertTrue(result([hit(unit(false))]).isEmpty)
        let entries=result([hit(unit(true))]);XCTAssertEqual(entries.count,1)
        let aligned=ImmersionEngine().align(original:source,translation:target,entries:entries,density:1,targetLanguage:"es")
        XCTAssertEqual(aligned.spans.first?.original,"phone number")
        XCTAssertTrue(result([hit(unit(true),[])]).isEmpty)
        XCTAssertTrue(result([hit(unit(true)),hit(unit(true,"rival","a different meaning"),[])]).isEmpty)
        let malformed=ContextFrame(id:"bad",meaning:"contact",sourceLanguage:"en",targetLanguage:"es",
            sourceParts:[.literal("my "),.focus("phone number")],targetParts:[.focus("número de teléfono")],lexicalUnit:true)
        XCTAssertTrue(result([hit(malformed)]).isEmpty)
    }
    func testCompletePluralTargetKeepsItsSuffixWithoutResolvingOtherAmbiguities() {
        let source="children", target="子どもたち"
        func hit(_ id:String,_ word:String,_ reading:String,_ meaning:String="human children",_ start:Int=0) -> ContextFrameHit {
            .init(frame:.init(id:id,meaning:meaning,sourceLanguage:"en",targetLanguage:"ja",sourceParts:[.focus(source)],
                              targetParts:[.focus(word)],reading:reading,lexicalUnit:true),
                  sourceWindows:[NSRange(location:0,length:source.utf16.count)],targetWindows:[NSRange(location:start,length:word.utf16.count)])
        }
        func entries(_ text:String,_ hits:[ContextFrameHit]) -> [VocabularyEntry] {
            ContextFrameMatcher.entries(original:source,translation:text,source:"en",target:"ja",hits:hits)
        }
        func result(_ text:String,_ hits:[ContextFrameHit]) -> ImmersionResult {
            ImmersionEngine().align(original:source,translation:text,entries:entries(text,hits),density:1,targetLanguage:"ja")
        }
        let short=hit("short","子ども","kodomo"), full=hit("full",target,"kodomotachi")
        let aligned=result(target,[short,full])
        XCTAssertEqual(aligned.spans.map(\.translated),[target]);XCTAssertEqual(aligned.spans.first?.romanization,"kodomotachi")
        XCTAssertTrue(entries(target,[short,hit("other",target,"kodomotachi","another meaning")]).isEmpty)
        XCTAssertTrue(result(target,[short,full,hit("reading-conflict",target,"different")]).spans.isEmpty)
        let separate="子ども 子どもたち", second=hit("second",target,"kodomotachi","human children",4)
        XCTAssertTrue(result(separate,[short,second]).spans.isEmpty)
        let repeated=ContextFrameHit(frame:short.frame,sourceWindows:short.sourceWindows,
            targetWindows:[NSRange(location:0,length:3),NSRange(location:4,length:3)])
        XCTAssertTrue(entries(separate,[repeated,second]).isEmpty)
    }

    func testCommonNounCaseAliasesPreserveNameAndContraryMeaningGuards() {
        func run(_ original:String,_ translated:String,language:String="en",flag:Bool=true,other:ContextFrameHit?=nil)->[VocabularyEntry] {
            let frame=ContextFrame(id:"case",meaning:"food",sourceLanguage:language,targetLanguage:"es",
                sourceParts:[.focus("Food")],targetParts:[.focus("comida")],lexicalUnit:true,commonNounCaseVariants:flag)
            let hit=ContextFrameHit(frame:frame,sourceWindows:[(original as NSString).range(of:"Food")],
                targetWindows:[(translated as NSString).range(of:"comida")])
            return ContextFrameMatcher.entries(original:original,translation:translated,source:language,target:"es",hits:[hit]+(other.map{[$0]} ?? []))
        }
        XCTAssertEqual(run("Food is ready.","La comida está lista.").count,1)
        XCTAssertEqual(run("Done. Food is ready.","La comida está lista.").count,1)
        XCTAssertTrue(run("I called Food yesterday.","Llamé a la comida ayer.").isEmpty)
        XCTAssertEqual(run("I called Food yesterday.","Llamé a la comida ayer.",flag:false).count,1)
        XCTAssertEqual(run("Ich mag Food.","Me gusta la comida.",language:"de").count,1)
        let source="Food is ready.",translated="La comida está lista."
        let contrary=ContextFrameHit(frame:ContextFrame(id:"contrary",meaning:"another sense",sourceLanguage:"en",targetLanguage:"es",
            sourceParts:[.focus("Food")],targetParts:[.focus("other")],lexicalUnit:true,commonNounCaseVariants:true),
            sourceWindows:[(source as NSString).range(of:"Food")],targetWindows:[])
        XCTAssertTrue(run(source,translated,other:contrary).isEmpty)
        let original="Llamé a la comida ayer.",target="I called Food yesterday."
        let reverse=ContextFrameHit(frame:ContextFrame(id:"reverse",meaning:"food",sourceLanguage:"es",targetLanguage:"en",
            sourceParts:[.focus("comida")],targetParts:[.focus("Food")],lexicalUnit:true,commonNounCaseVariants:true),
            sourceWindows:[(original as NSString).range(of:"comida")],targetWindows:[(target as NSString).range(of:"Food")])
        XCTAssertTrue(ContextFrameMatcher.entries(original:original,translation:target,source:"es",target:"en",hits:[reverse]).isEmpty)
    }

    func testOpeningPunctuationPreservesSentenceCaseWithoutExcusingNames() {
        for text in ["¿Tiempo?","¡Food!","Done. “Food”","'Food'"] {
            let offset=(text as NSString).rangeOfCharacter(from:CharacterSet(charactersIn:"TF")).location
            XCTAssertTrue(WrittenCase.sentenceInitial(text,start:offset))
        }
        for text in ["I called “Food”.","Dije ¿Tiempo?","Use ROOM."] {
            let offset=(text as NSString).rangeOfCharacter(from:CharacterSet(charactersIn:"FTR")).location
            XCTAssertFalse(WrittenCase.sentenceInitial(text,start:offset))
        }
    }

}
