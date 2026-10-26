import Foundation
import XCTest
@testable import VipiCore

final class TargetScopeTests:XCTestCase {
    let source="🙂 I read a book."
    let target="🙂 Leo un libro. Ese libro es nuevo."
    func entry(_ start:Int=10,_ end:Int=15,_ translation:String?=nil) -> VocabularyEntry {
        .init(source:"book",targets:["libro"],sourceScope:.init(original:source,start:12,end:16),
            targetScope:.init(translation:translation ?? target,start:start,end:end))
    }
    func testBoundTargetSelectsOnlyItsMatchedOccurrence() {
        let result=ImmersionEngine().align(original:source,translation:target,entries:[entry()],density:1,targetLanguage:"es")
        XCTAssertEqual(result.spans.count,1)
        XCTAssertEqual(result.spans.first?.targetRange,NSRange(location:10,length:5))
        XCTAssertEqual(result.spans.first?.original,"book")
    }
    func testChangedTranslationInvalidRangeOrMissingSourceScopeNeverFallsBack() {
        let engine=ImmersionEngine()
        for value in [entry(9,14),entry(10,15,"Different translation"),
            VocabularyEntry(source:"book",targets:["libro"],targetScope:entry().targetScope)] {
            XCTAssertTrue(engine.align(original:source,translation:target,entries:[value],density:1).spans.isEmpty)
        }
        XCTAssertTrue(engine.align(original:"Changed "+source,translation:target,entries:[entry()],density:1).spans.isEmpty)
    }
    func testConflictingMatchedTargetsStillAbstain() {
        XCTAssertTrue(ImmersionEngine().align(original:source,translation:target,entries:[entry(),entry(21,26)],density:1).spans.isEmpty)
    }
    func testGenericDecodingCannotGrantTargetScope() throws {
        let data=try JSONEncoder().encode(entry())
        XCTAssertNil(try JSONDecoder().decode(VocabularyEntry.self,from:data).targetScope)
        XCTAssertNil(try JSONDecoder().decode(VocabularyEntry.self,from:data).sourceScope)
    }
    func testSharedIdeographRetainsQualifiedTargetReadingAndSpeechLanguage() {
        let entry=VocabularyEntry(source:"水",targets:["水"],romanizations:["水":["mizu"]],
            sourceScope:.init(original:"水",start:0,end:1),targetScope:.init(translation:"水",start:0,end:1))
        let result=ImmersionEngine().align(original:"水",translation:"水",entries:[entry],density:1,targetLanguage:"ja")
        XCTAssertEqual(result.spans.first?.romanization,"mizu")
        XCTAssertEqual(result.speech(source:"zh",target:"ja"),[.init(text:"水",language:"ja")])
        let unqualified=VocabularyEntry(source:"水",targets:["水"],romanizations:["水":["mizu"]])
        XCTAssertTrue(ImmersionEngine().align(original:"水",translation:"水",entries:[unqualified],density:1,targetLanguage:"ja").spans.isEmpty)
        let unread=VocabularyEntry(source:"水",targets:["水"],sourceScope:entry.sourceScope,targetScope:entry.targetScope)
        XCTAssertTrue(ImmersionEngine().align(original:"水",translation:"水",entries:[unread],density:1,targetLanguage:"ja").spans.isEmpty)
    }
}
