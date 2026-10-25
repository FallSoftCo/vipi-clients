import Foundation
import Translation

/// Actual Mac provider output, explicitly separate from physical iOS evidence.
@main struct MacTranslationMatrix {
    struct Corpus: Decodable {
        struct Sample: Decodable { let id: String; let text: [String:String] }
        let version: String; let languages: [String]; let cases: [Sample]
    }
    static func main() async throws {
        guard CommandLine.arguments.count == 3 else { fatalError("Expected corpus and new output path") }
        let sourceURL = URL(fileURLWithPath:CommandLine.arguments[1]), output = URL(fileURLWithPath:CommandLine.arguments[2])
        guard !FileManager.default.fileExists(atPath:output.path) else { fatalError("Preserve existing evidence") }
        let corpusData = try Data(contentsOf:sourceURL), corpus = try JSONDecoder().decode(Corpus.self, from:corpusData)
        let attribution = (try JSONSerialization.jsonObject(with:corpusData) as? [String:Any])?["attribution"]
        let availability = LanguageAvailability(preferredStrategy:.lowLatency)
        var rows: [[String:Any]] = []
        for from in corpus.languages { for to in corpus.languages where from != to {
            let source = Locale.Language(identifier:from), target = Locale.Language(identifier:to)
            let state = await availability.status(from:source,to:target)
            var row: [String:Any] = ["source":from,"target":to,"availability":String(describing:state)]
            if state != .installed { row["status"] = "not_installed" }
            else {
                let session = TranslationSession(installedSource:source,target:target,preferredStrategy:.lowLatency)
                var samples: [[String:Any]] = []
                for sample in corpus.cases {
                    let original = sample.text[from]!, start = ContinuousClock.now
                    var result: [String:Any] = ["id":sample.id,"original":original,"reference":sample.text[to]!]
                    do {
                        let response = try await session.translate(original)
                        let duration = start.duration(to:.now).components
                        result["translation"] = response.targetText; result["status"] = "executed"
                        result["translation_ms"] = Double(duration.seconds)*1000 + Double(duration.attoseconds)/1e15
                    } catch { result["status"] = "failed"; result["error_type"] = String(describing:error) }
                    samples.append(result)
                }
                row["status"] = samples.allSatisfy { $0["status"] as? String == "executed" } ? "executed" : "failed"
                row["samples"] = samples
                session.cancel()
            }
            rows.append(row)
            var report: [String:Any] = ["schema":1,"platform":"macOS","provider":"Apple Translation lowLatency",
                "system":ProcessInfo.processInfo.operatingSystemVersionString,"corpus":corpus.version,
                "evidence":"actual_mac_translation_not_iOS_execution_network_not_disabled",
                "linguistic_acceptance":false,"results":rows]
            if let attribution { report["attribution"] = attribution }
            try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
            print("\(from)-\(to): \(row["status"]!)")
        } }
    }
}
