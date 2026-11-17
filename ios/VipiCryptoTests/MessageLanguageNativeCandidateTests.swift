import XCTest
@testable import Vipi

@MainActor final class MessageLanguageNativeCandidateTests: XCTestCase {
    func testAutomaticCandidateOnRepresentativeMessagesAndLiteralBounds() async throws {
        let detector = MessageLanguage()
        let rows = [
            ("I like music.", "en"), ("I love music.", "en"), ("I heard music.", "en"),
            ("I love music. https://example.com/path", "en"),
            ("Me gusta escuchar música con mis amigos.", "es"),
            ("J’aime écouter de la musique avec mes amis.", "fr"),
            ("Ich höre gerne Musik mit meinen Freunden.", "de"),
            ("Mi piace ascoltare musica con i miei amici.", "it"),
            ("Gosto de ouvir música com os meus amigos.", "pt"),
            ("友達と一緒に音楽を聴くのが好きです。", "ja"),
            ("친구들과 함께 음악을 듣는 것을 좋아해요.", "ko"),
            ("我喜欢和朋友一起听音乐。", "zh"),
            ("أحب الاستماع إلى الموسيقى مع أصدقائي.", "ar"),
            ("Ninapenda kusikiliza muziki pamoja na marafiki zangu.", "sw"),
            // These measured native-language disagreements retain the reliable CLD2 decision.
            ("Je suis très content with my friend and I love music.", "en"),
            ("Ich liebe Musik and I like to listen with my friends.", "en")
        ]
        for (text, expected) in rows { let actual = try await detector.identify(text, automatic: true); XCTAssertEqual(actual, expected, text) }
        for text in ["pain", "gift", "room", "code", "Alice", "https://example.com/music", "`hello_world`", String(repeating: "a", count: 16_385)] {
            let actual = try await detector.identify(text, automatic: true); XCTAssertNil(actual, text)
        }
        let unsupported = try await detector.identify("To jest bardzo piękna muzyka i przyjaciele.", automatic: true)
        let mixed = try await detector.identify("I love 音楽.", automatic: true)
        XCTAssertNil(unsupported); XCTAssertNil(mixed)
    }
    func testNativeFallbackIsBoundedAndDoesNotChangeLegacyFullMode() async throws {
        XCTAssertNil(MessageLanguage.nativeFallback(code: "en", confidence: 0.699))
        XCTAssertEqual(MessageLanguage.nativeFallback(code: "en", confidence: 0.70), "en")
        XCTAssertEqual(MessageLanguage.nativeFallback(code: "zh-Hant", confidence: 0.99), "zh")
        XCTAssertNil(MessageLanguage.nativeFallback(code: "pl", confidence: 0.99))
        XCTAssertNil(MessageLanguage.nativeFallback(code: "en", confidence: nil))
        let legacy = try await MessageLanguage().identify("I like music.")
        XCTAssertNil(legacy) // Existing full-translation detector behavior.
        let cancelled = Task { try await MessageLanguage().identify("I love music.", automatic: true) }
        cancelled.cancel()
        do { _ = try await cancelled.value; XCTFail("Cancellation must propagate") }
        catch is CancellationError { }
    }
}
