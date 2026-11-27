import Foundation
import CryptoKit
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers
@preconcurrency import AVFoundation

/// Private files are addressed only by authenticated UUIDs, never a filename
/// supplied by a message. Prepared manifests must commit into the draft first.
final class AttachmentRepository: Sendable {
    let account: UUID
    private let root: URL
    private let verified: URL
    private let crypto = MediaCryptography.shared
    init(account: UUID, directory: URL? = nil) throws {
        self.account = account
        let manager = FileManager.default
        root =
            (try directory
            ?? manager.url(
                for: .applicationSupportDirectory, in: .userDomainMask,
                appropriateFor: nil, create: true)).appendingPathComponent(
                "Attachments/\(account.uuidString.lowercased())", isDirectory: true)
        verified = try manager.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("Attachments/\(account.uuidString.lowercased())", isDirectory: true)
        for var url in [root, verified] {
            try manager.createDirectory(
                at: url, withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700, .protectionKey: FileProtectionType.complete])
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            try url.setResourceValues(values)
        }
    }
    static func eraseFiles(account: UUID) throws {
        let fm = FileManager.default
        for location in [FileManager.SearchPathDirectory.applicationSupportDirectory, .cachesDirectory] {
            let base = try fm.url(for: location, in: .userDomainMask, appropriateFor: nil, create: false)
            let owned = base.appendingPathComponent("Attachments").appendingPathComponent(
                account.uuidString.lowercased())
            if fm.fileExists(atPath: owned.path) { try fm.removeItem(at: owned) }
        }
    }
    func ciphertext(_ part: MediaPart) -> URL { root.appendingPathComponent(part.blobID + ".ciphertext") }
    func discardPrepared(_ manifest: AttachmentManifest) {
        for part in [manifest.original, manifest.thumbnail].compactMap({ $0 }) {
            try? FileManager.default.removeItem(at: ciphertext(part))
        }
    }
    private func copyBounded(_ source: URL, _ destination: URL) throws {
        let manager = FileManager.default
        guard source.isFileURL,
            manager.createFile(
                atPath: destination.path, contents: nil,
                attributes: [.posixPermissions: 0o600, .protectionKey: FileProtectionType.complete])
        else {
            throw MediaCryptography.Failure.invalidFile
        }
        let input = try FileHandle(forReadingFrom: source), output = try FileHandle(forWritingTo: destination)
        defer {
            try? input.close()
            try? output.close()
        }
        var count = 0
        while let data = try input.read(upToCount: 65536), !data.isEmpty {
            try Task.checkCancellation()
            count += data.count
            guard count <= MediaCryptography.maxBytes else { throw MediaCryptography.Failure.tooLarge }
            try output.write(contentsOf: data)
        }
        guard count > 0 else { throw MediaCryptography.Failure.invalidFile }
        try output.synchronize()
    }
    private func writeThumbnail(_ image: CGImage, _ destination: URL) throws {
        guard
            let output = CGImageDestinationCreateWithURL(
                destination as CFURL, UTType.jpeg.identifier as CFString, 1, nil)
        else {
            throw MediaCryptography.Failure.invalidFile
        }
        CGImageDestinationAddImage(output, image, [kCGImageDestinationLossyCompressionQuality: 0.8] as CFDictionary)
        guard CGImageDestinationFinalize(output) else { throw MediaCryptography.Failure.invalidFile }
    }
    func prepare(source: URL, kind: AttachmentKind) async throws -> AttachmentManifest {
        guard [.photo, .video, .voice].contains(kind) else { throw MediaCryptography.Failure.invalidManifest }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        let id = UUID().uuidString.lowercased(), key = MediaCryptography.freshKey()
        // AVFoundation selects a demuxer from the local URL's type hint.
        // Keep only a short native type extension, never a sender path/name.
        let sourceType = UTType(filenameExtension: source.pathExtension)
        let hint = sourceType?.preferredFilenameExtension ?? (kind == .voice ? "m4a" : kind == .video ? "mp4" : "img")
        let clear = verified.appendingPathComponent("inspect-\(UUID())").appendingPathExtension(hint)
        let thumb = verified.appendingPathComponent("thumbnail-\(UUID()).jpg")
        var created: [URL] = []
        defer {
            try? FileManager.default.removeItem(at: clear)
            try? FileManager.default.removeItem(at: thumb)
        }
        do {
            // Bound the provider import and inspect the same owned bytes we seal.
            try copyBounded(source, clear)
            var width: Int?, height: Int?, duration: Int?, thumbnail: MediaPart?
            let contentType: String
            var image: CGImage?
            if kind == .photo {
                guard let decoder = CGImageSourceCreateWithURL(clear as CFURL, nil),
                    let properties = CGImageSourceCopyPropertiesAtIndex(decoder, 0, nil) as? [CFString: Any],
                    let w = properties[kCGImagePropertyPixelWidth] as? NSNumber,
                    let h = properties[kCGImagePropertyPixelHeight] as? NSNumber,
                    (1...16384).contains(w.intValue), (1...16384).contains(h.intValue),
                    let type = CGImageSourceGetType(decoder), let mime = UTType(type as String)?.preferredMIMEType,
                    mime.hasPrefix("image/")
                else { throw MediaCryptography.Failure.invalidFile }
                try Self.checkPhotoDimensions(width: w.intValue, height: h.intValue)
                width = w.intValue
                height = h.intValue
                contentType = mime
                image = CGImageSourceCreateThumbnailAtIndex(
                    decoder, 0,
                    [
                        kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceCreateThumbnailWithTransform: true,
                        kCGImageSourceThumbnailMaxPixelSize: 256
                    ] as CFDictionary)
                guard image != nil else { throw MediaCryptography.Failure.invalidFile }
            } else {
                let asset = AVURLAsset(url: clear)
                let length = try await asset.load(.duration).seconds
                guard length.isFinite, length > 0, length <= 180 else { throw MediaCryptography.Failure.invalidFile }
                duration = Int((length * 1000).rounded())
                let video = try await asset.loadTracks(withMediaType: .video)
                let audio = try await asset.loadTracks(withMediaType: .audio)
                if kind == .video {
                    guard let track = video.first else { throw MediaCryptography.Failure.invalidFile }
                    let size = try await track.load(.naturalSize)
                    let transform = try await track.load(.preferredTransform)
                    let oriented = size.applying(transform)
                    width = Int(abs(oriented.width).rounded())
                    height = Int(abs(oriented.height).rounded())
                    guard (1...16384).contains(width!), (1...16384).contains(height!) else {
                        throw MediaCryptography.Failure.invalidFile
                    }
                    contentType = UTType(filenameExtension: source.pathExtension)?.preferredMIMEType ?? "video/mp4"
                    guard contentType.hasPrefix("video/") else { throw MediaCryptography.Failure.invalidFile }
                    let generator = AVAssetImageGenerator(asset: asset)
                    generator.appliesPreferredTrackTransform = true
                    generator.maximumSize = CGSize(width: 256, height: 256)
                    image = try await generator.image(at: .zero).image
                } else {
                    guard video.isEmpty, !audio.isEmpty else { throw MediaCryptography.Failure.invalidFile }
                    contentType = UTType(filenameExtension: source.pathExtension)?.preferredMIMEType ?? "audio/mp4"
                    guard contentType.hasPrefix("audio/") else { throw MediaCryptography.Failure.invalidFile }
                }
            }
            try Task.checkCancellation()
            let (original, originalFile) = try await crypto.seal(
                source: clear, directory: root, key: key, attachment: id, role: "original")
            created.append(originalFile)
            if let image {
                try writeThumbnail(image, thumb)
                let (part, file) = try await crypto.seal(
                    source: thumb, directory: root, key: key, attachment: id, role: "thumbnail", maxBytes: 512 * 1024)
                thumbnail = part
                created.append(file)
            }
            try Task.checkCancellation()
            let cleaned = String(
                String.UnicodeScalarView(source.lastPathComponent.unicodeScalars.filter { $0.value >= 32 }))
            let filename =
                cleaned.isEmpty
                ? (kind == .photo ? "Photo.jpg" : kind == .video ? "Video.mp4" : "Voice message.m4a")
                : String(cleaned.prefix(255))
            let manifest = AttachmentManifest(
                version: 1, id: id, kind: kind, key: key, original: original,
                thumbnail: thumbnail, filename: filename, contentType: contentType, width: width, height: height,
                durationMillis: duration)
            try manifest.validate()
            return manifest
        } catch {
            for file in created { try? FileManager.default.removeItem(at: file) }
            throw error
        }
    }
    @MainActor func ensureUploaded(
        _ manifest: AttachmentManifest, api: any ChatTransport,
        bytes: CiphertextTransport, device: DeviceCredential
    ) async throws {
        try manifest.validate()
        for part in [manifest.original] + (manifest.thumbnail.map { [$0] } ?? []) {
            let body = try JSONSerialization.data(withJSONObject: [
                "id": part.blobID,
                "ciphertext_bytes": part.ciphertextBytes, "ciphertext_sha256": part.ciphertextSHA256
            ])
            let state: MediaUploadState = try await api.request("POST", "/v1/media/uploads", body: body, device: device)
            guard state.matches(part) else { throw ServiceFailure(status: 0, code: "invalid_media_response") }
            switch state.state {
            case "ready": break
            case "uploading": _ = try await bytes.upload(part, source: ciphertext(part), device: device)
            default: throw ServiceFailure(status: 404, code: "media_unavailable")
            }
        }
    }
    private func matches(_ part: MediaPart, at url: URL) throws -> Bool {
        guard FileManager.default.fileExists(atPath: url.path) else { return false }
        let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard values.isRegularFile == true, values.fileSize == part.ciphertextBytes else { return false }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        var digest = SHA256()
        while let data = try file.read(upToCount: 65536), !data.isEmpty {
            try Task.checkCancellation()
            digest.update(data: data)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined() == part.ciphertextSHA256
    }
    enum PhotoFailure: Error { case dimensions }
    private static func checkPhotoDimensions(width: Int, height: Int) throws {
        guard (1...16384).contains(width), (1...16384).contains(height), width * height <= 64_000_000 else {
            throw PhotoFailure.dimensions
        }
    }
    private func obtain(_ part: MediaPart, bytes: CiphertextTransport, device: DeviceCredential) async throws -> URL {
        let source = ciphertext(part)
        if try matches(part, at: source) { return source }
        return try await bytes.download(part, destination: source, device: device)
    }
    func viewPhoto(_ manifest: AttachmentManifest, bytes: CiphertextTransport, device: DeviceCredential) async throws
        -> CGImage
    {
        try manifest.validate()
        guard manifest.kind == .photo else { throw MediaCryptography.Failure.invalidManifest }
        let source = try await obtain(manifest.original, bytes: bytes, device: device)
        let data = try await crypto.authenticatedBytes(
            source: source, key: manifest.key,
            attachment: manifest.id, part: manifest.original)
        try Task.checkCancellation()
        guard
            let decoder = CGImageSourceCreateWithData(
                data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
            let properties = CGImageSourceCopyPropertiesAtIndex(decoder, 0, nil) as? [CFString: Any],
            let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
            let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
            let type = CGImageSourceGetType(decoder), UTType(type as String)?.conforms(to: .image) == true
        else {
            throw MediaCryptography.Failure.invalidFile
        }
        try Self.checkPhotoDimensions(width: width.intValue, height: height.intValue)
        guard
            let image = CGImageSourceCreateThumbnailAtIndex(
                decoder, 0,
                [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceShouldCacheImmediately: true, kCGImageSourceThumbnailMaxPixelSize: 1536
                ] as CFDictionary)
        else { throw MediaCryptography.Failure.invalidFile }
        try Task.checkCancellation()
        return image
    }
    func open(_ manifest: AttachmentManifest, thumbnail: Bool, bytes: CiphertextTransport, device: DeviceCredential)
        async throws -> URL
    {
        try manifest.validate()
        let part: MediaPart
        if thumbnail {
            guard let value = manifest.thumbnail else { throw MediaCryptography.Failure.invalidManifest }
            part = value
        } else {
            part = manifest.original
        }
        let source = try await obtain(part, bytes: bytes, device: device)
        // AVFoundation relies on a file-type hint even after authenticated bytes
        // have been verified. Derive only a bounded platform MIME extension;
        // sender filenames never become paths or extensions.
        let mediaType = thumbnail ? "image/jpeg" : manifest.contentType
        let suggested = UTType(mimeType: mediaType)?.preferredFilenameExtension ?? "bin"
        let suffix = suggested.range(of: "^[A-Za-z0-9]{1,10}$", options: .regularExpression) != nil ? suggested : "bin"
        return try await crypto.open(
            source: source,
            destination: verified.appendingPathComponent("\(manifest.id).\(part.role).verified.\(suffix)"),
            key: manifest.key, attachment: manifest.id, part: part)
    }
    @MainActor func cancelUnsent(_ manifest: AttachmentManifest, api: any ChatTransport, device: DeviceCredential)
        async throws
    {
        struct Cancelled: Decodable { let cancelled: Bool }
        try manifest.validate()
        for part in [manifest.original] + (manifest.thumbnail.map { [$0] } ?? []) {
            let result: Cancelled = try await api.request("DELETE", "/v1/media/uploads/\(part.blobID)", device: device)
            guard result.cancelled else { throw ServiceFailure(status: 0, code: "invalid_media_response") }
        }
    }
}
