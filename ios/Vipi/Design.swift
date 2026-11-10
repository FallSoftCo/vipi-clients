import SwiftUI

enum VipiDesign {
    static let accent = Color(red: 0.20, green: 0.39, blue: 0.31)
    static let ink = Color(uiColor: .label)
    static let secondary = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.72, green: 0.75, blue: 0.71, alpha: 1) : UIColor(red: 0.34, green: 0.37, blue: 0.34, alpha: 1) })
    static let canvas = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.065, green: 0.078, blue: 0.071, alpha: 1) : UIColor(red: 0.976, green: 0.969, blue: 0.949, alpha: 1) })
    static let surface = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.12, green: 0.14, blue: 0.125, alpha: 1) : .white })
    static let highlight = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.69, green: 0.85, blue: 0.64, alpha: 1) : UIColor(red: 0.17, green: 0.38, blue: 0.26, alpha: 1) })
    static let destructive = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 1, green: 0.706, blue: 0.671, alpha: 1) : UIColor(red: 0.72, green: 0.11, blue: 0.11, alpha: 1) })
    static let onHighlight = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.065, green: 0.078, blue: 0.071, alpha: 1) : .white })
    static let outgoing = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.18, green: 0.26, blue: 0.20, alpha: 1) : UIColor(red: 0.88, green: 0.93, blue: 0.83, alpha: 1) })
}

// Original two-voice mark; geometry matches design/vipi-icon.svg and Android.
struct VipiMark: View {
    var size: CGFloat = 42
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.28).fill(Color(red: 35/255, green: 78/255, blue: 61/255))
            VipiVoiceShape(right: false).fill(Color(red: 249/255, green: 247/255, blue: 242/255))
            VipiVoiceShape(right: true).fill(Color(red: 221/255, green: 243/255, blue: 166/255))
        }.frame(width: size, height: size).accessibilityHidden(true)
    }
}

private struct VipiVoiceShape: Shape {
    var right: Bool
    func path(in rect: CGRect) -> Path {
        var p = Path()
        if right {
            p.move(to: CGPoint(x: 68, y: 29))
            p.addQuadCurve(to: CGPoint(x: 63, y: 32), control: CGPoint(x: 64.5, y: 29))
            p.addLine(to: CGPoint(x: 48, y: 62)); p.addLine(to: CGPoint(x: 57, y: 80))
            p.addLine(to: CGPoint(x: 81, y: 32))
            p.addQuadCurve(to: CGPoint(x: 79, y: 29), control: CGPoint(x: 82.5, y: 29))
        } else {
            p.move(to: CGPoint(x: 27, y: 29))
            p.addQuadCurve(to: CGPoint(x: 25.5, y: 32), control: CGPoint(x: 24, y: 29))
            p.addLine(to: CGPoint(x: 45, y: 70))
            p.addQuadCurve(to: CGPoint(x: 51, y: 74), control: CGPoint(x: 47, y: 74))
            p.addLine(to: CGPoint(x: 56, y: 74)); p.addLine(to: CGPoint(x: 45, y: 52))
            p.addLine(to: CGPoint(x: 35, y: 32))
            p.addQuadCurve(to: CGPoint(x: 30, y: 29), control: CGPoint(x: 33.5, y: 29))
        }
        p.closeSubpath()
        return p.applying(CGAffineTransform(scaleX: rect.width / 108, y: rect.height / 108))
    }
}

struct PrimaryButton: View {
    let title: String
    var busy = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if busy { ProgressView().tint(VipiDesign.onHighlight) }
                Text(title).font(.body.weight(.semibold))
                if !busy { Image(systemName: "arrow.right").font(.body.weight(.medium)) }
            }.frame(maxWidth: .infinity).padding(.vertical, 17)
        }
        .buttonStyle(.plain).foregroundStyle(VipiDesign.onHighlight)
        .background(VipiDesign.highlight, in: RoundedRectangle(cornerRadius: 18))
        .disabled(busy)
    }
}

struct IntroHeading: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let eyebrow: String
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if !dynamicTypeSize.isAccessibilitySize {
                Text(eyebrow.uppercased()).font(.caption.weight(.semibold)).tracking(2.1).foregroundStyle(VipiDesign.highlight)
            }
            Text(title).font(.system(.largeTitle, design: .serif).weight(.medium)).lineSpacing(1).fixedSize(horizontal: false, vertical: true)
            Text(detail).font(.body).foregroundStyle(VipiDesign.secondary).lineSpacing(4).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
