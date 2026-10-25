import SwiftUI

@main struct VipiApp: App {
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
                if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") { TimelineQualificationView() }
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
