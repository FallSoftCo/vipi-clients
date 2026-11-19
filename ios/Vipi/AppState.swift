import Foundation
import Observation
import SwiftUI

struct VipiLanguage: Identifiable, Hashable {
    let id: String
    let name: String
    let localName: String
    // UI locale is independent of the language selected for immersion.
    var localizedName: String {
        let locale = Bundle.main.preferredLocalizations.first.map { Locale(identifier: $0) } ?? .current
        return locale.localizedString(forLanguageCode: id) ?? name
    }
    /// Source UI copy only; the practice face is always produced on device.
    let exampleGreeting: String
    static let initial = LocalLanguageCatalog.languages
    static func named(_ code: String) -> Self { initial.first { $0.id == code } ?? initial[0] }
}

enum OnboardingStep: String { case welcome, language, account }
enum AppAppearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    var scheme: ColorScheme? { self == .system ? nil : (self == .dark ? .dark : .light) }
}

@MainActor @Observable final class AppState {
    var onboarding: OnboardingStep { didSet { defaults.set(onboarding.rawValue, forKey: "onboardingStep") } }
    var knownLanguage: String { didSet { defaults.set(knownLanguage, forKey: "knownLanguage") } }
    var targetLanguage: String { didSet { defaults.set(targetLanguage, forKey: "targetLanguage") } }
    var appearance: AppAppearance { didSet { defaults.set(appearance.rawValue, forKey: "appearance") } }
    let chatReading: ChatReadingState
    let translationServices: MessageTranslationServices
    var isAuthenticated = false
    var invitationUsername: String? {
        didSet { defaults.set(invitationUsername, forKey: "invitationUsername") }
    }
    private let defaults: UserDefaults

    @discardableResult func acceptInvitation(_ url: URL) -> Bool {
        guard let name = FriendInvitationLink.username(in: url) else { return false }
        invitationUsername = name
        return true
    }

    func selectKnownLanguage(_ value: String) {
        guard VipiLanguage.initial.contains(where: { $0.id == value }) else { return }
        // Adjust the target in the same action, before publishing the new
        // source. A delayed view onChange exposes an invalid equal pair.
        if value == targetLanguage { targetLanguage = value == "es" ? "en" : "es" }
        knownLanguage = value
    }

    init(defaults: UserDefaults = .standard, translationServices: MessageTranslationServices? = nil) {
        self.translationServices = translationServices ?? MessageTranslationServices()
        chatReading = ChatReadingState(defaults:defaults)
        self.defaults = defaults
        invitationUsername = defaults.string(forKey: "invitationUsername").flatMap {
            URL(string: "https://api.mambovipi.app/invite/" + $0).flatMap(FriendInvitationLink.username)
        }
        onboarding = OnboardingStep(rawValue: defaults.string(forKey: "onboardingStep") ?? "") ?? .welcome
        knownLanguage = defaults.string(forKey: "knownLanguage") ?? "en"
        targetLanguage = defaults.string(forKey: "targetLanguage") ?? "es"
        appearance = AppAppearance(rawValue: defaults.string(forKey: "appearance") ?? "") ?? .system
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-vipi-welcome") { onboarding = .welcome }
        if args.contains("-vipi-language") { onboarding = .language }
        if let index = args.firstIndex(of: "-vipi-source"), args.indices.contains(index + 1), VipiLanguage.initial.contains(where: { $0.id == args[index + 1] }) { knownLanguage = args[index + 1] }
        if let index = args.firstIndex(of: "-vipi-target"), args.indices.contains(index + 1), VipiLanguage.initial.contains(where: { $0.id == args[index + 1] }), args[index + 1] != knownLanguage { targetLanguage = args[index + 1] }
        if args.contains("-vipi-preview-home") { isAuthenticated = true }
        if args.contains("-vipi-appearance-light") { appearance = .light }
        if args.contains("-vipi-appearance-dark") { appearance = .dark }

        #endif
    }
}
