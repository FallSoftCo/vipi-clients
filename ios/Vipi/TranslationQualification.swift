#if DEBUG
import SwiftUI
@preconcurrency import Translation
import Network

/// Dedicated authored QA corpus. Never feeds real conversations to a network
/// translator. A simulator rejection is retained, not replaced with sample text.
struct TranslationQualification: View {
    struct Corpus: Decodable {
        struct Sample: Decodable { let id: String; let text: [String: String] }
        let languages: [String]; let cases: [Sample]
    }
    @State private var configuration: TranslationSession.Configuration?
    @State private var index = 0
    @State private var preparing = false
    @State private var running = false
    @State private var status = "Prepare the local translation models, then run the authored matrix."
    @State private var rows: [[String: Any]] = []
    @State private var networkAvailable: Bool?
    @State private var monitor = NWPathMonitor()
    private var corpus: Corpus? {
        guard let url = Bundle.main.url(forResource: "corpus", withExtension: "json"), let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Corpus.self, from: data)
    }
    private var pairs: [(String, String)] {
        let languages = corpus?.languages ?? []
        if preparing { return languages.filter { $0 != "en" }.map { ("en", $0) } }
        return languages.flatMap { from in languages.filter { $0 != from }.map { (from, $0) } }
    }
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 24) {
                Text("Local translation qualification").font(.title2)
                Text(status).accessibilityIdentifier("translationStatus")
                Text("Network path: \(networkAvailable.map { $0 ? "available" : "unavailable" } ?? "unknown")").font(.footnote)
                Button("Prepare language models") { begin(preparation: true) }.disabled(running)
                Button("Run 90 directions") { begin(preparation: false) }.disabled(running)
                if running { Button("Stop qualification") { running = false; configuration = nil; status = "Stopped; partial results retained." } }
                Spacer()
            }.padding(28)
                .translationTask(configuration) { session in await execute(session) }
                .task {
                    monitor.pathUpdateHandler = { path in Task { @MainActor in networkAvailable = path.status == .satisfied } }
                    monitor.start(queue: DispatchQueue(label: "vipi-qa-path"))
                }
                .onDisappear { monitor.cancel(); running = false; configuration = nil }
        }
    }
    private func begin(preparation: Bool) {
        preparing = preparation; rows = []; index = 0; running = true; next()
    }
    private func next() {
        guard running, index < pairs.count else { running = false; configuration = nil; status = "Finished \(rows.count) directions. Read the receipt for failures."; return }
        let (source, target) = pairs[index]
        status = "\(preparing ? "Preparing" : "Translating") \(source) → \(target) (\(index + 1)/\(pairs.count))"
        configuration = .init(source: .init(identifier: source), target: .init(identifier: target))
    }
    @MainActor private func execute(_ session: TranslationSession) async {
        guard running, index < pairs.count, let corpus else { return }
        let current = index
        let (source, target) = pairs[current]
        var row: [String: Any] = ["source": source, "target": target, "networkAvailable": networkAvailable.map { $0 as Any } ?? NSNull()]
        do {
            if preparing { try await session.prepareTranslation(); row["status"] = "prepared" }
            else {
                let availability = await LanguageAvailability().status(from: .init(identifier: source), to: .init(identifier: target))
                guard availability == .installed else { throw QualificationError.notInstalled }
                var samples: [[String: Any]] = []
                for sample in corpus.cases {
                    guard let text = sample.text[source] else { continue }
                    let start = ContinuousClock.now
                    let response = try await session.translate(text)
                    let duration = start.duration(to: .now).components
                    samples.append(["id": sample.id, "original": text, "translation": response.targetText,
                        "latency_ms": Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15])
                }
                row["status"] = "executed"; row["samples"] = samples
            }
        } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
        guard running, current == index else { return }
        rows.append(row)
        let report: [String: Any] = ["evidence": "actual_apple_translation_execution_not_linguistic_or_immersion_acceptance", "device": UIDevice.current.model,
            "systemVersion": UIDevice.current.systemVersion, "preparation": preparing, "results": rows]
        do {
            let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let file = directory.appendingPathComponent(preparing ? "apple-translation-preparation.json" : "apple-translation-matrix.json")
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: file, options: .atomic)
        } catch { status = "Receipt failed: \(error.localizedDescription)"; running = false; configuration = nil; return }
        index += 1; next()
    }
    private enum QualificationError: Error { case notInstalled }
}
#endif
