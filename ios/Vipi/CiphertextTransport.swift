import Foundation
import CryptoKit

struct MediaUploadState: Decodable, Sendable {
    let id: String
    let state: String
    let ciphertext_bytes: Int
    let ciphertext_sha256: String
    func matches(_ part: MediaPart) -> Bool {
        id == part.blobID && ciphertext_bytes == part.ciphertextBytes && ciphertext_sha256 == part.ciphertextSHA256
    }
}
private struct MediaServiceError: Decodable { let error: String }
private final class NoCiphertextRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(
        _ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

/// Opaque streaming transport. No filename, MIME, key or plaintext enters it.
/// The production caller supplies its immutable-account authentication method.
final class CiphertextTransport: Sendable {
    private let endpoint: URL
    private let http: URLSession
    private let authorize: @MainActor @Sendable (String?) async throws -> String
    init(endpoint: URL, authorize: @escaping @MainActor @Sendable (String?) async throws -> String) throws {
        var permitted = endpoint.scheme == "https"
        #if DEBUG
        permitted = permitted || (endpoint.scheme == "http" && endpoint.host == "127.0.0.1")
        #endif
        guard permitted, endpoint.user == nil, endpoint.password == nil, endpoint.query == nil,
            endpoint.fragment == nil,
            endpoint.path.isEmpty || endpoint.path == "/"
        else { throw ServiceFailure(status: 0, code: "invalid_service_address") }
        self.endpoint = endpoint
        self.authorize = authorize
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 120
        configuration.httpMaximumConnectionsPerHost = 2
        http = URLSession(configuration: configuration, delegate: NoCiphertextRedirects(), delegateQueue: nil)
    }
    deinit { http.invalidateAndCancel() }
    private func request(_ method: String, part: MediaPart, device: DeviceCredential, token: String) throws
        -> URLRequest
    {
        try part.validate()
        guard let url = URL(string: "/v1/media/\(part.blobID)/ciphertext", relativeTo: endpoint)?.absoluteURL else {
            throw ServiceFailure(status: 0, code: "invalid_request")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
        request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
        request.setValue(
            method == "GET" ? "application/octet-stream" : "application/json", forHTTPHeaderField: "Accept")
        return request
    }
    private func smallBody(_ stream: URLSession.AsyncBytes) async throws -> Data {
        var data = Data()
        for try await byte in stream {
            guard data.count < 8192 else { throw ServiceFailure(status: 0, code: "media_response_too_large") }
            data.append(byte)
        }
        return data
    }
    private func checked(_ response: HTTPURLResponse, body: Data) throws {
        guard (200...299).contains(response.statusCode) else {
            throw ServiceFailure(
                status: response.statusCode,
                code: (try? JSONDecoder().decode(MediaServiceError.self, from: body).error) ?? "media_unavailable")
        }
    }
    private func authenticated<T: Sendable>(_ operation: @Sendable (String) async throws -> T) async throws -> T {
        var token = try await authorize(nil)
        for attempt in 0...1 {
            try Task.checkCancellation()
            do { return try await operation(token) } catch let error as ServiceFailure {
                if attempt == 0, error.status == 401, error.code == "sign_in_required" {
                    token = try await authorize(token)
                } else {
                    throw error
                }
            }
        }
        throw ServiceFailure(status: 401, code: "sign_in_required")
    }
    func upload(_ part: MediaPart, source: URL, device: DeviceCredential) async throws -> MediaUploadState {
        try part.validate()
        let values = try source.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard values.isRegularFile == true, values.fileSize == part.ciphertextBytes else {
            throw MediaCryptography.Failure.invalidFile
        }
        return try await authenticated { token in
            var request = try self.request("PUT", part: part, device: device, token: token)
            request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            request.setValue(String(part.ciphertextBytes), forHTTPHeaderField: "Content-Length")
            // A fresh stream for each explicit retry; no whole-video Data body.
            guard let input = InputStream(url: source) else { throw MediaCryptography.Failure.invalidFile }
            request.httpBodyStream = input
            let (stream, response) = try await self.http.bytes(for: request)
            defer { stream.task.cancel() }
            guard let response = response as? HTTPURLResponse else {
                throw ServiceFailure(status: 0, code: "invalid_response")
            }
            let data = try await self.smallBody(stream)
            try self.checked(response, body: data)
            let state = try JSONDecoder().decode(MediaUploadState.self, from: data)
            guard state.state == "ready", state.matches(part) else {
                throw ServiceFailure(status: 0, code: "invalid_media_response")
            }
            return state
        }
    }
    func download(_ part: MediaPart, destination: URL, device: DeviceCredential) async throws -> URL {
        try part.validate()
        return try await authenticated { token in
            let request = try self.request("GET", part: part, device: device, token: token)
            let (stream, response) = try await self.http.bytes(for: request)
            defer { stream.task.cancel() }
            guard let response = response as? HTTPURLResponse else {
                throw ServiceFailure(status: 0, code: "invalid_response")
            }
            if !(200...299).contains(response.statusCode) {
                try self.checked(response, body: try await self.smallBody(stream))
            }
            guard response.expectedContentLength == Int64(part.ciphertextBytes),
                response.value(forHTTPHeaderField: "X-Ciphertext-SHA256") == part.ciphertextSHA256
            else {
                throw MediaCryptography.Failure.authentication
            }
            let temporary = destination.deletingLastPathComponent().appendingPathComponent("download-\(UUID()).partial")
            guard
                FileManager.default.createFile(
                    atPath: temporary.path, contents: nil, attributes: [.posixPermissions: 0o600])
            else {
                throw MediaCryptography.Failure.invalidFile
            }
            defer { try? FileManager.default.removeItem(at: temporary) }
            let output = try FileHandle(forWritingTo: temporary)
            defer { try? output.close() }
            var digest = SHA256(), count = 0, buffer = Data()
            buffer.reserveCapacity(65536)
            for try await byte in stream {
                count += 1
                guard count <= part.ciphertextBytes else { throw MediaCryptography.Failure.authentication }
                buffer.append(byte)
                if buffer.count == 65536 {
                    try Task.checkCancellation()
                    digest.update(data: buffer)
                    try output.write(contentsOf: buffer)
                    buffer.removeAll(keepingCapacity: true)
                }
            }
            digest.update(data: buffer)
            try output.write(contentsOf: buffer)
            let hash = digest.finalize().map { String(format: "%02x", $0) }.joined()
            guard count == part.ciphertextBytes, hash == part.ciphertextSHA256 else {
                throw MediaCryptography.Failure.authentication
            }
            try output.synchronize()
            try output.close()
            try Task.checkCancellation()
            if FileManager.default.fileExists(atPath: destination.path) {
                _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
            } else {
                try FileManager.default.moveItem(at: temporary, to: destination)
            }
            try MediaDurability.sync(destination)
            return destination
        }
    }
}
