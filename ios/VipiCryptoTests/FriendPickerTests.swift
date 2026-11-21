import Contacts
import XCTest
@testable import Vipi

@MainActor final class FriendPickerTests: XCTestCase {
    func testDraftKeepsOnlyExplicitRecipientForItsNativeComposer() {
        let body = FriendInvitation.message(username: "fixture")
        let tel = "+1 202-555-0147", mail = "friend@example.invalid"
        let sms = InviteDraft.make(channel: .message, body: body, recipient: tel, canMessage: true, canMail: true)
        XCTAssertEqual(sms.channel, .message); XCTAssertEqual(sms.recipient, tel)
        let email = InviteDraft.make(channel: .mail, body: body, recipient: mail, canMessage: true, canMail: true)
        XCTAssertEqual(email.channel, .mail); XCTAssertEqual(email.recipient, mail)
        for (channel, address) in [(InviteDraft.Channel.message, tel), (.mail, mail)] {
            let share = InviteDraft.make(channel: channel, body: body, recipient: address, canMessage: false, canMail: false)
            XCTAssertEqual(share.channel, .share); XCTAssertNil(share.recipient)
            XCTAssertFalse(share.body.contains(address))
            XCTAssertTrue(share.body.contains("https://api.mambovipi.app/invite/fixture"))
        }
    }

    func testPrepareOrRemoveOwnedContactsForLimitedPicker() throws {
        #if targetEnvironment(simulator)
        let phase = ProcessInfo.processInfo.environment["VIPI_LIMITED_PICKER_FIXTURE"]
        try XCTSkipUnless(["prepare", "remove"].contains(phase) && Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
                          "Requires the isolated native contact picker UI run")
        let store = CNContactStore()
        XCTAssertEqual(CNContactStore.authorizationStatus(for: .contacts), .authorized)
        let marker = URL.documentsDirectory.appendingPathComponent("vipi-picker-owned-fixture.json")
        let names = ["Vipi Cedar Fixture", "Vipi Maple Fixture"]
        let change = CNSaveRequest()
        if phase == "prepare" {
            XCTAssertFalse(FileManager.default.fileExists(atPath: marker.path))
            let contacts = names.enumerated().map { index, name in
                let contact = CNMutableContact(); contact.givenName = name
                contact.emailAddresses = [CNLabeledValue(label: CNLabelHome, value: "picker-\(index)@example.invalid" as NSString)]
                change.add(contact, toContainerWithIdentifier: nil)
                return contact
            }
            try store.execute(change)
            try JSONEncoder().encode(contacts.map(\.identifier)).write(to: marker, options: .withoutOverwriting)
        } else {
            let ids = try JSONDecoder().decode([String].self, from: Data(contentsOf: marker))
            for (index, id) in ids.enumerated() {
                let contact = try store.unifiedContact(withIdentifier: id, keysToFetch: [CNContactGivenNameKey as CNKeyDescriptor])
                let owned = try XCTUnwrap(contact.givenName == names[index] ? contact.mutableCopy() as? CNMutableContact : nil)
                change.delete(owned)
            }
            try store.execute(change); try FileManager.default.removeItem(at: marker)
        }
        #else
        throw XCTSkip("Owned fixture requires an isolated simulator")
        #endif
    }

    func testLimitedAndDeniedContactAccessOnOwnedSimulator() async throws {
        #if targetEnvironment(simulator)
        let env = ProcessInfo.processInfo.environment
        try XCTSkipUnless(env["VIPI_CONTACTS_ACCESS"] != nil && Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
                          "Requires an explicit OS permission state on an isolated QA simulator")
        let expected = try XCTUnwrap(["limited": CNAuthorizationStatus.limited, "denied": .denied][env["VIPI_CONTACTS_ACCESS"] ?? ""])
        XCTAssertEqual(Bundle.main.bundleIdentifier, "co.fallsoft.vipi.uxqa")
        XCTAssertEqual(CNContactStore.authorizationStatus(for: .contacts), expected)
        let session = PhoneInviteContacts()
        session.enabled = true; session.refresh()
        while session.loading { try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertEqual(session.status, expected)
        if expected == .denied {
            XCTAssertTrue(session.targets.isEmpty)
            let read = try await PhoneInviteContacts.readTargets(); XCTAssertTrue(read.isEmpty)
        }
        #else
        throw XCTSkip("Synthetic address book test is simulator-only")
        #endif
    }

    func testGrantedDeviceContactsAndClearingOnOwnedSimulator() async throws {
        #if targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        try XCTSkipUnless(environment["VIPI_SYNTHETIC_CONTACTS"] == "1" &&
                          Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",
                          "Requires the isolated Vipi QA simulator with explicit synthetic contacts permission")
        let store = CNContactStore()
        XCTAssertEqual(CNContactStore.authorizationStatus(for: .contacts), .authorized)
        let contact = CNMutableContact()
        contact.givenName = "VipiQA" + UUID().uuidString.prefix(8)
        contact.familyName = "Invitation"
        contact.phoneNumbers = [CNLabeledValue(label: CNLabelPhoneNumberMobile, value: CNPhoneNumber(stringValue: "+1 202-555-0147"))]
        contact.emailAddresses = [CNLabeledValue(label: CNLabelHome, value: "invite@example.invalid")]
        let add = CNSaveRequest(); add.add(contact, toContainerWithIdentifier: nil); try store.execute(add)
        defer { let remove = CNSaveRequest(); remove.delete(contact); XCTAssertNoThrow(try store.execute(remove)) }

        let session = PhoneInviteContacts()
        XCTAssertTrue(session.targets.isEmpty)
        session.enabled = true; session.refresh()
        let deadline = ContinuousClock.now.advanced(by: .seconds(8))
        while !session.targets.contains(where: { $0.name.contains(contact.givenName) }) && ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        let matches = session.targets.filter { $0.matches(contact.givenName) }
        XCTAssertEqual(matches.count, 2)
        let number = try XCTUnwrap(matches.first(where: { $0.channel == .message }))
        let current = try await PhoneInviteContacts.readTargets(contactID: number.contactID)
        XCTAssertEqual(Set(current.map(\.id)), Set(matches.map(\.id)))
        XCTAssertTrue(number.matches("2025550147")); XCTAssertFalse(number.matches("unknown@example.invalid"))
        let email = try XCTUnwrap(matches.first(where: { $0.channel == .mail }))
        XCTAssertTrue(email.matches("INVITE@EXAMPLE")); XCTAssertEqual(email.address, "invite@example.invalid")
        session.clear(); XCTAssertTrue(session.targets.isEmpty)
        #else
        throw XCTSkip("Synthetic address book test is simulator-only")
        #endif
    }
}
