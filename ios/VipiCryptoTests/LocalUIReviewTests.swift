import XCTest
import SwiftUI
import VipiCore
@testable import Vipi

/// Real native components in an isolated test window. Does not qualify account
/// routing, keychain access or signing; the ordinary app's deletion gate stays intact.
@MainActor final class LocalUIReviewTests: XCTestCase {
    func testOnboardingAndContinuousComponent() async throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene)
        window.windowLevel = .alert + 1
        let suite = "vipi-component-review-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        let state = AppState(defaults: defaults)
        let auth = AuthenticationManager()
        defer { window.isHidden = true; window.rootViewController = nil; previous?.makeKey(); defaults.removePersistentDomain(forName: suite) }
        func mount<V: View>(_ view: V) {
            window.rootViewController = UIHostingController(rootView: view)
            window.makeKeyAndVisible(); window.layoutIfNeeded()
        }
        func capture(_ name: String) {
            window.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            let a = XCTAttachment(image: image); a.name = name; a.lifetime = .keepAlways; add(a)
        }
        for (name, step, scheme, size) in [
            ("welcome-light", OnboardingStep.welcome, ColorScheme.light, DynamicTypeSize.large),
            ("welcome-dark", .welcome, .dark, .large),
            ("language-light", .language, .light, .large),
            ("account-largest", .account, .dark, .accessibility5)
        ] {
            state.onboarding = step
            mount(OnboardingView().environment(state).environment(auth)
                .environment(\.scenePhase, .active).environment(\.dynamicTypeSize, size)
                .preferredColorScheme(scheme).tint(VipiDesign.highlight))
            try await Task.sleep(for: .seconds(2)); capture(name)
            if step == .account {
                func scrollViews(_ view: UIView) -> [UIScrollView] {
                    (view as? UIScrollView).map { [$0] } ?? view.subviews.flatMap { scrollViews($0) }
                }
                let scroll = try XCTUnwrap(scrollViews(window).max { $0.contentSize.height < $1.contentSize.height })
                let bottom = max(-scroll.adjustedContentInset.top, scroll.contentSize.height-scroll.bounds.height+scroll.adjustedContentInset.bottom)
                scroll.setContentOffset(CGPoint(x:0,y:bottom),animated:false)
                try await Task.sleep(for: .milliseconds(500)); capture("account-largest-bottom")
                XCTAssertLessThanOrEqual(abs(scroll.contentOffset.y-bottom),1)
            }
        }
        // Preserve one mounted onboarding view while changing steps after scrolling.
        // Individually mounted screenshots cannot detect inherited scroll offsets.
        state.onboarding = .language
        mount(OnboardingView().environment(state).environment(auth)
            .environment(\.scenePhase, .active).environment(\.dynamicTypeSize, .accessibility5)
            .preferredColorScheme(.dark).tint(VipiDesign.highlight))
        try await Task.sleep(for: .seconds(1))
        func primaryScroll(_ view: UIView) -> UIScrollView? {
            func collect(_ item: UIView) -> [UIScrollView] {
                (item as? UIScrollView).map { [$0] } ?? item.subviews.flatMap { collect($0) }
            }
            return collect(view).max { $0.contentSize.height < $1.contentSize.height }
        }
        let languageScroll = try XCTUnwrap(primaryScroll(window))
        let bottom = max(-languageScroll.adjustedContentInset.top,
                         languageScroll.contentSize.height-languageScroll.bounds.height+languageScroll.adjustedContentInset.bottom)
        XCTAssertGreaterThan(bottom, 100)
        languageScroll.setContentOffset(CGPoint(x: 0, y: bottom), animated: false)
        state.onboarding = .account
        try await Task.sleep(for: .seconds(1))
        let accountScroll = try XCTUnwrap(primaryScroll(window))
        XCTAssertEqual(accountScroll.contentOffset.y, -accountScroll.adjustedContentInset.top, accuracy: 1)
        capture("account-largest-arrival")
        mount(ScrollView { ImmersionBubble(result: .complete(ImmersionPreview.result)).padding(24) }
            .environment(\.scenePhase, .active).background(VipiDesign.canvas))
        try await Task.sleep(for: .seconds(1))
        func paragraph(_ view: UIView) -> ImmersionNativeTextView? {
            if let value = view as? ImmersionNativeTextView { return value }
            return view.subviews.lazy.compactMap { paragraph($0) }.first
        }
        let text = try XCTUnwrap(paragraph(window))
        let height = text.bounds.height
        var previousText = text.visibleText(), transitions = 0
        let deadline = Date().addingTimeInterval(32)
        while transitions < 6 && Date() < deadline {
            try await Task.sleep(for: .milliseconds(250))
            let visible = text.visibleText()
            if visible != previousText { transitions += 1; previousText = visible }
            XCTAssertEqual(text.bounds.height, height, accuracy: 0.5)
        }
        XCTAssertEqual(transitions, 6)
        capture("continuous-component")
    }
}
