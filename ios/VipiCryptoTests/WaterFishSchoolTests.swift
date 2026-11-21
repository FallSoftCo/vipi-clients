import XCTest
@testable import Vipi

final class WaterFishSchoolTests: XCTestCase {
    func testSeededCrossingsVaryWithoutJumpingOrCrowding() throws {
        for seed: UInt64 in [0, .max, 17, 203] {
            let school = WaterFishSchool(seed: seed)
            let passes = school.passes(cycle: 0)
            XCTAssertEqual(passes, school.passes(cycle: 0))
            XCTAssertNotEqual(passes, school.passes(cycle: 1))
            XCTAssertNotEqual(passes, WaterFishSchool(seed: seed &+ 1).passes(cycle: 0))
            XCTAssertEqual(passes[0].heading, -passes[1].heading)
            XCTAssertNotEqual(passes[0].tailRate, passes[1].tailRate)
            for viewport in [320.0, 393, 760] {
                for pass in passes {
                    let first = try XCTUnwrap(pass.pose(at: pass.start, width: viewport, height: 720))
                    let midpoint = pass.start + pass.duration / 2
                    let middle = try XCTUnwrap(pass.pose(at: midpoint, width: viewport, height: 720))
                    let later = try XCTUnwrap(pass.pose(at: midpoint + 0.2, width: viewport, height: 720))
                    XCTAssertGreaterThan((later.centerX - middle.centerX) * pass.heading, 0)
                    XCTAssertEqual(middle.centerX, viewport / 2, accuracy: 0.001)
                    XCTAssertTrue(first.centerX + first.width / 2 < 0 || first.centerX - first.width / 2 > viewport)
                    XCTAssertLessThanOrEqual(abs(middle.tilt), 0.07)
                }
                for pass in passes.prefix(2) {
                    let entering = try XCTUnwrap(pass.pose(at: 8, width: viewport, height: 720))
                    XCTAssertTrue(entering.centerX + entering.width / 2 > 0 && entering.centerX - entering.width / 2 < viewport)
                }
            }
            for t in stride(from: 0.0, to: WaterFishSchool.cycleLength, by: 0.1) {
                let active = passes.filter { $0.pose(at: t, width: 393, height: 720) != nil }
                XCTAssertLessThanOrEqual(active.count, 2)
                if (22...25).contains(t) { XCTAssertTrue(active.isEmpty) }
            }
        }
    }

    @MainActor
    func testNavigationSharesPhaseAndLastConsumerFreezesTime() {
        let clock = ConversationWaterClock(seed: 123)
        clock.join(at: 11)
        clock.join(at: 13)
        XCTAssertEqual(clock.time(at: 14), 11)
        clock.leave(at: 15)
        XCTAssertEqual(clock.time(at: 16), 13)
        clock.leave(at: 17)
        XCTAssertEqual(clock.time(at: 111), 14)
        clock.join(at: 112)
        XCTAssertEqual(clock.time(at: 113), 15)
        XCTAssertEqual(clock.frame(at: 15).passes, clock.frame(at: 91).passes)
        XCTAssertNotEqual(clock.frame(at: 15).passes, clock.frame(at: 93).passes)
    }
}
