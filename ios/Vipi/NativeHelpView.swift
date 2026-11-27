import SwiftUI

private enum HelpTopic: String, CaseIterable, Identifiable {
    case friends, groups, languages, reading, voice, status, notifications, safety, backup, account
    var id: Self { self }
    var title: LocalizedStringKey { LocalizedStringKey("help_" + rawValue + "_title") }
    var first: LocalizedStringKey { LocalizedStringKey("help_" + rawValue + "_step1") }
    var second: LocalizedStringKey { LocalizedStringKey("help_" + rawValue + "_step2") }
    var image: String { "Help" + rawValue.capitalized }
}

struct NativeHelpView: View {
    @State private var expanded: HelpTopic?
    var body: some View {
        List {
            Section {
                NavigationLink {
                    ImmersionTutorialView()
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Immersion guide").font(.title3.weight(.semibold))
                        Text("help_guide_intro", tableName: "NativeHelp").font(.body).foregroundStyle(
                            VipiDesign.secondary)
                    }.padding(.vertical, 8)
                }.accessibilityIdentifier("tutorial-reentry")
            }
            Section {
                ForEach(HelpTopic.allCases) { topic in
                    DisclosureGroup(
                        isExpanded: Binding(
                            get: { expanded == topic },
                            set: { expanded = $0 ? topic : nil }
                        )
                    ) {
                        VStack(alignment: .leading, spacing: 14) {
                            if topic == .voice {
                                Label {
                                    Text("help_voice_hold", tableName: "NativeHelp")
                                } icon: {
                                    Image(systemName: "mic.fill")
                                }
                                Label {
                                    Text("help_voice_cancel", tableName: "NativeHelp")
                                } icon: {
                                    Image(systemName: "arrow.backward")
                                }
                                Label {
                                    Text("help_voice_lock", tableName: "NativeHelp")
                                } icon: {
                                    Image(systemName: "arrow.up")
                                }
                            } else if topic == .status {
                                ForEach(["accepted", "delivered", "read"], id: \.self) { state in
                                    HStack {
                                        MessageDeliveryMark(state: state).accessibilityHidden(true)
                                        Text(verbatim: MessageDeliveryMark.localizedDescription(state)).font(.callout)
                                    }
                                }
                            } else {
                                Image(topic.image).resizable().scaledToFit()
                                    .clipShape(RoundedRectangle(cornerRadius: 12)).accessibilityHidden(true)
                            }
                            Text(topic.first, tableName: "NativeHelp")
                            if topic == .voice {
                                HStack(spacing: 26) {
                                    Image(systemName: "trash")
                                    Image(systemName: "stop.circle")
                                    Image(systemName: "arrow.up.circle.fill").foregroundStyle(VipiDesign.highlight)
                                }.font(.title2).accessibilityHidden(true)
                            }
                            Text(topic.second, tableName: "NativeHelp")
                        }.font(.body).fixedSize(horizontal: false, vertical: true)
                            .padding(.vertical, 10)
                    } label: {
                        Text(topic.title, tableName: "NativeHelp").foregroundStyle(VipiDesign.ink).frame(
                            minHeight: 44, alignment: .leading)
                    }.accessibilityIdentifier("help-topic-" + topic.rawValue)
                }
            } header: {
                Text("help_guides", tableName: "NativeHelp")
            }
            Section {
                Link(destination: URL(string: "mailto:one@fallsoft.co")!) {
                    Label {
                        Text("help_email", tableName: "NativeHelp")
                    } icon: {
                        Image(systemName: "envelope")
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden).background(VipiDesign.canvas)
        .tint(VipiDesign.highlight)
        .navigationTitle(Text("help_title", tableName: "NativeHelp")).navigationBarTitleDisplayMode(.inline)
    }
}
