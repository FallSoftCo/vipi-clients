import SwiftUI

struct ConversationLanguageSelection {
    let source: String
    let target: String
    let defaultTarget: String
    let usesDefault: Bool
    let select: (String) -> Void
    let useDefault: () -> Void
}

/// Keep a single row in the space proposed between Back and the options button.
/// Full action titles yield first, then the language name shortens to its code.
struct ConversationHeaderActions<Identity: View>: View {
    let mode: ImmersionMode
    let autoplay: Bool
    let toggleMode: () -> Void
    let toggleAutoplay: () -> Void
    let language: ConversationLanguageSelection
    @ViewBuilder let identity: (_ showsAvatar: Bool) -> Identity
    @State private var choosingLanguage = false

    var body: some View {
        ViewThatFits(in: .horizontal) {
            row(actionTitles: true, shortLanguage: false, showsAvatar: true).fixedSize(horizontal: true, vertical: false)
            row(actionTitles: false, shortLanguage: false, showsAvatar: true).fixedSize(horizontal: true, vertical: false)
            row(actionTitles: false, shortLanguage: false, showsAvatar: false).fixedSize(horizontal: true, vertical: false)
            row(actionTitles: false, shortLanguage: true, showsAvatar: false)
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $choosingLanguage) {
            NavigationStack {
                LanguageSelectionView(title: "Practice language",
                                      selection: Binding(get: { language.target }, set: language.select),
                                      choices: VipiLanguage.initial, localName: true, practiceSource: language.source)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Cancel") { choosingLanguage = false }
                        }
                    }
                    .safeAreaInset(edge: .bottom) {
                        if !language.usesDefault {
                            Button {
                                language.useDefault()
                                choosingLanguage = false
                            } label: {
                                Text(String(format: String(localized: "Use account default (%@)"),
                                            VipiLanguage.named(language.defaultTarget).localizedName))
                                    .frame(maxWidth: .infinity, minHeight: 44)
                            }
                            .background(.bar)
                            .accessibilityIdentifier("conversation-language-default")
                        }
                    }
            }
        }
    }

    private func row(actionTitles: Bool, shortLanguage: Bool, showsAvatar: Bool) -> some View {
        HStack(spacing: 2) {
            identity(showsAvatar)
            ConversationLanguageButton(language: language, shortLabel: shortLanguage) { choosingLanguage = true }
                .fixedSize(horizontal: true, vertical: false)
            ImmersionModeToggle(mode: mode, showTitle: actionTitles, onToggle: toggleMode)
                .fixedSize(horizontal: true, vertical: false)
            ChatAutoplayButton(enabled: autoplay, showTitle: actionTitles, toggle: toggleAutoplay)
                .fixedSize(horizontal: true, vertical: false)
        }
    }
}

private struct ConversationLanguageButton: View {
    let language: ConversationLanguageSelection
    let shortLabel: Bool
    let openPicker: () -> Void

    private var name: String { VipiLanguage.named(language.target).localizedName }
    private var code: String {
        (Locale.Language(identifier: language.target).languageCode?.identifier ?? language.target).uppercased()
    }

    var body: some View {
        Button(action: openPicker) {
            HStack(spacing: 3) {
                Text(verbatim: shortLabel ? code : name).lineLimit(1)
                Image(systemName: "chevron.down").font(.caption2.weight(.bold)).accessibilityHidden(true)
            }
            .font(.subheadline.weight(.semibold))
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .fixedSize()
            .padding(.horizontal, 4).padding(.vertical, 5)
            .foregroundStyle(language.usesDefault ? VipiDesign.ink : VipiDesign.onHighlight)
            .background(language.usesDefault ? Color.clear : VipiDesign.highlight, in: Capsule())
            .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }
        .accessibilityLabel("Practice language")
        .accessibilityValue(Text(name))
        .accessibilityHint("Change the practice language for this conversation")
        .accessibilityIdentifier("conversation-language")
    }
}

struct ImmersionModeToggle: View {
    let mode: ImmersionMode
    var showTitle = true
    let onToggle: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 5) {
                ImmersionModeSymbol(mode: mode)
                    .contentTransition(.opacity)
                    .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                if showTitle {
                    // Reserve both localized titles. Toggling never changes which
                    // layout fits or moves the adjacent Autoplay button.
                    ZStack(alignment: .leading) {
                        ForEach(ImmersionMode.allCases) { choice in
                            Text(choice.title).hidden().accessibilityHidden(true)
                        }
                        Text(mode.title).contentTransition(.opacity)
                    }
                }
            }
            .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: mode)
            .font(.subheadline.weight(.medium))
            .fixedSize()
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("Immersion").accessibilityValue(mode.title)
        .accessibilityHint(LocalizedStringKey(mode == .fullMessages ? "Switch to Shallow":"Switch to Deep"))
        .accessibilityIdentifier("chat-immersion-picker")
    }
}

