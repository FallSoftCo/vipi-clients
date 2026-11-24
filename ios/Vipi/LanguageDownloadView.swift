import SwiftUI
@preconcurrency import Translation

struct TranslationPair: Hashable, Sendable {
    let source: String
    let target: String
    var valid: Bool { source != target && LocalLanguageCatalog.codes.contains(source) && LocalLanguageCatalog.codes.contains(target) }
    var appleSource: Locale.Language { .init(identifier: LocalLanguageCatalog.appleIdentifier(source)) }
    var appleTarget: Locale.Language { .init(identifier: LocalLanguageCatalog.appleIdentifier(target)) }
}

enum LocalLanguageAvailability: Equatable { case checking, downloadable, installed, unsupported }
enum LocalTranslationProvider: Equatable { case apple, mlKit, unsupported }

/// A provider is chosen from actual pair support, never from a fixed shortlist.
/// Missing Apple models remain on Apple; only unsupported pairs use ML Kit.
@MainActor enum LocalTranslationCapability {
    struct Resolution {
        let provider: LocalTranslationProvider
        let availability: LocalLanguageAvailability
    }
    static func resolve(_ pair: TranslationPair) async -> Resolution {
        guard pair.valid else { return .init(provider: .unsupported, availability: .unsupported) }
        let apple = await LanguageAvailability().status(from: pair.appleSource, to: pair.appleTarget)
        switch apple {
        case .installed: return .init(provider: .apple, availability: .installed)
        case .supported: return .init(provider: .apple, availability: .downloadable)
        case .unsupported: break
        @unknown default: break
        }
        guard SwahiliTranslation.supports(pair) else { return .init(provider: .unsupported, availability: .unsupported) }
        return .init(provider: .mlKit, availability: SwahiliTranslation.installed(pair) ? .installed : .downloadable)
    }
}

@MainActor @Observable final class LanguagePreparation {
    struct Request: Identifiable, Equatable { let id = UUID(); let pair: TranslationPair; let provider: LocalTranslationProvider }
    private(set) var pair: TranslationPair?
    private(set) var availability = LocalLanguageAvailability.checking
    private(set) var request: Request?
    private(set) var busy = false
    private(set) var prepared = false
    private(set) var provider = LocalTranslationProvider.unsupported
    private let nativePrepare: (@MainActor (TranslationPair) async throws -> Void)?
    private var preparationTask: Task<Void,Never>?
    var usesNativePresenter: Bool { nativePrepare == nil }
    private(set) var message: String?
    private var revision = UUID()
    private let status: @MainActor (TranslationPair) async -> LocalLanguageAvailability
    private let resolveProvider: @MainActor (TranslationPair) async -> LocalTranslationProvider

