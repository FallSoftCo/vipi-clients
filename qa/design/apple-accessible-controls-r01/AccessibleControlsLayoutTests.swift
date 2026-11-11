import XCTest
import SwiftUI
import VipiCore
@testable import Vipi

@MainActor final class AccessibleControlsLayoutTests: XCTestCase {
    func testReadyAndPreparingControlsAtMaximumText() async throws {
        XCTAssertTrue(UIAccessibility.isReduceMotionEnabled)
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }, window = UIWindow(windowScene:scene)
        window.windowLevel = .alert + 1
        defer { window.isHidden = true; window.rootViewController = nil; previous?.makeKey() }
        let owner = ConversationImmersion()
        await owner.configure(pair:.init(source:"en",target:"ja"),density:0.25)
        let produced = await owner.result(for:"I drink coffee every morning.")
        let result = try XCTUnwrap(produced)
        XCTAssertFalse(result.spans.isEmpty)
        let preparing = SpeechPlayback(), ready = SpeechPlayback()
        ready.qualificationPrepare = {}
        ready.prepare(source:"en",target:"ja",warmups:[:])
        for _ in 0..<50 where ready.state == .preparing { try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(ready.state,.ready)
        for (name,size,speech) in [("max-preparing",DynamicTypeSize.accessibility5,preparing),("max-ready",.accessibility5,ready),("ordinary-ready",.large,ready)] {
            window.rootViewController = UIHostingController(rootView: ScrollView { ImmersionBubble(result:result,speech:speech,sourceLanguage:"en",targetLanguage:"ja",interactionPaused:true).padding(26) }.environment(\.scenePhase,.active).environment(\.dynamicTypeSize,size).preferredColorScheme(.light))
            window.makeKeyAndVisible();window.layoutIfNeeded();try await Task.sleep(for:.milliseconds(400))
            let image=UIGraphicsImageRenderer(bounds:window.bounds).image { _ in window.drawHierarchy(in:window.bounds,afterScreenUpdates:true) }
            let a=XCTAttachment(image:image);a.name="fixed-controls-"+name;a.lifetime = .keepAlways;add(a)
        }
        preparing.close();ready.close();owner.close()
    }
}
