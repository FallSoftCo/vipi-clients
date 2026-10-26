import Foundation
import XCTest
@testable import VipiCore

final class ContextFrameTests:XCTestCase {
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
}
