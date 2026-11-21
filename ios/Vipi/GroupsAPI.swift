import Foundation

@MainActor final class GroupsAPI {
    struct ListResponse: Decodable { let groups: [GroupSnapshot]; let invitations: [GroupInvitation] }
    struct Flag: Decodable { let left: Bool?; let declined: Bool?; let control_acceptance: GroupFanout.Acceptance? }
    struct Changed: Decodable {
        let snapshot: GroupSnapshot
        let control_acceptance: GroupFanout.Acceptance?
        private enum Keys: String, CodingKey { case control_acceptance }
        init(from decoder: Decoder) throws { snapshot = try GroupSnapshot(from: decoder); control_acceptance = try decoder.container(keyedBy: Keys.self).decodeIfPresent(GroupFanout.Acceptance.self, forKey: .control_acceptance) }
    }
    let transport: any ChatTransport
    let device: DeviceCredential
    init(transport: any ChatTransport, device: DeviceCredential) { self.transport = transport; self.device = device }
    func list() async throws -> ListResponse { try await transport.request("GET", "/v1/groups", device: device) }
    func detail(_ id: UUID) async throws -> GroupSnapshot { try await transport.request("GET", path(id), device: device) }
    func create(_ id: UUID, title: String) async throws -> GroupSnapshot {
        try await transport.request("POST", "/v1/groups", body: data(["id": id.uuidString.lowercased(), "title": title]), device: device)
    }
    func change(_ group: GroupSnapshot, method: String, suffix: String = "", request: UUID, fields: [String: Any] = [:], control: GroupFanout? = nil) async throws -> Changed {
        var body = fields; body["request_id"] = request.uuidString.lowercased(); body["expected_epoch"] = group.epoch
        if let control { body["control"] = try JSONSerialization.jsonObject(with: control.body) }
        return try await transport.request(method, path(group.id) + suffix, body: data(body), device: device)
    }
    func answer(_ invitation: GroupInvitation, accept: Bool, request: UUID) async throws -> GroupSnapshot? {
        let endpoint = path(invitation.group_id) + "/invitations/\(invitation.id.uuidString.lowercased())/" + (accept ? "accept" : "decline")
        let body = try data(["request_id": request.uuidString.lowercased(), "expected_epoch": invitation.epoch])
        if accept { return try await transport.request("POST", endpoint, body: body, device: device) }
        let _: Flag = try await transport.request("POST", endpoint, body: body, device: device); return nil
    }
    func leave(_ group: GroupSnapshot, request: UUID, control: GroupFanout) async throws -> GroupFanout.Acceptance {
        let value: Flag = try await transport.request("POST", path(group.id) + "/leave", body: data(["request_id": request.uuidString.lowercased(), "expected_epoch": group.epoch, "control": try JSONSerialization.jsonObject(with: control.body)]), device: device)
        guard value.left == true, let accepted = value.control_acceptance else { throw GroupsFailure.invalidResponse }; return accepted
    }
    func send(_ fanout: GroupFanout) async throws -> GroupFanout.Acceptance {
        try await transport.request("POST", path(fanout.groupID) + "/messages", body: fanout.body, device: device)
    }
    func sendControl(_ fanout: GroupFanout) async throws -> GroupFanout.Acceptance {
        try await transport.request("POST", path(fanout.groupID) + "/controls", body: fanout.body, device: device)
    }
    private func path(_ id: UUID) -> String { "/v1/groups/" + id.uuidString.lowercased() }
    private func data(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
}
