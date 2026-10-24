import Foundation
import Testing
@testable import VipiCore

@Test func nativeWordBoundariesSupportUnspacedScriptsWithoutPartialMatches() {
    let entry = VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei"]])
    let result = ImmersionEngine().align(original: "Want coffee?", translation: "明天喝咖啡。", entries: [entry], density: 1, targetLanguage: "zh", targetBoundaries: [0, 2, 3, 5])
    #expect(result.spans.first?.translated == "咖啡")
    let partial = VocabularyEntry(source: "coffee", targets: ["咖"], romanizations: ["咖": ["ka"]])
    #expect(ImmersionEngine().align(original: "Want coffee?", translation: "明天喝咖啡。", entries: [partial], density: 1, targetLanguage: "zh", targetBoundaries: [0, 2, 3, 5]).spans.isEmpty)
}

@Test func protectedTargetIsNotContextEvidence() {
    let entry = VocabularyEntry(source: "coffee", targets: ["cafe"])
    for translated in ["https://example.test/cafe", "`cafe`", "@cafe"] {
        #expect(ImmersionEngine().align(original: "coffee", translation: translated, entries: [entry], density: 1).spans.isEmpty)
    }
}

@Test func mandatoryReadingRemainsSeparateFromSpeech() {
    let entry = VocabularyEntry(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei"]])
    let engine = ImmersionEngine()
    let result = engine.align(original: "Want coffee?", translation: "咖啡", entries: [entry], density: 1, targetLanguage: "zh")
    #expect(result.spans.first?.displayedTarget == "kafei")
    #expect(result.speech(source: "en", target: "zh").map(\.text).joined() == "Want 咖啡?")
    #expect(result.speech(source: "en", target: "zh", revealed: Set(result.spans.map(\.id))).map(\.text).joined() == "Want coffee?")
    for entries in [[VocabularyEntry(source: "coffee", targets: ["咖啡"])],
                    [.init(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["kafei", "wrong"]])],
                    [entry, .init(source: "coffee", targets: ["咖啡"], romanizations: ["咖啡": ["other"]])]] {
        #expect(engine.align(original: "coffee", translation: "咖啡", entries: entries, density: 1, targetLanguage: "zh").spans.isEmpty)
    }
}

@Test func duplicateEntriesCannotHideMultipleSenses() {
    let entries = [VocabularyEntry(source: "bank", targets: ["banco"]), VocabularyEntry(source: "Bank", targets: ["orilla"])]
    #expect(ImmersionEngine().align(original: "The bank is nearby.", translation: "El banco está en la orilla.", entries: entries, density: 1).spans.isEmpty)
    #expect(ImmersionEngine().align(original: "coffee", translation: "Café", entries: [.init(source: "coffee", targets: ["café", "Café"])], density: 1).spans.count == 1)
}

@Test func sentenceContextSelectsTheBankSense() {
    let entry = VocabularyEntry(source: "bank", targets: ["banco", "orilla"])
    let river = ImmersionEngine().align(original: "Meet at the river bank.", translation: "Nos vemos en la orilla del río.", entries: [entry], density: 0.3)
    #expect(river.spans.map(\.translated) == ["orilla"])
    let money = ImmersionEngine().align(original: "I am going to the bank.", translation: "Voy al banco.", entries: [entry], density: 0.3)
    #expect(money.spans.map(\.translated) == ["banco"])
}

@Test func uncertaintyKeepsTheOriginal() {
    let entries = [VocabularyEntry(source: "bank", targets: ["banco", "orilla"])]
    let engine = ImmersionEngine()
    #expect(engine.align(original: "The bank is by the bank.", translation: "El banco está junto a la orilla.", entries: entries, density: 1).spans.isEmpty)
    #expect(engine.align(original: "The bank is nearby.", translation: "El banco está en la orilla.", entries: entries, density: 1).spans.isEmpty)
    #expect(engine.align(original: "The bank is nearby.", translation: "Está cerca.", entries: entries, density: 1).spans.isEmpty)
}

@Test func protectsIdentifiersAndWordBoundaries() {
    let entries = [VocabularyEntry(source: "cat", targets: ["gato"])]
    for source in ["https://cat.example", "mycat@example.com", "`cat`", "@cat", "scatter"] {
        #expect(ImmersionEngine().align(original: source, translation: "gato", entries: entries, density: 1).spans.isEmpty)
    }
}

@Test func unicodeRangesAndVisibleSpeechAgree() {
    let original = "👩🏽‍💻 Want coffee?"
    let result = ImmersionEngine().align(original: original, translation: "¿Quieres café?", entries: [.init(source: "coffee", targets: ["café"])], density: 1)
    #expect(result.spans.count == 1)
    let mixed = result.speech(source: "en", target: "es")
    #expect(mixed.map(\.text).joined() == "👩🏽‍💻 Want café?")
    #expect(mixed.map(\.language) == ["en", "es", "en"])
    #expect(result.speech(source: "en", target: "es", revealed: Set(result.spans.map(\.id))).map(\.text).joined() == original)
}

@Test func phrasesWinWithoutOverlappingReplacements() {
    let result = ImmersionEngine().align(original: "See you in the morning.", translation: "Nos vemos por la mañana.", entries: [.init(source: "in the morning", targets: ["por la mañana"]), .init(source: "morning", targets: ["mañana"])], density: 1)
    #expect(result.spans.map(\.original) == ["in the morning"])
}

@Test func conflictingTargetAlignmentAbstains() {
    let result = ImmersionEngine().align(original: "A house and a home.", translation: "Una casa.", entries: [.init(source: "house", targets: ["casa"]), .init(source: "home", targets: ["casa"])], density: 1)
    #expect(result.spans.isEmpty)
}

@Test func disabledImmersionAndOversizeInputRemainOriginal() {
    let entries = [VocabularyEntry(source: "coffee", targets: ["café"])]
    #expect(ImmersionEngine().align(original: "coffee", translation: "café", entries: entries, density: 0).spans.isEmpty)
    #expect(ImmersionEngine().align(original: String(repeating: "x", count: 20_000) + " coffee", translation: "café", entries: entries, density: 1).spans.isEmpty)
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
