import AVFoundation
import Foundation
import Translation
import XCTest

final class SwahiliCapabilityTests: XCTestCase {
    nonisolated private static func translationCapabilities() async -> ([String], String) {
        let availability = LanguageAvailability()
        let languages = await availability.supportedLanguages.map(\.minimalIdentifier).sorted()
        let status = await availability.status(from: .init(identifier: "en"), to: .init(identifier: "sw"))
        return (languages, String(describing: status))
    }
    @MainActor func testRecordDeviceTranslationAndVoiceCapabilities() async throws {
        let (languages, status) = await Self.translationCapabilities()
        let voices = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.hasPrefix("sw") }.map {
            [
                "identifier": $0.identifier, "language": $0.language, "name": $0.name,
                "quality": String($0.quality.rawValue)
            ]
        }
        let result: [String: Any] = [
            "schema": "vipi-swahili-capabilities-1", "system": ProcessInfo.processInfo.operatingSystemVersionString,
            "apple_translation_languages": languages, "english_swahili_status": status,
            "installed_swahili_voices": voices, "execution_evidence": false
        ]
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let output = documents.appendingPathComponent("swahili-capabilities-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path), "Preserve earlier capability receipts")
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(
            to: output, options: .withoutOverwriting)
        XCTAssertFalse(languages.isEmpty)
    }
}
