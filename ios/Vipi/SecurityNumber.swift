import CryptoKit
import Foundation
import LibSignalClient

struct SecurityNumber: Sendable, Equatable {
    let digits: String
    let binding: Data
    let verified: Bool
    var groups: [String] {
        stride(from: 0, to: digits.count, by: 5).map { start in
            String(digits.dropFirst(start).prefix(5))
        }
    }
    static func make(local: UUID, localKey: IdentityKey, peer: UUID, peerKey: IdentityKey, receipt: Data?) throws
        -> SecurityNumber
    {
        let localID = local.uuidString.lowercased(), peerID = peer.uuidString.lowercased()
        let fingerprint = try NumericFingerprintGenerator(iterations: 5200).create(
            version: 2,
            localIdentifier: Data(localID.utf8), localKey: localKey.publicKey,
            remoteIdentifier: Data(peerID.utf8), remoteKey: peerKey.publicKey)
        let digits = fingerprint.displayable.formatted
        guard digits.utf8.count == 60, digits.utf8.allSatisfy({ (48...57).contains($0) }) else {
            throw MessageVault.Failure.invalidRecord
        }
        var bytes = Data("vipi-identity-verification-v1\0\(localID)\0\(peerID)\0".utf8)
        bytes.append(localKey.serialize())
        bytes.append(peerKey.serialize())
        let binding = Data(SHA256.hash(data: bytes))
        return SecurityNumber(digits: digits, binding: binding, verified: receipt == binding)
    }
}
