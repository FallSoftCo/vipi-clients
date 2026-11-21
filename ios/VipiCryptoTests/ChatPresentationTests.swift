import XCTest
import SwiftUI
import UIKit
import VipiCore
@testable import Vipi

@MainActor final class ChatPresentationTests:XCTestCase {
    func testRestoredAndUnknownDeliveryNeverClaimQueuedAndFailureCopyMatchesGlyph() {
        XCTAssertEqual(MessageDeliveryMark.singleSymbol("imported"),"archivebox")
        XCTAssertEqual(MessageDeliveryMark.localizedDescription("imported"),String(localized:"Saved history"))
        XCTAssertNil(MessageDeliveryMark.singleSymbol("future-unknown-state"))
        XCTAssertTrue(MessageDeliveryMark.localizedDescription("future-unknown-state").isEmpty)
        for state in ["unavailable","identity_changed","failed"] {
            XCTAssertEqual(MessageDeliveryMark.singleSymbol(state),"exclamationmark.circle")
            XCTAssertEqual(MessageDeliveryMark.localizedDescription(state),String(localized:"Not delivered"))
        }
        for state in ["queued","pending"] { XCTAssertEqual(MessageDeliveryMark.singleSymbol(state),"clock") }
        XCTAssertEqual(MessageDeliveryMark.localizedDescription("read"),String(localized:"Read"))
        XCTAssertEqual(MessageDeliveryMark.localizedDescription("delivered"),String(localized:"Delivered"))
    }

