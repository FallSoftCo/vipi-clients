import Foundation
import CryptoKit
import Darwin

private struct Inputs: Decodable {
    struct Item: Decodable { let id: String, text: String, expectInvalid: Bool }
    let cases: [Item]
}
private func hash(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
@main struct ResourceProbe {
    static func main() throws {
        let args = CommandLine.arguments; precondition(args.count == 5)
        let input = try Data(contentsOf: URL(fileURLWithPath: args[1]))
        precondition(hash(input) == args[4] && !FileManager.default.fileExists(atPath: args[3]))
        let rows = try JSONDecoder().decode(Inputs.self, from: input).cases
        precondition(rows.count <= 8)
        let reader = try ChineseFullReading(data: Data(contentsOf: URL(fileURLWithPath: args[2])))
        let watchdog = DispatchSource.makeTimerSource(queue: .global()); watchdog.schedule(deadline: .now() + 90)
        watchdog.setEventHandler { exit(124) }; watchdog.resume(); defer { watchdog.cancel() }
        var results: [[String: Any]] = []
        for item in rows {
            for pass in 0..<2 {
                let start = ProcessInfo.processInfo.systemUptime
                do {
                    let raw = try reader.resolve(item.text, preserveOpaque: false)
                    let value = try reader.resolve(item.text)
                    precondition(!item.expectInvalid && value.pieces.map(\.source).joined() == item.text)
                    let literalPreserved = value.pieces.filter(\.protected).allSatisfy { $0.source == $0.reading && !$0.converted }
                    precondition(literalPreserved)
                    results.append(["id": item.id, "pass": pass, "status": "resolved",
                        "milliseconds": (ProcessInfo.processInfo.systemUptime - start) * 1000,
                        "utf16": item.text.utf16.count, "scalar_count": value.pieces.count,
                        "whole_reading_available": value.reading != nil, "literal_preserved": literalPreserved,
                        "raw_reading_sequence_sha256": hash(Data(raw.pieces.map(\.reading).joined(separator: "\0").utf8)),
                        "guarded_reading_sha256": value.reading.map { hash(Data($0.utf8)) } as Any? ?? NSNull()])
                } catch ChineseFullReading.Invalid.input {
                    precondition(item.expectInvalid)
                    results.append(["id": item.id, "pass": pass, "status": "invalid_input",
                        "milliseconds": (ProcessInfo.processInfo.systemUptime - start) * 1000])
                }
            }
        }
        var rss = rusage(); _ = getrusage(RUSAGE_SELF, &rss)
        let result: [String: Any] = ["input_sha256": hash(input), "policy": ChineseFullReading.policy,
            "platform": "macOS VM resource control; not physical iOS", "peak_rss_bytes": rss.ru_maxrss,
            "rows": results]
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(to: URL(fileURLWithPath: args[3]), options: .atomic)
    }
}
