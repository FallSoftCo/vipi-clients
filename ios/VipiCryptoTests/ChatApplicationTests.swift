import Foundation
import XCTest
@testable import Vipi

@MainActor final class ChatApplicationTests: XCTestCase {
    private struct Config: Decodable {
        let run: String
        let peer: String
    }
    private func file(_ name: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(name)
    }
    func testPrepareRealConversationUI() async throws {
        guard FileManager.default.fileExists(atPath: file("runtime-session.json").path) else {
            throw XCTSkip("Explicit controlled staging account required")
        }
        let config = try JSONDecoder().decode(Config.self, from: Data(contentsOf: file("runtime-config.json")))
        XCTAssertTrue(config.peer.hasPrefix("vqa_"))
        XCTAssertNil(try KeychainStore.read(account: "runtime-session-backup"))
        if let old = try KeychainStore.read(account: "session") {
            try KeychainStore.save(old, account: "runtime-session-backup")
        }
        let session = try JSONDecoder().decode(VipiSession.self, from: Data(contentsOf: file("runtime-session.json")))
        try FileManager.default.removeItem(at: file("runtime-session.json"))
        try KeychainStore.save(JSONEncoder().encode(session), account: "session")
        let auth = AuthenticationManager(), chat = try ChatSession(authentication: auth, userID: session.userID)
        await chat.start()
        XCTAssertTrue(chat.ready, chat.notice ?? "Not ready")
        let peer = try await chat.find(config.peer)
        let text = "A real conversation from the iOS app coordinator — café ☕"
        try chat.saveCompose(text, peer: peer.id)
        try chat.send(text, peer: peer.id)
        XCTAssertEqual(try chat.compose(peer.id), "")
        XCTAssertEqual(try chat.messages(peer.id).first?.state, "queued")
        await chat.synchronize()
        XCTAssertEqual(try chat.messages(peer.id).first?.state, "accepted", chat.notice ?? "Not sent")
        try JSONSerialization.data(withJSONObject: [
            "run": config.run, "sent": true, "account": chat.profile!.id.uuidString.lowercased()
        ]).write(to: file("runtime-ready.json"), options: .atomic)
    }
    func testSynchronizeAndRestoreAfterUI() async throws {
        guard FileManager.default.fileExists(atPath: file("runtime-config.json").path) else {
            throw XCTSkip("Explicit UI QA required")
        }
        let auth = AuthenticationManager(),
            chat = try ChatSession(authentication: auth, userID: XCTUnwrap(auth.session?.userID))
        await chat.start()
        XCTAssertTrue(chat.ready, chat.notice ?? "Not ready")
        let config = try JSONDecoder().decode(Config.self, from: Data(contentsOf: file("runtime-config.json")))
        let peer = try await chat.find(config.peer)
        let messages = try chat.messages(peer.id)
        XCTAssertTrue(
            messages.contains {
                !$0.outgoing && $0.text == "Coffee tomorrow? Sent from the Android conversation screen."
            })
        if let old = try KeychainStore.read(account: "runtime-session-backup") {
            try KeychainStore.save(old, account: "session")
        } else {
            KeychainStore.delete(account: "session")
        }
        KeychainStore.delete(account: "runtime-session-backup")
        try FileManager.default.removeItem(at: file("runtime-config.json"))
        try JSONSerialization.data(withJSONObject: [
            "run": config.run, "received_android_ui_message": true, "restored_session": true
        ]).write(to: file("runtime-complete.json"), options: .atomic)
    }
}