    func testInitialsPreserveRealUnicodeGraphemesAndNeverInventAPhoto() {
        for (name,initial) in [("  👩🏽‍🚀 Astronaut","👩🏽‍🚀A"),("👨‍👩‍👧‍👦 Family","👨‍👩‍👧‍👦F"),("e\u{301}lodie","e\u{301}"),("لُمى","لُ"),("朋子","朋"),("Ada María Lovelace","AL"),("   ","?")] {
            XCTAssertEqual(ContactMonogram.text(name),initial)
        }
    }
    func testContactPaletteMatchesSharedUUIDByteContract() throws {
        for (id,slot) in [("00000000-0000-0000-0000-000000000000",0),("00000000-0000-0001-0000-000000000000",1),("00000000-0000-0003-0000-000000000001",2),("00000000-0000-0000-0000-000000000003",3)] {
            XCTAssertEqual(ContactMonogram.colorIndex(try XCTUnwrap(UUID(uuidString:id))),slot)
        }
    }
    func testReadMarkKeepsContrastAgainstActualOutgoingMaterialInBothThemes() throws {
        func luminance(_ color:UIColor) -> Double {
            var red:CGFloat = 0,green:CGFloat = 0,blue:CGFloat = 0,alpha:CGFloat = 0
            XCTAssertTrue(color.getRed(&red,green:&green,blue:&blue,alpha:&alpha))
            func linear(_ component:CGFloat) -> Double {
                let value = Double(component)
                if value <= 0.04045 { return value/12.92 }
                return pow((value+0.055)/1.055,2.4)
            }
            let r = linear(red),g = linear(green),b = linear(blue)
            return r*0.2126+g*0.7152+b*0.0722
        }
        for style:UIUserInterfaceStyle in [.light,.dark] {
            let traits = UITraitCollection(userInterfaceStyle:style)
            let ink = luminance(UIColor(VipiDesign.readIndicator).resolvedColor(with:traits))
            let bubble = luminance(UIColor(VipiDesign.outgoingBubble).resolvedColor(with:traits))
            XCTAssertGreaterThanOrEqual((max(ink,bubble)+0.05)/(min(ink,bubble)+0.05),3)
        }
    }
    func testReadViewportExcludesNavKeyboardAndMostlyClippedRows() {
        let viewport = CGRect(x:0,y:116,width:402,height:347)
        XCTAssertFalse(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:40,width:200,height:60),in:viewport))
        XCTAssertFalse(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:480,width:200,height:60),in:viewport))
        XCTAssertFalse(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:450,width:200,height:80),in:viewport))
        XCTAssertTrue(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:360,width:200,height:80),in:viewport))
        XCTAssertTrue(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:-100,width:200,height:1000),in:viewport))
        XCTAssertFalse(ChatMessageVisibility.containsReadableMessage(CGRect(x:20,y:200,width:200,height:60),in:.zero))
    }
    func testMeasuredClippedContainerDoesNotSubtractKeyboardTwice() {
        let composer = CGRect(x:0,y:471,width:402,height:68)
        let clipped = ChatMessageVisibility.viewport(frame:CGRect(x:18,y:116,width:366,height:347),containerHeight:347,topInset:116,bottomInset:411,composer:composer)
        let full = ChatMessageVisibility.viewport(frame:CGRect(x:18,y:0,width:366,height:874),containerHeight:347,topInset:116,bottomInset:411,composer:composer)
        XCTAssertEqual(clipped,full)
        XCTAssertEqual(clipped.height,347)
        XCTAssertTrue(ChatMessageVisibility.containsReadableMessage(CGRect(x:18,y:134,width:366,height:69.33),in:clipped))
        XCTAssertFalse(ChatMessageVisibility.containsReadableMessage(CGRect(x:18,y:480,width:366,height:69.33),in:clipped))
    }
    private func contrast(_ ink:UIColor,_ background:UIColor) -> Double {
        func luminance(_ color:UIColor) -> Double {
            var r:CGFloat = 0,g:CGFloat = 0,b:CGFloat = 0,a:CGFloat = 0
            XCTAssertTrue(color.getRed(&r,green:&g,blue:&b,alpha:&a));XCTAssertEqual(a,1,accuracy:0.0001)
            func linear(_ x:CGFloat)->Double { let v = Double(x);return v <= 0.04045 ? v/12.92:pow((v+0.055)/1.055,2.4) }
            return linear(r)*0.2126+linear(g)*0.7152+linear(b)*0.0722
        }
        let x = luminance(ink),y = luminance(background)
        return (max(x,y)+0.05)/(min(x,y)+0.05)
    }
    func testSemanticPalettePreservesOpaqueTextAndStateContrastAcrossNativeTraits() {
        for style:UIUserInterfaceStyle in [.light,.dark] {
            for higher:UIAccessibilityContrast in [.normal,.high] {
                let traits = UITraitCollection(traitsFrom:[UITraitCollection(userInterfaceStyle:style),UITraitCollection(accessibilityContrast:higher)])
                func color(_ role:VipiColorRole)->UIColor { VipiPalette.uiColor(role).resolvedColor(with:traits) }
                for background:VipiColorRole in [.canvas,.surface,.incoming] {
                    for ink:VipiColorRole in [.ink,.secondary,.read,.failed] {
                        XCTAssertGreaterThanOrEqual(contrast(color(ink),color(background)),4.5,"\(style) \(higher) \(ink) on \(background)")
                    }
                }
                for ink:VipiColorRole in [.outgoingInk,.outgoingSecondary,.outgoingRead,.outgoingFailed] {
                    XCTAssertGreaterThanOrEqual(contrast(color(ink),color(.outgoing)),4.5,"\(style) \(higher) \(ink) on outgoing")
                }
                for pair:(VipiColorRole,VipiColorRole) in [(.onAction,.action),(.practiceInk,.practiceFill),(.spokenInk,.spokenFill)] {
                    XCTAssertGreaterThanOrEqual(contrast(color(pair.0),color(pair.1)),4.5)
                }
                for slot in 0..<4 { XCTAssertGreaterThanOrEqual(contrast(color(.ink),UIColor(VipiPalette.avatar(slot)).resolvedColor(with:traits)),4.5) }
            }
        }
    }
    func testActualNativeMixedPracticeAndPlayingWordUseBothMessageContextsInDayAndNight() async throws {
        // Supplied word equivalents isolate native painting from model quality.
        // Playback and its whole-word marker are the existing actual player.
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in nil},nativeTranslation:{text,_ in text.lowercased() == "water" ? "agua":text})
        await owner.configure(pair:.init(source:"en",target:"es"));defer { owner.close() }
        let translated = await owner.translatedMessage(for:owner.identity(messageID:"native-theme",text:"water, water!"))
        let value = try XCTUnwrap(translated)
        XCTAssertEqual(value.practiceText,"agua, agua!")
        let player = SpeechPlayback();defer { player.close() }
        player.prepare(source:"es",target:"es",warmups:["es":"agua"])
        try await waitForNativeVoicePreparation(player)
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first)
        func find(_ view:UIView)->ImmersionTextContainer? {
            if let view = view as? ImmersionTextContainer { return view }
            return view.subviews.lazy.compactMap(find).first
        }
        for dark in [false,true] {
            for outgoing in [false,true] {
                let label = "native-theme-"+(dark ? "dark":"light")+"-"+(outgoing ? "outgoing":"incoming")
                let previous = scene.windows.first{$0.isKeyWindow},window = UIWindow(windowScene:scene)
                window.frame = scene.coordinateSpace.bounds;window.overrideUserInterfaceStyle = dark ? .dark:.light
                let controls = ChatReadingState()
                let metadata = AnyView(HStack(spacing:4) {
                    Text("12:34 PM").monospacedDigit()
                    if outgoing { MessageDeliveryMark(state:"read") }
                }.font(.caption2).foregroundStyle(VipiDesign.messageSecondary(outgoing)))
                let host = UIHostingController(rootView:VStack(alignment:.leading,spacing:24) {
                    Text("Native renderer · supplied water → agua").font(.caption).foregroundStyle(VipiDesign.secondary)
                    HStack {
                        if outgoing { Spacer(minLength:38) }
                        ImmersionBubble(result:value.presentation,speech:player,sourceLanguage:"en",targetLanguage:"es",messageID:label,
                            embedded:true,metadata:metadata,reading:controls,incremental:true)
                            .modifier(MessageBubbleSurface(outgoing:outgoing))
                        if !outgoing { Spacer(minLength:38) }
                    }
                    Spacer()
                }.padding(18).frame(maxWidth:.infinity,maxHeight:.infinity).background(VipiDesign.canvas)
                    .environment(\.dynamicTypeSize,.large).environment(\.colorScheme,dark ? .dark:.light))
                window.rootViewController = host;window.makeKeyAndVisible()
                defer { player.stop();window.rootViewController = nil;window.isHidden = true;previous?.makeKeyAndVisible() }
                host.view.layoutIfNeeded();try await Task.sleep(for:.milliseconds(50));host.view.layoutIfNeeded()
                let native = try XCTUnwrap(find(host.view)?.textView)
                func attachments()->[ImmersionWordAttachment] {
                    var output:[ImmersionWordAttachment] = []
                    native.attributedText.enumerateAttribute(.attachment,in:NSRange(location:0,length:native.attributedText.length)) { value,_,_ in
                        if let value = value as? ImmersionWordAttachment { output.append(value) }
                    };return output
                }
                XCTAssertEqual(attachments().count,2)
                let expected = VipiPalette.uiColor(outgoing ? .outgoingInk:.ink).resolvedColor(with:native.traitCollection)
                var plain:[UIColor] = []
                native.attributedText.enumerateAttributes(in:NSRange(location:0,length:native.attributedText.length)) { attrs,_,_ in
                    if attrs[.attachment] == nil,let color = attrs[.foregroundColor] as? UIColor { plain.append(color) }
                }
                XCTAssertFalse(plain.isEmpty);XCTAssertTrue(plain.allSatisfy{$0.isEqual(expected)},"Original punctuation must retain the contextual message ink")
                func snapshot(_ phase:String) {
                    let image = UIGraphicsImageRenderer(size:window.bounds.size).image{_ in window.drawHierarchy(in:window.bounds,afterScreenUpdates:true)}
                    let item = XCTAttachment(image:image);item.name = label+"-"+phase;item.lifetime = .keepAlways;add(item)
                    let proof:[String:Any] = ["context":outgoing ? "outgoing":"incoming","appearance":dark ? "dark":"light","phase":phase,
                        "actual_player_state":String(describing:player.state),"actual_active_word":player.activeWord?.text ?? "", "supplied_translation":"water → agua", "new_language_or_pronunciation_certification":false]
                    let data = XCTAttachment(data:(try? JSONSerialization.data(withJSONObject:proof,options:.sortedKeys)) ?? Data(),uniformTypeIdentifier:"public.json")
                    data.name = label+"-"+phase+"-proof";data.lifetime = .keepAlways;add(data)
                }
                snapshot("practice")
                player.start(message:label,spans:[("agua, agua","es")],pauseBetweenSpans:true)
                let deadline = ContinuousClock.now.advanced(by: .seconds(15))
                var highlighted = [Int]()
                while ContinuousClock.now < deadline && player.activeMessage != nil {
                    host.view.layoutIfNeeded()
                    if player.state == .playing, let active = player.activeWord {
                        let words = attachments()
                        for (index, word) in words.enumerated() where word.playingRange != nil {
                            // The two occurrences have the same text, but distinct
                            // positions in both the audio and the displayed message.
                            let expectedOffset = index == 0 ? 0 : 6
                            guard active.range.location == expectedOffset else { continue }
                            XCTAssertEqual(word.displayed, "agua")
                            XCTAssertEqual(word.playingRange, NSRange(location: 0, length: 4))
                            if !highlighted.contains(index) {
                                highlighted.append(index)
                                snapshot("actual-playing-word-\(index + 1)")
                            }
                        }
                    }
                    try await Task.sleep(for: .milliseconds(10))
                }
                XCTAssertEqual(highlighted, [0, 1], "Both occurrences must highlight in playback order")
                player.stop()
            }
        }
    }
    private final class Transport:ChatTransport {
        let account:UUID
        init(_ account:UUID) { self.account = account }
        func request<T:Decodable>(_ method:String,_ path:String,body:Data?,device:DeviceCredential?,query:[String:String],as type:T.Type) async throws -> T {
            let value:[String:Any]
            switch path {
            case "/v1/me":value = ["id":account.uuidString,"username":"notify_qa","display_name":"Notification QA"]
            case "/v1/devices":
                let input = try XCTUnwrap(JSONSerialization.jsonObject(with:XCTUnwrap(body)) as? [String:Any]); value = ["id":input["device_id"]!,"active":true]
            case "/v1/keys":value = ["revision":1,"remaining":20]
            case "/v1/messages/pending":value = ["messages":[],"next_cursor":NSNull()]
            default:throw ServiceFailure(status:500,code:"unexpected_notification_fixture_request")
            }
            return try JSONDecoder().decode(type,from:JSONSerialization.data(withJSONObject:value))
        }
    }
    func testInvitationClaimIsAtomicDurableAndScopedToEncryptedAccount() async throws {
        let one = UUID(),two = UUID(),userOne = "notification-"+UUID().uuidString,userTwo = "notification-"+UUID().uuidString
        var sessions:[ChatSession] = []
        defer {
            for session in sessions { try? session.close() }
            for (id,user) in [(one,userOne),(two,userTwo)] {
                KeychainStore.delete(account:"profile-"+user); KeychainStore.delete(account:"messages-"+id.uuidString.lowercased())
                let root = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("Messages").appendingPathComponent(id.uuidString.lowercased())
                try? FileManager.default.removeItem(at:root)
            }
        }
        let api = Transport(one),first = try ChatSession(api:api,userID:userOne)
        sessions.append(first)
        XCTAssertFalse(first.claimReplyNotificationInvitation(),"No profile/vault means no invitation")
        await first.start(); XCTAssertTrue(first.ready)
        XCTAssertTrue(first.claimReplyNotificationInvitation()); XCTAssertFalse(first.claimReplyNotificationInvitation())
        try first.close()
        let reopened = try ChatSession(api:api,userID:userOne)
        sessions.append(reopened)
        XCTAssertFalse(reopened.claimReplyNotificationInvitation()); try reopened.close()
        let other = try ChatSession(api:Transport(two),userID:userTwo)
        sessions.append(other)
        await other.start(); XCTAssertTrue(other.claimReplyNotificationInvitation()); try other.close()

    }
}
