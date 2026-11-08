import Foundation
import CryptoKit
import NaturalLanguage
import Darwin

@main enum MacJapaneseReadingProbe {
    struct Input: Decodable {
        struct Item: Decodable { let id: String, text: String, group: String }
        let schema: String, cases: [Item]
    }
    struct Observation: Codable {
        let result: JapaneseReadingCandidate.Result
        let milliseconds: Double, peakRSSBytes: Int64
    }
    struct Row: Codable {
        let id: String, source: String, group: String
        let first: Observation, warm: Observation
    }
    struct Report: Codable {
        let schema = "vipi-japanese-native-guard-report-1"
        let platform = "macOS VM native APIs; not physical iOS or acoustic validation"
        let policy = JapaneseReadingCandidate.policy
        let inputSHA256: String, os: String, lexicalSchemes: [String]
        let requestedAssets = false, generatedAudio = false, networkDisabled = false
        let complete: Bool, elapsedSeconds: Double, peakRSSBytes: Int64, cases: [Row]
    }
    static func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func rss() -> Int64 {
        var usage = rusage()
        return getrusage(RUSAGE_SELF, &usage) == 0 ? Int64(usage.ru_maxrss) : -1
    }
    static func observe(_ text: String) -> Observation {
        let start = ProcessInfo.processInfo.systemUptime
        let result = JapaneseReadingCandidate.resolve(text)
        return .init(result: result, milliseconds: (ProcessInfo.processInfo.systemUptime - start) * 1000, peakRSSBytes: rss())
    }
    static func main() throws {
        let args = CommandLine.arguments
        precondition(args.count == 4, "INPUT NEW_OUTPUT INPUT_SHA256")
        let output = URL(fileURLWithPath: args[2])
        precondition(!FileManager.default.fileExists(atPath: output.path))
        let bytes = try Data(contentsOf: URL(fileURLWithPath: args[1]))
        precondition(sha(bytes) == args[3])
        let input = try JSONDecoder().decode(Input.self, from: bytes)
        precondition(input.schema == "vipi-japanese-guard-input-1" && input.cases.count == 32)
        precondition(Set(input.cases.map(\.id)).count == input.cases.count)
        let watchdog = DispatchSource.makeTimerSource(queue: .global(qos: .utility))
        watchdog.schedule(deadline: .now() + 90)
        watchdog.setEventHandler { exit(124) }; watchdog.resume(); defer { watchdog.cancel() }
        let start = ProcessInfo.processInfo.systemUptime
        let schemes = NLTagger.availableTagSchemes(for: .word, language: .japanese).map(\.rawValue).sorted()
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        var rows: [Row] = []
        for item in input.cases {
            let first = autoreleasepool { observe(item.text) }
            let warm = autoreleasepool { observe(item.text) }
            rows.append(.init(id: item.id, source: item.text, group: item.group, first: first, warm: warm))
            let report = Report(inputSHA256: sha(bytes), os: ProcessInfo.processInfo.operatingSystemVersionString,
                lexicalSchemes: schemes, complete: rows.count == input.cases.count,
                elapsedSeconds: ProcessInfo.processInfo.systemUptime - start, peakRSSBytes: rss(), cases: rows)
            try encoder.encode(report).write(to: output, options: .atomic)
        }
    }
}
