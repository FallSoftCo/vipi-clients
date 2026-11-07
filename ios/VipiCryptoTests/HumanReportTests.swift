import XCTest
@testable import Vipi

final class HumanReportTests: XCTestCase {
    func testOnlyOriginalIncomingTextAndDurableIdempotentReport() throws {
        let account = UUID(), peer = UUID(), id = UUID()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("report-test-" + UUID().uuidString)
        let vault = try MessageVault(account: account, directory: directory)
        defer { try? vault.close(); try? FileManager.default.removeItem(at: directory); KeychainStore.delete(account: "messages-" + account.uuidString.lowercased()) }
        let original = StoredChat(envelope: ChatEnvelope(id: id, sender: peer, recipient: account, createdAt: 1, type: 2, ciphertext: Data([1])), text: "Original café 日本語 — not the translated rendering", state: "delivered")
        try vault.transaction { try vault.put("incoming", id.uuidString.lowercased(), JSONEncoder().encode(original)); try vault.put("compose", peer.uuidString.lowercased(), Data("Private draft".utf8)) }
        let item = ChatItem(id: id, peer: peer, text: original.text, createdAt: 1, outgoing: false, state: "delivered", cursor: "unused")
        let first = try HumanReportStore.prepare(vault: vault, peer: peer, message: item, reason: .harassment)
        let retry = try HumanReportStore.prepare(vault: vault, peer: peer, message: item, reason: .harassment)
        XCTAssertEqual(first.body, retry.body); XCTAssertFalse(retry.reported)
        let data = try JSONEncoder().encode(first.body)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(Set(body.keys), ["report_id", "reported_user_id", "message_id", "reason", "selected_text", "consent_version"])
        XCTAssertEqual(body["selected_text"] as? String, original.text)
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("Private draft"))
        try HumanReportStore.complete(vault: vault, report: first)
        XCTAssertTrue(try HumanReportStore.prepare(vault: vault, peer: peer, message: item, reason: .harassment).reported)
        for (text, outgoing, state, selectedPeer) in [("Changed text", false, "delivered", peer), (original.text, true, "delivered", peer), (original.text, false, "imported", peer), (original.text, false, "delivered", UUID())] {
            let invalid = ChatItem(id: id, peer: selectedPeer, text: text, createdAt: 1, outgoing: outgoing, state: state, cursor: "unused")
            XCTAssertThrowsError(try HumanReportStore.prepare(vault: vault, peer: peer, message: invalid, reason: .spam))
        }
        let person = try HumanReportStore.prepare(vault: vault, peer: peer, message: nil, reason: .other)
        let profileBody = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(person.body)) as? [String: Any])
        XCTAssertTrue(profileBody["message_id"] is NSNull); XCTAssertTrue(profileBody["selected_text"] is NSNull)
        XCTAssertThrowsError(try HumanReportStore.prepare(vault: vault, peer: account, message: nil, reason: .other))
    }
}
