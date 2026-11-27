import Foundation
import Testing
@testable import VipiCore

@Test func competingSourceContextVetoesMistranslatedPolysemy() {
    for (word, cue, wrong, right) in [
        ("bank", "river", "banco", "orilla"), ("mouse", "computer", "ratón animal", "ratón informático"),
        ("crane", "construction", "grulla", "grúa")
    ] {
        let entries = [
            VocabularyEntry(source: word, targets: [wrong], contextHints: ["animal", "institution"]),
            VocabularyEntry(source: word, targets: [right], contextHints: [cue])
        ]
        let result = ImmersionEngine().align(
            original: "The \(word) is beside the \(cue).", translation: wrong, entries: entries, density: 1)
        #expect(result.spans.isEmpty)
        #expect(
            ImmersionEngine().align(
                original: "The \(word) is beside the \(cue).", translation: right, entries: entries, density: 1
            ).spans.count == 1)
    }
}

@Test func cuesDoNotCrossSentencesOrComeFromProtectedIdentifiers() {
    let entries = [
        VocabularyEntry(source: "bank", targets: ["banco"], contextHints: ["institution"]),
        VocabularyEntry(source: "bank", targets: ["orilla"], contextHints: ["river"])
    ]
    for text in [
        "Go to the bank. Then see the river.", "The bank has https://example.test/river", "The bank uses `river`."
    ] {
        #expect(
            ImmersionEngine().align(original: text, translation: "banco", entries: entries, density: 1).spans.count == 1
        )
    }
    #expect(
        ImmersionEngine().align(
            original: "The bank is by the river.", translation: "banco orilla", entries: entries, density: 1
        ).spans.isEmpty)
}

@Test func unmappedOrConflictingEvidenceCannotBeOverruledByAnotherCue() {
    let entries = [
        VocabularyEntry(source: "bank", targets: ["banco"], contextHints: ["institution"], requiresContext: true),
        VocabularyEntry(source: "bank", targets: [], contextHints: ["river"], requiresContext: true)
    ]
    #expect(
        ImmersionEngine().align(
            original: "The bank is an institution.", translation: "banco", entries: entries, density: 1
        ).spans.count == 1)
    for text in ["Walk by the river bank.", "The institution is by the river bank.", "Go to the bank."] {
        #expect(
            ImmersionEngine().align(original: text, translation: "banco", entries: entries, density: 1).spans.isEmpty)
    }
}

@Test func arabicVowelsPreserveOriginalRangesAndReadingUncertainty() {
    let engine = ImmersionEngine()
    let entry = VocabularyEntry(source: "coffee", targets: ["قَهْوَة"], romanizations: ["قَهْوَة": ["qahwa"]])
    for value in ["قهوة", "قَهْوَة", "قَـهْوَة"] {
        let result = engine.align(
            original: "coffee", translation: value, entries: [entry], density: 1, targetLanguage: "ar")
        #expect(result.spans.first?.translated == value)
        #expect(result.spans.first?.displayedTarget == "qahwa")
        #expect(result.speech(source: "en", target: "ar").first?.text == value)
    }
    let uncertain = VocabularyEntry(
        source: "flag", targets: ["عَلَم", "عِلْم"], romanizations: ["عَلَم": ["alam"], "عِلْم": ["ilm"]])
    #expect(
        engine.align(original: "flag", translation: "علم", entries: [uncertain], density: 1, targetLanguage: "ar").spans
            .isEmpty)
    #expect(ImmersionEngine.lookupKey("أمل") != ImmersionEngine.lookupKey("امل"))
}
