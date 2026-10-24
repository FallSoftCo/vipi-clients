import Foundation
import Observation
import SwiftUI

struct VipiLanguage: Identifiable, Hashable {
    let id: String
    let name: String
    let localName: String
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
        .init(id: "ar", name: "Arabic", localName: "العربية")
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
        if args.contains("-vipi-preview-home") { isAuthenticated = true }
        #endif
    }
}
