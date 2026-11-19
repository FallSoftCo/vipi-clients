import XCTest
import AVFoundation
import UIKit
import VipiCore
@testable import Vipi

/// Production playback owner; controlled SDK preparation failure and genuine
/// in-process system notifications. Translation completions are supplied, not
/// claimed as native model execution. Successful preparation uses real TTS.
@MainActor final class ChatAutoplayTests: XCTestCase {
    private enum Failure: Error { case deadline, preparation }
    @MainActor private final class PreparationGate {
        var continuation: CheckedContinuation<Void,Never>?
        func waitThenFail() async throws {
            await withCheckedContinuation { continuation = $0 }
            throw Failure.preparation
        }
        func release() { let value = continuation; continuation = nil; value?.resume() }
    }
    private func wait(_ reason:String,seconds:Int = 5,until predicate:()->Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by:.seconds(seconds))
        while !predicate() && ContinuousClock.now < deadline { try await Task.sleep(for:.milliseconds(10)) }
        guard predicate() else { XCTFail(reason); throw Failure.deadline }
    }
    private func model() async -> ConversationImmersion {
        let value = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "fr"})
        await value.configure(pair:.init(source:"fr",target:"en")); return value
    }
    func testIdleVoicePreparationFailureTurnsAutoplayOffAndKeepsNonmodalHelp() async throws {
        let owner = await model(), speech = SpeechPlayback(), autoplay = ChatAutoplay(), gate = PreparationGate()
        defer { gate.release(); autoplay.stop(speech:speech); speech.close(); owner.close() }
        speech.qualificationPrepare = { try await gate.waitThenFail() }
        speech.prepare(source:"en",target:"en",warmups:[:])
        try await wait("Real SDK preparation seam must be pending",until:{gate.continuation != nil})
        autoplay.toggle(snapshot:[],immersion:owner,speech:speech)
        XCTAssertTrue(autoplay.enabled); XCTAssertEqual(speech.state,.preparing)
        gate.release()
        try await wait("Voice failure must leave Preparing",until:{speech.state == .unavailable})
        try await wait("Autoplay must turn OFF even with no new message",until:{!autoplay.enabled})
        XCTAssertNotNil(autoplay.voiceNotice)
        XCTAssertNil(speech.activeMessage)
    }
    func testOldOutputRouteStopsOwnerAndLateTranslationCannotRestartPlayback() async throws {
        let owner = await model(), speech = SpeechPlayback(), autoplay = ChatAutoplay(), gate = PreparationGate()
        defer { gate.release(); autoplay.stop(speech:speech); speech.close(); owner.close() }
        speech.qualificationPrepare = { try await gate.waitThenFail() }
        speech.prepare(source:"en",target:"en",warmups:[:])
        try await wait("Notification observer must be registered",until:{gate.continuation != nil})
        autoplay.toggle(snapshot:[],immersion:owner,speech:speech)
        autoplay.arrived(.init(id:"arrival",text:"Un nouveau message."),immersion:owner,speech:speech,foreground:true)
        try await wait("Production translation request is pending",until:{owner.request != nil})
        let request = try XCTUnwrap(owner.request)
        NotificationCenter.default.post(name:AVAudioSession.routeChangeNotification,object:nil,
            userInfo:[AVAudioSessionRouteChangeReasonKey:AVAudioSession.RouteChangeReason.newDeviceAvailable.rawValue])
        try await Task.sleep(for:.milliseconds(30))
        XCTAssertTrue(autoplay.enabled,"A newly available route alone does not interrupt current playback")
        NotificationCenter.default.post(name:AVAudioSession.routeChangeNotification,object:nil,
            userInfo:[AVAudioSessionRouteChangeReasonKey:AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue])
        try await wait("Unplugging output must drain autoplay rather than resume on the speaker",until:{!autoplay.enabled})
        await owner.finish(request,translation:"A new message.")
        try await wait("Translation belongs to account, independent of stopped audio",until:{owner.translation(for:owner.identity(messageID:"arrival",text:"Un nouveau message.")) != nil})
        XCTAssertEqual(speech.playbackSerial,0); XCTAssertNil(speech.activeMessage)
    }
    func testSystemInterruptionTurnsOwnerOffWithoutQueuedMessages() async throws {
        let owner = await model(), speech = SpeechPlayback(), autoplay = ChatAutoplay(), gate = PreparationGate()
        defer { gate.release(); autoplay.stop(speech:speech); speech.close(); owner.close() }
        speech.qualificationPrepare = { try await gate.waitThenFail() }
        speech.prepare(source:"en",target:"en",warmups:[:])
        try await wait("Native interruption observer ready",until:{gate.continuation != nil})
        autoplay.toggle(snapshot:[],immersion:owner,speech:speech)
        NotificationCenter.default.post(name:AVAudioSession.interruptionNotification,object:nil,
            userInfo:[AVAudioSessionInterruptionTypeKey:AVAudioSession.InterruptionType.began.rawValue])
        try await wait("An OS interruption must stop the conversation owner",until:{!autoplay.enabled})
    }
    func testHeaderOffCancelsManualPendingIntentWithoutCancellingAccountTranslation() async throws {
        let owner = await model(), speech = SpeechPlayback(), autoplay = ChatAutoplay()
        defer { autoplay.stop(speech:speech); speech.close(); owner.close() }
        speech.prepare(source:"en",target:"en",warmups:["en":"Hello."])
        try await wait("Actual native practice voice must prepare",until:{speech.state == .ready || speech.state == .unavailable})
        XCTAssertEqual(speech.state,.ready)
        let identity = owner.identity(messageID:"manual-pending",text:"Un message en attente.")
        autoplay.manual(identity,immersion:owner,speech:speech,onModels:{_ in XCTFail("Models controlled installed")},onVoiceHelp:{XCTFail("Actual prepared native voice required")})
        try await wait("Translation must remain pending before header OFF",until:{owner.request != nil})
        let request = try XCTUnwrap(owner.request)
        autoplay.stop(speech:speech)
        await owner.finish(request,translation:"A pending message.")
        try await wait("Shared translation can complete after playback cancellation",until:{owner.translation(for:identity) != nil})
        try await Task.sleep(for:.milliseconds(80))
        XCTAssertFalse(autoplay.enabled); XCTAssertNil(speech.activeMessage); XCTAssertEqual(speech.playbackSerial,0)
    }
    @MainActor private final class RecordingPair: PreparedSpeechPair {
        let native: LocalSpeechPair, root:URL
        var requests:[String] = [], failed:[String] = []
        var failText:String?
        init(root:URL) throws { self.root = root; native = try LocalSpeechPair(source:"en",target:"en",root:root) }
        func prepare(warmups:[String:String]) async throws { try await native.prepare(warmups:warmups) }
        func render(_ spans:[(text:String,language:String)]) async throws -> RenderedSpeech {
            let text = spans.map(\.text).joined(); requests.append(text)
            if failText == text {
                // Real native file I/O failure in an exclusively test-owned root.
                try FileManager.default.removeItem(at:root)
                defer { try? FileManager.default.createDirectory(at:root,withIntermediateDirectories:true) }
                do { return try await native.render(spans) }
                catch { failed.append(text); throw error }
            }
            return try await native.render(spans)
        }
        func stop() { native.stop() }
    }
    private func nativeSpeech() throws -> (SpeechPlayback,RecordingPair) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("autoplay-native-" + UUID().uuidString)
        let pair = try RecordingPair(root:root)
        addTeardownBlock { try? FileManager.default.removeItem(at:root) }
        let speech = SpeechPlayback(pairFactory:{_,_,_ in pair})
        speech.prepare(source:"en",target:"en",warmups:["en":"Hello."])
        return (speech,pair)
    }
    private func immediateModel() async -> ConversationImmersion {
        let owner = ConversationImmersion(modelStatus:{_ in .installed},identify:{_ in "fr"},nativeTranslation:{text,_ in text})
        await owner.configure(pair:.init(source:"fr",target:"en")); return owner
    }
    func testNewDurableFIFOIgnoresDuplicateAndHistoryThenCompletesActualNativePlayback() async throws {
        let owner = await immediateModel(), (speech,pair) = try nativeSpeech(), autoplay = ChatAutoplay()
        defer { autoplay.stop(speech:speech); speech.close(); owner.close() }
        try await wait("Actual native voice prepared",until:{speech.state == .ready || speech.state == .unavailable})
        XCTAssertEqual(speech.state,.ready)
        autoplay.toggle(snapshot:[.init(id:"history",text:"Never play history.")],immersion:owner,speech:speech)
        for message in [ChatAutoplay.Message(id:"one",text:"First message."),.init(id:"one",text:"First message."),.init(id:"two",text:"Second message.")] {
            autoplay.arrived(message,immersion:owner,speech:speech,foreground:true)
        }
        try await wait("Both actual native audio completions",seconds:25,until:{speech.lastCompletion?.message == "two" && speech.activeMessage == nil})
        XCTAssertEqual(pair.requests,["First message.","Second message."])
        XCTAssertEqual(speech.playbackSerial,2); XCTAssertTrue(speech.lastCompletion?.succeeded == true)
        XCTAssertTrue(autoplay.enabled); XCTAssertNil(autoplay.failure(for:"one")); XCTAssertNil(autoplay.failure(for:"two"))
    }
    func testManualQueuedItemPlaysOnceThenRemainingFIFOResumes() async throws {
        let owner = await immediateModel(), (speech,pair) = try nativeSpeech(), autoplay = ChatAutoplay()
        defer { autoplay.stop(speech:speech); speech.close(); owner.close() }
        try await wait("Actual native voice prepared",until:{speech.state == .ready})
        autoplay.toggle(snapshot:[],immersion:owner,speech:speech)
        let first = "First message continues for a moment before manual interruption."
        for message in [ChatAutoplay.Message(id:"one",text:first),.init(id:"two",text:"Selected second."),.init(id:"three",text:"Remaining third.")] {
            autoplay.arrived(message,immersion:owner,speech:speech,foreground:true)
        }
        try await wait("First real player started",until:{speech.activeMessage == "one" && speech.state == .playing})
        autoplay.manual(owner.identity(messageID:"two",text:"Selected second."),immersion:owner,speech:speech,
            onModels:{_ in XCTFail("Controlled installed models")},onVoiceHelp:{XCTFail("Actual voice prepared")})
        try await wait("Selected item and remaining item finish",seconds:25,until:{speech.lastCompletion?.message == "three" && speech.activeMessage == nil})
        XCTAssertEqual(pair.requests,[first,"Selected second.","Remaining third."])
        XCTAssertEqual(speech.playbackSerial,3); XCTAssertTrue(speech.lastCompletion?.succeeded == true)
    }
    func testNativeRenderFailureKeepsRowRetryableWhileNextNewItemPlays() async throws {
        let owner = await immediateModel(), (speech,pair) = try nativeSpeech(), autoplay = ChatAutoplay()
        defer { autoplay.stop(speech:speech); speech.close(); owner.close() }
        try await wait("Actual native voice prepared",until:{speech.state == .ready})
        pair.failText = "Failed native file."
        autoplay.toggle(snapshot:[],immersion:owner,speech:speech)
        autoplay.arrived(.init(id:"failed",text:"Failed native file."),immersion:owner,speech:speech,foreground:true)
        autoplay.arrived(.init(id:"next",text:"Next message."),immersion:owner,speech:speech,foreground:true)
        try await wait("Later item survives the native I/O failure",seconds:25,until:{speech.lastCompletion?.message == "next" && speech.activeMessage == nil})
        XCTAssertEqual(pair.failed,["Failed native file."]); XCTAssertNotNil(autoplay.failure(for:"failed"))
        XCTAssertNil(autoplay.failure(for:"next")); XCTAssertTrue(autoplay.enabled)
        pair.failText = nil
        autoplay.manual(owner.identity(messageID:"failed",text:"Failed native file."),immersion:owner,speech:speech,
            onModels:{_ in XCTFail("Installed")},onVoiceHelp:{XCTFail("Prepared")})
        try await wait("Only successful manual retry clears its row failure",seconds:20,until:{autoplay.failure(for:"failed") == nil && speech.lastCompletion?.message == "failed" && speech.activeMessage == nil})
        XCTAssertTrue(speech.lastCompletion?.succeeded == true)
    }
    func testLongPunctuationCannotAbortNativeAudioBeforePronounceableTail() async throws {
        let (speech,pair) = try nativeSpeech()
        defer { speech.close() }
        try await wait("Actual native voice prepared",until:{speech.state == .ready})
        let original = "Beginning. " + String(repeating:". ",count:400) + "Final audible tail."
        speech.start(message:"punctuation-tail",spans:[(original,"en")])
        try await wait("Actual player reaches and completes tail",seconds:25,until:{speech.lastCompletion?.message == "punctuation-tail"})
        XCTAssertTrue(speech.lastCompletion?.succeeded == true)
        XCTAssertTrue(pair.requests.last?.contains("Final audible tail.") == true)
        XCTAssertTrue(pair.requests.allSatisfy{SpeechChunks.hasSpokenContent($0)})
    }

    func testCopyEntryCancelsOffManualPendingTranslationAndReadingSurfaceIntent() async throws {
        let owner = await model(), (speech,pair) = try nativeSpeech(), autoplay = ChatAutoplay()
        let suite = "CopyPendingTranslation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName:suite))
        let reading = ChatReadingState(defaults:defaults), copy = CopyOriginalContext(editorID:"message-input")
        defer { defaults.removePersistentDomain(forName:suite); autoplay.stop(speech:speech); speech.close(); owner.close() }
        try await wait("Real native voice prepared before pending translation",until:{speech.state == .ready})
        let identity = owner.identity(messageID:"copy-pending-translation",text:"Un message en attente.")
        reading.register(.init(identity:identity,frame:.zero,activate:{_ in false}))
        reading.activate(identity) // Actual fallback surface pending intent.
        autoplay.manual(identity,immersion:owner,speech:speech,onModels:{_ in XCTFail("Installed")},onVoiceHelp:{XCTFail("Prepared")})
        try await wait("Actual production translation request is held",until:{owner.request != nil})
        let request = try XCTUnwrap(owner.request)
        XCTAssertFalse(autoplay.enabled); XCTAssertEqual(speech.playbackSerial,0)
        // The header action uses this exact entry, not an extracted lookalike.
        // No UIKit window is required to prove cancellation before presentation.
        copy.open([],autoplay:autoplay,speech:speech,reading:reading)
        await owner.finish(request,translation:"A pending message.")
        try await wait("Account-owned translation still completes",until:{owner.translation(for:identity) != nil})
        var lateReadingActivation = false
        reading.register(.init(identity:identity,frame:.zero,activate:{_ in lateReadingActivation = true; return true}))
        XCTAssertFalse(lateReadingActivation,"Copy must clear the reading surface's deferred activation")
        try await Task.sleep(for:.milliseconds(80)) // Settle after the explicit request completion, not a pending detector.
        XCTAssertFalse(autoplay.enabled); XCTAssertNil(speech.activeMessage)
        XCTAssertEqual(speech.playbackSerial,0); XCTAssertTrue(pair.requests.isEmpty)
    }
    @MainActor private final class CopyPreparationGate {
        var continuation:CheckedContinuation<Void,Never>?
        func wait() async { await withCheckedContinuation { continuation = $0 } }
        func release() { let held = continuation; continuation = nil; held?.resume() }
    }
    @MainActor private final class CopyGatedPair: PreparedSpeechPair {
        let native:RecordingPair, gate:CopyPreparationGate
        init(native:RecordingPair,gate:CopyPreparationGate) { self.native = native; self.gate = gate }
        func prepare(warmups:[String:String]) async throws { await gate.wait(); try Task.checkCancellation(); try await native.prepare(warmups:warmups) }
        func render(_ spans:[(text:String,language:String)]) async throws->RenderedSpeech { try await native.render(spans) }
        func stop() { native.stop() }
    }
    func testCopyEntryCancelsOffManualPendingRealVoicePreparationWithoutLateRender() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("copy-native-preparation-" + UUID().uuidString)
        let pair = try RecordingPair(root:root), gate = CopyPreparationGate()
        let speech = SpeechPlayback(pairFactory:{_,_,_ in CopyGatedPair(native:pair,gate:gate)})
        let owner = await immediateModel(), autoplay = ChatAutoplay()
        let suite = "CopyPendingVoice-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName:suite)), reading = ChatReadingState(defaults:defaults)
        let copy = CopyOriginalContext(editorID:"message-input")
        defer { gate.release(); defaults.removePersistentDomain(forName:suite); autoplay.stop(speech:speech); speech.close(); owner.close(); try? FileManager.default.removeItem(at:root) }
        speech.prepare(source:"en",target:"en",warmups:["en":"Hello."])
        try await wait("Actual voice preparation boundary is held",until:{gate.continuation != nil})
        let identity = owner.identity(messageID:"copy-pending-voice",text:"A prepared practice message.")
        autoplay.manual(identity,immersion:owner,speech:speech,onModels:{_ in XCTFail("Installed")},onVoiceHelp:{XCTFail("Actual preparation must succeed")})
        try await wait("Translation complete while real voice preparation remains held",until:{owner.translation(for:identity) != nil})
        XCTAssertEqual(speech.state,.preparing); XCTAssertFalse(autoplay.enabled)
        copy.open([],autoplay:autoplay,speech:speech,reading:reading)
        gate.release()
        try await wait("Gated real native voice genuinely prepares",until:{speech.state == .ready || speech.state == .unavailable})
        XCTAssertEqual(speech.state,.ready)
        try await Task.sleep(for:.milliseconds(80)) // Only after the explicit preparation gate and real completion.
        XCTAssertEqual(speech.playbackSerial,0); XCTAssertNil(speech.activeMessage)
        XCTAssertTrue(pair.requests.isEmpty,"Cancelled manual work must not render after voices become ready")
    }

    func testNewNonTouchMenuEventReplacesCancelledMenuSelectionAndScrollSnapshot() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first{$0.activationState == .foregroundActive})
        let window = UIWindow(windowScene:scene), controller = UIViewController()
        window.rootViewController = controller; window.frame = scene.coordinateSpace.bounds
        window.isHidden = false
        let copy = CopyOriginalContext(editorID:"copy-regression-editor")
        defer { copy.abandon(); window.isHidden = true; window.rootViewController = nil }
        let anchor = UIView(frame:CGRect(x:0,y:0,width:1,height:1))
        let editor = UITextView(frame:CGRect(x:20,y:200,width:260,height:80))
        editor.accessibilityIdentifier = "copy-regression-editor"; editor.text = "alpha bravo charlie delta"
        editor.selectedRange = NSRange(location:0,length:5)
        let timeline = UIScrollView(frame:CGRect(x:20,y:300,width:260,height:180))
        timeline.accessibilityIdentifier = "conversation-timeline"; timeline.contentSize = CGSize(width:260,height:2000)
        for view in [anchor,editor,timeline] { controller.view.addSubview(view) }
        copy.attachAnchor(anchor)
        let button = UIButton(type:.system); button.frame = CGRect(x:20,y:80,width:44,height:44)
        button.menu = UIMenu(children:[UIAction(title:"Copy original message",handler:{_ in})])
        button.showsMenuAsPrimaryAction = true
        let probe = CopyOriginalMenuCapture.Probe(frame:button.bounds)
        probe.setOwner(copy); button.addSubview(probe); controller.view.addSubview(button)
        controller.view.layoutIfNeeded(); probe.layoutIfNeeded()
        XCTAssertTrue(copy.menuSignalAttached,"Public menu control must actually bind the production bridge")
        // This is a real native semantic control event without a UITouch, not
        // a claim that a hardware keyboard or visible menu was exercised.
        button.sendActions(for:.menuActionTriggered)
        XCTAssertEqual(copy.menuGeneration,1); XCTAssertEqual(copy.preparedSelectionForQualification,[0,5])
        button.contextMenuInteraction?.dismissMenu()
        // A cancelled menu previously left this saved snapshot behind. Keep it
        // deliberately, then edit real UIKit state before another activation.
        editor.text = "new original selected range"; editor.selectedRange = NSRange(location:4,length:8)
        timeline.contentOffset = CGPoint(x:0,y:77)
        XCTAssertEqual(copy.preparedSelectionForQualification,[0,5],"Establish the retained-old-snapshot regression condition")
        button.sendActions(for:.menuActionTriggered)
        XCTAssertEqual(copy.menuGeneration,2)
        XCTAssertEqual(copy.captureStage,"native-menu-before-presentation")
        XCTAssertEqual(copy.preparedSelectionForQualification,[4,12])
        XCTAssertEqual(try XCTUnwrap(copy.preparedTimelineOffsetForQualification).y,77,accuracy:0.5)
        // A bare programmatic Copy is not a Menu action. It must capture now,
        // even if a cancelled/native menu previously left prepared state.
        editor.selectedRange = NSRange(location:8,length:6)
        let autoplay = ChatAutoplay(), speech = SpeechPlayback()
        copy.open([.init(id:"synthetic",original:"Synthetic original")],autoplay:autoplay,speech:speech,reading:ChatReadingState())
        XCTAssertEqual(copy.captureStage,"action-fallback")
        XCTAssertEqual(copy.activeSelectionForQualification,[8,14])
        copy.abandon(); speech.close()
        // Public bridge detachment must also invalidate any prepared snapshot.
        probe.removeFromSuperview()
        XCTAssertFalse(copy.menuSignalAttached); XCTAssertTrue(copy.preparedSelectionForQualification.isEmpty)
    }

}
