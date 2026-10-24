import SwiftUI

@main struct VipiApp: App {
    @State private var state = AppState()
    @State private var authentication = AuthenticationManager()
    var body: some Scene {
        WindowGroup {
            Group {
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("-vipi-translation-matrix") { TranslationQualification() }
                else if state.isAuthenticated { HomeView() }
                else { OnboardingView() }
                #else
                if state.isAuthenticated { HomeView() }
                else { OnboardingView() }
                #endif
            }
            .environment(state)
            .environment(authentication)
            .tint(VipiDesign.highlight)
            .preferredColorScheme(state.appearance.scheme)
            .onChange(of: authentication.session?.userID, initial: true) { _, value in
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("-vipi-preview-home") { return }
                #endif
                state.isAuthenticated = value != nil
            }
            .onOpenURL { url in Task { await authentication.complete(url) } }
        }
    }
}
