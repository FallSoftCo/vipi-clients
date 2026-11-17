import SwiftUI
import UIKit

private struct DependencyNotice: Decodable, Identifiable {
    let id: String; let title: String; let file: String; let sha256: String; let origin: String
    var text: String {
        guard let url = Bundle.main.url(forResource: file, withExtension: nil, subdirectory: "ThirdPartyNotices"),
              let value = try? String(contentsOf: url, encoding: .utf8) else { return String(localized: "This notice could not be opened.") }
        return value
    }
    static var all: [Self] {
        guard let url = Bundle.main.url(forResource: "index", withExtension: "json", subdirectory: "ThirdPartyNotices"),
              let bytes = try? Data(contentsOf: url), let entries = try? JSONDecoder().decode([Self].self, from: bytes) else { return [] }
        return entries
    }
}
struct NoticesView: View {
    private let entries = DependencyNotice.all
    var body: some View {
        List {
            Section { Text("Vipi is made with open-source software and the native services listed here. Each component retains its own license.") }
            if entries.isEmpty { Text("Notices could not be opened. Please reopen Vipi.") }
            ForEach(entries) { entry in
                NavigationLink(entry.title) {
                    NoticeTextView(text: entry.text).navigationTitle(entry.title).navigationBarTitleDisplayMode(.inline)
                }
            }
        }.scrollContentBackground(.hidden).background(VipiDesign.canvas).navigationTitle("Licenses and notices").navigationBarTitleDisplayMode(.inline)
    }
}
private struct NoticeTextView: UIViewRepresentable {
    let text: String
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView(); view.isEditable = false; view.isSelectable = true
        view.adjustsFontForContentSizeCategory = true; view.font = .preferredFont(forTextStyle: .body)
        view.textColor = .label; view.backgroundColor = UIColor(VipiDesign.canvas)
        view.textContainerInset = UIEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        view.text = text
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) { if view.text != text { view.text = text } }
}
