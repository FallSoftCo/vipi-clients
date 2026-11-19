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

}
