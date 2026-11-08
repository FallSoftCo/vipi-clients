import Foundation
@main struct Batch {
    @MainActor static func main() async {
        do {
            guard CommandLine.arguments.count == 3 else { throw LabFailure.invalid("Usage: vipi-translation-compare protocol.json new-report.json") }
            let output = URL(fileURLWithPath: CommandLine.arguments[2])
            guard !FileManager.default.fileExists(atPath: output.path) else { throw LabFailure.invalid("Output exists; use a new evidence path.") }
            let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
            let report = try await ComparisonRunner().run(data) { done, total, label in
                print("\(done)/\(total) \(label)")
            }
            try ComparisonRunner.encoded(report).write(to: output, options: .withoutOverwriting)
            print("Saved \(output.path)")
            if report.cancelled || report.results.contains(where: { $0.error != nil || $0.words.contains(where: { $0.error != nil }) }) { exit(2) }
        } catch {
            fputs("\(error)\n", stderr)
            exit(1)
        }
    }
}
