import Foundation
import XCTest
@testable import VipiCore

final class TranslationIntegrityEncodedLiteralTests: XCTestCase {
    func testProtectedNFCAndNFDOccurrencesRequireActualEncodedIdentity() {
        for (nfd, nfc) in [
            ("@cafe\u{301}", "@caf\u{e9}"), ("#cafe\u{301}", "#caf\u{e9}"),
            ("`cafe\u{301}`", "`caf\u{e9}`"), ("```\ncafe\u{301}\n```", "```\ncaf\u{e9}\n```"),
            ("https://example.test/cafe\u{301}", "https://example.test/caf\u{e9}"),
            ("cafe\u{301}@example.test", "caf\u{e9}@example.test")
        ] {
            XCTAssertEqual(nfd, nfc) // Explicit Swift canonical-equality prerequisite.
            XCTAssertFalse(Array(nfd.utf8) == Array(nfc.utf8))
            XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: nfd, translation: nfc))
            XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: nfc, translation: nfd))
            XCTAssertTrue(TranslationIntegrity.preservesIdentifiers(original: nfd, translation: nfd))
        }
    }
    func testRawOccurrenceMultiplicitiesMustBeComparedBeforeStringKeyFolding() {
        let nfd = "@cafe\u{301}", nfc = "@caf\u{e9}"
        XCTAssertTrue(TranslationIntegrity.preservesIdentifiers(original: nfd + " " + nfc + " " + nfd,
            translation: nfc + " " + nfd + " " + nfd))
        XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: nfd + " " + nfc,
            translation: nfd + " " + nfd))
        XCTAssertFalse(TranslationIntegrity.preservesIdentifiers(original: nfd + " " + nfc,
            translation: nfc + " " + nfc))
        XCTAssertTrue(TranslationIntegrity.preservesIdentifiers(original: "Ordinary cafe\u{301}", translation: "Normal caf\u{e9}"))
    }
}