    private let remove: @MainActor (TranslationPair) async throws -> Void
    init(remove: @escaping @MainActor (TranslationPair) async throws -> Void = SwahiliTranslation.removeDownloads,
         status: @escaping @MainActor (TranslationPair) async -> LocalLanguageAvailability = LanguagePreparation.nativeStatus,
         resolveProvider: @escaping @MainActor (TranslationPair) async -> LocalTranslationProvider = { await LocalTranslationCapability.resolve($0).provider },
         nativePrepare: (@MainActor (TranslationPair) async throws -> Void)? = nil) {
        self.status = status; self.remove = remove; self.nativePrepare = nativePrepare; self.resolveProvider = resolveProvider
    }
    static func nativeStatus(_ pair: TranslationPair) async -> LocalLanguageAvailability {
        await LocalTranslationCapability.resolve(pair).availability
    }
    func refresh(_ pair: TranslationPair) async {
        guard !busy else { return }
        invalidate(); self.pair = pair; availability = .checking
        let active = revision
        let observed = pair.valid ? await status(pair) : .unsupported
        guard active == revision, !Task.isCancelled else { return }
        let resolved = pair.valid && nativePrepare == nil ? await resolveProvider(pair) : .unsupported
        guard active == revision, !Task.isCancelled else { return }
        provider = resolved
        availability = observed
    }
    func prepare() {
        guard !busy, !prepared, availability == .downloadable || availability == .installed, let pair, pair.valid else { return }
        message = nil; prepared = false; busy = true; let active = Request(pair:pair,provider:provider); request = active
        if let nativePrepare {
            preparationTask = Task { @MainActor [weak self] in
                do { try await nativePrepare(pair); try Task.checkCancellation(); self?.finish(active,availability:.installed,prepared:true) }
                catch { self?.finish(active,availability:.downloadable,message:String(localized:"The download isn’t ready. Check your connection, then try again.")) }
            }
        }
    }
    func finish(_ active: Request, availability observed: LocalLanguageAvailability, message: String? = nil, prepared:Bool = false) {
        guard request?.id == active.id, pair == active.pair else { return }
        busy = false; availability = observed; self.message = message; self.prepared = prepared
        // Keep the presenter alive while Apple's download sheet dismisses.
        // A finished request cannot run a second time.
    }
    func invalidate() { preparationTask?.cancel(); preparationTask = nil; revision = UUID(); request = nil; busy = false; prepared = false; message = nil }
    func removeDownloads() async {
        guard !busy, let pair, pair.valid, provider == .mlKit else { return }
        invalidate(); busy = true
        let active = revision
        var failure: String?
        do { try await remove(pair) }
        catch is CancellationError {
            if active == revision { busy = false }
            return
        }
        catch { failure = String(localized: "These downloads couldn’t be removed. Please try again.") }
        guard active == revision, !Task.isCancelled else { return }
        let observed = await status(pair)
        guard active == revision, !Task.isCancelled else { return }
        availability = observed; message = failure; busy = false
    }
}

struct LanguageDownloadView: View {
    var requestedPair: TranslationPair? = nil
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    @State private var preparation = LanguagePreparation()
    @State private var availableVoices: Set<String>?
    @State private var confirmRemoval = false
    private var pair: TranslationPair { requestedPair ?? .init(source:state.knownLanguage,target:state.targetLanguage) }

    var body: some View {
        Form {
            Section {
                if let requestedPair {
                    LabeledContent("Message language",value:VipiLanguage.named(requestedPair.source).localizedName)
                    LabeledContent("I’m learning",value:VipiLanguage.named(requestedPair.target).localizedName)
                } else {
                languagePicker("I already speak", language: state.knownLanguage) {
                    LanguageSelectionView(title: "I already speak",
                        selection: Binding(get: { state.knownLanguage }, set: { state.selectKnownLanguage($0) }),
                        choices: VipiLanguage.initial, localName: false)
                }.accessibilityIdentifier("language-source-picker")
                languagePicker("I want to learn", language: state.targetLanguage) {
                    PracticeLanguagePicker()
                }.accessibilityIdentifier("language-target-picker")
                }
            }
            Section {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: preparation.availability == .installed ? "checkmark.circle" : "arrow.down.circle")
                        .foregroundStyle(VipiDesign.highlight)
                        .accessibilityHidden(true)
                    Text(statusText)
                        .font(.body).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("language-download-status")
                    if preparation.busy || preparation.availability == .checking { Spacer(); ProgressView().accessibilityLabel(statusText) }
                }.padding(.vertical, 5)
                PracticeLanguageNotice(target: pair.target, availableVoices: availableVoices)
                if preparation.availability == .downloadable && !preparation.busy {
                    Button { preparation.prepare() } label: {
                        Text("Download languages").foregroundStyle(VipiDesign.highlight)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }.accessibilityIdentifier("language-download-start")
                }
                if let message = preparation.message {
                    Text(message).font(.body).foregroundStyle(VipiDesign.secondary)
                        .accessibilityIdentifier("language-download-message")
                }
                if !preparation.busy && preparation.availability != .checking {
                    Button { Task { await preparation.refresh(pair) } } label: {
                        Text(LocalizedStringKey(preparation.availability == .unsupported ? "Check again" : "Check downloads"))
                            .foregroundStyle(VipiDesign.highlight)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                        .accessibilityIdentifier("language-download-check")
                }
            }
            Section {
                if preparation.provider == .mlKit {
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
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            let voices = await LocalVoice.availableLanguageCodes()
            guard !Task.isCancelled else { return }
            availableVoices = voices
        }
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
    private func languagePicker(_ title: LocalizedStringKey, language: String,
                                @ViewBuilder destination: () -> some View) -> some View {
        NavigationLink(destination: destination) {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.callout).foregroundStyle(VipiDesign.secondary)
                Text(VipiLanguage.named(language).localizedName).foregroundStyle(VipiDesign.highlight)
            }.fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
                .accessibilityElement(children: .combine)
        }.disabled(preparation.busy)
    }
    private var statusText: String {
        if preparation.busy { return preparation.request == nil ? String(localized: "Removing downloads…") : String(localized: "Preparing translation downloads…") }
        switch preparation.availability {
        case .checking: return String(localized: "Checking this device…")
        case .downloadable: return String(localized: "Translation needs a language download.")
        case .installed: return String(localized: "Languages downloaded")
        case .unsupported: return String(localized:"Translation isn’t supported for this language pair on this device.")
        }
    }
}

