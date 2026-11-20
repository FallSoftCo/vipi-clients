import XCTest
@testable import Vipi

@MainActor final class ImmersionTutorialCoreTests: XCTestCase {
    func testKnownSourceSamplesCoverListedLanguagesAndModeWireKeysStayStable() {
        XCTAssertEqual(Set(ImmersionTutorialSource.messages.keys),Set(LocalLanguageCatalog.codes))
        XCTAssertEqual(ImmersionMode.incremental.rawValue,"incremental")
        XCTAssertEqual(ImmersionMode.fullMessages.rawValue,"fullMessages")
        XCTAssertEqual(ImmersionMode.incremental.symbolName,"water.waves")
        XCTAssertEqual(ImmersionMode.fullMessages.symbolName,"anchor")
        XCTAssertEqual(ImmersionTutorialSource.messageID(source:"en",target:"es"),ImmersionTutorialSource.messageID(source:"en",target:"es"))
    }
    func testTutorialModeAndStepPersistWithoutChangingPendingInvitation() {
        let name = "tutorial-state-"+UUID().uuidString
        let defaults = UserDefaults(suiteName:name)!
        defer { defaults.removePersistentDomain(forName:name) }
        let state = AppState(defaults:defaults)
        state.invitationUsername = "qa_friend"; state.onboarding = .tutorial; state.immersionMode = .fullMessages
        let reopened = AppState(defaults:defaults)
        XCTAssertEqual(reopened.onboarding,.tutorial); XCTAssertEqual(reopened.immersionMode,.fullMessages)
        XCTAssertEqual(reopened.invitationUsername,"qa_friend"); XCTAssertFalse(reopened.isAuthenticated)
    }
}
