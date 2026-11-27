import Foundation
import XCTest
@testable import VipiCore

final class TechnicalLiteralIntegrityTests: XCTestCase {
    func testTechnicalTokensPreserveBytesAndRepeatedOccurrences() {
        for token in [
            "coffee_today.txt", "music_notes", "_music_notes", "music__notes", "music.txt_notes", ".music_notes",
            "music_notes_", "music..notes_", "music.txt", "family-notes.json", "music.tar.gz", "music.JPG",
            "music.vipihistory", "cafe\u{301}_notes.txt", "家族_notes.pdf"
        ] {
            XCTAssertEqual(TranslationIntegrity.identifiers(token), [token: 1], token)
            XCTAssertTrue(
                TranslationIntegrity.preservesIdentifiers(original: "Send \(token).", translation: "送る \(token)。"),
                token)
            XCTAssertFalse(
                TranslationIntegrity.preservesIdentifiers(
                    original: "Send \(token).", translation: "送る renamed_\(token)。"), token)
            XCTAssertFalse(
                TranslationIntegrity.preservesIdentifiers(original: "\(token) \(token)", translation: token), token)
        }
        XCTAssertFalse(
            TranslationIntegrity.preservesIdentifiers(original: "coffee_today.txt", translation: "コーヒー_today.txt"))
        XCTAssertFalse(
            TranslationIntegrity.preservesIdentifiers(
                original: "cafe\u{301}_notes.txt", translation: "caf\u{e9}_notes.txt"))
        XCTAssertTrue(
            TranslationIntegrity.preservesIdentifiers(
                original: "music.txt, family_notes.json", translation: "family_notes.json、music.txt。"))
    }
    func testOrdinaryTextAndExistingLiteralPrecedence() {
        XCTAssertTrue(
            TranslationIntegrity.preservesIdentifiers(original: "Have coffee after work.", translation: "仕事の後でコーヒーを飲む。")
        )
        XCTAssertTrue(TranslationIntegrity.preservesIdentifiers(original: "back.big dogs", translation: "戻る。大きな犬"))
        XCTAssertTrue(
            TranslationIntegrity.preservesIdentifiers(
                original: "Meet at 12:30. Pay 1.25.", translation: "12.30に会う。1,25を払う。"))
        XCTAssertEqual(
            TranslationIntegrity.identifiers(
                "`music_notes.txt` @music_notes music_notes@example.test https://example.test/music_notes.txt"),
            [
                "`music_notes.txt`": 1, "@music_notes": 1, "music_notes@example.test": 1,
                "https://example.test/music_notes.txt": 1
            ])
    }
}
