import SwiftUI
import Translation

/// Developer-only Mac evidence. Never substitutes for iPad model preparation.
@main struct VipiTranslationPreparation: App {
    var body: some Scene {
        WindowGroup("Vipi language qualification") { PreparationView() }.defaultSize(width: 500, height: 300)
    }
}
private struct PreparationView: View {
    let targets = ["es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko"]
    @State private var configuration: TranslationSession.Configuration?
    @State private var index = 0
    @State private var running = false
    @State private var status = "Prepare Apple's local translation models for a separate Mac evaluation."
    @State private var rows: [[String: String]] = []
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Vipi language qualification").font(.title2)
            Text(status).textSelection(.enabled)
            Text("Mac evidence only · low-latency local models").font(.footnote)
            Button("Prepare ten languages") { running = true; rows = []; index = 0; next() }.disabled(running)
            if running { ProgressView() }
        }.padding(28).frame(minWidth: 450, minHeight: 240)
            .translationTask(configuration) { session in
                guard running, index < targets.count else { return }
                let current = index, target = targets[index]
                do {
                    try await session.prepareTranslation()
                    let availability = await LanguageAvailability(preferredStrategy:.lowLatency).status(from: .init(identifier:"en"), to: .init(identifier:target))
                    rows.append(["source":"en", "target":target, "status":"preparation_api_returned", "availability":String(describing:availability)])
                } catch {
                    rows.append(["source":"en", "target":target, "status":"failed", "error":String(describing:error)])
                }
                guard current == index else { return }
                index += 1; next()
            }
    }
    private func next() {
        if index >= targets.count { running = false; configuration = nil; status = "Finished preparation. Inspect the receipt for any failures." }
        else {
            status = "Preparing en → \(targets[index]) (\(index + 1)/9)"
            configuration = .init(source: .init(identifier:"en"), target: .init(identifier:targets[index]), preferredStrategy: .lowLatency)
        }
        let receipt: [String:Any] = ["platform":"macOS", "strategy":"lowLatency", "iPad_evidence":false,
            "status":status, "running":running, "results":rows]
        let output = URL(fileURLWithPath: "/Users/Apple/Development/vipi/artifacts/apple-mac-preparation-001.json")
        do { try JSONSerialization.data(withJSONObject:receipt, options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic) }
        catch { status = "Receipt write failed: \(error.localizedDescription)"; running = false; configuration = nil }
    }
}
