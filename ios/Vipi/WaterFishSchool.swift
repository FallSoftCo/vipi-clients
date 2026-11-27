import Foundation

/// The drawing faces right in its original 640 × 170 coordinate system.
struct WaterFishPass: Equatable, Sendable {
    let start, duration, widthFraction, lane, amplitude, arcPhase, tailPhase, tailRate: Double
    let heading: Double

    struct Pose {
        let centerX, centerY, width, tilt, tailAngle: Double
    }

    func pose(at time: Double, width viewport: Double, height: Double) -> Pose? {
        let progress = (time - start) / duration
        guard (0...1).contains(progress), viewport > 0, height > 0 else { return nil }
        let width = min(viewport * widthFraction, 350)
        let travel = viewport + width + 16
        let center = viewport / 2 + heading * (progress - 0.5) * travel
        let arc = arcPhase + progress * .pi * 1.5
        let y = height * (lane + amplitude * sin(arc))
        let slope = height * amplitude * .pi * 1.5 * cos(arc) / travel
        return Pose(
            centerX: center, centerY: y, width: width,
            tilt: min(0.07, max(-0.07, atan(slope))),
            tailAngle: tailPhase + (time - start) * tailRate)
    }
}

struct WaterFishSchool {
    static let cycleLength = 92.0
    let seed: UInt64

    /// Build once on entering a cycle. The two opening passes share a brief
    /// crossing, then singles and occasional pairs leave clear water between.
    func passes(cycle: UInt64) -> [WaterFishPass] {
        var state = seed &+ cycle &* 0xD1342543DE82EF95
        func sample() -> Double {
            state &+= 0x9E3779B97F4A7C15
            var value = state
            value = (value ^ (value >> 30)) &* 0xBF58476D1CE4E5B9
            value = (value ^ (value >> 27)) &* 0x94D049BB133111EB
            return Double((value ^ (value >> 31)) >> 11) / 9_007_199_254_740_992
        }
        let starts = [0.0, 3.2, 25.5, 39, 53.5, 70, 78.5]
        let durations = [15.0, 13, 11, 14, 10, 13, 10]
        let lanes = [0.55, 0.34, 0.71, 0.42, 0.63, 0.32, 0.73]
        let firstHeading = sample() < 0.5 ? -1.0 : 1.0
        return starts.indices.map { index in
            let heading: Double
            switch index {
            case 0: heading = firstHeading
            case 1: heading = -firstHeading
            default: heading = sample() < 0.5 ? -1 : 1
            }
            let width = (index == 0 ? 0.54 : index == 1 ? 0.34 : 0.31) + sample() * (index < 2 ? 0.10 : 0.34)
            return WaterFishPass(
                start: starts[index] + (index == 0 ? 0 : sample()),
                duration: durations[index] + sample() * (index == 6 ? 2 : 4),
                widthFraction: width, lane: lanes[index] + (sample() - 0.5) * 0.08,
                amplitude: 0.014 + sample() * 0.018, arcPhase: sample() * 2 * .pi,
                tailPhase: sample() * 2 * .pi, tailRate: 2.9 + sample() * 2.1,
                heading: heading)
        }
    }
}

/// Both backgrounds follow the same foreground clock. Navigation can briefly
/// mount both views, so the last visible consumer owns the pause.
@MainActor
final class ConversationWaterClock {
    static let shared = ConversationWaterClock(seed: UInt64.random(in: .min ... .max))
    private let school: WaterFishSchool
    private var consumers = 0
    private var runningSince: TimeInterval?
    private var accumulated = 8.0
    private var cachedCycle: UInt64?
    private var cachedPasses: [WaterFishPass] = []

    init(seed: UInt64) { school = WaterFishSchool(seed: seed) }

    func time(at now: TimeInterval) -> TimeInterval {
        accumulated + (runningSince.map { max(0, now - $0) } ?? 0)
    }

    func join(at now: TimeInterval) {
        if consumers == 0 { runningSince = now }
        consumers += 1
    }

    func leave(at now: TimeInterval) {
        guard consumers > 0 else { return }
        consumers -= 1
        if consumers == 0 {
            accumulated = time(at: now)
            runningSince = nil
        }
    }

    func frame(at elapsed: TimeInterval) -> (time: Double, passes: [WaterFishPass]) {
        let cycle = UInt64(elapsed / WaterFishSchool.cycleLength)
        if cachedCycle != cycle {
            cachedPasses = school.passes(cycle: cycle)
            cachedCycle = cycle
        }
        return (elapsed.truncatingRemainder(dividingBy: WaterFishSchool.cycleLength), cachedPasses)
    }
}
