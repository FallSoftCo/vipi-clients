import XCTest
import SwiftUI
@testable import Vipi

@MainActor final class LanguagePreviewMatrixTests: XCTestCase {
    func testNativeTokenizationAndParagraphLayoutAcrossNinetyDirections() async throws {
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("reading-matrix-001")
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        try? FileManager.default.removeItem(at: output.appendingPathComponent("report.json"))
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
                        for original in [false, true] {
                            let root = StableImmersionText(result: result, revealed: original ? Set(result.spans.map(\.id)) : [], script: false, onWord: { _ in }, onSelection: { _ in })
                                .environment(\.dynamicTypeSize, size).environment(\.colorScheme, .light)
                            let host = UIHostingController(rootView: root)
                            host.view.frame = CGRect(x: 0, y: 0, width: width, height: 1000)
                            host.view.backgroundColor = .white
                            let measured = host.sizeThatFits(in: CGSize(width: width, height: 1000))
                            XCTAssertGreaterThan(measured.height, 0)
                            XCTAssertLessThan(measured.height, 1000, "Clipped \(source)->\(target)")
                            heights.append(measured.height)
                            host.view.frame.size.height = measured.height; host.view.layoutIfNeeded()
                            if width == 360 && size == .large {
                                displayHost.rootView = AnyView(root.frame(width: width).fixedSize(horizontal: false, vertical: true))
                                try await Task.sleep(for: .milliseconds(40))
                                displayHost.view.layoutIfNeeded()
                                let native = try XCTUnwrap(nativeText(in: displayHost.view))
                                native.backgroundColor = .white
                                XCTAssertFalse(native.text.isEmpty)
                                XCTAssertGreaterThan(native.bounds.height, 0)
                                let image = UIGraphicsImageRenderer(size: native.bounds.size).image { _ in native.drawHierarchy(in: native.bounds, afterScreenUpdates: true) }
                                try image.pngData()?.write(to: output.appendingPathComponent("\(source)-\(target)-\(original ? "meaning" : "target").png"))
                            }
                        }
                        XCTAssertEqual(heights[0], heights[1], accuracy: 0.5, "Bubble jumps \(source)->\(target) \(width) \(size)")
                        measurements.append(["width": width, "typeSize": String(describing: size), "height": heights[0]])
                    }
                }
                rows.append(["source": source, "target": target, "selected": result.spans.count, "readings": result.spans.map(\.displayedTarget), "measurements": measurements])
            }
        }
        XCTAssertEqual(rows.count, 90)
        let report: [String: Any] = ["evidence": "authored_preview_native_tokenization_paragraph_layout_not_live_translation_or_linguistic_acceptance", "directions": rows]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("report.json"))
    }
}
