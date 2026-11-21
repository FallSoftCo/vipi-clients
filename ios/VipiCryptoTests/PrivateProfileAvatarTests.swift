import XCTest
import UIKit
@testable import Vipi

@MainActor final class PrivateProfileAvatarTests: XCTestCase {
    private func jpeg() -> Data {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1; format.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width:96,height:96),format:format).jpegData(withCompressionQuality:0.6) { ctx in
            UIColor.red.setFill(); ctx.fill(CGRect(x:0,y:0,width:96,height:96))
        }
    }
    func testAuthenticatedUpdateTombstoneAndOutOfOrderOlderUpdate() throws {
        let alice = UUID(), bob = UUID(), base = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let senderVault = try MessageVault(account: alice,directory: base.appendingPathComponent("s"))
        let receiverVault = try MessageVault(account: bob,directory: base.appendingPathComponent("r"))
        defer {
            try? senderVault.close(); try? receiverVault.close(); try? FileManager.default.removeItem(at:base)
            for id in [alice,bob] { KeychainStore.delete(account:"messages-" + id.uuidString.lowercased()) }
        }
        let sender = try MessagingCore(vault:senderVault), receiver = try MessagingCore(vault:receiverVault)
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let keys = try receiver.keys.publication(now:now,count:1)
        let request = UUID()
        _ = try sender.keys.establish(peer:bob,requestID:request,response:ClaimedKeys(request_id:request,user_id:bob,
            device_id:receiver.device.id,signal_device_id:1,registration_id:keys.registration_id,
            identity_key:keys.identity_key,signed:keys.signed,one_time:try XCTUnwrap(keys.one_time.first)))
        let data = jpeg()
        XCTAssertThrowsError(try sender.journal.setOwnAvatar(Data("x".utf8),now:now))
        try sender.journal.setOwnAvatar(data,now:now)
        let photo = try sender.queue(id:UUID(),peer:bob,text:"one",createdAt:now,now:now)
        _ = try receiver.receive(photo,now:now)
        XCTAssertEqual(try receiver.journal.avatar(alice)?.jpeg,data)
        let stale = try sender.queue(id:UUID(),peer:bob,text:"two",createdAt:now,now:now)
        try sender.journal.setOwnAvatar(nil,now:now-5)
        let removed = try sender.queue(id:UUID(),peer:bob,text:"three",createdAt:now,now:now)
        _ = try receiver.receive(removed,now:now)
        let tombstone = try XCTUnwrap(receiver.journal.avatar(alice))
        XCTAssertNil(tombstone.jpeg); XCTAssertEqual(tombstone.revision, now+1)
        _ = try receiver.receive(stale,now:now)
        XCTAssertEqual(try receiver.journal.avatar(alice),tombstone)
        XCTAssertNil(try receiver.journal.avatar(bob))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with:JSONEncoder().encode(tombstone)) as? [String:Any])
        XCTAssertTrue(json["jpeg"] is NSNull)
        XCTAssertNil((try JSONSerialization.jsonObject(with:photo.sendData()) as? [String:Any])?["profile_avatar"])
    }
}
