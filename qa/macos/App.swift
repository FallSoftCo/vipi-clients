import SwiftUI
import Translation
import AppKit
import AVFoundation

@main struct VipiImmersionLab: App {
    var body: some Scene {
        WindowGroup("Vipi Immersion Lab") { LabView() }
            .defaultSize(width: 1120, height: 850)
    }
}
@MainActor final class LabModel: ObservableObject {
    @Published var strategy = "lowLatency"
    @Published var source = "en"
    @Published var target = "es"
    @Published var text = "I want to buy a red car."
    @Published var languages = ["en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw"]
    @Published var running = false
    @Published var status = "Compare a sentence with translations of its individual words."
    @Published var results: [CaseResult] = []
    @Published var selected = 0
    @Published var report: LabReport?
    @Published var preparation: TranslationSession.Configuration?
    @Published var preparing = false
    @Published var availability = ""
    let runner = ComparisonRunner()
    private var task: Task<Void, Never>?
    let speaker = AVSpeechSynthesizer()
    var result: CaseResult? { results.indices.contains(selected) ? results[selected] : nil }
    func label(_ code: String) -> String { Locale.current.localizedString(forLanguageCode: code) ?? code }
    func refresh() async {
        let checker = strategy == "platformDefault" ? LanguageAvailability() : LanguageAvailability(preferredStrategy: .lowLatency)
        let supported = await checker.supportedLanguages
        languages = Array(Set(languages + supported.map(\.minimalIdentifier))).sorted { label($0) < label($1) }
        availability = String(describing: await checker.status(from: .init(identifier: source), to: .init(identifier: target)))
    }
    func compare() {
        do {
            let input = LabProtocol(name: "Interactive comparison", strategy: strategy, cases: [.init(id: UUID().uuidString, source: source, target: target, text: text)])
            run(try JSONEncoder().encode(input))
        } catch { status = error.localizedDescription }
    }
    func run(_ data: Data) {
        guard !running else { return }
        speaker.stopSpeaking(at: .immediate)
        running = true; results = []; report = nil; selected = 0
        task = Task {
            defer { running = false; task = nil }
            do {
                let output = try await runner.run(data) { done, total, label in
                    self.status = "\(done)/\(total) · \(label)"
                }
                report = output; results = output.results
                status = output.cancelled ? "Cancelled; partial results retained." : "Finished. \(results.count) sentence comparisons."
            } catch { status = error.localizedDescription }
        }
    }
    func cancel() { runner.cancel(); task?.cancel() }
    func prepare() {
        guard source != target else { return }
        preparing = true; status = "Preparing \(label(source)) → \(label(target))…"
        preparation = strategy == "platformDefault"
            ? .init(source: .init(identifier: source), target: .init(identifier: target))
            : .init(source: .init(identifier: source), target: .init(identifier: target), preferredStrategy: .lowLatency)
    }
    func openProtocol() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            do { run(try Data(contentsOf: url)) } catch { status = error.localizedDescription }
        }
    }
    func export() {
        guard let report else { return }
        let panel = NSSavePanel(); panel.allowedContentTypes = [.json]; panel.nameFieldStringValue = "vipi-comparison.json"
        if panel.runModal() == .OK, let url = panel.url {
            do { try ComparisonRunner.encoded(report).write(to: url, options: .atomic); status = "Saved \(url.lastPathComponent)" }
            catch { status = error.localizedDescription }
        }
    }
    func loadReport(_ url: URL) {
        do {
            let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
            let value = try decoder.decode(LabReport.self, from: Data(contentsOf: url))
            report = value; results = value.results; selected = 0; strategy = value.requestedStrategy ?? "lowLatency"
            if let first = value.results.first { source = first.input.source; target = first.input.target; text = first.input.text }
            status = "Loaded \(results.count) comparisons · \(value.system)"
        } catch { status = error.localizedDescription }
    }
    func speak(_ text: String, language: String) {
        speaker.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: language)
        speaker.speak(utterance)
    }
}
struct LabView: View {
    @StateObject private var model = LabModel()
    @State private var density = 0.5
    @State private var onlyPresent = false
    @State private var automatic = false
    @State private var targetPhase = true
    private let timer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Vipi Immersion Lab").font(.largeTitle.bold())
                    Text("Words ↔ whole sentences").font(.title3).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Open corpus…", action: model.openProtocol).disabled(model.running || model.preparing)
                Button("Export results…", action: model.export).disabled(model.report == nil || model.running)
            }
            HStack {
                Picker("From", selection: $model.source) { ForEach(model.languages, id: \.self) { Text(model.label($0)).tag($0) } }
                Button { swap(&model.source, &model.target) } label: { Image(systemName: "arrow.left.arrow.right") }.help("Swap languages")
                Picker("To", selection: $model.target) { ForEach(model.languages, id: \.self) { Text(model.label($0)).tag($0) } }
                Button("Prepare languages", action: model.prepare).disabled(model.source == model.target)
                Text(model.availability).font(.caption).foregroundStyle(.secondary)
            }.disabled(model.running || model.preparing)
            HStack {
                Picker("Translation strategy", selection: $model.strategy) {
                    Text("Low latency").tag("lowLatency")
                    Text("iOS API default").tag("platformDefault")
                }.pickerStyle(.segmented).frame(maxWidth: 350).disabled(model.running || model.preparing)
                Text("Results record the resolved strategy.").font(.caption).foregroundStyle(.secondary)
            }
            TextEditor(text: $model.text).font(.title3).frame(height: 65).padding(8)
                .background(.background, in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                .disabled(model.running)
                .accessibilityLabel("Sentence to compare")
            HStack {
                Button("Compare", action: model.compare).buttonStyle(.borderedProminent).keyboardShortcut(.return, modifiers: .command)
                    .disabled(model.running || model.preparing || model.source == model.target || model.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if model.running { ProgressView().controlSize(.small); Button("Stop", action: model.cancel) }
                Text(model.status).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
            }
            Divider()
            if model.results.count > 1 {
                Picker("Result", selection: $model.selected) {
                    ForEach(Array(model.results.enumerated()), id: \.offset) { index, row in
                        Text("\(row.input.source) → \(row.input.target) · \(row.input.text)").tag(index)
                    }
                }
            }
            if let result = model.result { comparison(result) }
            else {
                Spacer()
                Text("Translate the whole sentence and each word separately.\nThen move the slider to inspect progressively more substitutions.")
                    .font(.title3).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                Spacer()
            }
            Text("Apple Translation · \(model.report?.strategy ?? model.strategy) · installed local models · Mac results")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(24).frame(minWidth: 850, minHeight: 720)
        .task {
            let arguments = CommandLine.arguments
            if let index = arguments.firstIndex(of: "--report"), arguments.count > index + 1 {
                model.loadReport(URL(fileURLWithPath: arguments[index + 1]))
            }
            await model.refresh()
        }
        .onChange(of: model.strategy) { _, _ in Task { await model.refresh() } }
        .onChange(of: model.source) { _, _ in Task { await model.refresh() } }
        .onChange(of: model.target) { _, _ in Task { await model.refresh() } }
        .onReceive(timer) { _ in if automatic { targetPhase.toggle() } }
        .translationTask(model.preparation) { session in
            guard model.preparing else { return }
            do { try await session.prepareTranslation(); model.status = "Languages ready." }
            catch { model.status = error.localizedDescription }
            model.preparing = false; model.preparation = nil; await model.refresh()
        }
    }
    private func comparison(_ result: CaseResult) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error = result.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                block("Original", result.input.text, language: result.input.source)
                block("Full sentence translation", result.fullTranslation ?? "Unavailable", language: result.input.target)
                block("Every word translated independently · original order", result.renderedAll, language: nil)
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Progressive preview").font(.headline)
                        Spacer()
                        Toggle("Automatic flip", isOn: $automatic).toggleStyle(.switch)
                    }
                    HStack {
                        Slider(value: $density, in: 0...1).accessibilityLabel("Proportion of eligible words to flip")
                        Text("\(Int(density * 100))%").monospacedDigit().frame(width: 45)
                    }
                    Toggle("Only words whose isolated translation also appears in the full translation", isOn: $onlyPresent)
                    let eligible = result.words.filter { $0.isolated != nil && (!onlyPresent || !$0.occurrencesInSentence.isEmpty) }
                    let count = Int((Double(eligible.count) * density).rounded(.down))
                    let indices = Set(eligible.prefix(count).map(\.id))
                    Text(result.preview(indices: automatic && !targetPhase ? [] : indices))
                        .font(.title2).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14).background(.tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                    Text("\(count) of \(result.words.count) source words selected. Left-to-right order is a diagnostic, not a learning policy.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Word comparison").font(.headline)
                Grid(alignment: .leading, horizontalSpacing: 25, verticalSpacing: 10) {
                    GridRow { Text("Source word").bold(); Text("Isolated translation").bold(); Text("In full translation?").bold() }
                    Divider()
                    ForEach(result.words) { word in
                        GridRow {
                            Text(word.source)
                            VStack(alignment: .leading) {
                                Text(word.isolated ?? word.error ?? "Unavailable")
                                if let isolated = word.isolated, let latin = isolated.applyingTransform(.toLatin, reverse: false), latin != isolated {
                                    Text(latin).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Text(word.occurrencesInSentence.isEmpty ? "No exact token match" : "\(word.occurrencesInSentence.count) occurrence(s)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }.textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                Text("Presence is not proof of correct meaning. The full translation can also be wrong. Neither preview repairs grammar, word order, or word boundaries.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(.trailing, 8)
        }
    }
    private func block(_ label: String, _ text: String, language: String?) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(label).font(.headline)
                if let language { Button { model.speak(text, language: language) } label: { Image(systemName: "speaker.wave.2") }.buttonStyle(.plain).help("Listen") }
            }
            Text(text).font(.title3).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            if let language, ["ja", "zh", "ko", "ar", "ru", "hi", "th", "uk", "el", "he"].contains(language),
               let latin = text.applyingTransform(.toLatin, reverse: false), latin != text {
                Text(latin).foregroundStyle(.secondary).textSelection(.enabled)
            }
        }
    }
}
