import Foundation
import CryptoKit
import VipiCore

/// Account-local exposure records share chat encryption and account deletion.
/// Only hashes of language-pair/word faces and bounded counters are persisted.
final class VocabularyFamiliarityStore {
    private let vault: MessageVault
    private var cached: [String: VocabularyFamiliarity] = [:]
    private var idKey: SymmetricKey?
    init(vault: MessageVault) { self.vault = vault }
    private func key(_ span: ImmersionSpan, source: String, target: String) throws -> String {
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
        // Plain dictionary hashes would reveal vocabulary through offline guessing.
        return HMAC<SHA256>.authenticationCode(for: Data(["v1", source, target, span.original.lowercased(), span.translated]
            .joined(separator: "\0").utf8), using: idKey!).map { String(format: "%02x", $0) }.joined()
    }
    private func read(_ key: String) throws -> VocabularyFamiliarity {
        guard let data = try vault.get("immersion-exposure", key) else { return .init() }
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
}
