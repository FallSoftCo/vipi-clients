import SwiftUI

enum VipiDesign {
    // In narrow iPad windows the system's window controls share the leading
    // edge of the navigation bar with Back. Keep custom toolbar content trailing.
    static func hasNarrowPadToolbar(_ width: CGFloat) -> Bool {
        if #available(iOS 26.0, *) {
            // Five 44pt actions, 16pt of spacing and 136pt of window chrome.
            return UIDevice.current.userInterfaceIdiom == .pad && (372..<600).contains(width)
        }
        return false
    }

    static let conversationWidth: CGFloat = 644
    static let accent = VipiPalette.color(.action)
    static let ink = VipiPalette.color(.ink)
    static let secondary = VipiPalette.color(.secondary)
    static let canvas = VipiPalette.color(.canvas)
    static let surface = VipiPalette.color(.surface)
    static let highlight = VipiPalette.color(.action)
    static let destructive = VipiPalette.color(.failed)
    static let onHighlight = VipiPalette.color(.onAction)
    static let outgoing = VipiPalette.color(.outgoing)
    static let incomingBubble = VipiPalette.color(.incoming)
    static let outgoingBubble = VipiPalette.color(.outgoing)
    static let readIndicator = VipiPalette.color(.outgoingRead)
    static let outline = VipiPalette.color(.outline)
    static let focus = VipiPalette.color(.focus)
    static let subdued = VipiPalette.color(.subdued)
    static let separator = VipiPalette.color(.separator)
    static let practiceInk = VipiPalette.color(.practiceInk)
    static let practiceFill = VipiPalette.color(.practiceFill)
    static let spokenInk = VipiPalette.color(.spokenInk)
    static let spokenFill = VipiPalette.color(.spokenFill)
    static let bubbleBorder = Color(uiColor:UIColor { traits in
        VipiPalette.uiColor(traits.accessibilityContrast == .high ? .outline:.separator).resolvedColor(with:traits)
    })
    static func messageInk(_ outgoing:Bool) -> Color { VipiPalette.color(outgoing ? .outgoingInk:.ink) }
    static func messageSecondary(_ outgoing:Bool) -> Color { VipiPalette.color(outgoing ? .outgoingSecondary:.secondary) }
    static func messageRead(_ outgoing:Bool) -> Color { VipiPalette.color(outgoing ? .outgoingRead:.read) }
    static func messageFailure(_ outgoing:Bool) -> Color { VipiPalette.color(outgoing ? .outgoingFailed:.failed) }
}

/// Shared approved wordmark artwork, rendered from the bundled original vector.
struct VipiMark:View {
    var size:CGFloat = 42
    var accessibleName: String?
    var body:some View {
        Image("VipiWordmark")
            .resizable().renderingMode(.original).aspectRatio(contentMode:.fit)
            .environment(\.layoutDirection,.leftToRight)
            .frame(width:size,height:size)
            .accessibilityLabel(Text(verbatim:accessibleName ?? ""))
            .accessibilityHidden(accessibleName == nil)
    }
}

struct PrimaryButton: View {
    let title: LocalizedStringKey
    var busy = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if busy { ProgressView().tint(VipiDesign.onHighlight) }
                Text(title).font(.body.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                if !busy { Image(systemName: "arrow.right").flipsForRightToLeftLayoutDirection(true).font(.body.weight(.medium)) }
            }.frame(maxWidth: .infinity).padding(.vertical, 17)
                .frame(minHeight: 48).contentShape(Rectangle())
        }
        .buttonStyle(.plain).foregroundStyle(VipiDesign.onHighlight)
        .background(VipiDesign.highlight, in: RoundedRectangle(cornerRadius: 16))
        .disabled(busy)
    }
}

struct IntroHeading: View {
    @Environment(\.locale) private var locale
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let eyebrow: LocalizedStringKey
    let title: LocalizedStringKey
    let detail: LocalizedStringKey
    var showsDetail = true
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.largeTitle.weight(.bold)).lineSpacing(1).fixedSize(horizontal: false, vertical: true)
            if showsDetail { Text(detail).font(.body).foregroundStyle(VipiDesign.secondary).lineSpacing(4).fixedSize(horizontal: false, vertical: true) }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
