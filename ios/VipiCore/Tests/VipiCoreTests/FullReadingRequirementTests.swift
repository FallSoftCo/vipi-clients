import Foundation
import XCTest
import VipiCore

final class FullReadingRequirementTests: XCTestCase {
    func testActualScriptAndProtectedContentDetermineReadingNeed() {
        for text in ["café", "cafe\u{301}", "42 👩🏽‍💻", "`生日`", "```\n日本語\n```", "https://example.com/中文", "ok@example.com"] {
            XCTAssertFalse(FullReadingRequirement.needsReading(text), text)
        }
        for text in ["生日", "明日", "안녕하세요", "مرحبا", "café 中文", "`生日` 明日", "https://example.com/中文 明日", "👩🏽‍💻 مرحبا"] {
            XCTAssertTrue(FullReadingRequirement.needsReading(text), text)
        }
    }
    func testUnicodeEmailProtectionIsAnchoredAtActualAtSigns() {
        for text in ["用户@例子.公司", "用户@例子.公司.", "cafe\u{301}@例子.公司", "𐐀@例子.公司", "👩🏽‍💻 用户@例子.公司", "a@b a@例子.公司"] {
            XCTAssertFalse(FullReadingRequirement.needsReading(text),text)
        }
        for text in ["用户@例子.公司 明日", "用户@例子", "用户@例子.中", "@例子.公司", "用户@", "用户.example.com"] {
            XCTAssertTrue(FullReadingRequirement.needsReading(text),text)
        }
        // Long non-email identifiers have no candidate start until an actual @.
        XCTAssertTrue(FullReadingRequirement.needsReading(String(repeating:"x",count:32_768) + "生日"))
        XCTAssertFalse(FullReadingRequirement.needsReading(String(repeating:"a@",count:4096) + "例子.公司"))
        XCTAssertTrue(FullReadingRequirement.needsReading(String(repeating:"a@",count:4096) + "例子.公司 明日"))
    }
    func testStaticFailureMetadataIsNeverRetryable() throws {
        for reason in [FullMessageReadingState.Failure.outputLimit,.unresolved] {
            let value = FullMessageReadingState(status:.unavailable,failure:reason,policy:"test")
            XCTAssertFalse(value.canRetry)
            XCTAssertEqual(try JSONDecoder().decode(FullMessageReadingState.self,from:JSONEncoder().encode(value)),value)
        }
        XCTAssertEqual(FullMessageReadingState.Failure.outputLimit.rawValue,"OUTPUT_LIMIT")
        XCTAssertEqual(FullMessageReadingState.Failure.unresolved.rawValue,"UNRESOLVED")
        XCTAssertTrue(FullMessageReadingState(status:.unavailable,failure:.producerUnavailable,policy:"test").canRetry)
    }
    func testDamagedRequiredTranslationFieldStillFailsStrictDecode() {
        let bytes = Data(#"{"original":42,"practiceText":"明日","meaningText":"Tomorrow","inputLanguage":"en","practiceLanguage":"ja","meaningLanguage":"en"}"#.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(FullMessageTranslation.self,from:bytes))
    }
    func testLegacyMessageDecodesWithoutReadingMetadata() throws {
        let bytes = Data(#"{"original":"Tomorrow","practiceText":"明日","meaningText":"Tomorrow","inputLanguage":"en","practiceLanguage":"ja","meaningLanguage":"en","practiceReading":"asu"}"#.utf8)
        let value = try JSONDecoder().decode(FullMessageTranslation.self, from:bytes)
        XCTAssertNil(value.readingState); XCTAssertEqual(value.practiceReading,"asu")
    }
    func testCommonPhoneticModifiersDoNotBecomeUnresolvedNativeLetters() {
        for text in ["ʿ", "ʾ", "ʻ", "ˈ", "ʿrby", "ạ̉hlạaⁿ bạlʿạlm"] {
            XCTAssertFalse(FullReadingRequirement.needsReading(text), text)
        }
        for text in ["عربي", "中文", "にほんご", "한글"] {
            XCTAssertTrue(FullReadingRequirement.needsReading(text), text)
        }
    }

}
