import SwiftUI

/// Original vector King mackerel, shared with the CSS study. This view is purely
/// decorative: it never becomes a gesture surface or accessibility element.
struct ConversationWaterScene: View {
    let mode: ImmersionMode
    let motionEnabled: Bool
    var listSurface = false
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @State private var elapsed: TimeInterval = 18
    @State private var runningSince: Date?
    @State private var presented = false

    private var active: Bool { presented && motionEnabled && !reduceMotion && !reduceTransparency && scenePhase == .active }
    private var dark: Bool { scheme == .dark }
    private var deep: Bool { mode == .fullMessages }
    private var water: [Color] {
        if listSurface {
            return (dark
                ? (deep ? [0x221B22, 0x25212A, 0x24232D] : [0x221B22, 0x27212A, 0x292530])
                : (deep ? [0xFFF8EF, 0xF4EEE6, 0xEDE8E0] : [0xFFF8EF, 0xF7EFE6, 0xF0E5DA])
            ).map { sceneColor(UInt32($0)) }
        }
        let colors: [UInt32] = dark
            ? (deep ? [0x24202C, 0x243542, 0x142C3A] : [0x221B22, 0x292934, 0x273C45])
            : (deep ? [0xF4F0E7, 0xDBE2DF, 0xC1D1D1] : [0xFFF8EF, 0xF3E9DF, 0xD5DEDB])
        return colors.map(sceneColor)
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 24, paused: !active)) { timeline in
            let seconds = elapsed + (runningSince.map { max(0, timeline.date.timeIntervalSince($0)) } ?? 0)
            Canvas(opaque: true, rendersAsynchronously: true) { context, size in
                let bounds = Path(CGRect(origin: .zero, size: size))
                context.fill(bounds, with: .color(sceneColor(dark ? 0x221B22 : 0xFFF8EF)))
                guard !reduceTransparency else { return }
                context.fill(bounds, with: .linearGradient(Gradient(colors: water), startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))
                if listSurface {
                    let pigment = sceneColor(dark ? 0xC294A4 : 0x9A6370)
                    for index in 0..<17 {
                        let center = CGPoint(x: size.width * Double((index * 37 + 13) % 101) / 100, y: size.height * Double((index * 29 + 7) % 103) / 102)
                        let radius = Double(70 + (index * 17 % 60))
                        context.fill(Path(ellipseIn: CGRect(x: center.x-radius, y: center.y-radius, width: radius*2, height: radius*2)), with: .radialGradient(Gradient(colors: [pigment.opacity(0.055), .clear]), center: center, startRadius: 0, endRadius: radius))
                    }
                    for index in 0..<9 {
                        let y = size.height * (Double(index) + 0.35) / 9
                        var ripple = Path(); ripple.move(to: CGPoint(x: -size.width*0.1, y: y))
                        ripple.addCurve(to: CGPoint(x:size.width*1.1,y:y-5), control1: CGPoint(x:size.width*0.24,y:y-18), control2: CGPoint(x:size.width*0.62,y:y+20))
                        context.stroke(ripple, with: .color(pigment.opacity(0.10)), lineWidth: 0.7)
                    }
                }
                for index in 0..<3 {
                    let x = size.width * (Double(index) * 0.43 - 0.3) + sin(seconds / 20) * size.width * 0.05
                    var ray = Path()
                    ray.move(to: CGPoint(x: x, y: 0)); ray.addLine(to: CGPoint(x: x + size.width * 0.22, y: 0))
                    ray.addLine(to: CGPoint(x: x + size.width * 0.7, y: size.height))
                    ray.addLine(to: CGPoint(x: x + size.width * 0.38, y: size.height)); ray.closeSubpath()
                    context.fill(ray, with: .color(.white.opacity(dark ? 0.015 : 0.04)))
                }
                let opacity = listSurface ? (dark ? 0.17 : 0.12) : deep ? 0.36 : dark ? 0.29 : 0.27
                let widths = [0.76, 0.51, 0.35]
                let cycles = [39.0, 51.0, 62.0], offsets = [0.0, 23.0, 38.0], levels = [0.79, 0.36, 0.82]
                for index in 0..<3 {
                    let width = min(size.width * widths[index], 360)
                    let fraction = (seconds + offsets[index]).truncatingRemainder(dividingBy: cycles[index]) / cycles[index]
                    var fish = context
                    fish.opacity = opacity * (index == 0 ? 1 : index == 1 ? 0.58 : 0.45)
                    fish.translateBy(x: -width + fraction * (size.width + width), y: size.height * levels[index] + sin(seconds / 5 + Double(index)) * 5)
                    fish.scaleBy(x: width / 640, y: width / 640)
                    drawMackerel(in: &fish, seconds: seconds)
                }
                let bubbleX = [0.13, 0.86, 0.72, 0.41], durations = [17.0, 23.0, 27.0, 29.0], radii = [3.5, 2.5, 4.5, 2.0]
                for index in 0..<4 {
                    let fraction = (seconds + Double(index * 7)).truncatingRemainder(dividingBy: durations[index]) / durations[index]
                    let radius = radii[index]
                    let point = CGPoint(x: size.width * bubbleX[index] + sin(fraction * 3) * 9, y: size.height * (1 - fraction))
                    let bubble = Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2))
                    context.stroke(bubble, with: .color(sceneColor(dark ? 0xBBD0D2 : 0x8B8A8C).opacity(max(0, sin(fraction * .pi) * 0.3))), lineWidth: 0.65)
                }
                // Deterministic fine grain. No per-frame random texture.
                let step = listSurface ? 7.0 : 12.0
                for row in 0...Int(size.height / step) {
                    for column in 0...Int(size.width / step) {
                        let jitter = Double((row * 31 + column * 17) % 13) / 13
                        let x = Double(column) * step + jitter * step, y = Double(row) * step + (1 - jitter) * step
                        context.fill(Path(ellipseIn: CGRect(x: x, y: y, width: listSurface ? 0.64 : 0.44, height: listSurface ? 0.64 : 0.44)), with: .color(sceneColor(dark ? 0xF9ECE4 : 0x352233).opacity(listSurface ? 0.055 : 0.025)))
                    }
                }
            }
        }
        .clipped()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .onAppear { presented = true; updateClock() }
        .onChange(of: active) { _, _ in updateClock() }
        .onDisappear { presented = false; stopClock() }
    }
    private func stopClock() {
        if let start = runningSince { elapsed += max(0, Date().timeIntervalSince(start)); runningSince = nil }
    }
    private func updateClock() {
        if active { if runningSince == nil { runningSince = Date() } }
        else { stopClock() }
    }
}

