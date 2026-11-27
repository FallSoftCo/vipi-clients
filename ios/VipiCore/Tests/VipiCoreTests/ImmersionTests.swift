import Foundation
import Testing
@testable import VipiCore
@Test func assessedCompoundKeepsItsNestedNounAtBeginnerDensity() {
    let source = "I need a train ticket.", target = "Ninahitaji tiketi ya treni."
    let a = (source as NSString).range(of: "train ticket"), b = (target as NSString).range(of: "tiketi ya treni")
    let whole = VocabularyEntry(
        source: "train ticket", targets: ["tiketi ya treni"],
        sourceScope: .init(original: source, start: a.location, end: NSMaxRange(a)),
        targetScope: .init(translation: target, start: b.location, end: NSMaxRange(b)))
    let noun = VocabularyEntry(source: "train", targets: ["treni"])
    let engine = ImmersionEngine()
    let result = engine.align(original: source, translation: target, entries: [whole, noun], density: 0.25)
    #expect(result.spans.map(\.original) == ["train ticket"])
    #expect(result.speech(source: "en", target: "sw").map(\.text).joined() == "I need a tiketi ya treni.")
    #expect(
        engine.align(original: source, translation: target, entries: [noun], density: 0.25).spans.map(\.original) == [
            "train"
        ])
    #expect(engine.align(original: source, translation: target, entries: [whole, noun], density: 0).spans.isEmpty)
}
@Test func lowDensityKeepsAtomicPhrasesWithoutBypassingMeaningOrOffSetting() {
    let engine = ImmersionEngine()
    let entry = VocabularyEntry(source: "train ticket", targets: ["tiketi ya treni"])
    let source = "I need a train ticket.", target = "Ninahitaji tiketi ya treni."
    let result = engine.align(original: source, translation: target, entries: [entry], density: 0.25)
    #expect(result.spans.map(\.original) == ["train ticket"])
    #expect(result.original == source)
    #expect(engine.align(original: source, translation: target, entries: [entry], density: 0).spans.isEmpty)
    #expect(
        engine.align(original: source, translation: "Ninahitaji hoteli.", entries: [entry], density: 0.25).spans.isEmpty
    )
    let ambiguous = VocabularyEntry(source: "train ticket", targets: ["tiketi ya treni", "hoteli"])
    #expect(
        engine.align(original: source, translation: target + " hoteli", entries: [ambiguous], density: 0.25).spans
            .isEmpty)
}

@Test func nativeSourceEvidenceProtectsUnmappedCompoundsAndOmittedSenses() {
    let engine = ImmersionEngine()
    let blue = VocabularyEntry(source: "蓝", targets: ["blue"])
    let herb = VocabularyEntry(source: "板蓝根", targets: [], protectInner: true)
    #expect(
        engine.align(
            original: "板蓝根", translation: "blue root", entries: [blue], density: 1, sourceBoundaries: [0, 1, 2, 3]
        ).spans.count == 1)
    #expect(
        engine.align(
            original: "板蓝根", translation: "blue root", entries: [blue, herb], density: 1, sourceBoundaries: [0, 1, 2, 3]
        ).spans.isEmpty)
    let whole = VocabularyEntry(source: "板蓝根", targets: ["herb"])
    #expect(
        engine.align(
            original: "板蓝根", translation: "herb", entries: [whole, herb], density: 1, sourceBoundaries: [0, 1, 2, 3]
        ).spans.count == 1)
    #expect(
        engine.align(
            original: "蓝 板蓝根", translation: "blue herb", entries: [blue, herb], density: 1,
            sourceBoundaries: [0, 1, 2, 5]
        ).spans.count == 1)
    let moon = VocabularyEntry(source: "满月", targets: ["full moon"])
    let ambiguity = VocabularyEntry(source: "满月", targets: [], protectInner: true, unresolvedNativeSenses: true)
    #expect(
        engine.align(original: "满月", translation: "full moon", entries: [moon, ambiguity], density: 1).spans.isEmpty)
    let assessed = VocabularyEntry(
        source: "满月", targets: ["full moon"], sourceScope: .init(original: "满月", start: 0, end: 2))
    #expect(
        engine.align(original: "满月", translation: "full moon", entries: [assessed, ambiguity], density: 1).spans.count
            == 1)
}

@Test func nativeWordBoundariesSupportUnspacedScriptsWithoutPartialMatches() {
    let entry = VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei"]])
    let result = ImmersionEngine().align(
        original: "Want coffee?", translation: "明天喝咖啡。", entries: [entry], density: 1, targetLanguage: "zh",
        targetBoundaries: [0, 2, 3, 5])
    #expect(result.spans.first?.translated == "咖啡")
    let partial = VocabularyEntry(source: "coffee", targets: ["咖"], romanizations: ["咖": ["ka"]])
    #expect(
        ImmersionEngine().align(
            original: "Want coffee?", translation: "明天喝咖啡。", entries: [partial], density: 1, targetLanguage: "zh",
            targetBoundaries: [0, 2, 3, 5]
        ).spans.isEmpty)
}

