import Foundation
import XCTest
@testable import VipiCore

final class ImmersionSpeechEligibilityTests: XCTestCase {
    private func partial() throws -> PartialImmersionResult {
        try XCTUnwrap(SourceReferencePresentation.create(original: "Hello. Unknown.", target: "es",
            units: [.init(range: .init(location: 0, length: 6), original: "Hello.", translated: "Hola.", reading: nil,
                referenceID: "authored-speech-regression", catalogSHA256: String(repeating: "a", count: 64), nativeSourceTokens: 1)],
            density: 1, nativeSourceTokenCount: 2))
    }
    func testSourceOnlyPartialAllowsOriginalAndVisibleSpansButNotFullTargetSpeech() throws {
        let value = ImmersionPresentation.partial(try partial())
        XCTAssertEqual(value.speech(mode: .original, source: "en", target: "es"), [.init(text: "Hello. Unknown.", language: "en")])
        XCTAssertEqual(value.speech(mode: .immersed, source: "en", target: "es"),
            [.init(text: "Hola.", language: "es"), .init(text: " Unknown.", language: "en")])
        XCTAssertEqual(value.speech(mode: .immersed, source: "en", target: "es", revealed: [0]),
            [.init(text: "Hello.", language: "en"), .init(text: " Unknown.", language: "en")])
        XCTAssertNil(value.speech(mode: .fullTarget, source: "en", target: "es"))
    }
    func testFullTargetSpeechBecomesAvailableOnlyFromSeparateActualFullTarget() throws {
        let value = ImmersionPresentation.partial(try partial().withCompleteTranslation("Hola. Desconocido."))
        XCTAssertEqual(value.speech(mode: .fullTarget, source: "en", target: "es"), [.init(text: "Hola. Desconocido.", language: "es")])
        XCTAssertEqual(value.speech(mode: .immersed, source: "en", target: "es"),
            [.init(text: "Hola.", language: "es"), .init(text: " Unknown.", language: "en")])
        XCTAssertEqual(value.spans.first?.targetRange, NSRange(location: 0, length: 5))
    }
}
