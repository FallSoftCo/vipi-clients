import XCTest
@testable import Vipi

@MainActor final class MessageActionTests: XCTestCase {
    func testReactionReplayAndClearSurviveTargetAndRestart() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let owner = UUID(), peer = UUID(), device = UUID(), target = UUID()
        var vault = try MessageVault(account: owner, directory: folder)
        defer {
            try? vault.close()
            try? FileManager.default.removeItem(at: folder)
            try? KeychainStore.deleteChecked(account: "messages-" + owner.uuidString.lowercased())
        }
        func update(_ sequence: Int64, _ emoji: String?, event: UUID = UUID()) throws {
            try vault.transaction {
                try MessageReactions.apply(
                    vault, scope: .direct, conversation: peer, actor: peer, device: device, event: event,
                    reaction: .init(message_id: target, target_sender_id: owner, sequence: sequence, emoji: emoji),
                    targetKnown: false)
            }
        }
        let journal = MessageJournal(vault: vault), history = try ConversationHistory(vault: vault)
        try history.saveComposeDraft("Reaction", peer: peer)
        let when = Int64(Date().timeIntervalSince1970 * 1000)
        try journal.saveDraft(
            id: UUID(), recipient: peer, text: "Reaction", createdAt: when, now: when, consumeCompose: true,
            features: .init(reaction: .init(message_id: target, target_sender_id: owner, sequence: 1, emoji: "👍")))
        XCTAssertEqual(try history.composeDraft(peer), "Reaction")
        XCTAssertTrue(try history.threads().isEmpty)
        let clear = UUID()
        try update(3, nil, event: clear)
        try update(1, "👍")
        try update(2, "❤️")
        try update(3, nil, event: clear)
        try vault.transaction {
            try MessageReactions.resolve(vault, id: MessageReactions.key(.direct, peer, target, owner))
        }
        try vault.close()
        vault = try MessageVault(account: owner, directory: folder)
        let entries = try MessageReactions.entries(
            vault, scope: .direct, conversation: peer, target: target, author: owner)
        XCTAssertEqual(entries.map(\.event), [clear])
        XCTAssertNil(entries[0].emoji)
        XCTAssertTrue(
            try MessageReactions.entries(vault, scope: .group, conversation: peer, target: target, author: owner)
                .isEmpty)
        XCTAssertTrue(
            try MessageReactions.entries(vault, scope: .direct, conversation: peer, target: target, author: peer)
                .isEmpty)
    }
    func testQuotedLinkFallbackAndCancellableComposer() async throws {
        let url = try XCTUnwrap(URL(string: "https://example.com/"))
        var loads = 0
        let draft = MessageActionDraft { destination in
            loads += 1
            try await Task.sleep(for: .milliseconds(25))
            return .init(url: destination.absoluteString, title: "Example site")
        }
        draft.update(url.absoluteString, automatic: false)
        XCTAssertEqual(loads, 0)
        draft.fetch(url)
        draft.update("typed something else", automatic: false)
        try await Task.sleep(for: .milliseconds(40))
        XCTAssertNil(draft.preview)
        draft.fetch(url)
        try await Task.sleep(for: .milliseconds(40))
        XCTAssertEqual(draft.preview?.title, "Example site")
        let quote = ChatFeatures.Reply.quoting(id: UUID(), sender: UUID(), text: "A previously delivered message")
        draft.reply = quote
        let normal = try XCTUnwrap(draft.composed(url.absoluteString))
        let encoded = try JSONEncoder().encode(WireChatFeatures(normal))
        XCTAssertEqual(
            try JSONDecoder().decode(WireChatFeatures.self, from: encoded).value?.validated(in: url.absoluteString),
            normal)
        XCTAssertNil(normal.validated(in: "other https://elsewhere.com/")?.link_preview)
        draft.removePreview()
        XCTAssertEqual(draft.composed(url.absoluteString)?.reply, quote)
        let fitted = try ChatFeatures.fit(normal) { metadata in
            Data(repeating: 0, count: metadata?.link_preview != nil ? 65_536 : 36_000)
        }
        XCTAssertEqual(fitted.0?.reply, quote)
        XCTAssertNil(fitted.0?.link_preview)
        let unknown = try JSONDecoder().decode(
            WireChatFeatures.self, from: Data(#"{"version":9,"reply":"future"}"#.utf8))
        XCTAssertNil(unknown.value?.validated(in: "ordinary readable text"))
        let omitted = Data("{\"message_id\":\"\(UUID())\",\"target_sender_id\":\"\(UUID())\",\"sequence\":2}".utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(ChatFeatures.Reaction.self, from: omitted))
        XCTAssertFalse(ChatFeatures.Preview.publicURL(URL(string: "https://owner:secret@example.com/")!))
        XCTAssertFalse(ChatFeatures.Preview.publicURL(URL(string: "https://127.0.0.1/")!))
        XCTAssertFalse(SenderLinkPreview.allowedIPv4(0xc0a80001))
        XCTAssertFalse(SenderLinkPreview.allowedIPv4(0x7f000001))
    }
    func testExplicitSenderHTTPSPreview() async throws {
        let flag = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(
            "qa-public-preview-opt-in")
        guard FileManager.default.fileExists(atPath: flag.path) else {
            throw XCTSkip("Explicit local sender HTTPS smoke only")
        }
        let url = try XCTUnwrap(URL(string: "https://example.com/"))
        let value = try await SenderLinkPreview.load(url)
        XCTAssertEqual(value.url, url.absoluteString)
        XCTAssertEqual(value.title, "Example Domain")
        let proof = XCTAttachment(string: value.url + " · " + value.title)
        proof.name = "native-tls-website-title"
        proof.lifetime = .keepAlways
        add(proof)
        do {
            _ = try await SenderLinkPreview.load(URL(string: "https://localhost/")!)
            XCTFail("Unexpected local request")
        } catch SenderLinkPreview.Failure.unavailable {}
    }
}