/// Device inventory is read without loading a synthesizer, downloading a model,
/// or changing the person's selection. The tutorial exercises real synthesis.
struct PracticeLanguageNotice: View {
    let target: String
    let availableVoices: Set<String>?
    var body: some View {
        Group {
            if let availableVoices, !availableVoices.contains(target) {
                if target == "sw" {
                    Text("The built-in voice is unavailable. You can keep reading or choose another practice language.")
                } else {
                    Text("Add a \(VipiLanguage.named(target).localizedName) voice in Settings → Accessibility → Spoken Content → Voices, then retry.")
                }
            }
            if target == "ar" || (!LocalLanguageCatalog.commonPractice.contains(target) && !LocalLanguageCatalog.additionalLatinPractice.contains(target)) {
                Text("Reading guides can vary by message.")
            }
        }
        .font(.subheadline).foregroundStyle(VipiDesign.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
}

struct PracticeLanguagePicker: View {
    @Environment(AppState.self) private var state
    var body: some View {
        @Bindable var state = state
        LanguageSelectionView(title: "I want to learn", selection: $state.targetLanguage,
                              choices: VipiLanguage.initial.filter { $0.id != state.knownLanguage },
                              localName: true, practiceSource: state.knownLanguage)
    }
}

struct LanguageSelectionView: View {
    let title: LocalizedStringKey
    @Binding var selection: String
    let choices: [VipiLanguage]
    let localName: Bool
    var practiceSource: String? = nil
    @Environment(\.scenePhase) private var scenePhase
    @State private var deviceOptions: Set<String> = []
    @State private var checkedSource: String?
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    private var visibleChoices: [VipiLanguage] {
        choices.filter { language in
            if let practiceSource, !LocalLanguageCatalog.offersPractice(language.id, source: practiceSource, saved: selection, deviceOptions: checkedSource == practiceSource ? deviceOptions : []) { return false }
            return search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                [language.localizedName, language.localName, language.name, language.id].contains {
                    $0.localizedStandardContains(search.trimmingCharacters(in: .whitespacesAndNewlines))
                }
        }.sorted {
            if practiceSource != nil {
                let firstCommon = LocalLanguageCatalog.commonPractice.contains($0.id)
                let secondCommon = LocalLanguageCatalog.commonPractice.contains($1.id)
                if firstCommon != secondCommon { return firstCommon }
            }
            return $0.localizedName.localizedStandardCompare($1.localizedName) == .orderedAscending
        }
    }
    private func choiceRow(_ language: VipiLanguage) -> some View {
        Button {
            selection = language.id; dismiss()
        } label: {
            HStack(spacing: 16) {
                Text(localName ? "\(language.localizedName) · \(language.localName)" : language.localizedName)
                    .font(.body).foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                if selection == language.id {
                    Image(systemName: "checkmark").foregroundStyle(VipiDesign.highlight).accessibilityHidden(true)
                }
            }
            .frame(minHeight: 44).padding(.horizontal, 18).padding(.vertical, 6)
            .contentShape(Rectangle()).accessibilityElement(children: .combine)
        }.buttonStyle(.plain).accessibilityAddTraits(selection == language.id ? .isSelected : [])
            .accessibilityIdentifier("language-choice-" + language.id)
    }

    private var additionalHeading: some View {
        Text("More languages on this device")
            .font(.subheadline.weight(.semibold)).foregroundStyle(VipiDesign.secondary)
            .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .accessibilityAddTraits(.isHeader)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                let options = visibleChoices
                let firstAdditional = options.first { !LocalLanguageCatalog.commonPractice.contains($0.id) }
                ForEach(options) { language in
                    if practiceSource != nil && language.id == firstAdditional?.id {
                        additionalHeading
                    }
                    choiceRow(language)
                    if language.id != options.last?.id { Divider().padding(.leading, 18) }
                }
            }
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
            .padding(20).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
        .background(VipiDesign.canvas)
        .task(id: "\(practiceSource ?? ""):\(scenePhase == .active)") {
            checkedSource = nil
            guard let source = practiceSource, scenePhase == .active else { return }
            let voices = await LocalVoice.availableLanguageCodes()
            guard !Task.isCancelled else { return }
            var available = Set<String>()
            for target in LocalLanguageCatalog.additionalLatinPractice.intersection(voices) where target != source {
                let pair = TranslationPair(source: source, target: target)
                // The bundled provider supports all of its SDK pairs, including
                // downloadable models. Apple-only builds check actual OS support.
                if SwahiliTranslation.supports(pair) {
                    available.insert(target)
                } else if await LocalTranslationCapability.resolve(pair).availability != .unsupported {
                    available.insert(target)
                }
                if Task.isCancelled { return }
            }
            guard !Task.isCancelled else { return }
            deviceOptions = available
            checkedSource = source
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always))
        .overlay { if visibleChoices.isEmpty { ContentUnavailableView.search(text: search) } }
    }
}

