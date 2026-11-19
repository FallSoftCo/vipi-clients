import Foundation

struct GroupMutationPlan: Codable {
    let group: GroupSnapshot
    let request: UUID
    let control: UUID
    let method: String
    let suffix: String
    let fields: [String: String]
    let previous: GroupApprovedRoster?
    func transition(actor: UUID) throws -> GroupRosterTransition? {
        if suffix == "/leave", let previous {
            return .init(actor_id: actor, action: .leave, target_id: actor, from_revision: previous.revision, to_revision: previous.revision + 1, server_epoch: group.epoch + 1, previous_members: previous.members, members: previous.members.filter { $0.user_id != actor })
        }
        guard suffix.hasPrefix("/members/"), let target = UUID(uuidString: String(suffix.dropFirst("/members/".count))), let previous else { return nil }
        var people = previous.members
        let action: GroupControlAction
        var role: GroupRole?
        if method == "DELETE" { action = .remove; people.removeAll { $0.user_id == target } }
        else if fields["role"] == "owner" {
            action = .transfer
            people = people.map { .init(user_id: $0.user_id, role: $0.user_id == target ? .owner : ($0.role == .owner ? .admin : $0.role)) }
        } else {
            action = .role; role = fields["role"].flatMap(GroupRole.init(rawValue:))
            guard let role else { throw GroupsFailure.invalidResponse }
            people = people.map { .init(user_id: $0.user_id, role: $0.user_id == target ? role : $0.role) }
        }
        return GroupRosterTransition(actor_id: actor, action: action, target_id: target, from_revision: previous.revision, to_revision: previous.revision + 1, server_epoch: group.epoch + 1, previous_members: previous.members, members: people, role: role)
    }
}
