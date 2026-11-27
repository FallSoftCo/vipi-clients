import Foundation
import Observation
import CoreFoundation

enum ChatForegroundEvent: Equatable {
    case inbox, typing(UUID, Bool), receipts(UUID)

    static func decode(_ text: String) -> Self? {
        guard text.utf8.count <= 512,
            let object = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
            let event = object["event"] as? String
        else { return nil }
        if event == "inbox_changed" { return object.count == 1 ? .inbox : nil }
        guard let raw = object["peer"] as? String, let peer = UUID(uuidString: raw),
            peer.uuidString.lowercased() == raw
        else { return nil }
        if event == "receipts_changed", object.count == 2 { return .receipts(peer) }
        if event == "typing", object.count == 3, let active = object["active"] as? NSNumber,
            CFGetTypeID(active) == CFBooleanGetTypeID()
        {
            return .typing(peer, active.boolValue)
        }
        return nil
    }
}

struct ChatReadReply: Decodable, Sendable {
    let acknowledged: [UUID]
    let read: [UUID]
}
private actor ChatReadLedger {
    let vault: MessageVault
    init(_ vault: MessageVault) { self.vault = vault }
    func note(_ ids: [UUID], peer: UUID) throws {
        try vault.transaction {
            for id in ids {
                let key = id.uuidString.lowercased()
                guard let bytes = try vault.get("incoming", key) else { continue }
                var message = try JSONDecoder().decode(StoredChat.self, from: bytes)
                guard message.features?.reaction == nil, message.envelope.sender == peer, message.seen != true else {
                    continue
                }
                message.seen = true
                try vault.put("incoming", key, JSONEncoder().encode(message))
                try vault.put("read-pending", "q." + key, Data(peer.uuidString.utf8))
            }
        }
    }
    func checking(_ ids: [UUID], peer: UUID) throws -> [UUID] {
        try vault.transaction {
            try ids.filter { id in
                guard let bytes = try vault.get("outgoing", id.uuidString.lowercased()) else { return false }
                let message = try JSONDecoder().decode(StoredChat.self, from: bytes)
                return message.features?.reaction == nil && message.envelope.recipient == peer
                    && ["accepted", "delivered"].contains(message.state)
            }
        }
    }
    func pending(before: String?) throws -> (groups: [UUID: [UUID]], next: String?) {
        try vault.transaction {
            let keys = try vault.pageIDs("read-pending", prefix: "q.", before: before, limit: 64)
            var groups: [UUID: [UUID]] = [:]
            for key in keys {
                guard let id = UUID(uuidString: String(key.dropFirst(2))),
                    let data = try vault.get("read-pending", key),
                    let peer = UUID(uuidString: String(decoding: data, as: UTF8.self))
                else { throw MessageVault.Failure.invalidRecord }
                groups[peer, default: []].append(id)
            }
            return (groups, keys.count == 64 ? keys.last : nil)
        }
    }
    func apply(_ reply: ChatReadReply, for peer: UUID, seen: [UUID], check: [UUID]) throws -> Bool {
        guard Set(reply.acknowledged).isSubset(of: Set(seen)), Set(reply.read).isSubset(of: Set(check)) else {
            throw MessageVault.Failure.invalidRecord
        }
        return try vault.transaction {
            for id in reply.acknowledged { try vault.remove("read-pending", "q." + id.uuidString.lowercased()) }
            var changed = false
            for id in reply.read {
                let key = id.uuidString.lowercased()
                guard let bytes = try vault.get("outgoing", key) else { continue }
                var message = try JSONDecoder().decode(StoredChat.self, from: bytes)
                guard message.features?.reaction == nil, message.envelope.recipient == peer,
                    ["delivered", "accepted"].contains(message.state)
                else { continue }
                try ConversationStreak.observe(
                    vault, scope: .direct, id: peer, sender: vault.account, at: message.envelope.createdAt)
                message.state = "read"
                try vault.put("outgoing", key, JSONEncoder().encode(message))
                try vault.remove("pending", key)
                changed = true
            }
            return changed
        }
    }
}

