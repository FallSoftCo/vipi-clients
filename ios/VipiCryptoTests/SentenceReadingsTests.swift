import XCTest
import Foundation
import VipiCore
@testable import Vipi

final class SentenceReadingsTests: XCTestCase {
    func testLiveNonRomanFullTextReadingsDoNotNeedAuthoredSentenceMatches() throws {
        for (language,text) in [("zh","桌子旁边有三本新书。"),("ja","駅の近くで新しい本を読みます。"),("ko","오늘 새로운 책을 읽어요."),("ar","أين محطة القطار الجديدة؟")] {
            let result = try XCTUnwrap(FullSentenceReadings.resolve(text,language:language),language)
            XCTAssertFalse(result.text.isEmpty); XCTAssertEqual(result.provenance,.localTransliteration)
            XCTAssertNotEqual(result.text,text,language)
            XCTAssertNotNil(result.text.range(of:#"\p{Latin}"#,options:.regularExpression),language)
        }
        XCTAssertNil(FullSentenceReadings.resolve("Already Latin",language:"en"))
    }
    func testChineseLiveGuideKeepsMarkedTonesAndSourceIndependentAudioText() throws {
        let native = "你好，明天见！"
        let value = try XCTUnwrap(FullSentenceReadings.resolve(native,language:"zh"))
        XCTAssertTrue(value.text.contains { "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ".contains($0) })
        XCTAssertEqual(native,"你好，明天见！")
    }
    func testLongJapaneseKeepsNativeLexicalReadingAndExactUnicodeTail() throws {
        // More than the retired 16K UTF16 cap. No Han-Latin fallback is allowed.
        let original = String(repeating:"明日は学校に行きます。",count:1500) + " café\u{301} 👩🏽‍💻 END"
        let native = JapaneseFullReading.resolve(original)
        XCTAssertTrue(native.issues.isEmpty,String(describing:native.issues))
        let reading = try XCTUnwrap(native.reading)
        XCTAssertEqual(try XCTUnwrap(FullSentenceReadings.resolve(original,language:"ja")).text,reading)
        XCTAssertTrue(reading.hasSuffix("café\u{301} 👩🏽‍💻 END"))
        XCTAssertTrue(native.pieces.map(\.source).joined().utf8.elementsEqual(original.utf8))
        let observation:[String:Any] = ["original_utf8_bytes":original.utf8.count,
            "reading_utf8_bytes":reading.utf8.count,"reading_prefix":String(reading.prefix(240)),
            "tokens":native.tokens.prefix(12).map{["source":$0.source,"start":$0.startUTF16,"end":$0.endUTF16,"raw_latin":$0.rawLatin ?? ""] as [String:Any]}]
        let attachment = XCTAttachment(data:try JSONSerialization.data(withJSONObject:observation,options:[.sortedKeys]),uniformTypeIdentifier:"public.json")
        attachment.name = "long-japanese-actual-native-token-prefix"; attachment.lifetime = .keepAlways; add(attachment)
        let first = try XCTUnwrap(native.tokens.first)
        XCTAssertEqual(first.source,"明日"); XCTAssertEqual(first.startUTF16,0); XCTAssertEqual(first.endUTF16,2)
        // Kyoto University's Japanese course independently lists あした/あす/みょうにち:
        // https://www.samidori.k.kyoto-u.ac.jp/study/exam?id=153
        let acceptedReadings:Set<String> = ["ashita","asu","myounichi","myōnichi"]
        XCTAssertTrue(acceptedReadings.contains(try XCTUnwrap(first.rawLatin)),"Native 明日 reading must be Japanese, without requiring a single valid variant")
        let beginning = Array(native.tokens.prefix(6))
        XCTAssertEqual(beginning.count,6)
        XCTAssertTrue(beginning.allSatisfy{$0.rawLatin?.isEmpty == false})
        XCTAssertEqual(native.tokens.first{$0.source == "学校"}?.rawLatin,"gakkou")
        let composed = beginning.compactMap(\.rawLatin).joined(separator:" ") + "。"
        XCTAssertTrue(reading.hasPrefix(composed),"Composition must retain the actual native Japanese tokens")
    }

    func testActualArabicNativeGuideAcceptsPhoneticModifierLetters() throws {
        let original = "عربي"
        let actualNative = try XCTUnwrap(original.applyingTransform(.toLatin, reverse: false))
        let guide = try XCTUnwrap(FullSentenceReadings.resolve(original, language: "ar"))
        XCTAssertEqual(guide.text, actualNative)
        XCTAssertFalse(FullReadingRequirement.needsReading(guide.text))
        let state = FullSentenceReadings.state(text: original, language: "ar", reading: guide)
        XCTAssertEqual(state.status, .available)
        XCTAssertNil(state.failure)
        let record = XCTAttachment(string: actualNative)
        record.name = "actual-native-Arabic-guide-with-phonetic-modifiers"
        record.lifetime = .keepAlways
        add(record)
    }

}
