import SwiftUI

/// One action and the current depth, shared by chat and the optional preview.
struct ImmersionModeToggle: View {
    let mode: ImmersionMode
    let onToggle: () -> Void
    var body: some View {
        Button(action:onToggle) {
            // A toolbar can adapt Label into icon-only or title-only forms.
            // These are two named modes, so keep their symbol and title together.
            HStack(spacing:5) {
                ImmersionModeSymbol(mode:mode)
                Text(mode.title).fixedSize(horizontal:false,vertical:true)
            }
            .font(.subheadline.weight(.medium)).lineLimit(2)
            .multilineTextAlignment(.leading).fixedSize(horizontal:true,vertical:false)
            .frame(minHeight:44)
        }
        .accessibilityLabel("Immersion").accessibilityValue(mode.title)
        .accessibilityHint(LocalizedStringKey(mode == .fullMessages ? "Switch to Shallow":"Switch to Deep"))
        .accessibilityIdentifier("chat-immersion-picker")
    }
}

/// Both destinations are visible while learning the two modes. Real chats keep
/// their compact single-action control and the same preference/enum metadata.
struct ImmersionModeChoices: View {
    let mode: ImmersionMode
    let onSelect: (ImmersionMode) -> Void
    @Environment(\.dynamicTypeSize) private var textSize
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
