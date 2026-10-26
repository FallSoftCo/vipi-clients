import SwiftUI
@preconcurrency import Translation

struct TranslationPair: Equatable, Sendable {
    let source: String
    let target: String
    var usesMLKit: Bool { source == "sw" || target == "sw" }
    var valid: Bool { source != target && VipiLanguage.initial.contains { $0.id == source } && VipiLanguage.initial.contains { $0.id == target } }
}

enum LocalLanguageAvailability: Equatable { case checking, downloadable, installed, unsupported }

@MainActor @Observable final class LanguagePreparation {
    struct Request: Identifiable, Equatable { let id = UUID(); let pair: TranslationPair }
    private(set) var pair: TranslationPair?
    private(set) var availability = LocalLanguageAvailability.checking
    private(set) var request: Request?
    private(set) var busy = false
    private(set) var message: String?
    private var revision = UUID()
    private let status: @MainActor (TranslationPair) async -> LocalLanguageAvailability

    init(status: @escaping @MainActor (TranslationPair) async -> LocalLanguageAvailability = LanguagePreparation.nativeStatus) { self.status = status }
    static func nativeStatus(_ pair: TranslationPair) async -> LocalLanguageAvailability {
        guard pair.valid else { return .unsupported }
        if pair.usesMLKit {
            #if targetEnvironment(simulator)
            return .unsupported
            #else
            return SwahiliTranslation.installed(pair) ? .installed : .downloadable
            #endif
        }
        switch await LanguageAvailability().status(from: .init(identifier: pair.source), to: .init(identifier: pair.target)) {
        case .installed: return .installed
        case .supported: return .downloadable
        case .unsupported: return .unsupported
        @unknown default: return .unsupported
        }
    }
    func refresh(_ pair: TranslationPair) async {
        guard !busy else { return }
        invalidate(); self.pair = pair; availability = .checking
        let active = revision
        let observed = pair.valid ? await status(pair) : .unsupported
        guard active == revision, !Task.isCancelled else { return }
        availability = observed
    }
    func prepare() {
        guard !busy, availability == .downloadable, let pair, pair.valid else { return }
        message = nil; busy = true; request = Request(pair: pair)
    }
    func finish(_ active: Request, availability observed: LocalLanguageAvailability, message: String? = nil) {
        guard request?.id == active.id, pair == active.pair else { return }
        busy = false; availability = observed; self.message = message
        // Keep the presenter alive while Apple's download sheet dismisses.
        // A finished request cannot run a second time.
    }
    func invalidate() { revision = UUID(); request = nil; busy = false; message = nil }
    func removeDownloads() async {
        guard !busy, let pair, pair.usesMLKit else { return }
        invalidate(); busy = true
        do { try await SwahiliTranslation.removeDownloads(pair) }
        catch { message = "These downloads couldn’t be removed. Please try again." }
        availability = await status(pair); busy = false
    }
}

struct LanguageDownloadView: View {
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var preparation = LanguagePreparation()
    private var pair: TranslationPair { .init(source: state.knownLanguage, target: state.targetLanguage) }