struct LanguagePreparationTask: View {
    let request: LanguagePreparation.Request
    let preparation: LanguagePreparation
    @State private var submitted = false
    var body: some View {
        if !preparation.usesNativePresenter { Color.clear.frame(height:0).accessibilityHidden(true) }
        else if request.provider == .mlKit {
            Color.clear.frame(height: 0).accessibilityHidden(true).task {
                guard !submitted else { return }; submitted = true
                do {
                    let translator = try SwahiliTranslation(pair: request.pair)
                    try await translator.prepare()
                    preparation.finish(request, availability:.installed,prepared:true)
                } catch {
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request, availability: observed,
                        message:String(localized:"The download isn’t ready. Check your connection, then try again."))
                }
            }
        } else if request.provider == .apple {
        Color.clear.frame(height: 0).accessibilityHidden(true)
            .translationTask(source: request.pair.appleSource, target: request.pair.appleTarget) { session in
                guard !submitted else { return }; submitted = true
                guard (session.sourceLanguage?.languageCode?.identifier).map(LocalLanguageCatalog.canonicalCode) == request.pair.source,
                      (session.targetLanguage?.languageCode?.identifier).map(LocalLanguageCatalog.canonicalCode) == request.pair.target else {
                    preparation.finish(request, availability: .downloadable, message: String(localized: "The language download couldn’t start. Please try again.")); return
                }
                do {
                    try await session.prepareTranslation()
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request,availability:observed,
                        message:observed == .downloadable ? String(localized:"The download hasn’t finished yet. You can check again shortly.") : nil,prepared:observed == .installed)
                } catch is CancellationError {
                    preparation.finish(request, availability: .downloadable,
                        message: String(localized: "The download isn’t ready. Check downloads to see its current status."))
                }
                catch {
                    let observed = await LanguagePreparation.nativeStatus(request.pair)
                    preparation.finish(request, availability: observed,
                        message:String(localized:"The download isn’t ready. Check your connection, then try again."))
                }
            }
        } else {
            Color.clear.frame(height: 0).accessibilityHidden(true).task {
                guard !submitted else { return }; submitted = true
                preparation.finish(request, availability: .unsupported)
            }
        }
    }
}
