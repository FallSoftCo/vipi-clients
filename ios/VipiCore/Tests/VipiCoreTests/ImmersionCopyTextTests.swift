import Foundation
import XCTest
@testable import VipiCore

/// Pure logical copy/accessibility composition. These are NOT UIKit clipboard,
/// selection gesture, visual-layout or VoiceOver runtime qualification.
final class ImmersionCopyTextTests: XCTestCase {
    private typealias Run = ImmersionCopyRun

    private func pair(_ left: String, _ right: String, gap: String = "",
                      leftOriginal: Bool = false, rightOriginal: Bool = false) -> [Run] {
        var runs = [Run(text: left, slotID: 0, showsOriginal: leftOriginal)]
        if !gap.isEmpty { runs.append(Run(text: gap)) }
        runs.append(Run(text: right, slotID: 1, showsOriginal: rightOriginal))
        return runs
    }

    func testCapturedJapaneseLogicalWordsAndOriginalFaces() {
        let original = "明日、一緒に昼ご飯を食べませんか。"
        func captured(_ revealed: Set<Int>) -> [Run] {
            [Run(text: revealed.contains(0) ? "明日" : "Tomorrow", slotID: 0, showsOriginal: revealed.contains(0)),
             Run(text: "、"),
             Run(text: revealed.contains(3) ? "一緒に" : "together", slotID: 3, showsOriginal: revealed.contains(3)),
             Run(text: revealed.contains(6) ? "昼ご飯" : "lunch", slotID: 6, showsOriginal: revealed.contains(6)),
             Run(text: "を食べませんか。")]
        }
        XCTAssertEqual(ImmersionCopyText.compose(captured([])), "Tomorrow、together lunchを食べませんか。")
        XCTAssertEqual(ImmersionCopyText.compose(captured([0, 3, 6])), original)
        XCTAssertEqual(ImmersionCopyText.compose(captured([0])), "明日、together lunchを食べませんか。")
        XCTAssertEqual(ImmersionCopyText.compose(captured([3])), "Tomorrow、一緒にlunchを食べませんか。")
        XCTAssertEqual(ImmersionCopyText.compose(captured([6])), "Tomorrow、together昼ご飯を食べませんか。")
    }

    func testReadingScriptAndMixedLatinRevealPolicy() {
        XCTAssertEqual(ImmersionCopyText.compose(pair("café", "tea")), "café tea")
        XCTAssertEqual(ImmersionCopyText.compose(pair("咖啡", "茶")), "咖啡茶")
        XCTAssertEqual(ImmersionCopyText.compose(pair("甲", "tea", leftOriginal: true)), "甲tea")
        XCTAssertEqual(ImmersionCopyText.compose(pair("café", "乙", rightOriginal: true)), "café乙")
        XCTAssertEqual(ImmersionCopyText.compose(pair("甲", "乙", leftOriginal: true, rightOriginal: true)), "甲乙")
        XCTAssertEqual(ImmersionCopyText.compose(pair("hello", "world")), "hello world")
        XCTAssertEqual(ImmersionCopyText.compose(pair("a", "world", leftOriginal: true)), "a world")
        XCTAssertEqual(ImmersionCopyText.compose(pair("hello", "b", rightOriginal: true)), "hello b")
        XCTAssertEqual(ImmersionCopyText.compose(pair("a", "b", leftOriginal: true, rightOriginal: true)), "ab")
    }

    func testSourceWhitespaceAndPunctuationRemainExact() {
        for gap in [" ", "  ", "\t", "\n", "\u{00A0}", "\u{2009}", ",", "、", ".", "؟", "—", "()"] {
            XCTAssertEqual(ImmersionCopyText.compose(pair("hello", "world", gap: gap)), "hello" + gap + "world")
        }
        for (left, right) in [("hello ", "world"), ("hello", " world"), ("hello-", "world"),
                              ("hello,", "world"), ("hello", "(world)"), ("hello", "\nworld")] {
            XCTAssertEqual(ImmersionCopyText.compose(pair(left, right)), left + right)
        }
    }

    func testOnlyWholeLatinLetterAndMarkEdgeClustersGainSeparator() {
        for (left, right) in [("hello", "2"), ("2", "world"), ("v2", "world"), ("hello", "2nd"),
                              ("hello", "العربية"), ("عربي", "world"), ("hello", "中文"),
                              ("α", "world"), ("hello", "б"), ("🙂", "world"), ("hello", "🙂"),
                              ("hello", "\u{0301}word"), ("\u{0301}", "word"), ("a\u{200D}", "word")] {
            XCTAssertEqual(ImmersionCopyText.compose(pair(left, right)), left + right)
        }
        for (left, right) in [("café", "déjà"), ("cafe\u{0301}", "lunch"), ("ø", "Łódź")] {
            let result = ImmersionCopyText.compose(pair(left, right))
            XCTAssertEqual(Array(result.utf8), Array((left + " " + right).utf8))
        }
    }

    func testSelectedRunsAndPartialOriginalCodeUnitsArePreserved() {
        let selected = [Run(text: "world", slotID: 1, showsOriginal: false),
                        Run(text: "friend", slotID: 2, showsOriginal: false)]
        XCTAssertEqual(ImmersionCopyText.compose(selected), "world friend")
        XCTAssertEqual(ImmersionCopyText.compose([Run(text: "hello", slotID: 0, showsOriginal: false)]), "hello")
        XCTAssertEqual(ImmersionCopyText.compose([]), "")
        XCTAssertEqual(ImmersionCopyText.compose([Run(text: "b", slotID: 0)]), "b")
        let original = "e\u{0301}Q"
        let partial = (original as NSString).substring(with: NSRange(location: 1, length: 2))
        XCTAssertEqual(Array(ImmersionCopyText.compose([Run(text: partial)]).utf8), Array(partial.utf8))
        XCTAssertEqual(ImmersionCopyText.compose([
            Run(text: "hel", slotID: 0, showsOriginal: false),
            Run(text: "lo", slotID: 0, showsOriginal: false),
            Run(text: "world", slotID: 1, showsOriginal: false)]), "hello world")
    }

    func testLiteralProtectedTextCaseOrderAndInputValueStayUnchanged() {
        let runs = [Run(text: "e\u{0301}"), Run(text: "hello", slotID: 2, showsOriginal: false),
                    Run(text: "world", slotID: 3, showsOriginal: false), Run(text: "🙂")]
        let before = runs
        XCTAssertEqual(ImmersionCopyText.compose(runs), "e\u{0301}hello world🙂")
        XCTAssertEqual(runs, before)
        XCTAssertEqual(ImmersionCopyText.compose([Run(text: "I "), Run(text: "Apenas", slotID: 2, showsOriginal: false),
                                                Run(text: " know him.")]), "I Apenas know him.")
        let identifier = "ID123 https://example.test/#a"
        XCTAssertEqual(ImmersionCopyText.compose([Run(text: identifier)]), identifier)
        let sentence = [Run(text: "My "), Run(text: "teléfono", slotID: 3, showsOriginal: false), Run(text: " "),
                        Run(text: "batería", slotID: 9, showsOriginal: false), Run(text: " is "),
                        Run(text: "casi", slotID: 20, showsOriginal: false), Run(text: " dead.")]
        XCTAssertEqual(ImmersionCopyText.compose(sentence), "My teléfono batería is casi dead.")
    }
}
