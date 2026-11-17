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
    static let initial: [Self] = [
        .init(id: "en", name: "English", localName: "English"),
        .init(id: "es", name: "Spanish", localName: "Español"),
        .init(id: "fr", name: "French", localName: "Français"),
        .init(id: "de", name: "German", localName: "Deutsch"),
        .init(id: "it", name: "Italian", localName: "Italiano"),
        .init(id: "pt", name: "Portuguese", localName: "Português"),
        .init(id: "ja", name: "Japanese", localName: "日本語"),
        .init(id: "ko", name: "Korean", localName: "한국어"),
        .init(id: "zh", name: "Chinese", localName: "中文"),
        .init(id: "ar", name: "Arabic", localName: "العربية"),
        .init(id: "sw", name: "Swahili", localName: "Kiswahili")
    ]
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
    var density: Double { didSet { defaults.set(density, forKey: "density") } }
    var isAuthenticated = false
    private let defaults: UserDefaults

    func selectKnownLanguage(_ value: String) {
        guard VipiLanguage.initial.contains(where: { $0.id == value }) else { return }
        // Adjust the target in the same action, before publishing the new
        // source. A delayed view onChange exposes an invalid equal pair.
        if value == targetLanguage { targetLanguage = value == "es" ? "en" : "es" }
        knownLanguage = value
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        onboarding = OnboardingStep(rawValue: defaults.string(forKey: "onboardingStep") ?? "") ?? .welcome
        knownLanguage = defaults.string(forKey: "knownLanguage") ?? "en"
        targetLanguage = defaults.string(forKey: "targetLanguage") ?? "es"
        appearance = AppAppearance(rawValue: defaults.string(forKey: "appearance") ?? "") ?? .system
        density = defaults.object(forKey: "density") as? Double ?? 0.25
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-vipi-welcome") { onboarding = .welcome }
        if args.contains("-vipi-language") { onboarding = .language }
        if let index = args.firstIndex(of: "-vipi-source"), args.indices.contains(index + 1), VipiLanguage.initial.contains(where: { $0.id == args[index + 1] }) { knownLanguage = args[index + 1] }
        if let index = args.firstIndex(of: "-vipi-target"), args.indices.contains(index + 1), VipiLanguage.initial.contains(where: { $0.id == args[index + 1] }), args[index + 1] != knownLanguage { targetLanguage = args[index + 1] }
        if args.contains("-vipi-preview-home") { isAuthenticated = true }
        if args.contains("-vipi-appearance-light") { appearance = .light }
        if args.contains("-vipi-appearance-dark") { appearance = .dark }
        if let index = args.firstIndex(of: "-vipi-density"), args.indices.contains(index + 1),
           let value = Double(args[index + 1]), value.isFinite, (0...0.75).contains(value) { density = value }
        #endif
    }
}
