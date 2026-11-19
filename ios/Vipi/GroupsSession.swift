import Foundation
import Observation

@MainActor @Observable final class GroupsSession {
    let account: UUID
    private let api: GroupsAPI
    let store: GroupsStore
    private let crypto: GroupsCrypto
    private let membership: GroupsMembership
    private let controls: GroupsControlCrypto
    private let preparePeer: (UUID) async throws -> Void
    private let identityReview: (UUID) -> Bool
    private(set) var groups: [GroupSnapshot] = []
    private(set) var departedGroups: [GroupSnapshot] = []
    private(set) var invitations: [GroupInvitation] = []
    private(set) var busy = false
    private(set) var loaded = false
    private(set) var revision = 0
    var notice: String?
    private var closed = false
    @ObservationIgnored private var arrivals: [UUID: (GroupMessage) -> Void] = [:]
    func observe(_ callback: @escaping (GroupMessage) -> Void) -> UUID { let id = UUID(); arrivals[id] = callback; return id }
    func removeObserver(_ id: UUID) { arrivals.removeValue(forKey: id) }
    init(account: UUID, api: GroupsAPI, store: GroupsStore, crypto: GroupsCrypto,
         preparePeer: @escaping (UUID) async throws -> Void, identityReview: @escaping (UUID) -> Bool) throws {
        self.account = account; self.api = api; self.store = store; self.crypto = crypto; membership = GroupsMembership(vault: store.vault)
        self.preparePeer = preparePeer; self.identityReview = identityReview; controls = GroupsControlCrypto(vault: store.vault, core: crypto.messagingCore)
        let cached = try store.snapshots(), active = try store.activeIDs()
        groups = cached.filter { active?.contains($0.id) ?? true }; departedGroups = cached.filter { active?.contains($0.id) == false }
    }
    func snapshot(_ id: UUID) -> GroupSnapshot? { (groups + departedGroups).first { $0.id == id } }
    func isActive(_ id: UUID) -> Bool { groups.contains { $0.id == id } }
    func hasMembershipConflict(_ id: UUID) -> Bool { _ = revision; return (try? store.vault.transaction { try store.vault.get("group-membership-conflict", id.uuidString.lowercased()) != nil }) == true }
    func messages(_ id: UUID) -> [GroupMessage] { _ = revision; return (try? store.messages(id)) ?? [] }
    func preferences(_ id: UUID) -> GroupLocalPreferences { _ = revision; return (try? store.preferences(id)) ?? .init() }
    func unread(_ id: UUID) -> Int { _ = revision; return (try? store.unread(id, account: account)) ?? 0 }
    func markRead(_ id: UUID, visible: Set<UUID>) { do { try store.markRead(id, visible: visible); revision += 1 } catch { notice = Self.explanation(error) } }
    func setMuted(_ id: UUID, _ muted: Bool) { do { try store.updatePreferences(id) { $0.muted = muted }; revision += 1 } catch { notice = Self.explanation(error) } }
    func saveDraft(_ id: UUID, _ value: String) { do { try store.updatePreferences(id) { $0.draft = value } } catch { notice = Self.explanation(error) } }
    func refresh() async {
        guard !closed, !busy else { return }; busy = true; defer { busy = false }
        do {
            let result = try await api.list(); try Task.checkCancellation(); guard !closed else { return }
            for group in result.groups { try store.save(group) }
            // Retain departed histories locally, but stop presenting cached stale
            // membership as an active conversation after authoritative refresh.
            try store.saveActiveIDs(Set(result.groups.map(\.id)))
            let activeIDs = Set(result.groups.map(\.id)); departedGroups = try store.snapshots().filter { !activeIDs.contains($0.id) }
            groups = result.groups; invitations = result.invitations; loaded = true; notice = nil; revision += 1
        } catch is CancellationError {} catch { notice = Self.explanation(error) }
    }
    private func put(_ value: GroupSnapshot) throws {
        try value.validate(); try store.save(value)
        groups.removeAll { $0.id == value.id }; groups.append(value); departedGroups.removeAll { $0.id == value.id }; try store.saveActiveIDs(Set(groups.map(\.id))); revision += 1
    }
    /// Durable immutable admission identity survives uncertain network outcomes.
    private func operation(_ scope: String, body: [String: String]) throws -> UUID {
        try store.vault.transaction {
            if let bytes = try store.vault.get("group-operation", scope) {
                let value = try JSONDecoder().decode([String: String].self, from: bytes)
                guard value.filter({ $0.key != "request_id" }) == body, let id = value["request_id"].flatMap(UUID.init(uuidString:)) else { throw GroupsFailure.retryRequiresReview }
                return id
            }
            let id = UUID(); var value = body; value["request_id"] = id.uuidString.lowercased()
            try store.vault.put("group-operation", scope, JSONEncoder().encode(value)); return id
        }
    }
    private func completed(_ scope: String) throws { try store.vault.transaction { try store.vault.remove("group-operation", scope) } }
    private func perform<T>(_ action: () async throws -> T) async -> T? {
        guard !closed, !busy else { return nil }; busy = true; notice = nil; defer { busy = false }
        do { let result = try await action(); guard !closed else { return nil }; return result }
        catch is CancellationError { return nil }
        catch { notice = Self.explanation(error); return nil }
    }
    func create(title: String) async -> GroupSnapshot? { await perform {
        let name = try GroupSelection.name(title), scope = "create"
        let id = try operation(scope, body: ["title": name])
        let value = try await api.create(id, title: name); try membership.createdLocally(value, expectedID: id); try put(value); try completed(scope); return value
    } }
    @discardableResult func change(_ group: GroupSnapshot, method: String, suffix: String = "", fields: [String: String] = [:]) async -> Bool {
        await perform {
            let scope = group.id.uuidString.lowercased() + suffix + method
            let plan: GroupMutationPlan = try store.vault.transaction {
                if let data = try store.vault.get("group-mutation", scope) {
                    let saved = try JSONDecoder().decode(GroupMutationPlan.self, from: data)
                    guard saved.method == method, saved.suffix == suffix, saved.fields == fields else { throw GroupsFailure.retryRequiresReview }
                    return saved
                }
                let old = try membership.currentInTransaction(group.id)
                if suffix.hasPrefix("/members/") { guard old?.matches(group) == true else { throw GroupsFailure.unapprovedMembership } }
                let value = GroupMutationPlan(group: group, request: UUID(), control: UUID(), method: method, suffix: suffix, fields: fields, previous: old)
                try store.vault.put("group-mutation", scope, JSONEncoder().encode(value)); return value
            }
            var fanout: GroupFanout?
            if let change = try plan.transition(actor: account) {
                for person in plan.group.members where person.id != account { guard !identityReview(person.id) else { throw GroupsFailure.identityChanged }; try await preparePeer(person.id) }
                let value = try controls.prepare(id: plan.control, roster: plan.group, change: change, now: Int64(Date().timeIntervalSince1970 * 1000))
                fanout = value
            }
            let result = try await api.change(plan.group, method: plan.method, suffix: plan.suffix, request: plan.request, fields: plan.fields, control: fanout)
            if let fanout {
                guard let accepted = result.control_acceptance else { throw GroupsFailure.invalidResponse }
                try controls.accepted(accepted, fanout: fanout)
                guard try membership.current(group.id)?.matches(result.snapshot) == true else { throw GroupsFailure.unapprovedMembership }
            }
            try put(result.snapshot)
            if let fanout { try controls.reconciled(fanout) }
            try store.vault.transaction { try store.vault.remove("group-mutation", scope) }; return true
        } ?? false
    }
    func rename(_ group: GroupSnapshot, title: String) async -> Bool {
        do { return await change(group, method: "PATCH", fields: ["title": try GroupSelection.name(title)]) }
        catch { notice = Self.explanation(error); return false }
    }
    func invite(_ group: GroupSnapshot, person: UUID) async -> Bool {
        await change(group, method: "POST", suffix: "/invitations", fields: ["user_id": person.uuidString.lowercased()])
    }
    func answer(_ invitation: GroupInvitation, accept: Bool) async {
        _ = await perform {
            let scope = "answer/" + invitation.id.uuidString.lowercased()
            let request = try operation(scope, body: ["accept": String(accept), "epoch": String(invitation.epoch)])
            if let value = try await api.answer(invitation, accept: accept, request: request) { try put(value) }
            invitations.removeAll { $0.id == invitation.id }; try completed(scope); return true
        }
    }
    func leave(_ group: GroupSnapshot) async -> Bool { await perform {
        let scope = "leave/" + group.id.uuidString.lowercased()
        let plan: GroupMutationPlan = try store.vault.transaction {
            if let data = try store.vault.get("group-mutation", scope) { return try JSONDecoder().decode(GroupMutationPlan.self, from: data) }
            guard let previous = try membership.currentInTransaction(group.id), previous.matches(group),
                  previous.members.first(where: { $0.user_id == account })?.role != .owner || previous.members.count == 1 else { throw GroupsFailure.noPermission }
            let value = GroupMutationPlan(group: group, request: UUID(), control: UUID(), method: "POST", suffix: "/leave", fields: [:], previous: previous)
            try store.vault.put("group-mutation", scope, JSONEncoder().encode(value)); return value
        }
        guard let change = try plan.transition(actor: account) else { throw GroupsFailure.unapprovedMembership }
        for member in plan.group.members where member.id != account { guard !identityReview(member.id) else { throw GroupsFailure.identityChanged }; try await preparePeer(member.id) }
        let fanout = try controls.prepare(id: plan.control, roster: plan.group, change: change, now: Int64(Date().timeIntervalSince1970 * 1000))
        let accepted = try await api.leave(plan.group, request: plan.request, control: fanout)
        try controls.accepted(accepted, fanout: fanout); try controls.reconciled(fanout)
        try store.vault.transaction { try store.vault.remove("group-mutation", scope) }
        groups.removeAll { $0.id == group.id }; departedGroups.removeAll { $0.id == group.id }; departedGroups.append(plan.group); try store.saveActiveIDs(Set(groups.map(\.id))); revision += 1; return true
    } ?? false }
    func send(_ group: GroupSnapshot, text: String) async -> Bool {
        guard isActive(group.id), let approved = try? membership.current(group.id), approved.matches(group) else { notice = Self.explanation(GroupsFailure.unapprovedMembership); return false }
        let value = GroupMessage(id: UUID(), groupID: group.id, epoch: group.epoch, membershipRevision: approved.revision, sender: account, text: text,
            createdAt: Int64(Date().timeIntervalSince1970 * 1000), delivery: .queued)
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= 32768 else { notice = Self.explanation(GroupsFailure.invalidMessage); return false }
        do { try store.saveMessage(value); try store.updatePreferences(group.id) { $0.draft = "" }; revision += 1 }
        catch { notice = Self.explanation(error); return false }
        await retry(value); return true // Queued locally, never implies delivered.
    }
    func retry(_ value: GroupMessage) async {
        _ = await perform {
            guard isActive(value.groupID), var roster = snapshot(value.groupID), roster.role(for: account) != nil else { throw GroupsFailure.notMember }
            let now = Int64(Date().timeIntervalSince1970 * 1000)
            guard now < value.createdAt + MessageJournal.ttl else { var expired = value; expired.delivery = .expired; try store.saveMessage(expired); revision += 1; return false }
            let saved = try crypto.pending(value.groupID, value.id)
            let fanout: GroupFanout
            if let saved { fanout = saved } // Exact immutable retry, even after an uncertain acceptance.
            else {
                roster = try await api.detail(value.groupID); try put(roster)
                guard roster.epoch == value.epoch else { var changed = value; changed.delivery = .membershipChanged; try store.saveMessage(changed); revision += 1; throw GroupsFailure.membershipChanged }
                for member in roster.members where member.user_id != account {
                    guard !identityReview(member.user_id) else { throw GroupsFailure.identityChanged }
                    try await preparePeer(member.user_id)
                }
                fanout = try crypto.prepare(value, roster: roster, now: now)
            }
            do {
                let response = try await api.send(fanout); try crypto.accepted(response, fanout: fanout)
            } catch let failure as ServiceFailure {
                var terminal = value
                if ["group_epoch_changed", "group_recipients_changed", "group_unavailable", "group_member_unavailable"].contains(failure.code) { terminal.delivery = .membershipChanged }
                else if ["recipient_identity_changed", "peer_identity_review_required"].contains(failure.code) { terminal.delivery = .identityChanged }
                if terminal.delivery != value.delivery { try store.saveMessage(terminal); revision += 1 }
                throw failure
            }
            revision += 1; return true
        }
    }
    func heldMessages(_ group: UUID) -> [GroupIncoming] { _ = revision; return ((try? crypto.heldEnvelopes()) ?? []).filter { $0.group_id == group } }
    func retryHeld(_ group: UUID) {
        do {
            for item in try crypto.heldEnvelopes() where item.group_id == group { _ = try received(item) }
            for item in try controls.heldEnvelopes() where item.group_id == group { try receivedControl(item) }
            revision += 1
        } catch { notice = Self.explanation(error) }
    }
    func heldControls(_ group: UUID) -> [GroupIncoming] { _ = revision; return ((try? controls.heldEnvelopes()) ?? []).filter { $0.group_id == group } }
    func pendingCreateTitle() -> String? { try? store.vault.transaction { guard let data = try store.vault.get("group-operation", "create") else { return nil }; return try JSONDecoder().decode([String: String].self, from: data)["title"] } }
    func pendingChanges(_ group: UUID) -> Int { _ = revision; return (try? store.vault.transaction { try store.vault.ids("group-mutation").filter { $0.contains(group.uuidString.lowercased()) }.count + store.vault.ids("group-join-plan").filter { $0.hasPrefix(group.uuidString.lowercased() + "/") }.count }) ?? 0 }
    func resumePending(_ group: UUID) async {
        do {
            let mutations: [GroupMutationPlan] = try store.vault.transaction { try store.vault.ids("group-mutation").compactMap { key in try store.vault.get("group-mutation", key).map { try JSONDecoder().decode(GroupMutationPlan.self, from: $0) } }.filter { $0.group.id == group } }
            for plan in mutations { if plan.suffix == "/leave" { _ = await leave(plan.group) } else { _ = await change(plan.group, method: plan.method, suffix: plan.suffix, fields: plan.fields) }; if notice != nil { return } }
            let joins: [GroupJoinApprovalPlan] = try store.vault.transaction { try store.vault.ids("group-join-plan").filter { $0.hasPrefix(group.uuidString.lowercased() + "/") }.compactMap { key in try store.vault.get("group-join-plan", key).map { try JSONDecoder().decode(GroupJoinApprovalPlan.self, from: $0) } } }
            for plan in joins { await approveJoin(plan.group, person: plan.change.target_id); if notice != nil { return } }
        } catch { notice = Self.explanation(error) }
    }
    func pendingApprovals(_ group: UUID) -> [GroupPendingControl] { _ = revision; return ((try? controls.pending()) ?? []).filter { $0.group == group } }
    func canBootstrap(_ control: GroupPendingControl) -> Bool { (try? membership.current(control.group)) == nil && control.transition.action == .add && control.transition.target_id == account }
    func confirmBootstrap(_ control: GroupPendingControl) { do { try controls.confirmBootstrap(control); _ = try crypto.releaseAuthorized(control.group); revision += 1 } catch { notice = Self.explanation(error) } }
    func approveJoin(_ group: GroupSnapshot, person: UUID) async {
        _ = await perform {
            let scope = group.id.uuidString.lowercased() + "/" + person.uuidString.lowercased()
            let plan: GroupJoinApprovalPlan = try store.vault.transaction {
                if let data = try store.vault.get("group-join-plan", scope) { return try JSONDecoder().decode(GroupJoinApprovalPlan.self, from: data) }
                guard let previous = try membership.currentInTransaction(group.id), !previous.contains(person),
                      group.members.first(where: { $0.id == person })?.role == .member,
                      Set(previous.members).isSubset(of: Set(group.members.map { GroupApprovedPerson(user_id: $0.id, role: $0.role) })) else { throw GroupsFailure.unapprovedMembership }
                let change = GroupRosterTransition(actor_id: account, action: .add, target_id: person, from_revision: previous.revision, to_revision: previous.revision + 1, server_epoch: group.epoch, previous_members: previous.members, members: previous.members + [.init(user_id: person, role: .member)])
                _ = try change.validated(group: group.id, previous: previous, authenticatedSender: account)
                let value = GroupJoinApprovalPlan(id: UUID(), group: group, change: change)
                try store.vault.put("group-join-plan", scope, JSONEncoder().encode(value)); return value
            }
            for member in plan.group.members where member.id != account { guard !identityReview(member.id) else { throw GroupsFailure.identityChanged }; try await preparePeer(member.id) }
            let fanout = try controls.prepare(id: plan.id, roster: plan.group, change: plan.change, now: Int64(Date().timeIntervalSince1970 * 1000))
            try controls.accepted(try await api.sendControl(fanout), fanout: fanout); try controls.reconciled(fanout)
            try store.vault.transaction { try store.vault.remove("group-join-plan", scope) }; revision += 1; return true
        }
    }
    func approved(_ group: UUID, person: UUID) -> Bool { _ = revision; return (try? membership.current(group))?.contains(person) == true }
    func receivedControl(_ item: GroupIncoming) throws { guard !closed else { throw CancellationError() }; try controls.receive(item, now: Int64(Date().timeIntervalSince1970 * 1000)); _ = try crypto.releaseAuthorized(item.group_id); revision += 1 }
    func received(_ item: GroupIncoming) throws -> GroupMessage? {
        guard !closed else { throw CancellationError() }
        let duplicate = try store.messages(item.group_id).contains { $0.id == item.group_message_id }
        let value = try crypto.receive(item, now: Int64(Date().timeIntervalSince1970 * 1000)); revision += 1
        if let value, !duplicate, value.delivery == .received { for callback in Array(arrivals.values) { callback(value) } }
        else if value == nil { notice = "A group message is held securely. Review the sender’s encryption identity before opening it." }
        return value
    }
    func close() { closed = true; arrivals.removeAll(); groups = []; departedGroups = []; invitations = []; notice = nil }
    static func explanation(_ error: Error) -> String {
        if let failure = error as? ServiceFailure {
            switch failure.code {
            case "group_epoch_changed", "group_recipients_changed": return "The group changed. Refresh to review the people, then send your message again."
            case "group_full": return "This group already has 16 people, including its creator."
            case "groups_not_available": return "Groups aren’t available on this service yet."
            case "recipient_identity_changed", "peer_identity_review_required": return "Someone’s encryption identity changed. Review their encryption details before sending."
            case "group_member_device_unavailable": return "Someone needs to reconnect their device before this message can be sent to everyone."
            default: break
            }
        }
        switch error {
        case GroupsFailure.unapprovedMembership: return "The people in this group haven’t been confirmed securely. Ask an existing admin to approve the change before sending."
        case GroupsFailure.holdCapacity: return "Saved messages need review before more can be opened. Review waiting messages in Group info, then try again."
        case GroupsFailure.noPermission: return "Review the group roles. If you’re the owner, transfer ownership before leaving. Resume any pending change before starting another."
        case GroupsFailure.invalidName: return "Give your group a name with 1–80 characters."
        case GroupsFailure.groupFull: return "Choose up to 15 other people. The limit of 16 includes you."
        case GroupsFailure.membershipChanged: return "The people or settings in this group changed. Review Group info and send again."
        case GroupsFailure.identityChanged: return "Someone’s encryption identity changed. Review their encryption details before sending."
        case GroupsFailure.notMember: return "You’re no longer in this group. Your saved messages remain on this device."
        case GroupsFailure.invalidMessage: return "Write a message up to 32 KB before sending."
        case GroupsFailure.retryRequiresReview: return "An earlier change hasn’t been confirmed. Retry that exact change before making another."
        default: return "Couldn’t connect. Your messages and draft are saved on this device. Try again when you’re online."
        }
    }
}