@Test func protectedTargetIsNotContextEvidence() {
    let entry = VocabularyEntry(source: "coffee", targets: ["cafe"])
    for translated in ["https://example.test/cafe", "`cafe`", "@cafe"] {
        #expect(
            ImmersionEngine().align(original: "coffee", translation: translated, entries: [entry], density: 1).spans
                .isEmpty)
    }
}

@Test func mandatoryReadingRemainsSeparateFromSpeech() {
    let entry = VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei"]])
    let engine = ImmersionEngine()
    let result = engine.align(
        original: "Want coffee?", translation: "咖啡", entries: [entry], density: 1, targetLanguage: "zh")
    #expect(result.spans.first?.displayedTarget == "kafei")
    #expect(result.speech(source: "en", target: "zh").map(\.text).joined() == "Want 咖啡?")
    #expect(
        result.speech(source: "en", target: "zh", revealed: Set(result.spans.map(\.id))).map(\.text).joined()
            == "Want coffee?")
    for entries in [
        [VocabularyEntry(source: "coffee", targets: ["咖啡"])],
        [.init(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei", "wrong"]])],
        [entry, .init(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["other"]])]
    ] {
        #expect(
            engine.align(original: "coffee", translation: "咖啡", entries: entries, density: 1, targetLanguage: "zh")
                .spans.isEmpty)
    }
}

@Test func duplicateEntriesCannotHideMultipleSenses() {
    let entries = [
        VocabularyEntry(source: "bank", targets: ["banco"]), VocabularyEntry(source: "Bank", targets: ["orilla"])
    ]
    #expect(
        ImmersionEngine().align(
            original: "The bank is nearby.", translation: "El banco está en la orilla.", entries: entries, density: 1
        ).spans.isEmpty)
    #expect(
        ImmersionEngine().align(
            original: "coffee", translation: "Café", entries: [.init(source: "coffee", targets: ["café", "Café"])],
            density: 1
        ).spans.count == 1)
}

@Test func sentenceContextSelectsTheBankSense() {
    let entry = VocabularyEntry(source: "bank", targets: ["banco", "orilla"])
    let river = ImmersionEngine().align(
        original: "Meet at the river bank.", translation: "Nos vemos en la orilla del río.", entries: [entry],
        density: 0.3)
    #expect(river.spans.map(\.translated) == ["orilla"])
    let money = ImmersionEngine().align(
        original: "I am going to the bank.", translation: "Voy al banco.", entries: [entry], density: 0.3)
    #expect(money.spans.map(\.translated) == ["banco"])
}

@Test func uncertaintyKeepsTheOriginal() {
    let entries = [VocabularyEntry(source: "bank", targets: ["banco", "orilla"])]
    let engine = ImmersionEngine()
    #expect(
        engine.align(
            original: "The bank is by the bank.", translation: "El banco está junto a la orilla.", entries: entries,
            density: 1
        ).spans.isEmpty)
    #expect(
        engine.align(
            original: "The bank is nearby.", translation: "El banco está en la orilla.", entries: entries, density: 1
        ).spans.isEmpty)
    #expect(
        engine.align(original: "The bank is nearby.", translation: "Está cerca.", entries: entries, density: 1).spans
            .isEmpty)
}

@Test func protectsIdentifiersAndWordBoundaries() {
    let entries = [VocabularyEntry(source: "cat", targets: ["gato"])]
    for source in ["https://cat.example", "mycat@example.com", "`cat`", "@cat", "scatter"] {
        #expect(
            ImmersionEngine().align(original: source, translation: "gato", entries: entries, density: 1).spans.isEmpty)
    }
}

@Test func unicodeRangesAndVisibleSpeechAgree() {
    let original = "👩🏽‍💻 Want coffee?"
    let result = ImmersionEngine().align(
        original: original, translation: "¿Quieres café?", entries: [.init(source: "coffee", targets: ["café"])],
        density: 1)
    #expect(result.spans.count == 1)
    let mixed = result.speech(source: "en", target: "es")
    #expect(mixed.map(\.text).joined() == "👩🏽‍💻 Want café?")
    #expect(mixed.map(\.language) == ["en", "es", "en"])
    #expect(
        result.speech(source: "en", target: "es", revealed: Set(result.spans.map(\.id))).map(\.text).joined()
            == original)
}

@Test func phrasesWinWithoutOverlappingReplacements() {
    let result = ImmersionEngine().align(
        original: "See you in the morning.", translation: "Nos vemos por la mañana.",
        entries: [
            .init(source: "in the morning", targets: ["por la mañana"]), .init(source: "morning", targets: ["mañana"])
        ], density: 1)
    #expect(result.spans.map(\.original) == ["in the morning"])
}

