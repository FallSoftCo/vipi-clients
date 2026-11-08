import Foundation
import Translation
import CryptoKit

struct LabCase: Codable, Identifiable {
    let id: String
    let source: String
    let target: String
    let text: String
}
struct LabProtocol: Codable {
    let name: String
    var strategy: String? = nil
    let cases: [LabCase]
}
struct LabRange: Codable {
    let location: Int
    let length: Int
}
struct WordResult: Codable, Identifiable {
    let id: Int
    let source: String
    let range: LabRange
    let isolated: String?
    let milliseconds: Double
    let reused: Bool
    let occurrencesInSentence: [LabRange]
    let error: String?
}
struct CaseResult: Codable, Identifiable {
    var id: String { input.id }
    let input: LabCase
    let availability: String
    let fullTranslation: String?
    let sentenceMilliseconds: Double?
    let words: [WordResult]
    let error: String?
    var renderedAll: String { preview(indices: Set(words.filter { $0.isolated != nil }.map(\.id))) }
    func preview(indices: Set<Int>) -> String {
        let result = NSMutableString(string: input.text)
        for word in words.reversed() where indices.contains(word.id) {
            if let isolated = word.isolated {
                result.replaceCharacters(in: NSRange(location: word.range.location, length: word.range.length), with: isolated)
            }
        }
        return result as String
    }
}
struct LabReport: Codable {
    var schema = 1
    var platform = "macOS"
    var provider = "Apple Translation"
    var strategy = "lowLatency"
    var requestedStrategy: String? = nil
    var modelVersion = "not exposed by public API"
    var linguisticAcceptance = false
    var networkDisabled = false
    var notes = [
        "Isolated words and full sentences are separate native translation requests.",
        "A normalized token sequence appearing in the full translation is a diagnostic, not proof of correct sense or replaceability.",
        "Source word order, punctuation and whitespace are preserved in previews; isolated output is not repaired.",
        "Words use the iOS LocalImmersion.words tokenizer compiled from the same source.",
        "This is an authored diagnostic or supplied corpus, not a population coverage estimate.",
        "A full sentence translation is a comparison, not a gold reference."
    ]
    let createdAt: Date
    let system: String
    let protocolName: String
    let inputSHA256: String
    let results: [CaseResult]
    let cancelled: Bool
}
enum LabFailure: LocalizedError {
    case invalid(String)
    var errorDescription: String? { if case .invalid(let text) = self { return text }; return nil }
}
@MainActor
final class ComparisonRunner {
    private var current: TranslationSession?
    private var stopped = false
    func cancel() { stopped = true; current?.cancel() }
    func run(_ protocolData: Data, progress: (Int, Int, String) -> Void) async throws -> LabReport {
        let protocolInput = try JSONDecoder().decode(LabProtocol.self, from: protocolData)
        guard !protocolInput.cases.isEmpty, protocolInput.cases.count <= 10000 else {
            throw LabFailure.invalid("Provide 1–10,000 cases.")
        }
        var identities = Set<String>()
        for input in protocolInput.cases {
            guard input.source != input.target, !input.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  input.text.utf16.count <= 16384,
                  identities.insert("\(input.id)|\(input.source)|\(input.target)").inserted else {
                throw LabFailure.invalid("Each case needs distinct source/target languages, nonempty text under 16,385 UTF-16 units, and a unique id/pair.")
            }
        }
        let requested = protocolInput.strategy ?? "lowLatency"
        guard ["lowLatency", "platformDefault"].contains(requested) else { throw LabFailure.invalid("Strategy must be lowLatency or platformDefault.") }
        let actual = requested == "lowLatency" || TranslationSession.Configuration().preferredStrategy == .lowLatency ? "lowLatency" : "highFidelity"
        stopped = false
        var results: [CaseResult] = []
        var cache: [String: (String, Double)] = [:]
        var pair = ""
        defer { current?.cancel(); current = nil }
        let availability = requested == "platformDefault" ? LanguageAvailability() : LanguageAvailability(preferredStrategy: .lowLatency)
        for input in protocolInput.cases {
            if stopped || Task.isCancelled { break }
            progress(results.count, protocolInput.cases.count, "\(input.source) → \(input.target) · \(input.id)")
            let from = Locale.Language(identifier: input.source), to = Locale.Language(identifier: input.target)
            let state = await availability.status(from: from, to: to)
            guard state == .installed else {
                results.append(.init(input: input, availability: String(describing: state),
                    fullTranslation: nil, sentenceMilliseconds: nil, words: [],
                    error: state == .supported ? "Models are not installed. Use Prepare languages in the app." : "Language pair unsupported by this Apple translation strategy."))
                continue
            }
            if pair != "\(input.source)|\(input.target)" {
                current?.cancel()
                current = requested == "platformDefault"
                    ? TranslationSession(installedSource: from, target: to)
                    : TranslationSession(installedSource: from, target: to, preferredStrategy: .lowLatency)
                pair = "\(input.source)|\(input.target)"
            }
            guard let session = current else { throw LabFailure.invalid("No translation session") }
            do {
                let start = ContinuousClock.now
                let full = try await session.translate(input.text).targetText
                let elapsed = Self.ms(start)
                var words: [WordResult] = []
                for (index, range) in LabTokenizer.words(input.text, language: input.source).enumerated() {
                    if stopped || Task.isCancelled { break }
                    let word = (input.text as NSString).substring(with: range)
                    let key = "\(pair)|\(word)"
                    do {
                        let cached = cache[key]
                        let isolated: String, duration: Double
                        if let cached { isolated = cached.0; duration = cached.1 }
                        else {
                            let wordStart = ContinuousClock.now
                            isolated = try await session.translate(word).targetText
                            duration = Self.ms(wordStart)
                            cache[key] = (isolated, duration)
                        }
                        words.append(.init(id: index, source: word, range: .init(location: range.location, length: range.length),
                            isolated: isolated, milliseconds: duration, reused: cached != nil,
                            occurrencesInSentence: Self.matches(isolated, in: full, language: input.target), error: nil))
                    } catch {
                        words.append(.init(id: index, source: word, range: .init(location: range.location, length: range.length),
                            isolated: nil, milliseconds: 0, reused: false, occurrencesInSentence: [], error: String(describing: error)))
                    }
                }
                results.append(.init(input: input, availability: "installed", fullTranslation: full,
                    sentenceMilliseconds: elapsed, words: words,
                    error: stopped || Task.isCancelled ? "Cancelled; word results incomplete." : nil))
            } catch {
                results.append(.init(input: input, availability: "installed", fullTranslation: nil,
                    sentenceMilliseconds: nil, words: [], error: String(describing: error)))
            }
        }
        progress(results.count, protocolInput.cases.count, stopped ? "Cancelled" : "Finished")
        return LabReport(strategy: actual, requestedStrategy: requested, createdAt: Date(), system: ProcessInfo.processInfo.operatingSystemVersionString,
            protocolName: protocolInput.name,
            inputSHA256: SHA256.hash(data: protocolData).map { String(format: "%02x", $0) }.joined(),
            results: results, cancelled: stopped || Task.isCancelled)
    }
    static func ms(_ start: ContinuousClock.Instant) -> Double {
        let parts = start.duration(to: .now).components
        return Double(parts.seconds) * 1000 + Double(parts.attoseconds) / 1e15
    }
    static func normalized(_ value: String, language: String) -> String {
        value.precomposedStringWithCanonicalMapping.lowercased(with: Locale(identifier: language))
    }
    static func matches(_ isolated: String, in sentence: String, language: String) -> [LabRange] {
        let ranges = LabTokenizer.words(sentence, language: language)
        let needles = LabTokenizer.words(isolated, language: language).map {
            normalized((isolated as NSString).substring(with: $0), language: language)
        }
        let haystack = ranges.map { normalized((sentence as NSString).substring(with: $0), language: language) }
        guard !needles.isEmpty, needles.count <= haystack.count else { return [] }
        return (0...(haystack.count - needles.count)).compactMap { start in
            guard Array(haystack[start..<(start + needles.count)]) == needles else { return nil }
            let end = NSMaxRange(ranges[start + needles.count - 1])
            return LabRange(location: ranges[start].location, length: end - ranges[start].location)
        }
    }
    static func encoded(_ report: LabReport) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(report)
    }
}
