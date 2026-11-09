import SwiftUI

@main struct VipiApp: App {
    @UIApplicationDelegateAdaptor(VipiAppDelegate.self) private var appDelegate
    @State private var state = AppState()
    @State private var authentication: AuthenticationManager
    @State private var deletion: AccountDeletion
    init() {
        let authentication = AuthenticationManager()
        _authentication = State(initialValue: authentication)
        _deletion = State(initialValue: AccountDeletion(authentication: authentication))
        #if DEBUG
        PersistenceProbe.startIfRequested()
        #endif
    }
    var body: some Scene {
        WindowGroup {
            Group {
                if deletion.active { AccountDeletionProgressView() }
                else {
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("-vipi-reauth-qa") { ReauthenticationQualificationView() }
                else if ProcessInfo.processInfo.arguments.contains("-vipi-network-qa") {
                    // The explicit native HTTP harness owns inbox ordering.
                    // It still uses the real account session and production
                    // cryptography; Release has no such launch path.
                    Color.clear.accessibilityLabel("Native messaging qualification")
                }
                else if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") { TimelineQualificationView() }
                else if ProcessInfo.processInfo.arguments.contains("-vipi-starter-route-qa") { StarterRouteQualificationView() }
                else if ProcessInfo.processInfo.arguments.contains("-vipi-full-reading-qa") { FullReadingQualificationView() }
                else if ProcessInfo.processInfo.arguments.contains("-vipi-translation-matrix") { TranslationQualification() }
                else if state.isAuthenticated {
                    if ProcessInfo.processInfo.arguments.contains("-vipi-preview-home") { HomeView() }
                    else { ConnectedChatRoot() }
                }
                else { OnboardingView() }
                #else
                if state.isAuthenticated { ConnectedChatRoot() }
                else { OnboardingView() }
                #endif
                }
            }
            .environment(state)
            .environment(authentication)
            .environment(deletion)
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
