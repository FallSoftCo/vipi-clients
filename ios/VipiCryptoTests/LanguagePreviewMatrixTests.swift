import XCTest
import SwiftUI
@testable import Vipi

@MainActor final class LanguagePreviewMatrixTests: XCTestCase {
    func testNativeTokenizationAndParagraphLayoutAcrossAllSupportedDirections() async throws {
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("reading-matrix-002")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        var rows: [[String: Any]] = []
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previousWindow = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene)
        window.frame = scene.screen.bounds
        let displayHost = UIHostingController(rootView: AnyView(EmptyView()))
        window.rootViewController = displayHost; window.makeKeyAndVisible()
        defer { window.isHidden = true; previousWindow?.makeKeyAndVisible() }
        func nativeText(in view: UIView) -> ImmersionNativeTextView? {
            if let text = view as? ImmersionNativeTextView { return text }
            return view.subviews.lazy.compactMap { nativeText(in: $0) }.first
        }
        let languages = VipiLanguage.initial.map(\.id)
        for source in languages {
            for target in languages where target != source {
                let result = try XCTUnwrap(ConversationExamples.result(source: source, target: target))
                XCTAssertFalse(result.spans.isEmpty, "No contextual preview vocabulary \(source)->\(target)")
                if ["ar", "zh", "ja", "ko"].contains(target) { XCTAssertTrue(result.spans.allSatisfy { $0.romanization != nil }) }
                XCTAssertEqual(result.speech(source: source, target: target, revealed: Set(result.spans.map(\.id))).map(\.text).joined(), result.original)
                var measurements: [[String: Any]] = []
                for width in [280.0, 360.0, 620.0] {
                    for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                        var heights: [CGFloat] = []
                        var anchors: [CGRect]?
                        for (face, original, script) in [("target", false, false), ("meaning", true, false), ("script", false, true)] {
                            let root = StableImmersionText(result: .complete(result), revealed: original ? Set(result.spans.map(\.id)) : [], script: script, onWord: { _ in }, onSelection: { _ in })
                                .environment(\.dynamicTypeSize, size).environment(\.colorScheme, .light)
                            displayHost.rootView = AnyView(root.frame(width: width).fixedSize(horizontal: false, vertical: true))
                            try await Task.sleep(for: .milliseconds(20))
                            displayHost.view.setNeedsLayout(); displayHost.view.layoutIfNeeded()
                            let paragraph = try XCTUnwrap(nativeText(in: displayHost.view))
                            paragraph.backgroundColor = .white
                            XCTAssertGreaterThan(paragraph.bounds.height, 0)
                            XCTAssertLessThan(paragraph.bounds.height, 1000, "Clipped \(source)->\(target)")
                            heights.append(paragraph.bounds.height)
                            paragraph.layoutManager.ensureLayout(for: paragraph.textContainer)
                            let glyphs = paragraph.layoutManager.glyphRange(for: paragraph.textContainer)
                            let positions = (0..<glyphs.length).map { paragraph.layoutManager.boundingRect(forGlyphRange: NSRange(location: $0, length: 1), in: paragraph.textContainer) }
                            if let anchors { XCTAssertEqual(anchors, positions, "Inline text shifts \(source)->\(target) \(width) \(size)") }
                            else { anchors = positions }
                            if original { XCTAssertEqual(paragraph.visibleText(), result.original) }
                            if width == 360 && size == .large {
                                paragraph.selectedRange = NSRange(location: 0, length: paragraph.attributedText.length)
                                paragraph.copy(nil)
                                XCTAssertEqual(UIPasteboard.general.string, paragraph.visibleText(), "Copy leaked an attachment placeholder")
                                paragraph.selectedRange = NSRange(location: 0, length: 0)
                                let image = UIGraphicsImageRenderer(size: paragraph.bounds.size).image { _ in paragraph.drawHierarchy(in: paragraph.bounds, afterScreenUpdates: true) }
                                try image.pngData()?.write(to: output.appendingPathComponent("\(source)-\(target)-\(face).png"))
                            }
                        }
                        XCTAssertEqual(heights[0], heights[1], accuracy: 0.5, "Bubble jumps \(source)->\(target) \(width) \(size)")
                        XCTAssertEqual(heights[0], heights[2], accuracy: 0.5, "Script changes bubble height \(source)->\(target)")
                        measurements.append(["width": width, "typeSize": String(describing: size), "height": heights[0]])
                    }
                }
                rows.append(["source": source, "target": target, "selected": result.spans.count, "readings": result.spans.map(\.displayedTarget), "measurements": measurements])
            }
        }
        XCTAssertEqual(rows.count, languages.count * (languages.count - 1))
        let greeting = try await BundledImmersionCatalog().result(original: "Thank you very much.", translation: "Asante sana.",
            pair: .init(source: "en", target: "sw"), density: 0.25)
        XCTAssertEqual(greeting.spans.count, 1)
        for revealed in [Set<Int>(), Set(greeting.spans.map(\.id))] {
            let root = StableImmersionText(result: .complete(greeting), revealed: revealed, script: false, onWord: { _ in }, onSelection: { _ in })
                .environment(\.dynamicTypeSize, .accessibility5)
            displayHost.rootView = AnyView(root.frame(width: 280).fixedSize(horizontal: false, vertical: true))
            try await Task.sleep(for: .milliseconds(20))
            displayHost.view.setNeedsLayout(); displayHost.view.layoutIfNeeded()
            let paragraph = try XCTUnwrap(nativeText(in: displayHost.view))
            let layout = paragraph.layoutManager
            layout.ensureLayout(for: paragraph.textContainer)
            XCTAssertEqual(layout.numberOfGlyphs, 2, "One complete phrase attachment and its original period")
            let first = layout.lineFragmentRect(forGlyphAt: 0, effectiveRange: nil)
            let last = layout.lineFragmentRect(forGlyphAt: layout.numberOfGlyphs - 1, effectiveRange: nil)
            XCTAssertEqual(first.minY, last.minY, accuracy: 0.5, "Never strand closing punctuation on another line")
        }
        let report: [String: Any] = ["evidence": "authored_preview_fixed_inline_blocks_native_tokenization_stable_glyph_positions_and_copy_not_live_translation_or_linguistic_acceptance", "directions": rows]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("report.json"))
    }
}
