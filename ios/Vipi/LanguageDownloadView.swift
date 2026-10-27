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

    private let remove: @MainActor (TranslationPair) async throws -> Void
    init(remove: @escaping @MainActor (TranslationPair) async throws -> Void = SwahiliTranslation.removeDownloads,
         status: @escaping @MainActor (TranslationPair) async -> LocalLanguageAvailability = LanguagePreparation.nativeStatus) {
        self.status = status; self.remove = remove
    }
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
        guard !busy, let pair, pair.valid, pair.usesMLKit else { return }
        invalidate(); busy = true
        let active = revision
        var failure: String?
        do { try await remove(pair) }
        catch is CancellationError {
            if active == revision { busy = false }
            return
        }
        catch { failure = "These downloads couldn’t be removed. Please try again." }
        guard active == revision, !Task.isCancelled else { return }
        let observed = await status(pair)
        guard active == revision, !Task.isCancelled else { return }
        availability = observed; message = failure; busy = false
    }
}

struct LanguageDownloadView: View {
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var preparation = LanguagePreparation()
    @State private var confirmRemoval = false
    private var pair: TranslationPair { .init(source: state.knownLanguage, target: state.targetLanguage) }

    var body: some View {
        @Bindable var state = state
        Form {
            Section {
                languagePicker("I already speak", selection: Binding(get: { state.knownLanguage }, set: { state.selectKnownLanguage($0) }),
                             choices: VipiLanguage.initial, localName: false)
                    .accessibilityIdentifier("language-source-picker")
                languagePicker("I’m picking up", selection: $state.targetLanguage,
                             choices: VipiLanguage.initial.filter { $0.id != state.knownLanguage }, localName: true)
                    .accessibilityIdentifier("language-target-picker")
            }
            Section {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: preparation.availability == .installed ? "checkmark.circle" : "arrow.down.circle")
                        .foregroundStyle(VipiDesign.highlight)
                        .accessibilityLabel(preparation.availability == .installed ? "Languages downloaded" : "Language download")
                    (Text("Offline translation\n").font(.headline) +
                     Text(statusText).foregroundColor(VipiDesign.secondary))
                        .lineSpacing(6).fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel("Offline translation. \(statusText)")
                        .accessibilityIdentifier("language-download-status")
                    if preparation.busy || preparation.availability == .checking { Spacer(); ProgressView().accessibilityLabel(statusText) }
                }.padding(.vertical, 5)
                if preparation.availability == .downloadable && !preparation.busy {
                    Button { preparation.prepare() } label: {
                        Text("Download languages").foregroundStyle(VipiDesign.highlight)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }.accessibilityIdentifier("language-download-start")
                }
                if let message = preparation.message {
                    Text(message).font(.footnote).foregroundStyle(VipiDesign.secondary)
                        .accessibilityIdentifier("language-download-message")
                }
                if !preparation.busy && preparation.availability != .checking {
                    Button { Task { await preparation.refresh(pair) } } label: {
                        Text(preparation.availability == .unsupported ? "Check again" : "Check downloads")
                            .foregroundStyle(VipiDesign.highlight)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                        .accessibilityIdentifier("language-download-check")
                }
                Text("Your messages are translated on this device. They aren’t sent to a translation service.")
                    .font(.callout).foregroundStyle(VipiDesign.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("language-download-explanation")
            }
            Section {
                if pair.usesMLKit {
                    if preparation.availability == .installed {
                        Button(role: .destructive) { confirmRemoval = true } label: {
                            Text("Remove these translation downloads").foregroundStyle(VipiDesign.destructive)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        }.disabled(preparation.busy).accessibilityIdentifier("language-download-remove")
                    }
                    Text("Removing a language frees storage. You can download it again.")
                        .font(.callout).foregroundStyle(VipiDesign.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("language-removal-explanation")
                } else {
                    Text("To remove translation languages, open Settings → Apps → Translate → Downloaded Languages. The Translate app needs to be installed.")
                        .font(.callout).foregroundStyle(VipiDesign.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("language-removal-explanation")
                }
            }
            if let request = preparation.request {
                LanguagePreparationTask(request: request, preparation: preparation).id(request.id)
            }
        }
        .scrollContentBackground(.hidden)
        .background(VipiDesign.canvas)
        .frame(maxWidth: 760).frame(maxWidth: .infinity).background(VipiDesign.canvas)
        .navigationTitle("Your languages").navigationBarTitleDisplayMode(.inline)
        .task(id: pair) { await preparation.refresh(pair) }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active && !preparation.busy { Task { await preparation.refresh(pair) } }
        }
        .onDisappear { preparation.invalidate() }
        .alert("Remove downloads?", isPresented: $confirmRemoval) {
            Button("Remove", role: .destructive) { Task { await preparation.removeDownloads() } }
            Button("Keep downloads", role: .cancel) { }
        } message: {
            Text("You’ll need to download these languages again before translating offline. Your conversations stay on this device.")
        }
    }
    private func languagePicker(_ title: String, selection: Binding<String>, choices: [VipiLanguage], localName: Bool) -> some View {
        NavigationLink {
            LanguageSelectionView(title: title, selection: selection, choices: choices, localName: localName)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.callout).foregroundStyle(VipiDesign.secondary)
                Text(VipiLanguage.named(selection.wrappedValue).name).foregroundStyle(VipiDesign.highlight)
            }.fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
                .accessibilityElement(children: .combine)
        }.disabled(preparation.busy)
    }
    private var statusText: String {
        if preparation.busy { return preparation.request == nil ? "Removing downloads…" : "Preparing your languages…" }
        switch preparation.availability {
        case .checking: return "Checking this device…"
        case .downloadable: return "Download \(VipiLanguage.named(pair.source).name) and \(VipiLanguage.named(pair.target).name) to translate offline."
        case .installed: return "\(VipiLanguage.named(pair.source).name) and \(VipiLanguage.named(pair.target).name) are ready for offline translation."
        case .unsupported: return "This device can’t translate this language pair. You can choose another language."
        }
    }
}

private struct LanguageSelectionView: View {
    let title: String
    @Binding var selection: String
    let choices: [VipiLanguage]
    let localName: Bool
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        List(choices) { language in
            Button {
                selection = language.id; dismiss()
            } label: {
                HStack {
                    Text(localName ? "\(language.name) · \(language.localName)" : language.name)
                        .foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 12)
                    if selection == language.id { Image(systemName: "checkmark").foregroundStyle(VipiDesign.highlight).accessibilityHidden(true) }
                }.frame(minHeight: 44)
            }.accessibilityAddTraits(selection == language.id ? .isSelected : [])
        }
        .scrollContentBackground(.hidden).background(VipiDesign.canvas)
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
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
