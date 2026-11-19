import XCTest
import SwiftUI
import UIKit
import VipiCore
@testable import Vipi

/// Actual UIKit accessibility paragraph produced by the production SwiftUI
/// bubble. This tests action routing, not the VoiceOver service or MT quality.
@MainActor final class ChatAccessibilityActivationTests: XCTestCase {
    func testLatinMessageKeepsTimeAndPlaybackWithoutAdvertisingAnUnavailableScript() async throws {
        let suite = "latin-message-accessibility-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName:suite))
        defer { defaults.removePersistentDomain(forName:suite) }
        let reading = ChatReadingState(defaults:defaults), owner = UUID()
        let identity = ImmersionRequestIdentity(messageID:"latin-message",text:"Tomorrow.",source:"en",target:"es",inputLanguage:"en",generation:UUID())
        var selected:[ImmersionRequestIdentity] = []
        reading.bindPlayback(owner:owner) { selected.append($0) }
        defer { reading.unbindPlayback(owner:owner) }
        let result = FullMessageTranslation(original:"Tomorrow.",practiceText:"Mañana.",meaningText:"Tomorrow.",inputLanguage:"en",practiceLanguage:"es",meaningLanguage:"en")
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first)
        let previous = scene.windows.first{$0.isKeyWindow}, window = UIWindow(windowScene:scene)
        window.frame = scene.coordinateSpace.bounds
        let context = "19 Nov 2026, 11:30 · Delivered"
        let host = UIHostingController(rootView:ImmersionBubble(result:result.presentation,targetLanguage:"es",messageID:identity.messageID,
            embedded:true,accessibilityMessageContext:context,originalMessage:result.original,reading:reading,identity:identity).frame(maxWidth:350))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        func find(_ view:UIView)->ImmersionTextContainer? {
            if let value = view as? ImmersionTextContainer { return value }
            return view.subviews.lazy.compactMap(find).first
        }
        let deadline = ContinuousClock.now.advanced(by:.seconds(2))
        while find(host.view)?.accessibilityElements?.isEmpty != false && ContinuousClock.now < deadline {
            host.view.layoutIfNeeded(); try await Task.sleep(for:.milliseconds(10))
        }
        let paragraph = try XCTUnwrap(find(host.view)?.accessibilityElements?.first as? UIAccessibilityElement)
        XCTAssertEqual(paragraph.accessibilityLabel,"Mañana.")
        XCTAssertTrue(paragraph.accessibilityHint?.contains(context) == true,"Exact time/state remains accessible when grouped visually")
        let actions = paragraph.accessibilityCustomActions?.map(\.name) ?? []
        XCTAssertTrue(actions.contains(String(localized:"Play in practice language")))
        XCTAssertTrue(actions.contains(String(localized:"Show meanings")))
        XCTAssertFalse(actions.contains(String(localized:"Show native script")))
        XCTAssertFalse(actions.contains(String(localized:"Show transliteration")))
        XCTAssertFalse(reading.hasAlternateScript)
        XCTAssertTrue(paragraph.accessibilityActivate()); XCTAssertEqual(selected,[identity])
    }
    func testCopyAnchorOwnershipFollowsNativeWindowAttachmentAcrossReplacement() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first)
        let previous = scene.windows.first{$0.isKeyWindow}, window = UIWindow(windowScene:scene)
        window.frame = scene.coordinateSpace.bounds
        let host = UIViewController(); window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        let owner = CopyOriginalContext(editorID:"owned-anchor-lifecycle-editor")
        let first = CopyOriginalAnchor.Probe(); first.setOwner(owner)
        XCTAssertNil(first.window); XCTAssertNil(owner.anchor)
        host.view.addSubview(first)
        XCTAssertTrue(first.window === window); XCTAssertTrue(owner.anchor === first)
        let replacement = CopyOriginalAnchor.Probe(); replacement.setOwner(owner)
        XCTAssertNil(replacement.window)
        XCTAssertTrue(owner.anchor === first,"An unattached replacement must not steal the live native anchor")
        replacement.setOwner(owner)
        XCTAssertTrue(owner.anchor === first,"An update before attachment must preserve the live anchor too")
        host.view.addSubview(replacement)
        XCTAssertTrue(replacement.window === window); XCTAssertTrue(owner.anchor === replacement)
        first.removeFromSuperview(); first.setOwner(nil)
        XCTAssertTrue(owner.anchor === replacement,"Old detachment/dismantling cannot clear the newly attached owner")
        replacement.removeFromSuperview()
        XCTAssertNil(replacement.window); XCTAssertNil(owner.anchor,"Final native detachment must clear the anchor")
        replacement.setOwner(nil); XCTAssertNil(owner.anchor)
    }

    func testDefaultNativeActivationReachesTheSameMessageAcrossReadingScriptAndMeaning() async throws {
        let suite = "full-message-accessibility-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName:suite))
        defer { defaults.removePersistentDomain(forName:suite) }
        let reading = ChatReadingState(defaults:defaults), playbackOwner = UUID()
        var selected:[ImmersionRequestIdentity] = []
        reading.bindPlayback(owner:playbackOwner) { selected.append($0) }
        defer { reading.unbindPlayback(owner:playbackOwner) }
        let identity = ImmersionRequestIdentity(messageID:"native-accessibility-message",text:"Tomorrow.",source:"en",target:"zh",inputLanguage:"en",generation:UUID())
        let result = FullMessageTranslation(original:"Tomorrow.",practiceText:"明天。",meaningText:"Tomorrow.",inputLanguage:"en",practiceLanguage:"zh",meaningLanguage:"en",practiceReading:"míngtiān.")
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first)
        let previous = scene.windows.first{$0.isKeyWindow}, window = UIWindow(windowScene:scene)
        window.frame = scene.coordinateSpace.bounds
        let host = UIHostingController(rootView:ImmersionBubble(result:result.presentation,targetLanguage:"zh",messageID:identity.messageID,
            fullReading:result.practiceReading,embedded:true,originalMessage:result.original,reading:reading,identity:identity).frame(maxWidth:350))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        func find(_ view:UIView)->ImmersionTextContainer? {
            if let value = view as? ImmersionTextContainer { return value }
            for child in view.subviews { if let value = find(child) { return value } }
            return nil
        }
        for (index,face) in ["míngtiān.","明天。","Tomorrow."].enumerated() {
            if index == 1 { reading.toggleScript() }
            if index == 2 { reading.toggleMeaning() }
            let deadline = ContinuousClock.now.advanced(by:.seconds(2))
            while (find(host.view)?.textView.visibleText() != face) && ContinuousClock.now < deadline {
                host.view.layoutIfNeeded(); try await Task.sleep(for:.milliseconds(10))
            }
            let container = try XCTUnwrap(find(host.view)), paragraph = try XCTUnwrap(container.accessibilityElements?.first as? UIAccessibilityElement)
            XCTAssertEqual(paragraph.accessibilityLabel,face)
            let hint = try XCTUnwrap(paragraph.accessibilityHint)
            let meaningAction = index == 2 ? String(localized:"Show practice text") : String(localized:"Show meanings")
            let scriptAction = index == 0 ? String(localized:"Show native script") : String(localized:"Show transliteration")
            let playAction = String(localized:"Play in practice language")
            XCTAssertTrue(hint.contains(playAction)); XCTAssertTrue(hint.contains(meaningAction)); XCTAssertTrue(hint.contains(scriptAction))
            XCTAssertNotEqual(hint,String(localized:"Tap to listen. Hold to see meanings. Double-tap to change script."))
            let nativeActions = paragraph.accessibilityCustomActions?.map(\.name) ?? []
            for action in [playAction,meaningAction,scriptAction] { XCTAssertTrue(nativeActions.contains(action),"Actual paragraph must expose its advertised native action: " + action) }
            XCTAssertTrue(paragraph.accessibilityActivate(),"Default native activation must invoke the production message play action")
            XCTAssertEqual(selected.count,index+1)
            XCTAssertEqual(selected.last,identity,"Meaning or romanization must not change the practice-audio message binding")
        }
    }
}
