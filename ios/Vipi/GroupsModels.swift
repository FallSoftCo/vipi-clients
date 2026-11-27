import Foundation

enum GroupsUpgrade {
    static let protocolVersion = 1
    static func isEnvelopeRequest(method: String, path: String) -> Bool {
        if method == "GET", path == "/v1/messages/pending" { return true }
        let parts = path.split(separator: "/")
        guard parts.count >= 3, parts[0] == "v1", parts[1] == "messages", UUID(uuidString: String(parts[2])) != nil
        else { return false }
        return (method == "GET" && parts.count == 3) || (method == "POST" && parts.count == 4 && parts[3] == "receipt")
    }
    static let maximumPeople = 16
    static let muteDeliveryQualified = false
}
enum GroupRole: String, Codable, Hashable { case owner, admin, member }
struct GroupMember: Codable, Identifiable, Equatable {
    var id: UUID { user_id }
    let user_id: UUID
    let display_name: String
    let username: String
    let role: GroupRole
    let joined_epoch: Int
    let device_id: UUID?
    var chat_features_version: Int? = nil
}
struct GroupInvitation: Codable, Identifiable, Equatable {
    let id: UUID
    let group_id: UUID
    let title: String
    let invited_by: UUID
    let epoch: Int
    let expires_at: String
}
struct GroupSnapshot: Codable, Identifiable, Equatable {
    let id: UUID
    let title: String
    let epoch: Int
    let state: String
    let members: [GroupMember]
    let invitations: [GroupPendingInvitation]
    func role(for user: UUID) -> GroupRole? { members.first { $0.user_id == user }?.role }
    func canManage(_ user: UUID) -> Bool { role(for: user) == .owner || role(for: user) == .admin }
    func canRemove(_ actor: UUID, _ subject: UUID) -> Bool {
        guard actor != subject, let target = role(for: subject) else { return false }
        return role(for: actor) == .owner || (role(for: actor) == .admin && target == .member)
    }
    func validate() throws {
        guard epoch >= 1, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            title.unicodeScalars.count <= 80, members.count <= GroupsUpgrade.maximumPeople,
            Set(members.map(\.user_id)).count == members.count,
            members.filter({ $0.role == .owner }).count == 1
        else { throw GroupsFailure.invalidResponse }
    }
}
struct GroupPendingInvitation: Codable, Identifiable, Equatable {
    let id: UUID
    let user_id: UUID
    let invited_by: UUID
    let expires_at: String
    let state: String
}
enum GroupDelivery: String, Codable {
    case queued, sending, accepted, failed, expired, membershipChanged, identityChanged, received, withheld
}
struct GroupMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let groupID: UUID
    let epoch: Int
    let membershipRevision: Int
    let sender: UUID
    let text: String
    let createdAt: Int64
    var delivery: GroupDelivery
    var withheldReason: String? = nil
    var features: ChatFeatures? = nil
    var renderID: String { "group:\(groupID.uuidString.lowercased()):\(id.uuidString.lowercased())" }
}
struct GroupLocalPreferences: Codable {
    var muted = false
    var readIDs: Set<UUID> = []
    var draft = ""
}
enum GroupsFailure: Error {
    case reactionsUnavailable, invalidResponse, groupFull, noPermission, invalidName, invalidMessage, membershipChanged,
        identityChanged, notMember, retryRequiresReview, unapprovedMembership, holdCapacity
}

/// UI policy shared by creation and invite pickers. Pending invitations reserve
/// seats on the server; these checks only provide immediate local feedback.
enum GroupSelection {
    static func toggled(_ person: UUID, in selected: Set<UUID>, account: UUID, occupied: Set<UUID> = []) throws -> Set<
        UUID
    > {
        guard person != account, !occupied.contains(person) else { throw GroupsFailure.noPermission }
        var next = selected
        if next.remove(person) != nil { return next }
        guard selected.count + occupied.count + 1 < GroupsUpgrade.maximumPeople else { throw GroupsFailure.groupFull }
        next.insert(person)
        return next
    }
    static func name(_ text: String) throws -> String {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.unicodeScalars.count <= 80,
            !value.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
        else { throw GroupsFailure.invalidName }
        return value
    }
}

extension RoutedMessage.Received {
    func groupIncoming() throws -> GroupIncoming {
        guard let group_id, let group_epoch, group_epoch > 0, let group_message_id, let group_kind,
            ["message", "control"].contains(group_kind)
        else { throw GroupsFailure.invalidResponse }
        return GroupIncoming(
            id: id, sender_id: sender_id, sender_device_id: sender_device_id, recipient_device_id: recipient_device_id,
            created_at: created_at, cipher_type: cipher_type, ciphertext: ciphertext, group_id: group_id,
            group_epoch: group_epoch, group_message_id: group_message_id, group_kind: group_kind)
    }
}
