import XCTest
import VipiCore
@testable import Vipi

final class ChatFeedbackTests: XCTestCase {
    @MainActor private final class Relay: ChatTransport {
        var available: Bool?
        var failPut = true
        var answers: [String] = []
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T {
            guard path == ChatFeedback.route else { throw MessageVault.Failure.invalidRecord }
            if method == "GET", let available {
                return try JSONDecoder().decode(type, from: JSONEncoder().encode(["available": available]))
            }
            if method == "PUT", let body, let choice = try JSONDecoder().decode([String: String].self, from: body)["choice"] {
                answers.append(choice)
                if !failPut, let ack = NoContentResponse() as? T { return ack }
            }
            throw ServiceFailure(status: 404, code: "not_found")
        }
    }

    @MainActor func testCapabilityDecisionOutboxAndIndependentReviewWithoutStoreKit() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let account = UUID(), other = UUID()
        let vault = try MessageVault(account: account, directory: folder)
        let unrelated = try MessageVault(account: other, directory: folder)
        defer {
            try? vault.close(); try? unrelated.close(); try? FileManager.default.removeItem(at: folder)
            for id in [account, other] { try? KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased()) }
        }
        let relay = Relay()
        func make(_ vault: MessageVault) -> ChatSession {
            ChatSession(qualificationAPI: relay, userID: vault.account.uuidString, ready: true,
                        profile: .init(id: vault.account, username: "qa", display_name: "QA"), vault: vault)
        }
        let chat = make(vault), second = make(unrelated)
        for store in [vault, unrelated] {
            try store.transaction {
                var record = ChatFeedback()
                for i in 0..<(store === vault ? 20 : 40) { record.accepted(authoredAt: Int64(i % 14) * 86_400_000) }
                try record.save(store)
            }
        }
        let oldRelay = await chat.considerChatIntervention { true }
        XCTAssertNil(oldRelay)
        let reviewOnOldRelay = await second.considerChatIntervention { true }
        XCTAssertEqual(reviewOnOldRelay, .review) // Only inspect scheduling; never call StoreKit here.
        relay.available = true
        let busy = await chat.considerChatIntervention { false }
        XCTAssertNil(busy)
        let survey = await chat.considerChatIntervention { true }
        XCTAssertEqual(survey, .survey)
        chat.chooseFundingResponse(.skip)
        for _ in 0..<10 where relay.answers.isEmpty { await Task.yield() }
        XCTAssertFalse(chat.showingFundingSurvey)
        XCTAssertEqual(try vault.transaction { try ChatFeedback.load(vault).pending }, .skip)
        let before = relay.answers.count
        await second.retryFundingResponse()
        XCTAssertEqual(relay.answers.count, before)
        relay.failPut = false
        let recovered = make(vault)
        await recovered.retryFundingResponse()
        XCTAssertEqual(relay.answers.last, "skip")
        XCTAssertNil(try vault.transaction { try ChatFeedback.load(vault).pending })
        let repeatAttempt = await recovered.considerChatIntervention { true }
        XCTAssertNil(repeatAttempt)
    }

    func testIndependentThresholdsSpacingAndEverySurveyChoice() throws {
        let date = Date(timeIntervalSince1970: 1_799_999_999), session = UUID()
        var below = ChatFeedback()
        for n in 0..<19 { below.accepted(authoredAt: Int64(n % 7) * 86_400_000) }
        XCTAssertFalse(below.eligible(.survey, now: date, session: session))
        var oneDay = ChatFeedback()
        for _ in 0..<40 { oneDay.accepted(authoredAt: 0) }
        XCTAssertFalse(oneDay.eligible(.survey, now: date, session: session))
        below.accepted(authoredAt: 86_400_000)
        XCTAssertTrue(below.eligible(.survey, now: date, session: session))
        XCTAssertFalse(below.eligible(.review, now: date, session: session))
        for n in 0..<20 { below.accepted(authoredAt: Int64(n % 14) * 86_400_000) }
        for choice in FundingChoice.allCases {
            var record = below
            XCTAssertTrue(record.claim(.survey, now: date, session: session))
            record.choose(choice)
            let restored = try JSONDecoder().decode(ChatFeedback.self, from: JSONEncoder().encode(record))
            XCTAssertEqual(restored.pending, choice)
            XCTAssertFalse(restored.eligible(.review, now: date.addingTimeInterval(604_799), session: UUID()))
            XCTAssertFalse(restored.eligible(.review, now: date.addingTimeInterval(604_800), session: session))
            XCTAssertTrue(restored.eligible(.review, now: date.addingTimeInterval(604_800), session: UUID()))
            XCTAssertFalse(restored.eligible(.survey, now: date.addingTimeInterval(604_800), session: UUID()))
        }
        XCTAssertTrue(below.claim(.review, now: date, session: session))
        XCTAssertFalse(below.eligible(.survey, now: date.addingTimeInterval(604_799), session: UUID()))
        XCTAssertTrue(below.eligible(.survey, now: date.addingTimeInterval(604_800), session: UUID()))
        XCTAssertFalse(below.eligible(.review, now: date.addingTimeInterval(900_000), session: UUID()))
    }

    func testFirstAcceptedTransitionAndAccountIsolation() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let account = UUID(), peer = UUID()
        defer { for id in [account, peer] { try? KeychainStore.deleteChecked(account: "messages-" + id.uuidString.lowercased()) } }
        let vault = try MessageVault(account: account, directory: directory)
        let other = try MessageVault(account: peer, directory: directory)
        defer { try? other.close() }
        let journal = MessageJournal(vault: vault)
        for n in 0..<21 {
            let id = UUID(), time = Int64(n % 7) * 86_400_000
            _ = try journal.queue(id: id, recipient: peer, text: "Fixture", createdAt: time, now: time) { _ in (2, Data(repeating: 0, count: 64)) }
            if n == 20 { try journal.applyStatus(id, state: "failed"); continue }
            try journal.applyStatus(id, state: "accepted")
            try journal.applyStatus(id, state: "accepted")
            try journal.applyStatus(id, state: "delivered")
        }
        try vault.close()
        let reopened = try MessageVault(account: account, directory: directory)
        defer { try? reopened.close() }
        let result = try reopened.transaction { try ChatFeedback.load(reopened) }
        XCTAssertEqual(result.sends, 20); XCTAssertEqual(result.sendDays.count, 7)
        XCTAssertEqual(try other.transaction { try ChatFeedback.load(other).sends }, 0)
    }

    func testUpgradedAccountBackfillsOnlyNativeAcceptedRowsAcrossReopen() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let account = UUID(), peer = UUID(), group = UUID()
        defer {
            try? FileManager.default.removeItem(at: folder)
            try? KeychainStore.deleteChecked(account: "messages-" + account.uuidString.lowercased())
        }
        let vault = try MessageVault(account: account, directory: folder)
        let journal = MessageJournal(vault: vault)
        let historical = UUID()
        for index in 0..<59 {
            let id = index == 0 ? historical : UUID(), now = Int64(index % 7) * 86_400_000
            _ = try journal.queue(id: id, recipient: peer, text: "Synthetic legacy row", createdAt: now, now: now) { _ in (2, Data(repeating: 0, count: 64)) }
            if index == 0 {
                try journal.applyStatus(id, state: "accepted") // Counted by live code before migration.
            } else if index < 19 {
                try vault.transaction {
                    let key = id.uuidString.lowercased()
                    let bytes = try XCTUnwrap(vault.get("outgoing", key))
                    var saved = try JSONDecoder().decode(StoredChat.self, from: bytes)
                    saved.state = index % 2 == 0 ? "delivered" : "read"
                    try vault.put("outgoing", key, JSONEncoder().encode(saved))
                    try vault.put("imported-message", UUID().uuidString, JSONEncoder().encode(saved))
                }
            }
        }
        let accepted = GroupMessage(id: UUID(), groupID: group, epoch: 1, membershipRevision: 1, sender: account, text: "Group fixture", createdAt: 0, delivery: .accepted)
        try GroupsStore(vault: vault).saveMessage(accepted)
        XCTAssertTrue(try ChatFeedback.backfillPage(vault))
        try vault.close()
        let reopened = try MessageVault(account: account, directory: folder)
        defer { try? reopened.close() }
        for _ in 0..<5 { _ = try ChatFeedback.backfillPage(reopened) }
        XCTAssertFalse(try ChatFeedback.backfillPage(reopened))
        let result = try reopened.transaction { try ChatFeedback.load(reopened) }
        XCTAssertEqual(result.sends, 20)
        XCTAssertEqual(result.sendDays.count, 7)
    }

    @MainActor func testRecallingDuringQuietWindowDoesNotSpendAnImpression() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let account = UUID()
        let vault = try MessageVault(account: account, directory: directory)
        defer {
            try? vault.close(); try? FileManager.default.removeItem(at: directory)
            try? KeychainStore.deleteChecked(account: "messages-" + account.uuidString.lowercased())
        }
        let day = RevealHintHistory.today()
        let first = RevealHintVisit(); first.vault = vault
        await first.check(on: day - 1) { XCTFail("First exposure should be immediate") }
        XCTAssertTrue(first.visible)
        let visit = RevealHintVisit(); visit.vault = vault
        await visit.check(on: day) { visit.revealed(keepSpace: true) }
        XCTAssertFalse(visit.visible); XCTAssertFalse(visit.offered)
        let history = try vault.transaction { try RevealHintHistory.load(vault) }
        XCTAssertEqual(history.dailyCount, 1); XCTAssertEqual(history.unpromptedDays, [day])
        let lostFocus = RevealHintVisit(); lostFocus.vault = vault
        await lostFocus.check(on: day) { throw CancellationError() }
        XCTAssertFalse(lostFocus.offered)
        let shown = RevealHintVisit(); shown.vault = vault
        await shown.check(on: day) {}
        XCTAssertTrue(shown.visible)
        shown.revealed(keepSpace: true); XCTAssertTrue(shown.reservedDuringReveal)
        shown.released(); XCTAssertFalse(shown.reservedDuringReveal)
        let another = RevealHintVisit(); another.vault = vault
        await another.check(on: day) { XCTFail("Same-day revisit must stay quiet") }
        XCTAssertFalse(another.offered); another.dismiss()
        let final = try vault.transaction { try RevealHintHistory.load(vault) }
        XCTAssertTrue(final.retired)
    }

    func testHintCadenceReopenMasteryDismissAndLocalCalendar() throws {
        var history = RevealHintHistory()
        for day in 1...21 { XCTAssertTrue(history.offer(on: day)); XCTAssertFalse(history.offer(on: day)) }
        var reopened = try JSONDecoder().decode(RevealHintHistory.self, from: JSONEncoder().encode(history))
        XCTAssertFalse(reopened.offer(on: 22)); XCTAssertFalse(reopened.offer(on: 27))
        XCTAssertTrue(reopened.offer(on: 28)); XCTAssertFalse(reopened.offer(on: 29))
        reopened.reveal(on: 28, prompted: true); XCTAssertEqual(reopened.unpromptedDays.count, 0)
        for day in 28...30 { reopened.reveal(on: day, prompted: false); reopened.reveal(on: day, prompted: false) }
        XCTAssertTrue(reopened.retired); XCTAssertFalse(reopened.offer(on: 100))
        var dismissed = RevealHintHistory(); dismissed.dismissed = true
        XCTAssertFalse(dismissed.offer(on: 1))
        let format = ISO8601DateFormatter()
        let zone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
        let before = try XCTUnwrap(format.date(from: "2026-03-08T04:59:00Z"))
        let after = try XCTUnwrap(format.date(from: "2026-03-08T05:01:00Z"))
        XCTAssertEqual(RevealHintHistory.today(after, timeZone: zone) - RevealHintHistory.today(before, timeZone: zone), 1)
    }
}
