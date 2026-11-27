import SwiftUI

@main struct VipiApp: App {
    @UIApplicationDelegateAdaptor(VipiAppDelegate.self) private var appDelegate
    @State private var state = AppState()
    @State private var authentication: AuthenticationManager
    @State private var deletion: AccountDeletion
    init() {
        #if DEBUG
        precondition(
            !(ProcessInfo.processInfo.arguments.contains("-vipi-deletion-root-qa")
                && ProcessInfo.processInfo.arguments.contains("-vipi-first-month-root-qa")),
            "One owned root qualification at a time")
        ConnectedDeletionUIQualification.prepareIfRequested()
        FirstMonthRootQualification.prepareIfRequested()
        if ProcessInfo.processInfo.arguments.contains("-vipi-onboarding-screenshot-fixture") {
            _state = State(initialValue: AppState(translationServices: OnboardingScreenshotTranslationFixture.services))
        } else if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa"),
            ProcessInfo.processInfo.arguments.contains("-vipi-funding-qa")
        {
            _state = State(initialValue: AppState(translationServices: TimelineQualificationView.fundingServices))
        } else if let services = FirstMonthRootQualification.current?.fullTranslationServices {
            _state = State(initialValue: AppState(translationServices: services))
        }
        #endif
        let authentication = AuthenticationManager()
        #if DEBUG
        FirstMonthRootQualification.current?.bind(authentication)
        #endif
        _authentication = State(initialValue: authentication)
        #if DEBUG
        if let qualification = ConnectedDeletionUIQualification.current {
            do { _deletion = State(initialValue: try qualification.makeDeletion(authentication)) } catch {
                preconditionFailure("Preserve unknown QA identity/deletion/audio state before qualification")
            }
        } else {
            _deletion = State(initialValue: AccountDeletion(authentication: authentication))
        }
        #else
        _deletion = State(initialValue: AccountDeletion(authentication: authentication))
        #endif
        #if DEBUG
        PersistenceProbe.startIfRequested()
        #endif
    }
    var body: some Scene {
        WindowGroup {
            Group {
                if deletion.active {
                    AccountDeletionProgressView()
                } else {
                    #if DEBUG
                    if KeychainStore.isMediaQualification,
                        ProcessInfo.processInfo.arguments.contains("-vipi-received-photo-qa")
                    {
                        ReceivedPhotoQualification()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-real-visible-read-qa"),
                        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
                    {
                        NativeReadQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-bot-ui-qa"),
                        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
                    {
                        BotUIQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-reauth-qa") {
                        ReauthenticationQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-network-qa") {
                        // The explicit native HTTP harness owns inbox ordering.
                        // It still uses the real account session and production
                        // cryptography; Release has no such launch path.
                        Color.clear.accessibilityLabel("Native messaging qualification")
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-timeline-qa") {
                        TimelineQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-home-preview-display-qa"),
                        Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa"
                    {
                        HomePreviewDisplayQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-reading-status-ui-qa") {
                        ReadingStatusUIQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-full-reading-qa") {
                        FullReadingQualificationView()
                    } else if ProcessInfo.processInfo.arguments.contains("-vipi-translation-matrix") {
                        TranslationQualification()
                    } else if state.isAuthenticated {
                        if ProcessInfo.processInfo.arguments.contains("-vipi-preview-home") {
                            HomeView()
                        } else {
                            ConnectedChatRoot(
                                qualification: ConnectedDeletionUIQualification.current?.connection
                                    ?? FirstMonthRootQualification.current?.connection)
                        }
                    } else if state.guestMode {
                        HomeView()
                    } else {
                        OnboardingView()
                    }
                    #else
                    if state.isAuthenticated {
                        ConnectedChatRoot()
                    } else if state.guestMode {
                        HomeView()
                    } else {
                        OnboardingView()
                    }
                    #endif
                }
            }
            #if DEBUG
            .frame(
                width: FirstMonthRootQualification.current != nil
                    && ProcessInfo.processInfo.arguments.contains("-vipi-compact-header-window-qa")
                    ? 375 : (ProcessInfo.processInfo.arguments.contains("-vipi-streaks-compact-qa") ? 320 : nil))
            #endif
            .modifier(ConversationStreakClock())
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
            .onOpenURL { url in
                if deletion.active || !state.acceptInvitation(url) {
                    Task { await authentication.complete(url) }
                } else {
                    PushNotifications.shared.clearInboxPresentation()
                }
            }
            .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                if let url = activity.webpageURL, !deletion.active, state.acceptInvitation(url) {
                    PushNotifications.shared.clearInboxPresentation()
                }
            }
            .onChange(of: deletion.active, initial: true) { _, active in
                if active {
                    state.invitationUsername = nil
                    PushNotifications.shared.clearInboxPresentation()
                }
            }
            #if DEBUG
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if let qualification = FirstMonthRootQualification.current {
                    if qualification.pendingPairEnabled {
                        Button {
                            qualification.releasePendingPair()
                        } label: {
                            Text("Release owned old-pair provider results")
                            .foregroundStyle(VipiDesign.highlight).frame(minHeight: 44).contentShape(Rectangle())
                        }
                        .accessibilityIdentifier("pending-pair-release")
                        .disabled(qualification.pendingPairReleased)
                    }
                    TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                        Color.clear.frame(height: 1).accessibilityElement(children: .ignore)
                        .accessibilityLabel("Local journey evidence")
                        .accessibilityIdentifier("first-month-root-qa-proof|" + qualification.proof)
                    }
                } else if FirstMonthRootQualification.cleaned {
                    Text("Owned first-month fixture removed").accessibilityIdentifier("first-month-root-cleaned")
                } else if let qualification = ConnectedDeletionUIQualification.current {
                    TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                        Text(qualification.proof).font(.caption2).lineLimit(1)
                        .accessibilityIdentifier("deletion-root-qa-proof")
                    }
                }
            }
            #endif
        }
    }
}

#if DEBUG
/// Simulator translation models are unavailable, so store captures use the
/// production translation service boundary with authored tutorial output.
/// Release builds contain no fixture path.
@MainActor private enum OnboardingScreenshotTranslationFixture {
    static let services = MessageTranslationServices(
        status: { pair in pair.valid ? .installed : .unsupported },
        translate: { text, pair in
            guard pair.source == "en", pair.target == "es" else { return text }
            switch text.trimmingCharacters(in: .whitespacesAndNewlines) {
            case "Coffee tomorrow?", "Coffee tomorrow": return "¿Café mañana?"
            case "Coffee", "coffee": return "Café"
            case "tomorrow": return "mañana"
            default: return text
            }
        })
}
#endif
