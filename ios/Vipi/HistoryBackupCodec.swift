import Foundation
import CryptoKit
import CommonCrypto
import Security

struct HistoryBackupPeer: Codable, Equatable, Sendable {
    let id: UUID
    let username: String?
    let displayName: String?
}

struct HistoryBackupMessage: Codable, Equatable, Sendable {
    let id: UUID
    let peer: UUID
    let outgoing: Bool
    let createdAt: Int64
    let text: String
}

enum HistoryBackupRecord: Equatable, Sendable {
    case metadata(account: UUID, createdAt: Int64)
    case peer(HistoryBackupPeer)
    case message(HistoryBackupMessage)
    case end(records: Int, peers: Int, messages: Int)
}

/// VIPIHST1 is a history interchange format, never a transport-state backup.
/// The complete framing contract and independent vectors live in qa/backup.
enum HistoryBackupCodec {
    enum Failure: Error { case damaged, passwordLength, differentAccount, conflict, cancelled }
    struct Summary: Equatable, Sendable {
        let peers: Int
        let messages: Int
        let sha256: Data
    }
    static let maxFileBytes = 1_073_741_824
    static let maxRecordBytes = 262_144
    static let maxRecords = 200_000
    static let iterations: UInt32 = 600_000
    private static let magic = Data("VIPIHST1".utf8)
    private static let maxTimestamp: Int64 = 253_402_300_799_999