private func sceneColor(_ value: UInt32) -> Color {
    Color(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
}
private enum FishFill: Sendable { case solid(UInt32), silver, fin }
private struct FishPart: Sendable {
    let path: Path
    let fill: FishFill
    var stroke: Double = 0
    var alpha: Double = 1
    var tail: Bool = false
}
private let fishParts: [FishPart] = [
FishPart(path: Path { p in p.move(to: CGPoint(x: 137, y: 81)); p.addCurve(to: CGPoint(x: 49, y: 20), control1: CGPoint(x: 103, y: 65), control2: CGPoint(x: 81, y: 37)); p.addLine(to: CGPoint(x: 76, y: 78)); p.addLine(to: CGPoint(x: 43, y: 148)); p.addCurve(to: CGPoint(x: 138, y: 97), control1: CGPoint(x: 84, y: 126), control2: CGPoint(x: 110, y: 104)); p.addLine(to: CGPoint(x: 161, y: 89)); p.closeSubpath() }, fill: .fin, alpha: 1.0, tail: true),
FishPart(path: Path { p in p.move(to: CGPoint(x: 55, y: 28)); p.addLine(to: CGPoint(x: 91, y: 84)); p.addLine(to: CGPoint(x: 49, y: 142)); p.move(to: CGPoint(x: 91, y: 84)); p.addLine(to: CGPoint(x: 139, y: 89)) }, fill: .solid(0xD6E3DF), stroke: 2, alpha: 0.45, tail: true),
FishPart(path: Path { p in p.move(to: CGPoint(x: 238, y: 48)); p.addLine(to: CGPoint(x: 276, y: 11)); p.addLine(to: CGPoint(x: 298, y: 49)); p.move(to: CGPoint(x: 346, y: 48)); p.addLine(to: CGPoint(x: 377, y: 31)); p.addLine(to: CGPoint(x: 390, y: 53)); p.move(to: CGPoint(x: 340, y: 119)); p.addLine(to: CGPoint(x: 368, y: 144)); p.addLine(to: CGPoint(x: 380, y: 116)) }, fill: .fin, alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 132, y: 81)); p.addCurve(to: CGPoint(x: 326, y: 43), control1: CGPoint(x: 193, y: 65), control2: CGPoint(x: 230, y: 43)); p.addCurve(to: CGPoint(x: 557, y: 72), control1: CGPoint(x: 427, y: 42), control2: CGPoint(x: 495, y: 54)); p.addLine(to: CGPoint(x: 603, y: 89)); p.addLine(to: CGPoint(x: 566, y: 101)); p.addCurve(to: CGPoint(x: 315, y: 124), control1: CGPoint(x: 497, y: 124), control2: CGPoint(x: 405, y: 130)); p.addCurve(to: CGPoint(x: 133, y: 97), control1: CGPoint(x: 238, y: 119), control2: CGPoint(x: 182, y: 101)); p.addLine(to: CGPoint(x: 111, y: 89)); p.closeSubpath() }, fill: .silver, alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 132, y: 81)); p.addCurve(to: CGPoint(x: 326, y: 43), control1: CGPoint(x: 193, y: 65), control2: CGPoint(x: 230, y: 43)); p.addCurve(to: CGPoint(x: 557, y: 72), control1: CGPoint(x: 427, y: 42), control2: CGPoint(x: 495, y: 54)); p.addLine(to: CGPoint(x: 603, y: 89)); p.addLine(to: CGPoint(x: 566, y: 101)); p.addCurve(to: CGPoint(x: 315, y: 124), control1: CGPoint(x: 497, y: 124), control2: CGPoint(x: 405, y: 130)); p.addCurve(to: CGPoint(x: 133, y: 97), control1: CGPoint(x: 238, y: 119), control2: CGPoint(x: 182, y: 101)); p.addLine(to: CGPoint(x: 111, y: 89)); p.closeSubpath() }, fill: .solid(0x5E7880), stroke: 1.5, alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 159, y: 81)); p.addCurve(to: CGPoint(x: 335, y: 53), control1: CGPoint(x: 229, y: 67), control2: CGPoint(x: 277, y: 52)); p.addCurve(to: CGPoint(x: 555, y: 77), control1: CGPoint(x: 427, y: 51), control2: CGPoint(x: 500, y: 62)) }, fill: .solid(0xD7E6E2), stroke: 2, alpha: 0.5, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 544, y: 70)); p.addCurve(to: CGPoint(x: 538, y: 108), control1: CGPoint(x: 529, y: 77), control2: CGPoint(x: 526, y: 98)); p.move(to: CGPoint(x: 550, y: 76)); p.addCurve(to: CGPoint(x: 548, y: 102), control1: CGPoint(x: 542, y: 85), control2: CGPoint(x: 541, y: 95)) }, fill: .solid(0x5D7881), stroke: 2, alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 533, y: 93)); p.addLine(to: CGPoint(x: 465, y: 105)); p.addLine(to: CGPoint(x: 496, y: 82)); p.closeSubpath() }, fill: .solid(0x5D7881), alpha: 0.8, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 533, y: 78)); p.addCurve(to: CGPoint(x: 430, y: 70), control1: CGPoint(x: 491, y: 71), control2: CGPoint(x: 461, y: 70)); p.addCurve(to: CGPoint(x: 391, y: 75), control1: CGPoint(x: 411, y: 69), control2: CGPoint(x: 405, y: 72)); p.addCurve(to: CGPoint(x: 357, y: 88), control1: CGPoint(x: 378, y: 79), control2: CGPoint(x: 368, y: 78)); p.addCurve(to: CGPoint(x: 305, y: 107), control1: CGPoint(x: 344, y: 102), control2: CGPoint(x: 329, y: 107)); p.addCurve(to: CGPoint(x: 155, y: 90), control1: CGPoint(x: 251, y: 104), control2: CGPoint(x: 207, y: 94)) }, fill: .solid(0x405E6B), stroke: 2.5, alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 453, y: 51)); p.addLine(to: CGPoint(x: 462, y: 41)); p.addLine(to: CGPoint(x: 472, y: 55)); p.move(to: CGPoint(x: 427, y: 48)); p.addLine(to: CGPoint(x: 435, y: 39)); p.addLine(to: CGPoint(x: 444, y: 50)); p.move(to: CGPoint(x: 404, y: 47)); p.addLine(to: CGPoint(x: 412, y: 38)); p.addLine(to: CGPoint(x: 421, y: 49)); p.move(to: CGPoint(x: 438, y: 122)); p.addLine(to: CGPoint(x: 447, y: 132)); p.addLine(to: CGPoint(x: 456, y: 119)); p.move(to: CGPoint(x: 411, y: 126)); p.addLine(to: CGPoint(x: 419, y: 136)); p.addLine(to: CGPoint(x: 429, y: 124)); p.move(to: CGPoint(x: 385, y: 126)); p.addLine(to: CGPoint(x: 392, y: 135)); p.addLine(to: CGPoint(x: 401, y: 125)) }, fill: .solid(0x647F89), alpha: 1.0, tail: false),
FishPart(path: Path { p in p.move(to: CGPoint(x: 572, y: 93)); p.addLine(to: CGPoint(x: 600, y: 89)) }, fill: .solid(0x526D77), stroke: 2, alpha: 1.0, tail: false),
]
private func drawMackerel(in context: inout GraphicsContext, seconds: Double) {
    for part in fishParts {
        var local = context
        local.opacity *= part.alpha
        if part.tail {
            local.translateBy(x: 138, y: 88); local.scaleBy(x: 0.91 + sin(seconds * 3.7) * 0.09, y: 1); local.translateBy(x: -138, y: -88)
        }
        let shading: GraphicsContext.Shading
        switch part.fill {
        case .solid(let hex): shading = .color(sceneColor(hex))
        case .silver: shading = .linearGradient(Gradient(stops: [
            .init(color: sceneColor(0x56656C), location: 0), .init(color: sceneColor(0x91A6AB), location: 0.36),
            .init(color: sceneColor(0xE4E9E4), location: 0.56), .init(color: sceneColor(0xB5C7C7), location: 0.76),
            .init(color: sceneColor(0x728F95), location: 1)]), startPoint: CGPoint(x: 300, y: 38), endPoint: CGPoint(x: 300, y: 128))
        case .fin: shading = .linearGradient(Gradient(colors: [sceneColor(0x526D77), sceneColor(0xA5BABD)]), startPoint: CGPoint(x: 100, y: 45), endPoint: CGPoint(x: 130, y: 122))
        }
        if part.stroke > 0 { local.stroke(part.path, with: shading, style: StrokeStyle(lineWidth: part.stroke, lineCap: .round)) }
        else { local.fill(part.path, with: shading) }
    }
    context.fill(Path(ellipseIn: CGRect(x: 555, y: 74, width: 10, height: 10)), with: .color(sceneColor(0x243E4B)))
    context.fill(Path(ellipseIn: CGRect(x: 559.2, y: 76.2, width: 3.6, height: 3.6)), with: .color(sceneColor(0xF6F5E9)))
}
