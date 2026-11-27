import SwiftUI

/// Keeps the illustration in the introduction or profile row and out of the way while editing.
struct ScreenSpot: ViewModifier {
    let asset: String
    var editing = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSize
    @State private var hasRoom = false

    func body(content: Content) -> some View {
        HStack(spacing: 8) {
            content.frame(maxWidth: .infinity, alignment: .leading)
            if hasRoom && !editing && !typeSize.isAccessibilitySize && verticalSize != .compact {
                Image(decorative: asset).resizable().scaledToFit()
                    .frame(width: 88, height: 53)
                    .allowsHitTesting(false).accessibilityHidden(true)
            }
        }
        .onGeometryChange(for: Bool.self) {
            $0.size.width >= 276
        } action: {
            hasRoom = $0
        }
    }
}
