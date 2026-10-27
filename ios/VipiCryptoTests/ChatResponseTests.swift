import XCTest
@testable import Vipi

final class ChatResponseTests: XCTestCase {
    @MainActor func testShortRepliesWorkWithoutTranslationPreparation() async throws {
        let owner=ConversationImmersion()
        await owner.configure(pair:.init(source:"en",target:"sw"),density:0.25)
        defer { owner.close() }
        for (original,expected) in [("yes","Ndiyo."),("YES","Ndiyo."),("No.","Hapana."),("OK","Sawa."),("Please.","Tafadhali.")] {
            let value=await owner.result(for:original)
            XCTAssertEqual(value?.original,original);XCTAssertEqual(value?.translation,expected);XCTAssertEqual(value?.spans.count,1)
            XCTAssertNil(owner.request,"No translation request for an exact short reply")
        }
        for (original,expected) in [("ndio","Yes."),("NDIO","Yes."),("Hapana","No."),("sawa","Okay."),("Tafadhali.","Please.")] {
            let value=await owner.result(for:original)
            XCTAssertEqual(value?.original,expected);XCTAssertEqual(value?.translation,original);XCTAssertEqual(value?.spans.count,1)
            XCTAssertNil(owner.request)
        }
        let catalog=BundledImmersionCatalog()
        for (original,source,target) in [("Please wait.","en","sw"),("No.","en","zh"),("Bitte.","de","sw"),("Please.","en","ko")] {
            let value=try await catalog.reference(original:original,pair:.init(source:source,target:target))
            XCTAssertNil(value,"No changed, incomplete or ambiguous standalone response")
        }
    }
    func testChineseReadingConstructionPreservesVerbAndRejectsLargerWords() async throws {
        let catalog=BundledImmersionCatalog()
        let forward=try await catalog.result(original:"She is reading a book.",translation:"她在看书。",pair:.init(source:"en",target:"zh"),density:1)
        XCTAssertEqual(forward.speech(source:"en",target:"zh").map(\.text).joined(),"She is reading a 书.")
        XCTAssertEqual(forward.spans.first?.romanization,"shū")
        let reverse=try await catalog.result(original:"她在看书。",translation:"She is reading a book.",pair:.init(source:"zh",target:"en"),density:1)
        XCTAssertEqual(reverse.speech(source:"zh",target:"en").map(\.text).joined(),"她在看book。")
        for (left,right) in [("看书店。","book."),("看书。","read."),("看书看书。","book.")] {
            let value=try await catalog.result(original:left,translation:right,pair:.init(source:"zh",target:"en"),density:1)
            XCTAssertTrue(value.spans.isEmpty,"No unqualified internal, missing or repeated focus")
        }
    }
}
