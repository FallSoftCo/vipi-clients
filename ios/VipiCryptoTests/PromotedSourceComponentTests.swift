import XCTest
import SwiftUI
import Darwin
import VipiCore
@testable import Vipi

/// Isolated native window only. Preserves the ordinary app's deletion/startup
/// gate and qualifies no account access, keychain, signing or menu taps.
@MainActor final class PromotedSourceComponentTests: XCTestCase {
    struct Case: Decodable { let source, target, original, mixed, script: String }
    private func rss() -> UInt64? {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let status = withUnsafeMutablePointer(to: &info) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
        } }
        return status == KERN_SUCCESS ? UInt64(info.resident_size) : nil
    }
    func testJapaneseArabic() async throws { try await check("ja-ar") }
    func testArabicJapanese() async throws { try await check("ar-ja") }
    func testKoreanChinese() async throws { try await check("ko-zh") }
    func testChineseKorean() async throws { try await check("zh-ko") }
    func testSwahiliFrench() async throws { try await check("sw-fr") }
    private func check(_ pairID: String) async throws {
        guard ProcessInfo.processInfo.environment["VIPI_PROMOTED_COMPONENT_UI"] == "true" else { throw XCTSkip("Explicit isolated component qualification only") }
        guard !UIAccessibility.isVoiceOverRunning else { throw XCTSkip("Normal continuous reading requires VoiceOver inactive; system setting preserved") }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let cases = try JSONDecoder().decode([Case].self, from: Data(contentsOf: documents.appendingPathComponent("all-pair-ui-cases-r01.json")))
        let row = try XCTUnwrap(cases.first { $0.source + "-" + $0.target == pairID })
        let initialRSS = rss()
        let owner = ConversationImmersion() // Real promoted default; no provider injection.
        await owner.configure(pair: .init(source: row.source, target: row.target), density: 0.25)
        let messageID = "promoted-component-" + pairID
        let produced = await owner.result(for: row.original, messageID: messageID)
        let result = try XCTUnwrap(produced)
        XCTAssertEqual(owner.lastOutcome?.localTranslationCalls, 0)
        let preparedRSS = rss()
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene); window.windowLevel = .alert + 1
        let suite = "vipi-promoted-component-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        let speech = SpeechPlayback()
        defer { window.isHidden = true; window.rootViewController = nil; previous?.makeKey(); owner.close(); speech.stop(); defaults.removePersistentDomain(forName: suite) }
        func mount<V: View>(_ view: V) {
            window.rootViewController = UIHostingController(rootView: view.environment(\.scenePhase, .active)
                .preferredColorScheme(.light).defaultAppStorage(defaults))
            window.makeKeyAndVisible(); window.layoutIfNeeded()
        }
        func paragraph(_ view: UIView) -> ImmersionNativeTextView? {
            if let text = view as? ImmersionNativeTextView { return text }
            return view.subviews.lazy.compactMap { paragraph($0) }.first
        }
        func capture(_ suffix: String) {
            window.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            let attachment = XCTAttachment(image: image); attachment.name = pairID + "-" + suffix; attachment.lifetime = .keepAlways; add(attachment)
        }
        mount(ScrollView { VStack(alignment: .leading, spacing: 20) {
            Text(VipiLanguage.named(row.source).name + " → " + VipiLanguage.named(row.target).name).font(.headline)
            ConversationImmersionText(text: row.original, id: messageID, immersion: owner, speech: speech,
                paused: false, metadata: AnyView(Text("Local message")), onVoiceHelp: {})
        }.padding(24) }.background(VipiDesign.canvas))
        try await Task.sleep(for: .seconds(1))
        let text = try XCTUnwrap(paragraph(window)), first = text.frame
        var last = text.visibleText(), transitions = 0, observations: [[String: Any]] = []
        let deadline = Date().addingTimeInterval(40)
        while transitions < 6 && Date() < deadline {
            try await Task.sleep(for: .milliseconds(250))
            let value = text.visibleText()
            XCTAssertTrue([row.original, row.mixed].contains(value), value)
            XCTAssertEqual(text.frame.height, first.height, accuracy: 0.5)
            XCTAssertEqual(text.frame.width, first.width, accuracy: 0.5)
            if value != last {
                transitions += 1; last = value
                observations.append(["text": value, "height": Double(text.frame.height), "width": Double(text.frame.width), "rss_bytes": rss() as Any? ?? NSNull()])
            }
        }
        XCTAssertEqual(transitions, 6)
        let afterFlipsRSS = rss()
        let readingDeadline = Date().addingTimeInterval(10)
        while text.visibleText() != row.mixed && Date() < readingDeadline { try await Task.sleep(for: .milliseconds(100)) }
        XCTAssertEqual(text.visibleText(), row.mixed); capture("continuous-reading")
        mount(ScrollView { VStack(alignment: .leading, spacing: 20) {
            Text(VipiLanguage.named(row.source).name + " → " + VipiLanguage.named(row.target).name + " · native script").font(.headline)
            StableImmersionText(result: result, revealed: [], script: true, onWord: { _ in }, onSelection: { _ in })
        }.padding(24) }.background(VipiDesign.canvas))
        try await Task.sleep(for: .milliseconds(750))
        XCTAssertEqual(try XCTUnwrap(paragraph(window)).visibleText(), row.script); capture("native-script")
        let receipt: [String: Any] = ["pair": pairID, "pid": ProcessInfo.processInfo.processIdentifier,
            "injected_provider": false, "normal_account_startup_qualified": false, "menu_taps_qualified": false,
            "scope": "isolated native message component; actual default engine; six flips and separate native-script renderer",
            "initial_rss_bytes": initialRSS as Any? ?? NSNull(), "prepared_rss_bytes": preparedRSS as Any? ?? NSNull(),
            "after_six_flips_rss_bytes": afterFlipsRSS as Any? ?? NSNull(), "observations": observations]
        try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]).write(to: documents.appendingPathComponent("promoted-component-" + pairID + ".json"))
    }
}
