import Foundation
import CryptoKit
import Darwin

enum AttachmentKind: String, Codable, Sendable { case photo, video, voice, file }
struct MediaPart: Codable, Equatable, Sendable {
    let blobID: String
    let role: String
    let plaintextBytes: Int
    let ciphertextBytes: Int
    let ciphertextSHA256: String
    enum CodingKeys: String, CodingKey {
        case blobID = "blob_id", role, plaintextBytes = "plaintext_bytes"
        case ciphertextBytes = "ciphertext_bytes", ciphertextSHA256 = "ciphertext_sha256"
    }
    func validate(maxBytes: Int = MediaCryptography.maxBytes) throws {
        guard UUID(uuidString: blobID)?.uuidString.lowercased() == blobID,
              ["original", "thumbnail"].contains(role), (1...maxBytes).contains(plaintextBytes),
              ciphertextBytes == plaintextBytes + 28,
              ciphertextSHA256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else {
            throw MediaCryptography.Failure.invalidManifest
        }
    }
}

/// Key and descriptive metadata are encrypted in the existing Signal payload.
struct AttachmentManifest: Codable, Equatable, Sendable {
    let version: Int
    let id: String
    let kind: AttachmentKind
    let key: Data
    let original: MediaPart
    let thumbnail: MediaPart?
    let filename: String
    let contentType: String
    let width: Int?
    let height: Int?
    let durationMillis: Int?
    enum CodingKeys: String, CodingKey {
        case version, id, kind, key, original, thumbnail, filename, width, height
        case contentType = "content_type", durationMillis = "duration_ms"
    }
    var blobIDs: [String] { [original.blobID] + (thumbnail.map { [$0.blobID] } ?? []) }
    func validate() throws {
        guard version == 1, UUID(uuidString: id)?.uuidString.lowercased() == id, key.count == 32,
              !filename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, filename.count <= 255,
              !filename.unicodeScalars.contains(where: { $0.value < 32 }), (1...127).contains(contentType.count),
              original.role == "original", width.map({ (1...16384).contains($0) }) ?? true,
              height.map({ (1...16384).contains($0) }) ?? true,
              durationMillis.map({ (1...180000).contains($0) }) ?? true else { throw MediaCryptography.Failure.invalidManifest }
        guard thumbnail?.blobID != original.blobID else { throw MediaCryptography.Failure.invalidManifest }
        try original.validate()
        if let thumbnail { guard thumbnail.role == "thumbnail" else { throw MediaCryptography.Failure.invalidManifest }; try thumbnail.validate(maxBytes: 512 * 1024) }
    }
}

/// CryptoKit's standard combined AES-GCM format matches platform Android GCM.
/// Bounded memory on Apple is deliberate:32MiB maximum original, no unbounded
/// video reads. Call this actor from native transfer tasks, never the UI thread.
actor MediaCryptography {
    static let shared = MediaCryptography()
    private init() {}
    static let maxBytes = 32 * 1024 * 1024
    enum Failure: Error { case invalidManifest, invalidFile, tooLarge, authentication }
    static func freshKey() -> Data { SymmetricKey(size: .bits256).withUnsafeBytes { Data($0) } }
    private func aad(_ id: String, _ role: String) -> Data { Data("vipi-attachment-v1\0\(id)\0\(role)".utf8) }
    private func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    func seal(source: URL, directory: URL, key: Data, attachment: String, role: String,
              maxBytes: Int = MediaCryptography.maxBytes) throws -> (MediaPart, URL) {
        guard key.count == 32, UUID(uuidString: attachment)?.uuidString.lowercased() == attachment,
              ["original", "thumbnail"].contains(role), (1...Self.maxBytes).contains(maxBytes) else { throw Failure.invalidManifest }
        let values = try source.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard values.isRegularFile == true, let size = values.fileSize, size > 0 else { throw Failure.invalidFile }
        guard size <= maxBytes else { throw Failure.tooLarge }
        try Task.checkCancellation()
        let clear = try Data(contentsOf: source, options: .mappedIfSafe)
        guard clear.count == size else { throw Failure.invalidFile }
        let sealed = try AES.GCM.seal(clear, using: SymmetricKey(data: key), authenticating: aad(attachment, role))
        guard let ciphertext = sealed.combined else { throw Failure.authentication }
        try Task.checkCancellation()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: 0o700])
        let blob = UUID().uuidString.lowercased()
        let target = directory.appendingPathComponent(blob + ".ciphertext")
        try ciphertext.write(to: target, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: target.path)
        try MediaDurability.sync(target)
        let part = MediaPart(blobID: blob, role: role, plaintextBytes: clear.count,
                             ciphertextBytes: ciphertext.count, ciphertextSHA256: sha256(ciphertext))
        try part.validate(maxBytes: maxBytes)
        return (part, target)
    }
    func open(source: URL, destination: URL, key: Data, attachment: String, part: MediaPart) throws -> URL {
        let clear = try authenticatedBytes(source: source, key: key, attachment: attachment, part: part)
        try clear.write(to: destination, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
        try MediaDurability.sync(destination)
        return destination
    }

    func authenticatedBytes(source: URL, key: Data, attachment: String, part: MediaPart) throws -> Data {
        try part.validate(); guard key.count == 32 else { throw Failure.invalidManifest }
        let size = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize
        guard size == part.ciphertextBytes else { throw Failure.authentication }
        try Task.checkCancellation()
        let ciphertext = try Data(contentsOf: source, options: .mappedIfSafe)
        guard sha256(ciphertext) == part.ciphertextSHA256 else { throw Failure.authentication }
        let clear: Data
        do { clear = try AES.GCM.open(AES.GCM.SealedBox(combined: ciphertext), using: SymmetricKey(data: key),
                                     authenticating: aad(attachment, part.role)) }
        catch { throw Failure.authentication }
        guard clear.count == part.plaintextBytes else { throw Failure.authentication }
        try Task.checkCancellation()
        return clear
    }
}

enum MessageAttachments {
    static func validate(_ values: [AttachmentManifest]) throws {
        guard values.count <= 4, Set(values.map(\.id)).count == values.count else { throw MessageJournal.Failure.invalidMessage }
        for value in values { try value.validate() }
        let blobs = values.flatMap(\.blobIDs)
        guard blobs.count <= 8, Set(blobs).count == blobs.count else { throw MessageJournal.Failure.invalidMessage }
    }
}

/// Commit opaque/verified file bytes and their rename before journal references.
/// This is not a claim of qualification against physical power loss.
enum MediaDurability {
    static func sync(_ file: URL) throws {
        let descriptor = Darwin.open(file.path, O_RDWR | O_NOFOLLOW)
        guard descriptor >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        defer { Darwin.close(descriptor) }
        guard Darwin.fsync(descriptor) == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        let directory = Darwin.open(file.deletingLastPathComponent().path, O_RDONLY)
        guard directory >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        defer { Darwin.close(directory) }
        guard Darwin.fsync(directory) == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    }
}
