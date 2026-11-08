import Foundation
import Translation
import NaturalLanguage
import CryptoKit
import Darwin

/// Exact-request native provider capture. No dictionary, pack expansion, model
/// downloads or extra word translations. Compile with TranslationIntegrity.swift.
@main struct MacDirectTranslationProbe {
    struct ProtocolFile: Decodable {
        struct Request: Decodable { let id, source, target, text: String }
        struct Message: Decodable { let full_query_id: String }
        let requests: [Request]
        let messages: [Message]
    }
    static func sha(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    static func milliseconds(_ start: ContinuousClock.Instant) -> Double {
        let elapsed = start.duration(to: .now).components
        return Double(elapsed.seconds)*1000 + Double(elapsed.attoseconds)/1e15
    }
    static func ranges(_ text: String, language: String) -> [[Int]] {
        // This first probe is explicitly English/Spanish, matching the native
        // Latin-language NLTokenizer path. It makes no non-Roman claim.
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        tokenizer.setLanguage(NLLanguage(rawValue: language))
        var result: [[Int]] = []
        tokenizer.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in
            if text[range].unicodeScalars.contains(where: { CharacterSet.letters.contains($0) }) {
                let scope = NSRange(range, in: text)
                result.append([scope.location, NSMaxRange(scope)])
            }
            return true
        }
        return result
    }
    @MainActor static func main() async throws {
        let args = CommandLine.arguments
        guard args.count == 4 || (args.count == 5 && args[4] == "--full-only") else {
            fatalError("protocol.json new-or-incomplete-output.json expected-sha256 [--full-only]")
        }
        let bytes = try Data(contentsOf: URL(fileURLWithPath: args[1]))
        guard sha(bytes) == args[3] else { fatalError("Protocol hash differs") }
        let input = try JSONDecoder().decode(ProtocolFile.self, from: bytes)
        guard input.requests.count <= 500,
              Set(input.requests.map(\.id)).count == input.requests.count,
              input.requests.allSatisfy({ $0.source == "en" && $0.target == "es" && !$0.text.isEmpty && $0.text.utf16.count <= 16384 }) else {
            fatalError("Unqualified protocol")
        }
        for request in input.requests {
            guard sha(Data((request.source+"\0"+request.target+"\0"+request.text).utf8)) == request.id else { fatalError("Request identity differs") }
        }
        let fullIDs = input.messages.map(\.full_query_id)
        let byID = Dictionary(uniqueKeysWithValues: input.requests.map { ($0.id, $0) })
        guard Set(fullIDs).isSubset(of: Set(byID.keys)) else { fatalError("Missing full request") }
        let selected = fullIDs.map { byID[$0]! } + (args.count == 5 ? [] : input.requests.filter { !Set(fullIDs).contains($0.id) })
        let output = URL(fileURLWithPath: args[2])
        var rows: [[String: Any]] = []
        let started = ISO8601DateFormatter().string(from: Date())
        var models: [[String: Any]] = []
        if FileManager.default.fileExists(atPath: output.path) {
            let existing = try JSONSerialization.jsonObject(with: Data(contentsOf: output)) as! [String: Any]
            guard existing["input_sha256"] as? String == args[3], existing["complete"] as? Bool == false else { fatalError("Preserve prior result") }
            rows = existing["requests"] as! [[String: Any]]
            for row in rows {
                guard let id = row["id"] as? String, let request = byID[id],
                      row["text"] as? String == request.text, row["source"] as? String == request.source,
                      row["target"] as? String == request.target else { fatalError("Resume identity differs") }
            }
        }
        let previousCount = rows.count
        var inFlight: String?
        func save(_ complete: Bool, reason: String) throws {
            let report: [String: Any] = ["schema": "vipi-direct-extension-native-capture-1",
                "input_sha256": args[3], "complete": complete, "production": false, "training_use": false,
                "provider": "Apple Translation lowLatency; installed models only",
                "platform": "macOS existing development VM; not physical iOS",
                "system": ProcessInfo.processInfo.operatingSystemVersionString,
                "network_disabled": false, "model_downloads_requested": false,
                "started_at": started, "updated_at": ISO8601DateFormatter().string(from: Date()),
                "requested_count": input.requests.count, "invocation_selected_count": selected.count,
                "resumed_verified_results": previousCount, "completed_count": rows.count,
                "new_provider_calls": rows.count-previousCount, "models": models,
                "requests": rows, "in_flight": inFlight as Any? ?? NSNull(), "termination_reason": reason]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
        }
        try save(false, reason: "checking_installed_models")
        // A process deadline also bounds an unexpectedly non-cooperative API.
        // Every completed row and the current request ID are already durable.
        let watchdog = Task.detached {
            try? await Task.sleep(for: .seconds(600))
            if !Task.isCancelled { Darwin._exit(124) }
        }
        defer { watchdog.cancel() }
        let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "es")
        let availability = await LanguageAvailability(preferredStrategy: .lowLatency).status(from: source, to: target)
        models.append(["source": "en", "target": "es", "availability": String(describing: availability)])
        guard availability == .installed else { try save(false, reason: "models_not_installed"); return }
        let session = TranslationSession(installedSource: source, target: target, preferredStrategy: .lowLatency)
        defer { session.cancel() }
        var first = true
        for request in selected where !rows.contains(where: { $0["id"] as? String == request.id }) {
            inFlight = request.id
            try save(false, reason: "running")
            let start = ContinuousClock.now
            var timedOut = false
            let timeout = Task { @MainActor in
                try? await Task.sleep(for: .seconds(30))
                if !Task.isCancelled { timedOut = true; session.cancel() }
            }
            var row: [String: Any] = ["id": request.id, "source": request.source, "target": request.target,
                "text": request.text, "input_sha256": args[3], "native_source_word_ranges": ranges(request.text, language: request.source),
                "first_call_for_prepared_pair": first, "started_at": ISO8601DateFormatter().string(from: Date())]
            first = false
            do {
                let translated = try await session.translate(request.text).targetText
                row["translation"] = translated
                row["native_target_word_ranges"] = ranges(translated, language: request.target)
                row["identifiers_preserved"] = TranslationIntegrity.preservesIdentifiers(original: request.text, translation: translated)
                row["status"] = "translated"
            } catch {
                row["status"] = timedOut ? "timeout" : "failed"
                row["error"] = String(describing: error)
            }
            timeout.cancel()
            row["elapsed_ms"] = milliseconds(start)
            rows.append(row)
            inFlight = nil
            try save(false, reason: timedOut ? "call_timeout" : "running")
            if timedOut { return }
        }
        try save(rows.count == input.requests.count, reason: args.count == 5 ? "full_only_finished" : "finished")
    }
}
