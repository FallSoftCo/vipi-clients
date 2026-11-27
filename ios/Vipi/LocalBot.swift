import Foundation
import FoundationModels

enum LocalBotAvailability: Equatable {
    case checking, ready, unavailable(String)
    var message: String? {
        switch self {
        case .checking: String(localized: "Checking this device…")
        case .ready: nil
        case .unavailable(let message): message
        }
    }
}

struct LocalBotTurn: Codable, Sendable {
    let role: String
    let content: String
}

enum LocalBotFailure: Error, LocalizedError {
    case unavailable(String), contextTooLong, refused, busy, incomplete
    var errorDescription: String? {
        switch self {
        case .unavailable(let reason): reason
        case .contextTooLong:
            String(localized: "This message is too long for vBot on this device. Try a shorter message.")
        case .refused: String(localized: "vBot can’t answer that message. Try asking something else.")
        case .busy: String(localized: "vBot is busy. Try again shortly.")
        case .incomplete: String(localized: "vBot couldn’t finish. Your message is still here.")
        }
    }
}

@MainActor protocol LocalBotGenerating: AnyObject {
    var provider: String { get }
    var maximumContextBytes: Int { get }
    func availability(language: String) -> LocalBotAvailability
    func reply(to turns: [LocalBotTurn], language: String) async throws -> String
}

/// Only the operating system model. No network or friend-journal dependency.
@MainActor final class AppleLocalBot: LocalBotGenerating {
    let provider = "apple-foundation-models"
    // Conservative byte bound leaves room for instructions and a short reply
    // in the 4096-token model, including on iOS26.0 without tokenCount().
    let maximumContextBytes = 3072
    func availability(language: String) -> LocalBotAvailability {
        guard #available(iOS 26.0, macOS 26.0, *) else {
            return .unavailable(
                String(localized: "vBot needs iOS 26 or later and a device that supports Apple Intelligence."))
        }
        let model = SystemLanguageModel.default
        switch model.availability {
        case .available:
            guard model.supportsLocale(Locale(identifier: language)) else {
                return .unavailable(
                    String(
                        localized:
                            "Apple Intelligence doesn’t support your writing language yet. You can still chat with friends."
                    ))
            }
            return .ready
        case .unavailable(.deviceNotEligible):
            return .unavailable(
                String(
                    localized: "vBot needs a device that supports Apple Intelligence. You can still chat with friends.")
            )
        case .unavailable(.appleIntelligenceNotEnabled):
            return .unavailable(String(localized: "Turn on Apple Intelligence in Settings to use vBot on this device."))
        case .unavailable(.modelNotReady):
            return .unavailable(String(localized: "Apple Intelligence is still preparing. Try vBot again shortly."))
        case .unavailable:
            return .unavailable(String(localized: "vBot is not available on this device right now."))
        @unknown default:
            return .unavailable(String(localized: "vBot is not available on this device right now."))
        }
    }
    func reply(to turns: [LocalBotTurn], language: String) async throws -> String {
        let state = availability(language: language)
        guard state == .ready else { throw LocalBotFailure.unavailable(state.message ?? "") }
        guard #available(iOS 26.0, macOS 26.0, *) else { throw LocalBotFailure.incomplete }
        guard let last = turns.last, last.role == "user",
            turns.reduce(0, { $0 + $1.content.utf8.count }) <= maximumContextBytes
        else {
            throw LocalBotFailure.contextTooLong
        }
        let instructions = """
            You are vBot, a friendly chatbot in Vipi. Reply naturally in one to three short sentences.
            The person's locale is \(language). Respond in that language.
            Talk about the person's message; do not give language lessons unless asked.
            You cannot read their friend chats, access current events, or take actions outside this conversation.
            Be honest about uncertainty. Do not claim to be human or invent personal memories.
            """
        var entries: [Transcript.Entry] = [
            .instructions(
                .init(
                    segments: [.text(.init(content: instructions))], toolDefinitions: []))
        ]
        for turn in turns.dropLast() {
            let segments: [Transcript.Segment] = [.text(.init(content: turn.content))]
            if turn.role == "user" {
                entries.append(.prompt(.init(segments: segments)))
            } else if turn.role == "assistant" {
                entries.append(.response(.init(assetIDs: [], segments: segments)))
            }
        }
        // Reconstruct only committed local history each turn: failed/cancelled
        // responses cannot contaminate later context or resurrect deleted text.
        let session = LanguageModelSession(model: .default, transcript: Transcript(entries: entries))
        do {
            try Task.checkCancellation()
            let result = try await session.respond(
                to: last.content, options: GenerationOptions(maximumResponseTokens: 384))
            try Task.checkCancellation()
            let text = result.content.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty, text.utf8.count <= 16384 else { throw LocalBotFailure.incomplete }
            return text
        } catch let error as LanguageModelSession.GenerationError {
            switch error {
            case .exceededContextWindowSize: throw LocalBotFailure.contextTooLong
            case .guardrailViolation, .refusal: throw LocalBotFailure.refused
            case .rateLimited, .concurrentRequests: throw LocalBotFailure.busy
            case .unsupportedLanguageOrLocale:
                throw LocalBotFailure.unavailable(
                    String(localized: "Apple Intelligence doesn’t support a language in this message yet."))
            case .assetsUnavailable:
                throw LocalBotFailure.unavailable(
                    String(localized: "Apple Intelligence is still preparing. Try vBot again shortly."))
            default: throw LocalBotFailure.incomplete
            }
        }
    }
}
