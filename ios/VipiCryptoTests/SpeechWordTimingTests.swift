import XCTest
import AVFoundation
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
