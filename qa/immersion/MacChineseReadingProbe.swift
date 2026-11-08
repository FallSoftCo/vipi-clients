// Frozen private research inputs; no labels are passed to the native candidate.
import Foundation
import CryptoKit
import Darwin

private struct Inputs: Decodable {
    struct Item: Decodable { let id: String; let text: String; let group: String }
    let schema: String
    let cases: [Item]
}
private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private func peakRSS() -> Int64 { var v = rusage(); return getrusage(RUSAGE_SELF, &v) == 0 ? Int64(v.ru_maxrss) : -1 }
@main struct Probe {
    static func main() throws {
        let a = CommandLine.arguments; precondition(a.count == 4)
        let input = URL(fileURLWithPath: a[1]), output = URL(fileURLWithPath: a[2]), bytes = try Data(contentsOf: input)
        precondition(!FileManager.default.fileExists(atPath: output.path) && digest(bytes) == a[3])
        let inputRows = try JSONDecoder().decode(Inputs.self, from: bytes)
        precondition(inputRows.schema == "vipi-chinese-reading-probe-1" && inputRows.cases.count <= 200)
        precondition(Set(inputRows.cases.map(\.id)).count == inputRows.cases.count)
        let watchdog = DispatchSource.makeTimerSource(queue: .global()); watchdog.schedule(deadline: .now() + 90)
        watchdog.setEventHandler { exit(124) }; watchdog.resume(); defer { watchdog.cancel() }
        var rows: [[String: Any]] = []; let start = Date()
        for item in inputRows.cases {
            func capture() throws -> [String: Any] {
                let time = ProcessInfo.processInfo.systemUptime
                let value = try ChineseReadingCandidate.resolve(item.text)
                return ["reading": value.reading as Any? ?? NSNull(), "complete": value.reading != nil,
                    "inspection": value.inspection, "marked": value.marked, "tokens": value.tokens,
                    "pieces": value.pieces, "issues": value.issues, "protected": value.protected,
                    "milliseconds": (ProcessInfo.processInfo.systemUptime - time) * 1000, "process_peak_rss_bytes": peakRSS()]
            }
            let first = try autoreleasepool { try capture() }, warm = try autoreleasepool { try capture() }
            rows.append(["id": item.id, "group": item.group, "text": item.text, "first": first, "warm": warm])
            let report: [String: Any] = ["schema": "vipi-chinese-reading-probe-output-1", "input_sha256": digest(bytes),
                "policy_version": ChineseReadingCandidate.policyVersion, "platform": "macOS VM, not physical iOS",
                "os": ProcessInfo.processInfo.operatingSystemVersionString, "complete": rows.count == inputRows.cases.count,
                "count": rows.count, "elapsed_seconds": Date().timeIntervalSince(start), "process_peak_rss_bytes": peakRSS(),
                "network_disabled": false, "model_downloads": false, "audio_generated": false,
                "first_warm_scope": "First observed call per exact text in one process then immediate repeat, not OS cold-cache performance",
                "cases": rows]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
        }
    }
}
