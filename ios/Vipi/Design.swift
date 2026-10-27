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

struct VipiMark: View {
    var size: CGFloat = 42
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.32).fill(VipiDesign.accent)
            Image(systemName: "bubble.left.fill").font(.system(size: size * 0.61)).foregroundStyle(Color(red: 0.87, green: 0.94, blue: 0.75))
            Text("v").font(.system(size: size * 0.44, weight: .semibold, design: .rounded)).foregroundStyle(VipiDesign.accent).offset(y: -size * 0.04)
        }.frame(width: size, height: size).accessibilityHidden(true)
    }
}

struct PrimaryButton: View {
    let title: String
    var busy = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if busy { ProgressView().tint(.white) }
                Text(title).font(.body.weight(.semibold))
                if !busy { Image(systemName: "arrow.right").font(.body.weight(.medium)) }
            }.frame(maxWidth: .infinity).padding(.vertical, 17)
        }
        .buttonStyle(.plain).foregroundStyle(.white)
        .background(VipiDesign.accent, in: RoundedRectangle(cornerRadius: 18))
        .disabled(busy)
    }
}

struct IntroHeading: View {
    let eyebrow: String
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(eyebrow.uppercased()).font(.caption.weight(.semibold)).tracking(2.1).foregroundStyle(VipiDesign.highlight)
            Text(title).font(.system(.largeTitle, design: .serif).weight(.medium)).lineSpacing(1).fixedSize(horizontal: false, vertical: true)
            Text(detail).font(.body).foregroundStyle(VipiDesign.secondary).lineSpacing(4).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