    static func passwordBytes(_ password: String) throws -> Data {
        let value = password.precomposedStringWithCanonicalMapping
        let bytes = Data(value.utf8)
        guard value.unicodeScalars.count >= 12, (12...1024).contains(bytes.count) else { throw Failure.passwordLength }
        return bytes
    }
    static func deriveKey(password: String, salt: Data) throws -> Data {
        guard salt.count == 16 else { throw Failure.damaged }
        var password = try passwordBytes(password), key = Data(count: 32)
        defer { password.resetBytes(in: password.startIndex..<password.endIndex) }
        let status = key.withUnsafeMutableBytes { output in
            password.withUnsafeBytes { input in
                salt.withUnsafeBytes { saltBytes in
                    CCKeyDerivationPBKDF(CCPBKDFAlgorithm(kCCPBKDF2),
                        input.baseAddress?.assumingMemoryBound(to: CChar.self), password.count,
                        saltBytes.baseAddress?.assumingMemoryBound(to: UInt8.self), salt.count,
                        CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256), iterations,
                        output.baseAddress?.assumingMemoryBound(to: UInt8.self), 32)
                }
            }
        }
        guard status == kCCSuccess else { throw Failure.damaged }
        return key
    }
    static func random(_ count: Int) throws -> Data {
        var bytes = Data(count: count)
        let status = bytes.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, count, $0.baseAddress!) }
        guard status == errSecSuccess else { throw Failure.damaged }
        return bytes
    }
    private static func uint32(_ value: UInt32) -> Data {
        Data([UInt8((value >> 24) & 255), UInt8((value >> 16) & 255), UInt8((value >> 8) & 255), UInt8(value & 255)])
    }
    private static func number(_ bytes: Data) -> UInt32 {
        bytes.reduce(0) { ($0 << 8) | UInt32($1) }
    }
    private static func read(_ file: FileHandle, count: Int) throws -> Data {
        var bytes = Data()
        while bytes.count < count {
            let chunk = try file.read(upToCount: count - bytes.count) ?? Data()
            guard !chunk.isEmpty else { throw Failure.damaged }
            bytes.append(chunk)
        }
        return bytes
    }

    final class Writer {
        private let file: FileHandle
        private let header: Data
        private let key: SymmetricKey
        private var validator: Validator
        private var byteCount = 36
        private var closed = false
        init(url: URL, password: String, account: UUID,
             salt: Data? = nil, noncePrefix: Data? = nil) throws {
            let salt = try salt ?? random(16), prefix = try noncePrefix ?? random(8)
            guard salt.count == 16, prefix.count == 8 else { throw Failure.damaged }
            header = magic + uint32(iterations) + salt + prefix
            key = SymmetricKey(data: try deriveKey(password: password, salt: salt))
            validator = Validator(account: account)
            guard !FileManager.default.fileExists(atPath: url.path),
                  FileManager.default.createFile(atPath: url.path, contents: nil,
                    attributes: [.posixPermissions: 0o600, .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else { throw Failure.damaged }
            file = try FileHandle(forWritingTo: url)
            try file.write(contentsOf: header)
        }
        deinit { try? file.close() }
        func append(_ record: HistoryBackupRecord) throws {
            try autoreleasepool { try appendRecord(record) }
        }
        private func appendRecord(_ record: HistoryBackupRecord) throws {
            try Task.checkCancellation()
            guard !closed, validator.records < maxRecords else { throw Failure.damaged }
            let index = uint32(UInt32(validator.records))
            let raw = try serialize(record)
            guard (1...maxRecordBytes).contains(raw.count) else { throw Failure.damaged }
            try validator.accept(record)
            let length = uint32(UInt32(raw.count + 16))
            let sealed = try AES.GCM.seal(raw, using: key, nonce: AES.GCM.Nonce(data: header.suffix(8) + index), authenticating: header + index + length)
            let frame = length + sealed.ciphertext + sealed.tag
            byteCount += frame.count
            guard byteCount <= maxFileBytes else { throw Failure.damaged }
            try file.write(contentsOf: frame)
        }
        func finish() throws {
            guard validator.ended, !closed else { throw Failure.damaged }
            try file.synchronize(); try file.close(); closed = true
        }
    }

    /// Callback execution does not imply acceptance. Only a successful return
    /// verifies footer and EOF. Mutating consumers must wrap the whole read in
    /// a vault transaction so any later failure rolls back all earlier records.
    static func inspect(url: URL, password: String, account: UUID,
                        consume: (HistoryBackupRecord) throws -> Void = { _ in }) throws -> Summary {
        let file = try FileHandle(forReadingFrom: url); defer { try? file.close() }
        let size = try file.seekToEnd(); try file.seek(toOffset: 0)
        guard (56...UInt64(maxFileBytes)).contains(size) else { throw Failure.damaged }
        let header = try read(file, count: 36)
        guard header.prefix(8) == magic, number(header.subdata(in: 8..<12)) == iterations else { throw Failure.damaged }
        let key = SymmetricKey(data: try deriveKey(password: password, salt: header.subdata(in: 12..<28)))
        var validator = Validator(account: account), digest = SHA256(), readBytes: UInt64 = 36
        digest.update(data: header)
        while !validator.ended {
            try autoreleasepool {
                try Task.checkCancellation()
                guard validator.records < maxRecords else { throw Failure.damaged }
                let lengthBytes = try read(file, count: 4), length = Int(number(lengthBytes))
                guard (17...(maxRecordBytes + 16)).contains(length), readBytes + 4 + UInt64(length) <= size else { throw Failure.damaged }
                let encrypted = try read(file, count: length), index = uint32(UInt32(validator.records))
                readBytes += 4 + UInt64(length); digest.update(data: lengthBytes); digest.update(data: encrypted)
                let box = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: header.suffix(8) + index), ciphertext: encrypted.dropLast(16), tag: encrypted.suffix(16))
                let raw: Data
                do { raw = try AES.GCM.open(box, using: key, authenticating: header + index + lengthBytes) }
                catch { throw Failure.damaged }
                let record = try parse(raw)
                try validator.accept(record)
                try consume(record)
            }
        }
        guard readBytes == size, (try file.read(upToCount: 1) ?? Data()).isEmpty else { throw Failure.damaged }
        return Summary(peers: validator.peers.count, messages: validator.messages.count, sha256: Data(digest.finalize()))
    }

    private struct Validator {
        let account: UUID
        var records = 0, peers = Set<UUID>(), messages = Set<UUID>()
        var ended = false
        mutating func accept(_ record: HistoryBackupRecord) throws {
            guard !ended, records < maxRecords else { throw Failure.damaged }
            switch record {
            case .metadata(let actual, let date):
                guard records == 0, validTime(date) else { throw Failure.damaged }
                guard actual == account else { throw Failure.differentAccount }
            case .peer(let peer):
                guard records > 0, messages.isEmpty, peer.id != account, peers.insert(peer.id).inserted else { throw Failure.damaged }
                if let username = peer.username {
                    guard username.range(of: "^[a-z][a-z0-9_]{2,23}$", options: .regularExpression) != nil else { throw Failure.damaged }
                }
                if let name = peer.displayName {
                    guard (1...80).contains(name.unicodeScalars.count), !name.unicodeScalars.contains(where: {
                        switch $0.properties.generalCategory {
                        case .control, .format, .surrogate, .privateUse, .unassigned: true
                        default: false
                        }
                    }) else { throw Failure.damaged }
                }
            case .message(let message):
                guard records > 0, peers.contains(message.peer), messages.insert(message.id).inserted,
                      validTime(message.createdAt), message.text.utf8.count <= 32768,
                      message.text.unicodeScalars.contains(where: { !$0.properties.isWhitespace && !(0x1c...0x1f).contains($0.value) }) else { throw Failure.damaged }
            case .end(let count, let peerCount, let messageCount):
                guard records > 0, count == records, peerCount == peers.count, messageCount == messages.count else { throw Failure.damaged }
                ended = true
            }
            records += 1
        }
    }
    private static func validTime(_ value: Int64) -> Bool { (0...maxTimestamp).contains(value) }
    private static func serialize(_ record: HistoryBackupRecord) throws -> Data {
        let object: [String: Any]
        switch record {
        case .metadata(let account, let date):
            object = ["type": "metadata", "version": 1, "account_id": account.uuidString.lowercased(), "created_at_ms": date]
        case .peer(let peer):
            object = ["type": "peer", "id": peer.id.uuidString.lowercased(), "username": peer.username as Any? ?? NSNull(), "display_name": peer.displayName as Any? ?? NSNull()]
        case .message(let message):
            object = ["type": "message", "id": message.id.uuidString.lowercased(), "peer_id": message.peer.uuidString.lowercased(), "direction": message.outgoing ? "outgoing" : "incoming", "sent_at_ms": message.createdAt, "text": message.text]
        case .end(let records, let peers, let messages):
            object = ["type": "end", "record_count": records, "peer_count": peers, "message_count": messages]
        }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
    }

    /// Flat schemas permit a small strict tokenizer. Foundation's ordinary
    /// keyed decoder collapses duplicate JSON keys, which this format rejects.
    private enum Value { case text(String), integer(Int64), null }
    private struct ObjectParser {
        let bytes: [UInt8]
        var offset = 0
        mutating func whitespace() { while offset < bytes.count && [9, 10, 13, 32].contains(bytes[offset]) { offset += 1 } }
        mutating func take(_ expected: UInt8) throws {
            whitespace(); guard offset < bytes.count, bytes[offset] == expected else { throw Failure.damaged }; offset += 1
        }
        mutating func string() throws -> String {
            whitespace(); let start = offset; try take(34)
            while offset < bytes.count {
                let byte = bytes[offset]; offset += 1
                if byte == 34 {
                    do { return try JSONDecoder().decode(String.self, from: Data(bytes[start..<offset])) }
                    catch { throw Failure.damaged }
                }
                if byte == 92 { guard offset < bytes.count else { throw Failure.damaged }; offset += 1 }
                else if byte < 32 { throw Failure.damaged }
            }
            throw Failure.damaged
        }
        mutating func object() throws -> [String: Value] {
            try take(123); whitespace(); var result: [String: Value] = [:]
            if offset < bytes.count, bytes[offset] == 125 { offset += 1 }
            else {
                while true {
                    let key = try string(); guard result[key] == nil else { throw Failure.damaged }; try take(58); whitespace()
                    guard offset < bytes.count else { throw Failure.damaged }
                    if bytes[offset] == 34 { result[key] = .text(try string()) }
                    else if bytes[offset] == 110 {
                        guard offset + 4 <= bytes.count, Array(bytes[offset..<(offset + 4)]) == Array("null".utf8) else { throw Failure.damaged }
                        offset += 4; result[key] = .null
                    } else {
                        let start = offset
                        while offset < bytes.count && (48...57).contains(bytes[offset]) { offset += 1 }
                        guard offset > start, offset - start == 1 || bytes[start] != 48,
                              let value = Int64(String(decoding: bytes[start..<offset], as: UTF8.self)) else { throw Failure.damaged }
                        result[key] = .integer(value)
                    }
                    whitespace(); guard offset < bytes.count else { throw Failure.damaged }
                    if bytes[offset] == 125 { offset += 1; break }
                    try take(44)
                }
            }
            whitespace(); guard offset == bytes.count else { throw Failure.damaged }; return result
        }
    }
    private static func parse(_ raw: Data) throws -> HistoryBackupRecord {
        guard String(data: raw, encoding: .utf8) != nil else { throw Failure.damaged }
        var parser = ObjectParser(bytes: Array(raw)); let values = try parser.object()
        func text(_ key: String) throws -> String { guard case .text(let value)? = values[key] else { throw Failure.damaged }; return value }
        func optional(_ key: String) throws -> String? {
            if case .null? = values[key] { return nil }; return try text(key)
        }
        func integer(_ key: String) throws -> Int64 { guard case .integer(let value)? = values[key] else { throw Failure.damaged }; return value }
        func uuid(_ key: String) throws -> UUID {
            let value = try text(key)
            guard let id = UUID(uuidString: value), id.uuidString.lowercased() == value else { throw Failure.damaged }; return id
        }
        func keys(_ names: Set<String>) throws { guard Set(values.keys) == names else { throw Failure.damaged } }
        switch try text("type") {
        case "metadata":
            try keys(["type", "version", "account_id", "created_at_ms"])
            guard try integer("version") == 1 else { throw Failure.damaged }
            return try .metadata(account: uuid("account_id"), createdAt: integer("created_at_ms"))
        case "peer":
            try keys(["type", "id", "username", "display_name"])
            return try .peer(HistoryBackupPeer(id: uuid("id"), username: optional("username"), displayName: optional("display_name")))
        case "message":
            try keys(["type", "id", "peer_id", "direction", "sent_at_ms", "text"])
            let direction = try text("direction"); guard ["incoming", "outgoing"].contains(direction) else { throw Failure.damaged }
            return try .message(HistoryBackupMessage(id: uuid("id"), peer: uuid("peer_id"), outgoing: direction == "outgoing", createdAt: integer("sent_at_ms"), text: text("text")))
        case "end":
            try keys(["type", "record_count", "peer_count", "message_count"])
            let counts = try [integer("record_count"), integer("peer_count"), integer("message_count")]
            guard counts.allSatisfy({ (0...Int64(maxRecords)).contains($0) }) else { throw Failure.damaged }
            return .end(records: Int(counts[0]), peers: Int(counts[1]), messages: Int(counts[2]))
        default: throw Failure.damaged
        }
    }
}
