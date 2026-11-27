import Foundation
import XCTest
@testable import Vipi

final class GroupsMembershipTests: XCTestCase {
    func testSharedAuthenticatedMembershipFixtures() throws {
        let root = try JSONSerialization.jsonObject(with: Data(Self.fixtures.utf8)) as! [String: Any]
        let decoder = JSONDecoder()
        for fixture in root["cases"] as! [[String: Any]] {
            let name = fixture["name"] as! String
            do {
                guard fixture["identity_pinned"] as? Bool == true else { throw GroupsFailure.identityChanged }
                let group = UUID(uuidString: fixture["group_id"] as! String)!
                let previous = try decoder.decode(
                    [GroupApprovedPerson].self, from: JSONSerialization.data(withJSONObject: fixture["previous"]!))
                let approved = GroupApprovedRoster(
                    group_id: group, revision: fixture["revision"] as! Int, members: previous)
                let transition = try decoder.decode(
                    GroupRosterTransition.self, from: JSONSerialization.data(withJSONObject: fixture["control"]!))
                let next = try transition.validated(
                    group: group, previous: approved,
                    authenticatedSender: UUID(uuidString: fixture["authenticated_actor"] as! String)!)
                XCTAssertNil(fixture["error"], name)
                XCTAssertEqual(next.revision, approved.revision + 1, name)
                XCTAssertEqual(Set(next.members), Set(transition.members), name)
            } catch { XCTAssertNotNil(fixture["error"], "Unexpected rejection: \(name): \(error)") }
        }
    }
    func testSelectionCountsCreatorAndCannotSelectSelf() throws {
        let account = UUID(), people = (0..<15).map { _ in UUID() }
        var selected = Set<UUID>()
        for person in people { selected = try GroupSelection.toggled(person, in: selected, account: account) }
        XCTAssertEqual(selected.count, 15)
        XCTAssertThrowsError(try GroupSelection.toggled(UUID(), in: selected, account: account))
        XCTAssertThrowsError(try GroupSelection.toggled(account, in: [], account: account))
        XCTAssertEqual(try GroupSelection.toggled(people[0], in: selected, account: account).count, 14)
    }
    func testRelayMemberAndRoleChangesNeverMatchApprovedRoster() {
        let account = UUID(), peer = UUID(), group = UUID()
        let approved = GroupApprovedRoster(
            group_id: group, revision: 1, members: [.init(user_id: account, role: .owner)])
        let snapshot = GroupSnapshot(
            id: group, title: "Friends", epoch: 99, state: "active",
            members: [
                .init(
                    user_id: account, display_name: "A", username: "aaa", role: .owner, joined_epoch: 1,
                    device_id: UUID()),
                .init(
                    user_id: peer, display_name: "B", username: "bbb", role: .member, joined_epoch: 99,
                    device_id: UUID())
            ], invitations: [])
        XCTAssertFalse(approved.matches(snapshot))
        XCTAssertFalse(approved.contains(peer))
    }
    private static let fixtures = #"""
        {
          "version": 1,
          "note": "Reference inputs already authenticated by pinned existing Signal sessions; not encryption vectors. Native validators must also bind group and envelope context.",
          "cases": [
            {
              "name": "owner adds ordinary member",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              }
            },
            {
              "name": "unconfirmed Signal identity",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": false,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "identity_confirmation_required"
            },
            {
              "name": "authenticated sender mismatch",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "22222222-2222-4222-8222-222222222222",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "actor_context_mismatch"
            },
            {
              "name": "skipped revision",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 3,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "missing_control_chain"
            },
            {
              "name": "old revision replay",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 0,
                "to_revision": 1,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "conflicting_revision"
            },
            {
              "name": "server roster substituted for previous approval",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "previous_roster_mismatch"
            },
            {
              "name": "member adds someone",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "22222222-2222-4222-8222-222222222222",
              "identity_pinned": true,
              "control": {
                "actor_id": "22222222-2222-4222-8222-222222222222",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "unauthorized_control"
            },
            {
              "name": "admin add also promotes self",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "admin"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "unexpected_roster_delta"
            },
            {
              "name": "duplicate member",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ]
              },
              "error": "invalid_roster"
            },
            {
              "name": "multiple owners",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "owner"
                  }
                ]
              },
              "error": "invalid_roster"
            },
            {
              "name": "no owner",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "member"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "invalid_roster"
            },
            {
              "name": "boolean revision",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": true,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "missing_control_chain"
            },
            {
              "name": "boolean epoch",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": true,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "invalid_control"
            },
            {
              "name": "unknown action",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "recovery",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "invalid_control_action"
            },
            {
              "name": "unknown control fields",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ],
                "server_says_trusted": true
              },
              "error": "invalid_control"
            },
            {
              "name": "untrusted extra roster fields",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner",
                  "verified": true
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "add",
                "target_id": "33333333-3333-4333-8333-333333333333",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner",
                    "verified": true
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner",
                    "verified": true
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  },
                  {
                    "user_id": "33333333-3333-4333-8333-333333333333",
                    "role": "member"
                  }
                ]
              },
              "error": "invalid_roster"
            },
            {
              "name": "valid remove",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "remove",
                "target_id": "22222222-2222-4222-8222-222222222222",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  }
                ]
              }
            },
            {
              "name": "valid role",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "role",
                "target_id": "22222222-2222-4222-8222-222222222222",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "admin"
                  }
                ],
                "role": "admin"
              }
            },
            {
              "name": "valid transfer",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "transfer",
                "target_id": "22222222-2222-4222-8222-222222222222",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "admin"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "owner"
                  }
                ]
              }
            },
            {
              "name": "valid leave",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "22222222-2222-4222-8222-222222222222",
              "identity_pinned": true,
              "control": {
                "actor_id": "22222222-2222-4222-8222-222222222222",
                "action": "leave",
                "target_id": "22222222-2222-4222-8222-222222222222",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  }
                ]
              }
            },
            {
              "name": "owner cannot silently leave with successor",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "11111111-1111-4111-8111-111111111111",
              "identity_pinned": true,
              "control": {
                "actor_id": "11111111-1111-4111-8111-111111111111",
                "action": "leave",
                "target_id": "11111111-1111-4111-8111-111111111111",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "owner"
                  }
                ]
              },
              "error": "explicit_owner_transfer_required"
            },
            {
              "name": "member cannot promote self",
              "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              "revision": 1,
              "previous": [
                {
                  "user_id": "11111111-1111-4111-8111-111111111111",
                  "role": "owner"
                },
                {
                  "user_id": "22222222-2222-4222-8222-222222222222",
                  "role": "member"
                }
              ],
              "control_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "authenticated_actor": "22222222-2222-4222-8222-222222222222",
              "identity_pinned": true,
              "control": {
                "actor_id": "22222222-2222-4222-8222-222222222222",
                "action": "transfer",
                "target_id": "11111111-1111-4111-8111-111111111111",
                "from_revision": 1,
                "to_revision": 2,
                "server_epoch": 4,
                "previous_members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ],
                "members": [
                  {
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "role": "owner"
                  },
                  {
                    "user_id": "22222222-2222-4222-8222-222222222222",
                    "role": "member"
                  }
                ]
              },
              "error": "unauthorized_control"
            }
          ]
        }

        """#
}