/// Toggles automatic playback of future messages. Tapping a message remains
/// an independent, one-message action.
struct ChatAutoplayButton: View {
    let enabled: Bool
    var showTitle = true
    let toggle: () -> Void
    @ScaledMetric(relativeTo: .subheadline) private var speakerWidth: CGFloat = 22

    var body: some View {
        Button(action: toggle) {
            HStack(spacing: 5) {
                Image(systemName: enabled ? "speaker.wave.2.fill" : "speaker.slash")
                    .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                    .frame(width: min(32, speakerWidth))
                if showTitle { Text("Autoplay") }
            }
            .font(.subheadline.weight(.semibold))
            .fixedSize()
            .padding(.horizontal, showTitle ? 8 : 4).padding(.vertical, 5)
            .foregroundStyle(enabled ? VipiDesign.onHighlight : VipiDesign.ink)
            .background(enabled ? VipiDesign.highlight : .clear, in: Capsule())
            .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }
        .accessibilityLabel("Autoplay")
        .accessibilityValue(enabled ? Text("On") : Text("Off"))
        .accessibilityHint("Play new messages aloud")
        .accessibilityAddTraits(enabled ? .isSelected : [])
        .accessibilityIdentifier("chat-autoplay-toggle")
    }
}

/// Both destinations are visible while learning the two modes. Real chats keep
/// their compact single-action control and the same preference/enum metadata.
struct ImmersionModeChoices: View {
    let mode: ImmersionMode
    let onSelect: (ImmersionMode) -> Void
    @Environment(\.dynamicTypeSize) private var textSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        let layout = textSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment:.leading,spacing:8)) : AnyLayout(HStackLayout(spacing:8))
        layout {
            ForEach(ImmersionMode.allCases) { choice in
                let active = choice == mode
                Button { onSelect(choice) } label: {
                    Label { Text(choice.title) } icon: { ImmersionModeSymbol(mode:choice) }
                        .font(.subheadline.weight(.semibold)).fixedSize(horizontal:false,vertical:true)
                        .frame(minHeight:44).padding(.horizontal,12)
                }
                .buttonStyle(.plain).foregroundStyle(active ? VipiDesign.ink:VipiDesign.secondary)
                .background(active ? VipiDesign.practiceFill:VipiDesign.surface,in:RoundedRectangle(cornerRadius:14))
                .overlay { RoundedRectangle(cornerRadius:14).stroke(active ? VipiDesign.practiceInk:VipiDesign.outline,lineWidth:1) }
                .animation(reduceMotion ? nil : .easeOut(duration:0.20),value:active)
                .accessibilityAddTraits(active ? .isSelected:[])
                .accessibilityIdentifier("tutorial-mode-"+choice.rawValue)
            }
        }
    }
}

/// SF Symbols availability varies by OS. Keep Deep's anchor visible everywhere.
private struct ImmersionModeSymbol: View {
    let mode: ImmersionMode
    @ScaledMetric(relativeTo:.subheadline) private var size:CGFloat = 18
    var body: some View {
        Group {
            if UIImage(systemName:mode.symbolName) != nil { Image(systemName:mode.symbolName).resizable().scaledToFit() }
            else { AnchorMark().stroke(style:StrokeStyle(lineWidth:1.7,lineCap:.round,lineJoin:.round)) }
        }.frame(width:size,height:size).accessibilityHidden(true)
    }
}
private struct AnchorMark: Shape {
    func path(in rect:CGRect) -> Path {
        let w = rect.width,h = rect.height
        func p(_ x:CGFloat,_ y:CGFloat)->CGPoint { .init(x:rect.minX+w*x,y:rect.minY+h*y) }
        return Path { path in
            path.addEllipse(in:CGRect(x:rect.minX+w*0.41,y:rect.minY+h*0.04,width:w*0.18,height:h*0.18))
            path.move(to:p(0.5,0.22));path.addLine(to:p(0.5,0.90))
            path.move(to:p(0.29,0.39));path.addLine(to:p(0.71,0.39))
            path.move(to:p(0.12,0.58));path.addCurve(to:p(0.88,0.58),control1:p(0.17,1.02),control2:p(0.83,1.02))
            path.move(to:p(0.12,0.58));path.addLine(to:p(0.08,0.76));path.move(to:p(0.12,0.58));path.addLine(to:p(0.30,0.66))
            path.move(to:p(0.88,0.58));path.addLine(to:p(0.92,0.76));path.move(to:p(0.88,0.58));path.addLine(to:p(0.70,0.66))
        }
    }
}
