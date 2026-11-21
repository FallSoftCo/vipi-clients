import XCTest
import AVFoundation
import SwiftUI
import VipiCore
@testable import Vipi

@MainActor final class SpeechWordTimingTests:XCTestCase {
    func testActualNativeMarkersSurviveResamplingJoinAndCacheForEnglishAndSwahili() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("native-word-"+UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let pair = try LocalSpeechPair(source:"en",target:"sw",root:root)
        defer { pair.stop() }
        try await pair.prepare(warmups:["en":"Hello.","sw":"Habari."])
        let spans = [(text:"Water and bread.",language:"en"),(text:"Habari rafiki yangu.",language:"sw")]
        let first = try await pair.render(spans),cached = try await pair.render(spans)
        XCTAssertEqual(first.marks.map(\.start),cached.marks.map(\.start)); XCTAssertEqual(first.marks.map(\.byteSampleOffset),cached.marks.map(\.byteSampleOffset))
        XCTAssertGreaterThanOrEqual(first.marks.count,6)
        let text = spans.map(\.text).joined() as NSString,file = try AVAudioFile(forReading:first.file)
        let bytesPerFrame = Int(file.processingFormat.streamDescription.pointee.mBytesPerFrame)
        for mark in first.marks {
            XCTAssertGreaterThan(mark.length,0); XCTAssertLessThanOrEqual(mark.start+mark.length,text.length)
            XCTAssertGreaterThanOrEqual(mark.byteSampleOffset,0); XCTAssertLessThan(mark.byteSampleOffset/bytesPerFrame,Int(file.length))
        }
        XCTAssertTrue(first.marks.contains{ text.substring(with:NSRange(location:$0.start,length:$0.length)).lowercased().contains("water") })
        XCTAssertTrue(first.marks.contains{ text.substring(with:NSRange(location:$0.start,length:$0.length)).lowercased().contains("rafiki") })
    }
    func testMissingAndIncompleteMarksPreserveContinuousNativeSpeech() async throws {
        let text = "Don't forget, we're leaving soon. Shall we meet by the window?"
        for retained in [0,1] {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent("phrase-geometry-"+UUID().uuidString)
            defer { try? FileManager.default.removeItem(at:root) }
            let pair = try LocalSpeechPair(source:"en",target:"en",root:root)
            defer { pair.stop() }
            try await pair.prepare(warmups:["en":"Hello."])
            pair.qualificationRetainNativeMarkers = retained
            let audio = try await pair.render([(text,"en")])
            XCTAssertTrue(audio.marks.isEmpty)
            XCTAssertTrue(audio.boundaryFrames.isEmpty,"Native sentence audio is never spliced at words")
            XCTAssertGreaterThan(audio.milliseconds,1000)
            let cached = try await pair.render([(text,"en")])
            XCTAssertEqual(cached.file,audio.file)
            XCTAssertTrue(cached.marks.isEmpty)
            let single = try await pair.render([("Water!","en")])
            XCTAssertEqual(single.marks.count,1)
            XCTAssertEqual(single.marks.first?.start,0)
            XCTAssertEqual(single.marks.first?.length,5)
            if retained == 0 {
                XCTAssertEqual(single.marks.first?.byteSampleOffset,0)
                XCTAssertEqual(single.marks.first?.source,"measured_single_word_pcm")
            }
        }
    }
    func testPlayerSampleClockHighlightsActualWordsAndClearsOnStopAndReplacement() async throws {
        let player = SpeechPlayback(); defer{player.close()}
        player.prepare(source:"en",target:"en",warmups:["en":"Hello."])
        let ready = ContinuousClock.now.advanced(by:.seconds(30))
        while player.state != .ready && ContinuousClock.now < ready { try await Task.sleep(for:.milliseconds(20)) }
        XCTAssertEqual(player.state,.ready)
        player.start(message:"native-word-clock",spans:[("Water bread coffee.","en")])
        var words = Set<String>(); let deadline = ContinuousClock.now.advanced(by:.seconds(20))
        while player.activeMessage != nil && ContinuousClock.now < deadline {
            if let word = player.activeWord { words.insert(word.text.lowercased()) }
            try await Task.sleep(for:.milliseconds(10))
        }
        XCTAssertTrue(words.contains("water")); XCTAssertTrue(words.contains("bread")); XCTAssertTrue(words.contains("coffee"))
        XCTAssertNil(player.activeWord); XCTAssertTrue(player.lastCompletion?.succeeded == true)
        player.start(message:"replace",spans:[("Water bread coffee.","en")]); player.stop()
        XCTAssertNil(player.activeWord); XCTAssertNil(player.activeMessage)
        try await Task.sleep(for:.milliseconds(200)); XCTAssertNil(player.activeWord)
    }
    func testActualPlayerWordHighlightRendersInReadingAndScriptAndCancelsOnHold() async throws {
        let player = SpeechPlayback(); defer { player.close() }
        player.prepare(source:"zh",target:"zh",warmups:["zh":"你好。"])
        let deadline = ContinuousClock.now.advanced(by:.seconds(30))
        while player.state != .ready && ContinuousClock.now < deadline { try await Task.sleep(for:.milliseconds(20)) }
        XCTAssertEqual(player.state,.ready)
        let text = "明天下班后我们能一起喝咖啡吗？",reading = try XCTUnwrap(FullSentenceReadings.resolve(text,language:"zh")?.text)
        let controls = ChatReadingState(),value = FullMessageTranslation(original:"Can we have coffee after work tomorrow?",practiceText:text,meaningText:"Can we have coffee after work tomorrow?",inputLanguage:"en",practiceLanguage:"zh",meaningLanguage:"en")
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap{$0 as? UIWindowScene}.first)
        let previous = scene.windows.first{$0.isKeyWindow},window = UIWindow(windowScene:scene)
        window.frame = scene.coordinateSpace.bounds
        let host = UIHostingController(rootView:ImmersionBubble(result:value.presentation,speech:player,sourceLanguage:"en",targetLanguage:"zh",messageID:"real-word-highlight",fullReading:reading,reading:controls).padding(24))
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { player.stop(); window.rootViewController = nil; window.isHidden = true; previous?.makeKeyAndVisible() }
        func find(_ view:UIView) -> ImmersionTextContainer? {
            if let value = view as? ImmersionTextContainer { return value }
            return view.subviews.lazy.compactMap(find).first
        }
        player.start(message:"real-word-highlight",spans:[(text,"zh")])
        func capture(_ name:String,expected:String) async throws {
            let limit = ContinuousClock.now.advanced(by:.seconds(15))
            while ContinuousClock.now < limit {
                host.view.layoutIfNeeded()
                if let view = find(host.view)?.textView,view.attributedText.string == expected,player.activeWord != nil {
                    var ranges:[NSRange] = []
                    view.attributedText.enumerateAttribute(.backgroundColor,in:NSRange(location:0,length:view.attributedText.length)) { value,range,_ in if value != nil { ranges.append(range) } }
                    if let range = ranges.first {
                        XCTAssertGreaterThan(range.length,0); XCTAssertLessThan(range.length,expected.utf16.count)
                        let image = UIGraphicsImageRenderer(size:window.bounds.size).image{_ in window.drawHierarchy(in:window.bounds,afterScreenUpdates:true)}
                        let attachment = XCTAttachment(image:image); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
                        return
                    }
                }
                try await Task.sleep(for:.milliseconds(10))
            }
            XCTFail("Native sample-clock word highlight must actually reach TextKit: "+name)
        }
        try await capture("native-audio-word-in-default-reading",expected:reading)
        controls.toggleScript()
        try await capture("native-audio-word-in-native-script",expected:text)
        controls.hold(at:.zero)
        let stopped = ContinuousClock.now.advanced(by:.seconds(2))
        while player.activeMessage != nil && ContinuousClock.now < stopped { try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertNil(player.activeMessage); XCTAssertNil(player.activeWord)
    }
    func testCompleteNativeWordMapsToCompleteReaderPieces() throws {
        for (language,text,word) in [("zh","水和面包","面包"),("ja","明日はコーヒーを飲みましょう。","コーヒー"),("ko","내일 커피를 마셔요.","커피"),("ar","الماء والخبز","والخبز")] {
            let reading = try XCTUnwrap(FullSentenceReadings.resolve(text,language:language)?.text)
            let native = (text as NSString).range(of:word)
            let alignment = FullSentenceReadings.alignment(text:text,reading:reading,language:language)
            let mapped = try XCTUnwrap(FullSentenceReadings.displayedRange(native,text:text,reading:reading,alignment:alignment),language)
            XCTAssertGreaterThan(mapped.length,1); XCTAssertLessThanOrEqual(NSMaxRange(mapped),reading.utf16.count)
        }
    }
}
