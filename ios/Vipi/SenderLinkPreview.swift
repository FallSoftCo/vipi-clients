import Foundation
import Network
import Security
import UIKit
import ImageIO

/// Sender-only HTTPS reader. Resolve once, connect to those validated bytes, and
/// authenticate TLS for the original hostname. The destination gets no cookies,
/// credentials, referrer, or identifying application headers.
enum SenderLinkPreview {
    enum Failure: Error { case unavailable }
    struct Response {
        let headers: [String: String]
        let body: Data
        let url: URL
    }
    #if DEBUG
    actor Qualification {
        static let shared = Qualification()
        private(set) var requests = 0
        func started() { requests += 1 }
    }
    #endif
    static func load(_ url: URL) async throws -> ChatFeatures.Preview {
        #if DEBUG
        await Qualification.shared.started()
        #endif
        let result = try await fetch(url, image: false)
        guard result.headers["content-type"]?.lowercased().hasPrefix("text/html") == true,
            let html = String(data: result.body, encoding: .utf8)
        else { throw Failure.unavailable }
        let title = meta("og:title", html) ?? match("<title[^>]*>([\\s\\S]*?)</title>", html) ?? ""
        let plain = title.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "&amp;", with: "&").replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'").split(whereSeparator: { $0.isWhitespace }).joined(
                separator: " ")
        var preview = ChatFeatures.Preview(
            url: url.absoluteString, title: ChatFeatures.excerpt(plain.isEmpty ? (url.host ?? "") : plain))
        if let raw = meta("og:image", html), let image = URL(string: raw, relativeTo: result.url)?.absoluteURL,
            image.host?.lowercased() == result.url.host?.lowercased(),
            let response = try? await fetch(image, image: true),
            response.headers["content-type"]?.hasPrefix("image/") == true
        {
            preview.thumbnail_jpeg = thumbnail(response.body)
        }
        return preview
    }
    private static func match(_ pattern: String, _ value: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
            let found = re.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)),
            let range = Range(found.range(at: 1), in: value)
        else { return nil }
        return String(value[range])
    }
    private static func meta(_ name: String, _ html: String) -> String? {
        let tag = "<meta\\b[^>]{0,2048}?(?:property|name)\\s*=\\s*[\"']" + name + "[\"'][^>]{0,2048}>"
        guard let range = html.range(of: tag, options: [.regularExpression, .caseInsensitive]) else { return nil }
        return match("content\\s*=\\s*\"([^\"]*)\"", String(html[range]))
            ?? match("content\\s*=\\s*'([^']*)'", String(html[range]))
    }
    private static func thumbnail(_ bytes: Data) -> Data? {
        guard let src = CGImageSourceCreateWithData(bytes as CFData, nil),
            let info = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
            let w = info[kCGImagePropertyPixelWidth] as? Int, let h = info[kCGImagePropertyPixelHeight] as? Int,
            (1...8192).contains(w), (1...8192).contains(h), w * h <= 16_777_216,
            let small = CGImageSourceCreateThumbnailAtIndex(
                src, 0,
                [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 112
                ] as CFDictionary),
            let data = UIImage(cgImage: small).jpegData(compressionQuality: 0.64),
            ChatFeatures.Preview.safeThumbnail(data)
        else { return nil }
        return data
    }
    static func allowedIPv4(_ n: UInt32) -> Bool {
        let a = n >> 24, b = n >> 16 & 255, c = n >> 8 & 255
        return
            !(a == 0 || a == 10 || a == 127 || a >= 224 || (a == 100 && (64...127).contains(b))
            || (a == 169 && b == 254) || (a == 172 && (16...31).contains(b))
            || (a == 192 && (b == 168 || b == 0 || (b == 88 && c == 99)))
            || (a == 198 && (b == 18 || b == 19 || (b == 51 && c == 100))) || (a == 203 && b == 0 && c == 113))
    }
    private static func publicAddress(_ host: String) async throws -> String {
        try await Task.detached(priority: .utility) {
            var hints = addrinfo()
            hints.ai_family = AF_UNSPEC
            hints.ai_socktype = SOCK_STREAM
            var head: UnsafeMutablePointer<addrinfo>?
            guard getaddrinfo(host, nil, &hints, &head) == 0 else { throw Failure.unavailable }
            defer { freeaddrinfo(head) }
            var cursor = head, result: String?
            while let row = cursor {
                let info = row.pointee
                cursor = info.ai_next
                guard let addr = info.ai_addr else { throw Failure.unavailable }
                if info.ai_family == AF_INET {
                    let n = UnsafeRawPointer(addr).assumingMemoryBound(to: sockaddr_in.self).pointee.sin_addr.s_addr
                    guard allowedIPv4(UInt32(bigEndian: n)) else { throw Failure.unavailable }
                } else if info.ai_family == AF_INET6 {
                    let addr6 = UnsafeRawPointer(addr).assumingMemoryBound(to: sockaddr_in6.self).pointee.sin6_addr
                    let bytes = withUnsafeBytes(of: addr6) { Array($0) }
                    guard bytes[0] & 0xe0 == 0x20,
                        !(bytes[0] == 0x20 && bytes[1] == 2),
                        !(bytes[0] == 0x20 && bytes[1] == 1
                            && (bytes[2] < 2 || (bytes[2] == 0x0d && bytes[3] == 0xb8))),
                        !(bytes[0] == 0x3f && bytes[1] == 0xff && bytes[2] < 0x10)
                    else { throw Failure.unavailable }
                } else {
                    continue
                }
                var buf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(addr, info.ai_addrlen, &buf, socklen_t(buf.count), nil, 0, NI_NUMERICHOST) == 0 {
                    if result == nil || info.ai_family == AF_INET { result = String(cString: buf) }
                }
            }
            guard let result else { throw Failure.unavailable }
            return result
        }.value
    }
    private static func fetch(_ first: URL, image: Bool) async throws -> Response {
        var url = first
        for _ in 0..<3 {
            try Task.checkCancellation()
            guard ChatFeatures.Preview.publicURL(url), let host = url.host,
                let parts = URLComponents(url: url, resolvingAgainstBaseURL: true)
            else { throw Failure.unavailable }
            let address = try await publicAddress(host)
            try Task.checkCancellation()
            let path =
                (parts.percentEncodedPath.isEmpty ? "/" : parts.percentEncodedPath)
                + (parts.percentEncodedQuery.map { "?" + $0 } ?? "")
            let request =
                "GET " + path + " HTTP/1.0\r\nHost: " + host
                + "\r\nConnection: close\r\nAccept-Encoding: identity\r\nAccept: " + (image ? "image/*" : "text/html")
                + "\r\n\r\n"
            let client = PinnedRead(address: address, host: host)
            let raw = try await client.read(Data(request.utf8), limit: image ? 256 * 1024 : 128 * 1024)
            guard let divider = raw.range(of: Data("\r\n\r\n".utf8)), divider.lowerBound < 16_384,
                let header = String(data: raw[..<divider.lowerBound], encoding: .isoLatin1)
            else { throw Failure.unavailable }
            let lines = header.components(separatedBy: "\r\n")
            guard let status = lines.first?.split(separator: " ").dropFirst().first.flatMap({ Int($0) }) else {
                throw Failure.unavailable
            }
            var headers = [String: String]()
            for line in lines.dropFirst() {
                if let i = line.firstIndex(of: ":") {
                    headers[line[..<i].lowercased()] = line[line.index(after: i)...].trimmingCharacters(
                        in: .whitespaces)
                }
            }
            if [301, 302, 303, 307, 308].contains(status),
                let next = headers["location"].flatMap({ URL(string: $0, relativeTo: url)?.absoluteURL })
            {
                if image && next.host?.lowercased() != first.host?.lowercased() { throw Failure.unavailable }
                url = next
                continue
            }
            guard status == 200, headers["transfer-encoding"] == nil else { throw Failure.unavailable }
            return Response(headers: headers, body: Data(raw[divider.upperBound...]), url: url)
        }
        throw Failure.unavailable
    }
    private final class PinnedRead: @unchecked Sendable {
        private let queue = DispatchQueue(label: "vipi.link-preview")
        private let connection: NWConnection
        private var continuation: CheckedContinuation<Data, Error>?
        private var buffer = Data()
        private var cancelled = false
        init(address: String, host: String) {
            let tls = NWProtocolTLS.Options()
            sec_protocol_options_set_min_tls_protocol_version(tls.securityProtocolOptions, .TLSv12)
            sec_protocol_options_set_tls_server_name(tls.securityProtocolOptions, host)
            sec_protocol_options_add_tls_application_protocol(tls.securityProtocolOptions, "http/1.1")
            sec_protocol_options_set_verify_block(
                tls.securityProtocolOptions,
                { _, trust, complete in
                    let object = sec_trust_copy_ref(trust).takeRetainedValue()
                    guard SecTrustSetPolicies(object, SecPolicyCreateSSL(true, host as CFString)) == errSecSuccess
                    else {
                        complete(false)
                        return
                    }
                    complete(SecTrustEvaluateWithError(object, nil))
                }, DispatchQueue.global(qos: .utility))
            connection = NWConnection(
                host: NWEndpoint.Host(address), port: .https, using: NWParameters(tls: tls, tcp: .init()))
        }
        func read(_ request: Data, limit: Int) async throws -> Data {
            try await withTaskCancellationHandler {
                try Task.checkCancellation()
                return try await withCheckedThrowingContinuation { c in
                    queue.async {
                        guard !self.cancelled else {
                            c.resume(throwing: CancellationError())
                            return
                        }
                        self.continuation = c
                        self.connection.stateUpdateHandler = { state in
                            if case .failed = state { self.finish(.failure(Failure.unavailable)) }
                            if case .ready = state {
                                self.connection.send(
                                    content: request,
                                    completion: .contentProcessed { error in
                                        if let error { self.finish(.failure(error)) } else { self.receive(limit) }
                                    })
                            }
                        }
                        self.connection.start(queue: self.queue)
                        self.queue.asyncAfter(deadline: .now() + 5) { self.finish(.failure(Failure.unavailable)) }
                    }
                }
            } onCancel: {
                self.queue.async {
                    self.cancelled = true
                    self.finish(.failure(CancellationError()))
                }
            }
        }
        private func receive(_ limit: Int) {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { data, _, complete, error in
                if let error {
                    self.finish(.failure(error))
                    return
                }
                if let data { self.buffer.append(data) }
                if self.buffer.count > limit {
                    self.finish(.failure(Failure.unavailable))
                    return
                }
                if complete {
                    self.finish(.success(self.buffer))
                } else if self.continuation != nil {
                    self.receive(limit)
                }
            }
        }
        private func finish(_ result: Result<Data, Error>) {
            guard let c = continuation else { return }
            continuation = nil
            connection.stateUpdateHandler = nil
            connection.cancel()
            c.resume(with: result)
        }
    }
}
