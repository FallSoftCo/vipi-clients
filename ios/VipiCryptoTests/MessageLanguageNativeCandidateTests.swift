import XCTest
@testable import Vipi

@MainActor final class MessageLanguageNativeCandidateTests: XCTestCase {
    func testNativeShortPracticeScriptIdentificationIsNotVetoedByWordCount() async throws {
        let language = MessageLanguage()
        let chinese = try await language.identify("你好"), japanese = try await language.identify("はい")
        XCTAssertEqual(chinese,"zh"); XCTAssertEqual(japanese,"ja")
    }
    func testEmptyInputHasNoClaimedLanguage() async throws {
        let value = try await MessageLanguage().identify("   ")
        XCTAssertNil(value)
    }
}
