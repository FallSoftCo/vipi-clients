import Foundation
import XCTest
@testable import Vipi

final class GroupsRoutingTests: XCTestCase {
    private func packet(_ fields: [String: Any] = [:]) throws -> RoutedMessage.Received {
        var value: [String: Any] = ["id": UUID().uuidString, "sender_id": UUID().uuidString,
            "sender_device_id": UUID().uuidString, "recipient_device_id": UUID().uuidString,
            "created_at": "2026-11-19T18:00:00.000Z", "cipher_type": 2, "ciphertext": Data(repeating: 7, count: 64).base64EncodedString()]
        value.merge(fields) { _, right in right }
        return try JSONDecoder().decode(RoutedMessage.Received.self, from: JSONSerialization.data(withJSONObject: value))
    }
    func testDirectPacketHasNoGroupContext() throws { XCTAssertFalse(try packet().hasGroupContext) }
    func testEveryPartialGroupContextFailsClosed() throws {
        let fields: [String: Any] = ["group_id": UUID().uuidString, "group_epoch": 3, "group_message_id": UUID().uuidString, "group_kind": "message"]
        for omitted in fields.keys {
            let incoming = try packet(fields.filter { $0.key != omitted })
            XCTAssertTrue(incoming.hasGroupContext)
            XCTAssertThrowsError(try incoming.groupIncoming())
        }
        XCTAssertThrowsError(try packet(["group_kind": "other"]).groupIncoming())
    }
    func testControlAndTextRemainDistinct() throws {
        let group = UUID(), logical = UUID()
        for kind in ["message", "control"] {
            let incoming = try packet(["group_id": group.uuidString, "group_epoch": 3, "group_message_id": logical.uuidString, "group_kind": kind]).groupIncoming()
            XCTAssertEqual(incoming.group_id, group); XCTAssertEqual(incoming.group_message_id, logical); XCTAssertEqual(incoming.group_kind, kind)
        }
        XCTAssertThrowsError(try packet(["group_id": group.uuidString, "group_epoch": 0, "group_message_id": logical.uuidString, "group_kind": "message"]).groupIncoming())
    }
}
