import Foundation
import XCTest
@testable import VipiCore

final class SourceOrthographyTests:XCTestCase {
 func testNativeOrReviewedScopesCannotSeverArabicArticles() {
  for(text,a,b) in [("أنا أشرب الماء الآن.",11,14),("أنا أحب الموسيقى.",10,16)] {
   let range=NSRange(location:a,length:b-a),surface=(text as NSString).substring(with:range)
   for scoped in [false,true] {
    let entry=VocabularyEntry(source:surface,targets:["meaning"],sourceScope:scoped ? .init(original:text,start:a,end:b):nil)
    XCTAssertTrue(ImmersionEngine().align(original:text,translation:"meaning",entries:[entry],density:1,targetLanguage:"en",sourceBoundaries:[a,b],sourceTokenCount:8).spans.isEmpty)
   }
   let unit=SourceReferenceUnit(range:range,original:surface,translated:"meaning",reading:nil,referenceID:"qa",catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:1)
   XCTAssertNil(SourceReferencePresentation.create(original:text,target:"en",units:[unit],density:1,nativeSourceTokenCount:8))
  }
 }
 func testFullArabicTokenSurvivesWithVowelsTatweelAndJoinControls() {
  for text in ["الماء","الْمَاءُ","الـماء","ال\u{200D}ماء","ال\u{200C}ماء","ماءـ"] {
   XCTAssertTrue(SourceOrthography.permitsReplacement(in:text,range:.init(location:0,length:text.utf16.count)))
   XCTAssertFalse(SourceOrthography.permitsReplacement(in:text,range:.init(location:0,length:text.utf16.count-1)))
  }
  XCTAssertFalse(SourceOrthography.permitsReplacement(in:"الـماء",range:.init(location:0,length:2)))
  XCTAssertFalse(SourceOrthography.permitsReplacement(in:"الـماء",range:.init(location:3,length:3)))
 }
 func testSafeWholeWordAndOtherScriptsRemainAvailable() throws {
  let text="الماء كتاب",sha=String(repeating:"a",count:64)
  let units=[SourceReferenceUnit(range:.init(location:2,length:3),original:"ماء",translated:"water",reading:nil,referenceID:"bad",catalogSHA256:sha,nativeSourceTokens:1),SourceReferenceUnit(range:.init(location:6,length:4),original:"كتاب",translated:"book",reading:nil,referenceID:"good",catalogSHA256:sha,nativeSourceTokens:1)]
  let partial=try XCTUnwrap(SourceReferencePresentation.create(original:text,target:"en",units:units,density:1,nativeSourceTokenCount:2))
  XCTAssertEqual(partial.spans.map(\.original),["كتاب"])
  XCTAssertEqual(ImmersionPresentation.partial(partial).speech(source:"ar",target:"en",revealed:Set(partial.spans.map(\.id))).map(\.text).joined(),text)
  for(text,end) in [("books",4),("책을",1),("私は",1),("中国",1)] {
   XCTAssertTrue(SourceOrthography.permitsReplacement(in:text,range:.init(location:0,length:end)))
  }
 }
}
