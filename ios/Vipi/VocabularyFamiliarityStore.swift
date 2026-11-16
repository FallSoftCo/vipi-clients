import Foundation
import CryptoKit
import VipiCore

/// Account-local exposure records share chat encryption and account deletion.
/// Only hashes of language-pair/word faces and bounded counters are persisted.
final class VocabularyFamiliarityStore {
    private let vault: MessageVault
    private var cached: [String: VocabularyFamiliarity] = [:]
    private var idKey: SymmetricKey?
    private var frameCached: [String: VocabularyFamiliarity] = [:]
    private(set) var frameHistoryRevision: UInt64 = 0
    init(vault: MessageVault) { self.vault = vault }
    private func ensureKey() throws -> SymmetricKey {
        if idKey == nil {
            let bytes = try vault.transaction {
                if let saved = try vault.get("immersion-metadata", "id-key-v1") {
                    guard saved.count == 32 else { throw MessageVault.Failure.invalidRecord }
                    return saved
                }
                let created = SymmetricKey(size: .bits256).withUnsafeBytes { Data($0) }
                try vault.put("immersion-metadata", "id-key-v1", created); return created
            }
            idKey = SymmetricKey(data: bytes)
        }
        return idKey!
    }
    private func key(_ span: ImmersionSpan, source: String, target: String) throws -> String {
        // Plain dictionary hashes would reveal vocabulary through offline guessing.
        return HMAC<SHA256>.authenticationCode(for: Data(["v1", source, target, span.original.lowercased(), span.translated]
            .joined(separator: "\0").utf8), using: try ensureKey()).map { String(format: "%02x", $0) }.joined()
    }
    private func frameKey(_ identity: ReviewedFrameIdentity) throws -> String {
        HMAC<SHA256>.authenticationCode(for: identity.encoded, using: try ensureKey()).map { String(format: "%02x", $0) }.joined()
    }
    private func read(_ key: String, namespace: String = "immersion-exposure") throws -> VocabularyFamiliarity {
        guard let data = try vault.get(namespace, key) else { return .init() }
        let record = try JSONDecoder().decode(VocabularyFamiliarity.self, from: data)
        guard (0...3650).contains(record.exposureDays), record.lastDay >= -1,
              record.lastDay <= 3_000_000 else { throw MessageVault.Failure.invalidRecord }
        return record
    }
    func targetMilliseconds(_ spans: [ImmersionSpan], source: String, target: String, day: Int) -> Int {
        guard !spans.isEmpty else { return 4500 }
        do {
            let ids = try spans.map { try key($0, source: source, target: target) }
            if ids.allSatisfy({ cached[$0] != nil }) {
                return ids.compactMap { cached[$0]?.targetMilliseconds(day: day) }.min() ?? 4500
            }
            return try vault.transaction {
                try ids.map { id in
                    let record = try cached[id] ?? read(id)
                    if cached.count < 4096 { cached[id] = record }
                    return record.targetMilliseconds(day: day)
                }.min() ?? 4500
            }
        } catch { return 4500 } // Storage failure cannot advance familiarity.
    }
    /// Call only after a complete visible target dwell; never for a lookup/cache hit.
    @discardableResult func observe(_ spans: [ImmersionSpan], source: String, target: String, day: Int) -> Bool {
        guard day >= 0, day <= 3_000_000, !spans.isEmpty else { return false }
        do {
            let ids = Set(try spans.map { try key($0, source: source, target: target) })
                .filter { cached[$0]?.lastDay != day }
            guard !ids.isEmpty else { return true }
            let saved = try vault.transaction {
                var updates: [String: VocabularyFamiliarity] = [:]
                for id in ids {
                    var value = try read(id)
                    if value.observe(day: day) { try vault.put("immersion-exposure", id, JSONEncoder().encode(value)) }
                    updates[id] = value
                }
                return updates
            }
            // Cache only committed records; an interrupted write is not exposure.
            if cached.count + saved.count > 4096 { cached.removeAll() }
            cached.merge(saved) { _, new in new }; return true
        } catch { return false }
    }
    struct FrameHistory { let seen: Bool, due: Bool }
    /// Failed reads are explicit: callers must not invent unseen/due history.
    func frameHistory(_ identities: [ReviewedFrameIdentity], day: Int) throws -> [FrameHistory?] {
        guard (0...3_000_000).contains(day), identities.count <= 4096 else { throw MessageVault.Failure.invalidRecord }
        let ids = try identities.map(frameKey)
        return try vault.transaction {
            ids.map { id -> FrameHistory? in
                let value: VocabularyFamiliarity
                do { value = try frameCached[id] ?? read(id, namespace:"immersion-frame-exposure-next") }
                catch { return nil } // A corrupt key cannot poison other eligible words.
                if frameCached.count < 4096 { frameCached[id] = value }
                let interval = value.exposureDays >= 5 ? 14 : value.exposureDays >= 4 ? 7 : value.exposureDays >= 3 ? 4 : value.exposureDays >= 2 ? 2 : 1
                return FrameHistory(seen:value.exposureDays > 0, due:value.exposureDays > 0 && day >= value.lastDay && day - value.lastDay >= interval)
            }
        }
    }
    /// Call only for approved references after a complete visible target dwell.
    @discardableResult func observeFrames(_ identities: [ReviewedFrameIdentity], day: Int) -> Bool {
        guard (0...3_000_000).contains(day), !identities.isEmpty, identities.count <= 128 else { return false }
        do {
            let ids = Set(try identities.map(frameKey))
            var changed = false
            let saved = try vault.transaction {
                var updates: [String:VocabularyFamiliarity] = [:]
                for id in ids {
                    var value = try read(id, namespace:"immersion-frame-exposure-next")
                    if value.observe(day:day) {
                        try vault.put("immersion-frame-exposure-next",id,JSONEncoder().encode(value)); changed = true
                    }
                    updates[id]=value
                }
                return updates
            }
            if frameCached.count + saved.count > 4096 { frameCached.removeAll() }
            frameCached.merge(saved) { _, new in new }
            if changed { frameHistoryRevision &+= 1 }
            return true
        } catch { return false }
    }

}
