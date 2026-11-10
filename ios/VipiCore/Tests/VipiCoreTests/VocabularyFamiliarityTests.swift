import XCTest
@testable import VipiCore

final class VocabularyFamiliarityTests: XCTestCase {
    func testRepeatedFlipsAndBackwardClockCannotClaimExtraExposure() {
        var value = VocabularyFamiliarity()
        XCTAssertTrue(value.observe(day: 100))
        for day in [100, 100, 99, -1] { XCTAssertFalse(value.observe(day: day)) }
        XCTAssertEqual(value.exposureDays, 1)
    }
    func testSpacedExposureGivesMoreTargetTimeAndAbsenceRestoresBeginnerPace() throws {
        var value = VocabularyFamiliarity()
        for day in 100...103 { _ = value.observe(day: day) }
        XCTAssertEqual(value.targetMilliseconds(day: 103), 6000)
        value = try JSONDecoder().decode(VocabularyFamiliarity.self, from: JSONEncoder().encode(value))
        for day in 104...111 { _ = value.observe(day: day) }
        XCTAssertEqual(value.targetMilliseconds(day: 111), 9000)
        XCTAssertEqual(value.targetMilliseconds(day: 142), 4500)
        XCTAssertEqual(value.targetMilliseconds(day: 90), 4500)
        XCTAssertEqual(value.exposureDays, 12)
    }
}
