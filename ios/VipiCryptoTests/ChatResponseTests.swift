import XCTest
@testable import Vipi

final class ChatResponseTests: XCTestCase {
    func testFriendLookupAcceptsOneOptionalAtSign() {
        XCTAssertEqual(FriendLookupUsername.normalize("  @Alice_42  "), "alice_42")
        XCTAssertEqual(FriendLookupUsername.normalize("alice"), "alice")
        for invalid in ["@@alice", "ali@ce", "@ alice", "@", "ab", "a!ice"] {
            XCTAssertNil(FriendLookupUsername.normalize(invalid), invalid)
        }
    }

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
    func testCombinedBookCarriersPreserveBothLanguagesGrammar() async throws {
        let catalog=BundledImmersionCatalog()
        for suffix in ["은","이","을","과","도","만","에","에서","의"] {
            let korean="책"+suffix
            let forward=try await catalog.result(original:korean,translation:"看书",pair:.init(source:"ko",target:"zh"),density:1)
            XCTAssertEqual(forward.spans.count,1)
            XCTAssertEqual(forward.speech(source:"ko",target:"zh").map(\.text).joined(),"书"+suffix)
            XCTAssertEqual(forward.spans.first?.romanization,"shū")
            let reverse=try await catalog.result(original:"看书",translation:korean,pair:.init(source:"zh",target:"ko"),density:1)
            XCTAssertEqual(reverse.spans.count,1)
            XCTAssertEqual(reverse.speech(source:"zh",target:"ko").map(\.text).joined(),"看책")
            XCTAssertEqual(reverse.spans.first?.romanization,"chaek")
        }
        for (korean,chinese) in [("책방","看书"),("책을","看书店"),("책을","看书看书"),("책을 책을","看书"),("책을","看")] {
            let forward=try await catalog.result(original:korean,translation:chinese,pair:.init(source:"ko",target:"zh"),density:1)
            let reverse=try await catalog.result(original:chinese,translation:korean,pair:.init(source:"zh",target:"ko"),density:1)
            XCTAssertTrue(forward.spans.isEmpty);XCTAssertTrue(reverse.spans.isEmpty)
        }
    }
}