    var body: some View {
        @Bindable var state = state
        Form {
            Section {
                Picker("I already speak", selection: $state.knownLanguage) {
                    ForEach(VipiLanguage.initial) { Text($0.name).tag($0.id) }
                }.pickerStyle(.menu).disabled(preparation.busy).accessibilityIdentifier("language-source-picker")
                Picker("I’m picking up", selection: $state.targetLanguage) {
                    ForEach(VipiLanguage.initial.filter { $0.id != state.knownLanguage }) {
                        Text("\($0.name) · \($0.localName)").tag($0.id)
                    }
                }.pickerStyle(.menu).disabled(preparation.busy).accessibilityIdentifier("language-target-picker")
            }.listRowBackground(VipiDesign.surface)
            Section {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: preparation.availability == .installed ? "checkmark.circle" : "arrow.down.circle")
                        .foregroundStyle(VipiDesign.highlight).accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Offline translation").font(.headline)
                        Text(statusText).foregroundStyle(VipiDesign.secondary)
                            .accessibilityIdentifier("language-download-status")
                    }
                    if preparation.busy || preparation.availability == .checking { Spacer(); ProgressView().accessibilityLabel("Checking languages") }
                }.padding(.vertical, 5)
                if preparation.availability == .downloadable && !preparation.busy {
                    Button("Download languages") { preparation.prepare() }.accessibilityIdentifier("language-download-start")
                }
                if let message = preparation.message {
                    Text(message).font(.footnote).foregroundStyle(VipiDesign.secondary)
                        .accessibilityIdentifier("language-download-message")
                }
                if !preparation.busy && preparation.availability != .checking {
                    Button(preparation.availability == .unsupported ? "Check again" : "Check downloads") { Task { await preparation.refresh(pair) } }
                        .accessibilityIdentifier("language-download-check")
                }
            } footer: {
                Text("Downloads are managed by your device. Once installed, translation happens here, even offline. Your messages aren’t sent to a translation service.")
            }.listRowBackground(VipiDesign.surface)
            Section {
                if pair.usesMLKit {
                    if preparation.availability == .installed {
                        Button("Remove these translation downloads", role: .destructive) {
                            Task { await preparation.removeDownloads() }
                        }.disabled(preparation.busy)
                    }
                    Text("These languages are stored in Vipi. Removing them means you’ll need to download them again before translating offline.")
                        .font(.footnote).foregroundStyle(VipiDesign.secondary)
                } else {
                    Text("To remove translation languages, open Settings → Apps → Translate → Downloaded Languages. The Translate app needs to be installed.")
                        .font(.footnote).foregroundStyle(VipiDesign.secondary)
                }
            }.listRowBackground(VipiDesign.surface)
            if let request = preparation.request {
                LanguagePreparationTask(request: request, preparation: preparation).id(request.id)
            }
        }
        .scrollContentBackground(.hidden).background(VipiDesign.canvas)
        .navigationTitle("Your languages").navigationBarTitleDisplayMode(.inline)
        .onChange(of: state.knownLanguage) { _, value in
            if state.targetLanguage == value { state.targetLanguage = value == "es" ? "en" : "es" }
        }
        .task(id: pair) { await preparation.refresh(pair) }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active && !preparation.busy { Task { await preparation.refresh(pair) } }
        }
        .onDisappear { preparation.invalidate() }
    }
    private var statusText: String {
        if preparation.busy { return "Preparing your languages…" }
        switch preparation.availability {
        case .checking: return "Checking this device…"
        case .downloadable: return "Download \(VipiLanguage.named(pair.source).name) and \(VipiLanguage.named(pair.target).name) to translate offline."
        case .installed: return "\(VipiLanguage.named(pair.source).name) and \(VipiLanguage.named(pair.target).name) are ready for offline translation."
        case .unsupported: return "This device can’t translate this language pair. You can choose another language."
        }
    }
}

private struct LanguagePreparationTask: View {
    let request: LanguagePreparation.Request
    let preparation: LanguagePreparation
    @State private var submitted = false
    var body: some View {
        if request.pair.usesMLKit {
            Color.clear.frame(height: 0).accessibilityHidden(true).task {
                guard !submitted else { return }; submitted = true
                do {
                    let translator = try SwahiliTranslation(pair: request.pair)
                    try await translator.prepare()
                    preparation.finish(request, availability: .installed)
                } catch {
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request, availability: observed,
                        message: observed == .installed ? nil : "The download isn’t ready. Check your connection, then try again.")
                }
            }
        } else {
        Color.clear.frame(height: 0).accessibilityHidden(true)
            .translationTask(source: .init(identifier: request.pair.source), target: .init(identifier: request.pair.target)) { session in
                guard !submitted else { return }; submitted = true
                guard session.sourceLanguage?.languageCode?.identifier == request.pair.source,
                      session.targetLanguage?.languageCode?.identifier == request.pair.target else {
                    preparation.finish(request, availability: .downloadable, message: "The language download couldn’t start. Please try again."); return
                }
                do {
                    try await session.prepareTranslation()
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request, availability: observed,
                        message: observed == .downloadable ? "The download hasn’t finished yet. You can check again shortly." : nil)
                } catch is CancellationError {
                    preparation.finish(request, availability: .downloadable,
                        message: "The download isn’t ready. Check downloads to see its current status.")
                }
                catch {
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request, availability: observed,
                        message: observed == .installed ? nil : "The download isn’t ready. Check your connection, then try again.")
                }
            }
        }
    }
}
