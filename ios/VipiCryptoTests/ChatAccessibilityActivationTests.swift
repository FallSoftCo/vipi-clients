import XCTest
import SwiftUI
import UIKit
import VipiCore
@testable import Vipi

/// Actual UIKit accessibility paragraph produced by the production SwiftUI
/// bubble. This tests action routing, not the VoiceOver service or MT quality.
@MainActor final class ChatAccessibilityActivationTests: XCTestCase {
    /// Observe the actual pixels of a long native editor, including the older
    /// UIKit layout engine as a diagnostic control. Text/value assertions alone
    /// cannot detect a blank viewport with a correctly retained draft.
    func testLongDraftNativeViewportContainsVisibleText() async throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }, window = UIWindow(windowScene: scene)
        window.frame = scene.coordinateSpace.bounds; window.overrideUserInterfaceStyle = .light
        let host = UIViewController(); host.view.backgroundColor = .white
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        var results: [[String: Any]] = []
        for legacy in [false, true] {
            let editor: UITextView = legacy ? UITextView(usingTextLayoutManager: false) : DraftTextView.messageEditor()
            editor.backgroundColor = .white; editor.textColor = .black; editor.tintColor = .systemGreen
            editor.font = .systemFont(ofSize: 53); editor.textContainerInset = .zero
            editor.textContainer.lineFragmentPadding = 0; editor.isScrollEnabled = true
            editor.frame = CGRect(x: 24, y: 180, width: 272, height: 190)
            host.view.addSubview(editor); editor.becomeFirstResponder()
            editor.insertText(String(repeating: "界", count: 10_923))
            // Reproduce the production representable's normal sizing query.
            _ = editor.sizeThatFits(CGSize(width: 272, height: CGFloat.greatestFiniteMagnitude))
            editor.scrollRangeToVisible(NSRange(location: editor.text.utf16.count, length: 0))
            try await Task.sleep(for: .milliseconds(700))
            let image = UIGraphicsImageRenderer(size: editor.bounds.size).image { _ in
                editor.drawHierarchy(in: CGRect(origin: .zero, size: editor.bounds.size), afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = legacy ? "long-draft-TextKit1-control" : "long-draft-production-native-editor"
            attachment.lifetime = .keepAlways; add(attachment)
            let cg = try XCTUnwrap(image.cgImage), width = cg.width, height = cg.height
            var bytes = [UInt8](repeating: 0, count: width * height * 4)
            let count = bytes.withUnsafeMutableBytes { buffer -> Int in
                let context = CGContext(data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                    bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
                context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
                let pixels = buffer.bindMemory(to: UInt8.self)
                return stride(from: 0, to: pixels.count, by: 4).filter { i in
                    let lo = min(pixels[i], pixels[i+1], pixels[i+2]), hi = max(pixels[i], pixels[i+1], pixels[i+2])
                    return hi < 120 && hi - lo < 15
                }.count
            }
            results.append(["legacy_control": legacy, "dark_text_pixels": count,
                "text_utf16": editor.text.utf16.count, "viewport": NSCoder.string(for: editor.bounds),
                "content_size": NSCoder.string(for: editor.contentSize), "textkit2": editor.textLayoutManager != nil])
            editor.resignFirstResponder(); editor.removeFromSuperview()
        }
        let proof = XCTAttachment(data: try JSONSerialization.data(withJSONObject: results, options: .sortedKeys), uniformTypeIdentifier: "public.json")
        proof.name = "long-draft-native-layout-comparison"; proof.lifetime = .keepAlways; add(proof)
        XCTAssertGreaterThan(results[0]["dark_text_pixels"] as? Int ?? 0, 100, "A retained draft must actually render its text")
    }

    func testNativeDraftEditingKeepsMixedScriptMarkedTextAndReplacement() async throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }, window = UIWindow(windowScene: scene)
        window.frame = scene.coordinateSpace.bounds
        let host = UIViewController(); window.rootViewController = host; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        var draft = "", rejected = 0
        let wrapper = MessageEditor(text: Binding(get: { draft }, set: { draft = $0 }), placeholder: "Message",
            focus: .constant(false), maximumBytes: 128 * 1024, rejected: { rejected += 1 })
        let coordinator = wrapper.makeCoordinator(), editor = DraftTextView.messageEditor()
        editor.delegate = coordinator; editor.font = .systemFont(ofSize: 24)
        editor.frame = CGRect(x: 20, y: 140, width: 320, height: 150)
        host.view.addSubview(editor); editor.becomeFirstResponder()
        let initial = "Coffee غدًا مع ليلى — café 👩🏽‍💻 "
        editor.insertText(initial)
        XCTAssertEqual(draft, initial); XCTAssertEqual(editor.text, initial)
        editor.setMarkedText("にほん", selectedRange: NSRange(location: 3, length: 0))
        XCTAssertNotNil(editor.markedTextRange)
        editor.setMarkedText("日本", selectedRange: NSRange(location: 2, length: 0)); editor.unmarkText()
        XCTAssertNil(editor.markedTextRange); XCTAssertEqual(editor.text, initial + "日本")
        let range = (editor.text as NSString).range(of: "غدًا")
        let start = try XCTUnwrap(editor.position(from: editor.beginningOfDocument, offset: range.location))
        let end = try XCTUnwrap(editor.position(from: start, offset: range.length))
        editor.selectedTextRange = editor.textRange(from: start, to: end); editor.insertText("اليوم")
        let expected = initial.replacingOccurrences(of: "غدًا", with: "اليوم") + "日本"
        XCTAssertEqual(editor.text, expected); XCTAssertEqual(draft, expected)
        XCTAssertEqual(rejected, 0)
        // Direct UITextInput insertion exercises composition and logical ranges,
        // but does not request the delegate's edit permission. Size rejection is
        // qualified by the actual native Paste journey, not programmatic input.
        let rendered = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in
            window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
        let image = XCTAttachment(image: rendered)
        image.name = "native-mixed-script-marked-text-and-replacement"; image.lifetime = .keepAlways; add(image)
        editor.resignFirstResponder()
    }

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
