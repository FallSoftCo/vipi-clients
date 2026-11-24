import Foundation
import XCTest
@testable import Vipi

@MainActor final class ConversationLanguagePreferencesTests: XCTestCase {
    private struct UnusedTransport: ChatTransport {
        func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?,
                                   query: [String: String], as type: T.Type) async throws -> T {
            throw ServiceFailure(status: 0, code: "transport_not_used")
        }
    }

    func testDirectAndGroupOverridesAreEncryptedNamespacedAndDurable() throws {
        let account = UUID()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ConversationLanguages-\(UUID())")
        addTeardownBlock {
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        // A direct peer and a group can legitimately share a UUID. Their
        // preferences must remain separate and survive reopening the vault.
        let sharedID = UUID(), direct = ConversationRef.direct(sharedID), group = ConversationRef.group(sharedID)
        do {
            let vault = try MessageVault(account: account, directory: root)
            let store = ConversationLanguageStore(vault: vault)
            try store.set(direct, target: "fr")
            try store.set(group, target: "ja")
            XCTAssertEqual(try store.all(), [direct.storageKey: "fr", group.storageKey: "ja"])
            try vault.close()
        }
        let reopened = try MessageVault(account: account, directory: root)
        defer { try? reopened.close() }
        let store = ConversationLanguageStore(vault: reopened)
        XCTAssertEqual(try store.all(), [direct.storageKey: "fr", group.storageKey: "ja"])
        try store.clear(direct)
        XCTAssertNil(try store.all()[direct.storageKey])
        XCTAssertEqual(try store.all()[group.storageKey], "ja")
    }

    func testConversationOverrideFallsBackToAccountDefaultAndCanReset() async throws {
        let account = UUID(), userID = "conversation-language-" + UUID().uuidString
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ConversationLanguageSession-\(UUID())")
        addTeardownBlock {
            try? FileManager.default.removeItem(at: root)
            KeychainStore.delete(account: "messages-" + account.uuidString.lowercased())
        }
        let vault = try MessageVault(account: account, directory: root)
        let profile = ChatProfile(id: account, username: "language_qa", display_name: "Language QA")
        let chat = ChatSession(qualificationAPI: UnusedTransport(), userID: userID, profile: profile, vault: vault)
        let services = MessageTranslationServices(status: { _ in .unsupported })
        await chat.configureTranslation(pair: .init(source: "en", target: "es"), services: services)

        let sharedID = UUID(), direct = ConversationRef.direct(sharedID), group = ConversationRef.group(sharedID)
        XCTAssertEqual(chat.targetLanguage(direct), "es")
        XCTAssertTrue(chat.usesDefaultLanguage(direct))
        chat.setConversationLanguage(direct, target: "fr")
        chat.setConversationLanguage(group, target: "ja")
        XCTAssertEqual(chat.targetLanguage(direct), "fr")
        XCTAssertEqual(chat.targetLanguage(group), "ja")
        XCTAssertFalse(chat.usesDefaultLanguage(direct))
        XCTAssertFalse(chat.usesDefaultLanguage(group))

        chat.useDefaultConversationLanguage(direct)
        XCTAssertEqual(chat.targetLanguage(direct), "es")
        XCTAssertTrue(chat.usesDefaultLanguage(direct))
        XCTAssertEqual(chat.targetLanguage(group), "ja")

        await chat.configureTranslation(pair: .init(source: "en", target: "it"), services: services)
        XCTAssertEqual(chat.targetLanguage(direct), "it")
        XCTAssertEqual(chat.targetLanguage(group), "ja")
        try chat.close()
    }

    func testOnboardingShareUsesTheHomepageAndNeverAssumesAStore() {
        let message = MamboOnboardingCopy.shareMessage
        XCTAssertTrue(message.contains(MamboOnboardingCopy.homeURL))
        XCTAssertEqual(URL(string: MamboOnboardingCopy.homeURL)?.host, "mambovipi.app")
        for platformLink in ["play.google.com", "apps.apple.com", "itunes.apple.com", "itms-apps://", "market://"] {
            XCTAssertFalse(message.contains(platformLink), platformLink)
        }
    }
}
