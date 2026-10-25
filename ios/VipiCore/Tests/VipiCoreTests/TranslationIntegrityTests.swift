import Foundation
import Testing
@testable import VipiCore

@Test func literalIntegrityAllowsReorderingAndSentencePunctuation() {
    #expect(TranslationIntegrity.preservesIdentifiers(
        original: "Send `open()` to Ana+Work@example.test. See https://example.test/a_(b)?x=1#here, @Ana #明日.",
        translation: "@Ana #明日 https://example.test/a_(b)?x=1#here。 Ana+Work@example.test に `open()` を送る。"))
    #expect(TranslationIntegrity.preservesIdentifiers(original: "Meet at 12:30 tomorrow.", translation: "Mañana a las 12.30."))
    #expect(TranslationIntegrity.identifiers("(https://example.test/a_(b)).") == ["https://example.test/a_(b)": 1])
}

@Test func literalIntegrityRejectsMutationsOmissionsAndInventions() {
    let original = "Email Ana+Work@example.test. Open https://example.test/Case?x=1. Run `open()`. @Ana #明日"
    for (from, to) in [("Ana+Work", "ana+work"), ("/Case", "/case"), ("?x=1", "?x=2"),
                       ("`open()`", "`abrir()`"), ("@Ana", "@ana"), ("#明日", "#mañana"), ("Ana+Work@example.test", "")] {
        #expect(!TranslationIntegrity.preservesIdentifiers(original: original, translation: original.replacingOccurrences(of: from, with: to)))
    }
    #expect(!TranslationIntegrity.preservesIdentifiers(original: original, translation: original + " https://invented.test"))
    #expect(!TranslationIntegrity.preservesIdentifiers(original: original, translation: original + " @Ana"))
}

@Test func literalIntegrityRetainsFencedAndUnclosedCodeWhitespace() {
    for code in ["```kotlin\nval x = 1\n```", "```kotlin\nval x = 1", "`x = 1"] {
        #expect(TranslationIntegrity.preservesIdentifiers(original: "Run " + code, translation: "Exécuter " + code))
        #expect(!TranslationIntegrity.preservesIdentifiers(original: "Run " + code, translation: "Exécuter " + code.replacingOccurrences(of: "x =", with: "x=")))
    }
    #expect(TranslationIntegrity.preservesIdentifiers(original: "`mail@example.test`", translation: "`mail@example.test`"))
}

@Test func literalIntegrityRetainsRepeatedUnicodeIdentifiers() {
    #expect(TranslationIntegrity.preservesIdentifiers(original: "مرحبا @朋友 @朋友", translation: "Hello @朋友 @朋友"))
    #expect(!TranslationIntegrity.preservesIdentifiers(original: "مرحبا @朋友 @朋友", translation: "Hello @朋友"))
}
