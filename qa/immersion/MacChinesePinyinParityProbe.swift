import Foundation
import CryptoKit
import Darwin

private struct Inputs: Decodable {
    struct Item: Decodable { let id: String, text: String, group: String }
    let schema: String, cases: [Item]
}
private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private func peakRSS() -> Int64 { var v = rusage(); return getrusage(RUSAGE_SELF, &v) == 0 ? Int64(v.ru_maxrss) : -1 }
@main struct Probe {
    static func main() throws {
        let a = CommandLine.arguments; precondition(a.count == 5)
        let input = URL(fileURLWithPath: a[1]), output = URL(fileURLWithPath: a[3])
        let bytes = try Data(contentsOf: input), tables = try Data(contentsOf: URL(fileURLWithPath: a[2]))
        precondition(digest(bytes) == a[4] && !FileManager.default.fileExists(atPath: output.path))
        let inputs = try JSONDecoder().decode(Inputs.self, from: bytes)
        precondition(inputs.schema == "vipi-chinese-native-pinyin-1" && inputs.cases.count <= 512)
        precondition(Set(inputs.cases.map(\.id)).count == inputs.cases.count)
        let start = ProcessInfo.processInfo.systemUptime
        let reader = try ChineseFullReading(data: tables)
        let loadMS = (ProcessInfo.processInfo.systemUptime - start) * 1000
        let watchdog = DispatchSource.makeTimerSource(queue: .global()); watchdog.schedule(deadline: .now() + 90)
        watchdog.setEventHandler { exit(124) }; watchdog.resume(); defer { watchdog.cancel() }
        var rows: [[String: Any]] = []
        for item in inputs.cases {
            func run(_ protect: Bool) throws -> [String: Any] {
                let began = ProcessInfo.processInfo.systemUptime
                let value = try reader.resolve(item.text, preserveOpaque: protect)
                return ["reading": value.reading as Any? ?? NSNull(),
                    "pieces": value.pieces.map { ["source": $0.source, "reading": $0.reading,
                        "start_utf16": $0.startUTF16, "end_utf16": $0.endUTF16,
                        "converted": $0.converted, "protected": $0.protected] as [String: Any] },
                    "unresolved_utf16": value.unresolved.map { [$0.location, NSMaxRange($0)] },
                    "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000]
            }
            let raw = try autoreleasepool { try run(false) }
            let first = try autoreleasepool { try run(true) }, warm = try autoreleasepool { try run(true) }
            rows.append(["id": item.id, "group": item.group, "source": item.text,
                         "raw_parity": raw, "first": first, "warm": warm])
        }
        let result: [String: Any] = ["schema": "vipi-chinese-native-pinyin-output-1",
            "input_sha256": digest(bytes), "data_sha256": digest(tables), "policy": ChineseFullReading.policy,
            "complete": rows.count == inputs.cases.count, "count": rows.count, "table_load_ms": loadMS,
            "elapsed_seconds": ProcessInfo.processInfo.systemUptime - start, "peak_rss_bytes": peakRSS(),
            "platform": "macOS VM, not physical iOS", "downloads": false, "audio": false,
            "cases": rows]
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(to: output, options: .atomic)
    }
}