@Test func conflictingTargetAlignmentAbstains() {
    let result = ImmersionEngine().align(
        original: "A house and a home.", translation: "Una casa.",
        entries: [.init(source: "house", targets: ["casa"]), .init(source: "home", targets: ["casa"])], density: 1)
    #expect(result.spans.isEmpty)
}

@Test func ineligibleEntriesStillPreserveAlignmentUncertainty() {
    let engine = ImmersionEngine()
    let result = engine.align(
        original: "Only the best way and best behavior.", translation: "最好的方式和行为。",
        entries: [
            .init(source: "only", targets: ["最好的"], romanizations: ["最好的": ["zuìhǎo de"]]),
            .init(source: "best", targets: ["最好的"], romanizations: ["最好的": ["zuìhǎo de"]])
        ], density: 1, targetLanguage: "zh", targetBoundaries: Set([0, 3, 5, 6, 8]))
    #expect(result.spans.isEmpty)
    let one = VocabularyEntry(source: "read", targets: ["読む"], romanizations: ["読む": ["yomu"]])
    let conflict = VocabularyEntry(source: "read", targets: ["読む"], romanizations: ["読む": ["yomu", "doku"]])
    #expect(
        engine.align(original: "read", translation: "読む", entries: [one, conflict], density: 1, targetLanguage: "ja")
            .spans.isEmpty)
    #expect(
        engine.align(
            original: "bank", translation: "banco orilla",
            entries: [.init(source: "bank", targets: ["banco"]), .init(source: "bank", targets: ["banco", "orilla"])],
            density: 1
        ).spans.isEmpty)
}

@Test func disabledImmersionAndOversizeInputRemainOriginal() {
    let entries = [VocabularyEntry(source: "coffee", targets: ["café"])]
    #expect(
        ImmersionEngine().align(original: "coffee", translation: "café", entries: entries, density: 0).spans.isEmpty)
    #expect(
        ImmersionEngine().align(
            original: String(repeating: "x", count: 20_000) + " coffee", translation: "café", entries: entries,
            density: 1
        ).spans.isEmpty)
}

@Test func deliveryDeadlineCannotMoveWithRetry() throws {
    let sent = Date(timeIntervalSince1970: 1_000_000)
    let window = DeliveryWindow(createdAt: sent)
    let restored = try JSONDecoder().decode(DeliveryWindow.self, from: JSONEncoder().encode(window))
    #expect(restored == window)
    #expect(restored.canRetry(at: sent.addingTimeInterval(259_199), state: .accepted))
    #expect(!restored.canRetry(at: sent.addingTimeInterval(259_200), state: .queued))
    #expect(!restored.canRetry(at: sent, state: .delivered))
    #expect(!restored.canRetry(at: sent, state: .expired))
}

@Test func familiarLatinReadingsKeepAccentsButRejectPhoneticGlyphs() {
    let engine = ImmersionEngine()
    for reading in ["kāfēi", "kōhī", "mu'jam", "sŏul"] {
        let entries = [VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": [reading]])]
        #expect(
            engine.align(original: "coffee", translation: "咖啡", entries: entries, density: 1, targetLanguage: "zh")
                .spans.first?.displayedTarget == reading)
    }
    for reading in ["ɡa", "ʰa", "ᴀ", "...", "コーヒー", "kafei / other"] {
        let entries = [VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": [reading]])]
        #expect(
            engine.align(original: "coffee", translation: "咖啡", entries: entries, density: 1, targetLanguage: "zh")
                .spans.isEmpty)
    }
}

@Test func multipleMeaningsNeedSentenceLocalEvidence() throws {
    let engine = ImmersionEngine()
    let entries = [
        VocabularyEntry(source: "period", targets: ["período"], contextHints: ["time"], requiresContext: true),
        VocabularyEntry(source: "period", targets: ["punto"], contextHints: ["punctuation"], requiresContext: true)
    ]
    for source in [
        "The period ends this sentence.", "The period ends here. Another time.", "The period uses `time`.",
        "The period has https://example.test/time"
    ] {
        #expect(engine.align(original: source, translation: "período", entries: entries, density: 1).spans.isEmpty)
    }
    #expect(
        engine.align(original: "A period of time.", translation: "período", entries: entries, density: 1).spans.count
            == 1)
    #expect(
        engine.align(original: "A period is punctuation.", translation: "período", entries: entries, density: 1).spans
            .isEmpty)
    #expect(
        engine.align(original: "A period is punctuation.", translation: "punto", entries: entries, density: 1).spans
            .count == 1)
    #expect(
        engine.align(original: "A period of time.", translation: "período punto", entries: entries, density: 1).spans
            .isEmpty)
    let decoded = try JSONDecoder().decode(VocabularyEntry.self, from: JSONEncoder().encode(entries[0]))
    #expect(decoded.requiresContext)
}