@MainActor @Observable final class ChatActivityEvents {
    private let ledger: ChatReadLedger
    private let eligible: (UUID) -> Bool
    private let sendTyping: (UUID, Bool) async throws -> Void
    private let receipts: (UUID, [UUID], [UUID]) async throws -> ChatReadReply
    private let changed: () -> Void
    private var remote: [UUID: Task<Void, Never>] = [:]
    @ObservationIgnored private var currentPeer: UUID?
    @ObservationIgnored private var seen: [UUID] = []
    @ObservationIgnored private var checking: [UUID] = []
    @ObservationIgnored private var typingPeer: UUID?
    @ObservationIgnored private var activeAt = Date.distantPast
    @ObservationIgnored private var idle: Task<Void, Never>?
    @ObservationIgnored private var sender: Task<Void, Never>?
    @ObservationIgnored private var worker: Task<Void, Never>?
    @ObservationIgnored private var typing: [UUID: Bool] = [:]
    @ObservationIgnored private var dirty = false
    @ObservationIgnored private var closed = false
    init(
        vault: MessageVault, eligible: @escaping (UUID) -> Bool,
        sendTyping: @escaping (UUID, Bool) async throws -> Void,
        receipts: @escaping (UUID, [UUID], [UUID]) async throws -> ChatReadReply, changed: @escaping () -> Void
    ) {
        ledger = ChatReadLedger(vault)
        self.eligible = eligible
        self.sendTyping = sendTyping
        self.receipts = receipts
        self.changed = changed
    }
    func isTyping(_ peer: UUID) -> Bool { remote[peer] != nil && eligible(peer) }
    func event(_ event: ChatForegroundEvent) {
        guard !closed else { return }
        switch event {
        case .inbox: wake()
        case let .receipts(peer): if peer == currentPeer { wake() }
        case let .typing(peer, active):
            remote.removeValue(forKey: peer)?.cancel()
            if active && peer == currentPeer && eligible(peer) {
                remote[peer] = Task { [weak self] in
                    do {
                        try await Task.sleep(for: .seconds(7))
                        self?.remote.removeValue(forKey: peer)
                    } catch {}
                }
            }
        }
    }
    func composer(_ peer: UUID, active: Bool) {
        guard !closed, active ? eligible(peer) : typingPeer == peer else { return }
        if active && typingPeer == peer {
            if Date().timeIntervalSince(activeAt) >= 4 {
                typing[peer] = true
                activeAt = Date()
            }
        } else {
            if let previous = typingPeer { typing[previous] = false }
            typingPeer = active ? peer : nil
            if active {
                typing[peer] = true
                activeAt = Date()
            }
        }
        idle?.cancel()
        if active {
            idle = Task { [weak self] in
                do {
                    try await Task.sleep(for: .milliseconds(2500))
                    self?.composer(peer, active: false)
                } catch {}
            }
        }
        if sender == nil && !typing.isEmpty {
            sender = Task { [weak self] in
                guard let self else { return }
                defer { sender = nil }
                while !Task.isCancelled, let (peer, value) = typing.first {
                    typing.removeValue(forKey: peer)
                    if eligible(peer) { try? await sendTyping(peer, value) }
                }
            }
        }
    }
    func visible(_ peer: UUID, incoming: [UUID], outgoing: [UUID]) {
        let ids = Array(incoming.prefix(64)), candidates = Array(outgoing.prefix(64))
        guard !closed, !(currentPeer == peer && seen == ids && checking == candidates) else { return }
        let existing = currentPeer == peer ? Set(seen) : []
        if currentPeer != peer {
            remote.values.forEach { $0.cancel() }
            remote.removeAll()
        }
        currentPeer = peer
        seen = ids
        checking = candidates
        guard eligible(peer), !ids.isEmpty || !candidates.isEmpty else { return }
        Task { [weak self] in
            guard let self, !closed else { return }
            do {
                try await ledger.note(ids.filter { !existing.contains($0) }, peer: peer)
                wake()
            } catch {}
        }
    }
    func outgoingAccepted(_ id: UUID, peer: UUID) {
        if peer == currentPeer && checking.contains(id) { wake() }
    }
    func wake() {
        guard !closed else { return }
        dirty = true
        guard worker == nil else { return }
        worker = Task { [weak self] in
            guard let self else { return }
            defer { worker = nil }
            while dirty && !Task.isCancelled {
                do {
                    try await Task.sleep(for: .milliseconds(175))
                    dirty = false
                    try await flush()
                } catch { if Task.isCancelled { return } }
            }
        }
    }
    private func flush() async throws {
        let peer = currentPeer
        var check: [UUID] = []
        if let peer, eligible(peer) { check = try await ledger.checking(checking, peer: peer) }
        var before: String?
        repeat {
            try Task.checkCancellation()
            let page = try await ledger.pending(before: before)
            var groups = page.groups
            if let peer, !check.isEmpty, groups[peer] == nil { groups[peer] = [] }
            for (recipient, pending) in groups where eligible(recipient) {
                let queries = recipient == peer ? check : []
                let reply = try await receipts(recipient, pending, queries)
                try Task.checkCancellation()
                if try await ledger.apply(reply, for: recipient, seen: pending, check: queries) { changed() }
            }
            check = []
            before = page.next
        } while before != nil
    }
    func close() {
        closed = true
        idle?.cancel()
        sender?.cancel()
        worker?.cancel()
        remote.values.forEach { $0.cancel() }
        remote.removeAll()
    }
}
