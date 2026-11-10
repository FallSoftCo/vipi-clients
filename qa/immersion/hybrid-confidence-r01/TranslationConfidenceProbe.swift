import Foundation
import Translation
import NaturalLanguage
import CryptoKit

struct ProbeCase: Codable {
    let id: String
    let source: String
    let target: String
    let text: String
    let candidate: String?
}
struct ProbeProtocol: Codable { let cases: [ProbeCase] }

// Research only. No preparation, downloads, UI, product activation or confidence claim.
@main struct TranslationConfidenceProbe {
    @MainActor static func main() async throws {
        guard CommandLine.arguments.count == 3 else { fatalError("protocol.json output.jsonl") }
        let input = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let protocolInput = try JSONDecoder().decode(ProbeProtocol.self, from: input)
        guard !protocolInput.cases.isEmpty, protocolInput.cases.count <= 220,
              Set(protocolInput.cases.map(\.id)).count == protocolInput.cases.count,
              protocolInput.cases.allSatisfy({ $0.source == "en" && $0.source != $0.target && !$0.text.isEmpty && $0.text.utf16.count <= 4000 }) else {
            fatalError("Invalid bounded research protocol")
        }
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        try Data().write(to: output, options: .withoutOverwriting)
        let handle = try FileHandle(forWritingTo: output)
        defer { try? handle.close() }
        func emit(_ value: [String: Any]) throws {
            var data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
            data.append(10)
            try handle.write(contentsOf: data)
            try handle.synchronize()
        }
        let digest = SHA256.hash(data: input).map { String(format: "%02x", $0) }.joined()
        let checker = LanguageAvailability(preferredStrategy: .lowLatency)
        let embedding = NLEmbedding.sentenceEmbedding(for: .english)
        try emit(["kind": "start", "protocol_sha256": digest,
                  "cases": protocolInput.cases.count, "os": ProcessInfo.processInfo.operatingSystemVersionString,
                  "translation_quality_score_exposed": false, "english_sentence_embedding_available": embedding != nil,
                  "network_disabled": false, "models_prepared": false])
        for target in Array(Set(protocolInput.cases.map(\.target))).sorted() {
            let from = Locale.Language(identifier: "en"), to = Locale.Language(identifier: target)
            let forwardState = await checker.status(from: from, to: to)
            let reverseState = await checker.status(from: to, to: from)
            try emit(["kind": "pair", "source": "en", "target": target,
                      "forward_status": String(describing: forwardState), "reverse_status": String(describing: reverseState)])
            let cases = protocolInput.cases.filter { $0.target == target }
            guard forwardState == .installed && reverseState == .installed else {
                for row in cases { try emit(["kind": "case", "id": row.id, "target": target, "status": "unavailable"] ) }
                continue
            }
            let forward = TranslationSession(installedSource: from, target: to, preferredStrategy: .lowLatency)
            let reverse = TranslationSession(installedSource: to, target: from, preferredStrategy: .lowLatency)
            for row in cases {
                var result: [String: Any] = ["kind": "case", "id": row.id, "source": row.source, "target": row.target,
                    "original": row.text, "candidate_origin": row.candidate == nil ? "native_translation" : "authored_diagnostic"]
                do {
                    let start = ContinuousClock.now
                    let candidate: String
                    if let supplied = row.candidate { candidate = supplied }
                    else {
                        let response = try await forward.translate(row.text)
                        guard response.sourceText == row.text else { throw NSError(domain: "SourceBinding", code: 1) }
                        candidate = response.targetText
                    }
                    result["forward_ms"] = row.candidate == nil ? milliseconds(start) : 0
                    result["translation"] = candidate
                    let reverseStart = ContinuousClock.now
                    let response = try await reverse.translate(candidate)
                    guard response.sourceText == candidate else { throw NSError(domain: "SourceBinding", code: 2) }
                    result["reverse_ms"] = milliseconds(reverseStart)
                    result["round_trip"] = response.targetText
                    if let embedding {
                        let scoreStart = ContinuousClock.now
                        let distance = embedding.distance(between: row.text, and: response.targetText)
                        if distance.isFinite { result["english_sentence_cosine_similarity"] = 1 - distance }
                        result["embedding_ms"] = milliseconds(scoreStart)
                    }
                    result["status"] = "complete"
                } catch { result["status"] = "error"; result["error"] = String(describing: error) }
                try emit(result)
            }
            forward.cancel(); reverse.cancel()
        }
        try emit(["kind": "complete", "protocol_sha256": digest])
    }
    static func milliseconds(_ start: ContinuousClock.Instant) -> Double {
        let value = start.duration(to: .now).components
        return Double(value.seconds) * 1000 + Double(value.attoseconds) / 1e15
    }
}
