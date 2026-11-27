#if DEBUG
import SwiftUI
@preconcurrency import Translation
import Network

/// Dedicated authored QA corpus. Never feeds real conversations to a network
/// translator. A simulator rejection is retained, not replaced with sample text.
struct TranslationQualification: View {
    struct Corpus: Decodable {
        struct Sample: Decodable {
            let id: String
            let text: [String: String]
        }
        let languages: [String]
        let cases: [Sample]
    }
    struct Request: Identifiable {
        let id = UUID()
        let run: UUID
        let index: Int
        let source: String
        let target: String
        let preparation: Bool
    }
    @State private var request: Request?
    @State private var runID = UUID()
    @State private var startedAt = Date()
    @State private var index = 0
    @State private var preparing = false
    @State private var running = false
    @State private var status = "Prepare the local translation models, then run the authored matrix."
    @State private var rows: [[String: Any]] = []
    @State private var networkAvailable: Bool?
    @State private var monitor = NWPathMonitor()
    @State private var didAutoStart = false
    private var corpus: Corpus? {
        guard let url = Bundle.main.url(forResource: "corpus", withExtension: "json"),
            let data = try? Data(contentsOf: url)
        else { return nil }
        return try? JSONDecoder().decode(Corpus.self, from: data)
    }
    private var pairs: [(String, String)] {
        let languages = corpus?.languages ?? []
        if preparing {
            let args = ProcessInfo.processInfo.arguments
            if let offset = args.firstIndex(of: "-vipi-translation-prepare-target"), args.indices.contains(offset + 1) {
                let target = args[offset + 1]
                return languages.contains(target) && target != "en" ? [("en", target)] : []
            }
            return languages.filter { $0 != "en" }.map { ("en", $0) }
        }
        return languages.flatMap { from in languages.filter { $0 != from }.map { (from, $0) } }
    }
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 24) {
                Text("Local translation qualification").font(.title2)
                Text(status).accessibilityIdentifier("translationStatus")
                Text("Network path: \(networkAvailable.map { $0 ? "available" : "unavailable" } ?? "unknown")").font(
                    .footnote
                )
                .accessibilityIdentifier("translationNetwork")
                Button {
                    begin(preparation: true)
                } label: {
                    Text("Prepare language models").frame(minHeight: 44)
                }
                .buttonStyle(.borderedProminent).disabled(running || networkAvailable == nil)
                .accessibilityIdentifier("translation-prepare")
                Button {
                    begin(preparation: false)
                } label: {
                    Text("Run 90 directions").frame(minHeight: 44)
                }
                .buttonStyle(.borderedProminent).disabled(running || networkAvailable == nil)
                .accessibilityIdentifier("translation-run")
                if running {
                    Button("Stop qualification") {
                        running = false
                        request = nil
                        status = "Stopped; partial results retained."
                        saveReport(finished: false)
                    }
                }
                if let request {
                    TranslationPairTask(request: request, execute: execute).id(request.id)
                }
                Spacer()
            }.padding(28)
                .task {
                    monitor.pathUpdateHandler = { path in
                        Task { @MainActor in networkAvailable = path.status == .satisfied }
                    }
                    monitor.start(queue: DispatchQueue(label: "vipi-qa-path"))
                    // Physical qualification can run directly, without XCTest
                    // UI automation. iPadOS still owns download consent prompts.
                }
                .onChange(of: networkAvailable) { _, value in
                    guard value != nil, !didAutoStart else { return }
                    didAutoStart = true
                    let args = ProcessInfo.processInfo.arguments
                    if args.contains("-vipi-translation-prepare") {
                        begin(preparation: true)
                    } else if args.contains("-vipi-translation-run") {
                        begin(preparation: false)
                    }
                }
                .onDisappear {
                    monitor.cancel()
                    running = false
                    request = nil
                }
        }
    }
    private func begin(preparation: Bool) {
        runID = UUID()
        startedAt = Date()
        preparing = preparation
        rows = []
        index = 0
        running = true
        saveReport(finished: false)
        next()
    }
    private func next() {
        guard running, index < pairs.count else {
            running = false
            request = nil
            let failures = rows.filter { $0["status"] as? String == "failed" }.count
            status = "Finished \(rows.count) directions. \(failures) failed."
            saveReport(finished: true)
            return
        }
        let (source, target) = pairs[index]
        status = "\(preparing ? "Preparing" : "Translating") \(source) → \(target) (\(index + 1)/\(pairs.count))"
        request = Request(run: runID, index: index, source: source, target: target, preparation: preparing)
        saveReport(finished: false)
    }
    @MainActor private func execute(_ session: TranslationSession, request active: Request) async {
        guard running, active.run == runID, active.id == request?.id, let corpus else { return }
        let source = active.source, target = active.target
        let sessionSource = session.sourceLanguage?.languageCode?.identifier
        let sessionTarget = session.targetLanguage?.languageCode?.identifier
        var row: [String: Any] = [
            "source": source, "target": target,
            "sessionSource": sessionSource ?? "unknown", "sessionTarget": sessionTarget ?? "unknown",
            "networkAvailable": networkAvailable.map { $0 as Any } ?? NSNull()
        ]
        do {
            guard sessionSource == source, sessionTarget == target else { throw QualificationError.sessionMismatch }
            if active.preparation {
                try await session.prepareTranslation()
                let availability = await LanguageAvailability().status(
                    from: .init(identifier: source), to: .init(identifier: target))
                guard availability == .installed else { throw QualificationError.notInstalled }
                row["status"] = "prepared"
            } else {
                let availability = await LanguageAvailability().status(
                    from: .init(identifier: source), to: .init(identifier: target))
                guard availability == .installed else { throw QualificationError.notInstalled }
                var samples: [[String: Any]] = []
                for sample in corpus.cases {
                    try Task.checkCancellation()
                    guard running, active.run == runID, active.id == request?.id else { return }
                    guard let text = sample.text[source] else { continue }
                    let networkBefore = networkAvailable
                    if ProcessInfo.processInfo.arguments.contains("-vipi-translation-offline") && networkBefore != false
                    {
                        throw QualificationError.networkAvailable
                    }
                    status = "Translating \(source) → \(target) (\(active.index + 1)/\(pairs.count)), \(sample.id)"
                    let start = ContinuousClock.now
                    let response = try await session.translate(text)
                    guard response.sourceLanguage.languageCode?.identifier == source,
                        response.targetLanguage.languageCode?.identifier == target,
                        response.sourceText == text
                    else { throw QualificationError.responseMismatch }
                    if ProcessInfo.processInfo.arguments.contains("-vipi-translation-offline")
                        && networkAvailable != false
                    {
                        throw QualificationError.networkAvailable
                    }
                    let duration = start.duration(to: .now).components
                    samples.append([
                        "id": sample.id, "original": text, "translation": response.targetText,
                        "networkBefore": networkBefore.map { $0 as Any } ?? NSNull(),
                        "networkAfter": networkAvailable.map { $0 as Any } ?? NSNull(),
                        "latency_ms": Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15
                    ])
                }
                row["status"] = "executed"
                row["samples"] = samples
            }
        } catch is CancellationError { return } catch {
            row["status"] = "failed"
            row["error"] = String(describing: error)
        }
        guard running, active.run == runID, active.id == request?.id else { return }
        rows.append(row)
        index += 1
        next()
    }
    private func saveReport(finished: Bool) {
        let report: [String: Any] = [
            "evidence": "actual_apple_translation_execution_not_linguistic_or_immersion_acceptance",
            "device": UIDevice.current.model,
            "systemVersion": UIDevice.current.systemVersion, "preparation": preparing, "results": rows,
            "run_id": runID.uuidString, "started_at": ISO8601DateFormatter().string(from: startedAt),
            "updated_at": ISO8601DateFormatter().string(from: Date()), "finished": finished, "status": status,
            "offline_required": ProcessInfo.processInfo.arguments.contains("-vipi-translation-offline")
        ]
        do {
            let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let file = directory.appendingPathComponent(
                preparing ? "apple-translation-preparation.json" : "apple-translation-matrix.json")
            let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: file, options: .atomic)
            if preparing, pairs.count == 1 {
                try data.write(
                    to: directory.appendingPathComponent("apple-translation-preparation-\(pairs[0].1).json"),
                    options: .atomic)
            }
        } catch {
            status = "Receipt failed: \(error.localizedDescription)"
            running = false
            request = nil
        }
    }
    private enum QualificationError: Error { case notInstalled, sessionMismatch, responseMismatch, networkAvailable }
}

/// Each task captures an immutable pair. A late callback cannot be relabelled
/// with the parent's next index or report a different pair as prepared.
private struct TranslationPairTask: View {
    let request: TranslationQualification.Request
    let execute: @MainActor (TranslationSession, TranslationQualification.Request) async -> Void
    @State private var submitted = false
    var body: some View {
        Text("Local session: \(request.source) → \(request.target)").font(.footnote)
            .translationTask(source: .init(identifier: request.source), target: .init(identifier: request.target)) {
                session in
                guard !submitted else { return }
                submitted = true
                await execute(session, request)
            }
    }
}
#endif
