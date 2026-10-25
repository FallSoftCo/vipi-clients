import Foundation
import CryptoKit

/// Replays immutable captures through the native Swift literal check. It never
/// invokes a provider, rewrites its output, or assigns linguistic acceptance.
@main struct TranslationIntegrityProbe {
    static func main() throws {
        guard CommandLine.arguments.count == 3 else { fatalError("capture.json output.json") }
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        guard !FileManager.default.fileExists(atPath: output.path) else { fatalError("Preserve receipts") }
        let data = try Data(contentsOf: input)
        let capture = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let pairs = capture["results"] as! [[String: Any]]
        var rows: [[String: Any]] = []
        for pair in pairs {
            for sample in pair["samples"] as! [[String: Any]] {
                let source = sample["original"] as! String, target = sample["translation"] as! String
                rows.append(["pair": (pair["source"] as! String) + "-" + (pair["target"] as! String),
                             "case": sample["id"] as! String,
                             "preserved": TranslationIntegrity.preservesIdentifiers(original: source, translation: target),
                             "source_identifiers": TranslationIntegrity.identifiers(source),
                             "translation_identifiers": TranslationIntegrity.identifiers(target)])
            }
        }
        let failures = rows.filter { $0["preserved"] as? Bool == false }.count
        let summary: [String: Any] = ["evidence": "native_swift_identifier_check_on_captured_output_not_translation_execution",
            "capture_sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            "linguistic_acceptance": false, "pairs": pairs.count, "samples": rows.count,
            "withheld": failures, "results": rows]
        try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
        print("\(pairs.count) directions, \(rows.count) samples, \(failures) withheld. Meaning is not evaluated.")
    }
}
