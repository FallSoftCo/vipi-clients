import XCTest
import UIKit
@testable import Vipi

@MainActor final class PushInboxHintTests: XCTestCase {
    func testBackendPayloadSynchronizesAndReturnsFetchResult() async throws {
        // backend/tests/test_push.py verifies this same fixture against the
        // actual APNs provider request body in both provider environments.
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "APNsInboxChanged", withExtension: "json"))
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        var calls = 0
        var expected: UIBackgroundFetchResult = .newData
        let delegate = VipiAppDelegate(backgroundInboxSync: {
            calls += 1
            return expected
        })
        for result in [UIBackgroundFetchResult.newData, .noData, .failed] {
            expected = result
            let actual = await delegate.application(.shared, didReceiveRemoteNotification: payload)
            XCTAssertEqual(actual, result)
        }
        XCTAssertEqual(calls, 3)
    }

    func testUnrelatedPayloadDoesNotFetchInbox() async {
        var calls = 0
        let delegate = VipiAppDelegate(backgroundInboxSync: {
            calls += 1
            return .newData
        })
        let payloads: [[String: Any]] = [[:], ["type": "inbox_changed"], ["kind": "another_event"], ["kind": 1]]
        for payload in payloads {
            let actual = await delegate.application(.shared, didReceiveRemoteNotification: payload)
            XCTAssertEqual(actual, .noData)
        }
        XCTAssertEqual(calls, 0)
    }
}
