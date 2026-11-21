import Foundation
import Security

private struct ServiceErrorBody: Decodable { let error: String }
private final class NoServiceRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

@MainActor protocol ChatTransport {
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T
}
extension ChatTransport {
    func request<T: Decodable>(_ method: String, _ path: String, body: Data? = nil, device: DeviceCredential? = nil, query: [String: String] = [:]) async throws -> T {
        try await request(method, path, body: body, device: device, query: query, as: T.self)
    }
}

@MainActor protocol ChatAccessTokenSource {
    func accessToken(for userID: String, rejected: String?) async throws -> String
}
extension AuthenticationManager: ChatAccessTokenSource {}

@MainActor final class ServiceClient: ChatTransport {
    private let authentication: any ChatAccessTokenSource
    let userID: String
    var acceptsGroupEnvelopes = false
    private let endpoint: URL
    private let http: URLSession
    private let eventHTTP: URLSession
    init(authentication: any ChatAccessTokenSource, userID: String, endpoint: URL = URL(string: "https://api.mambovipi.app")!, responseTimeout: TimeInterval = 30) throws {
        var permitted = endpoint.scheme == "https"
        #if DEBUG
        permitted = permitted || (endpoint.scheme == "http" && endpoint.host == "127.0.0.1")
        #endif
        guard permitted, endpoint.user == nil, endpoint.password == nil, endpoint.query == nil, endpoint.fragment == nil,
            endpoint.path.isEmpty || endpoint.path == "/" else { throw ServiceFailure(status: 0, code: "invalid_service_address") }
        self.authentication = authentication; self.userID = userID; self.endpoint = endpoint
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil; config.httpCookieStorage = nil
        config.timeoutIntervalForRequest = max(25, min(90, responseTimeout))
        config.timeoutIntervalForResource = max(30, min(90, responseTimeout))
        http = URLSession(configuration: config, delegate: NoServiceRedirects(), delegateQueue: nil)
        let events = URLSessionConfiguration.ephemeral
        events.urlCache = nil; events.httpCookieStorage = nil
        events.timeoutIntervalForRequest = 30
        events.timeoutIntervalForResource = 86_400
        eventHTTP = URLSession(configuration: events, delegate: NoServiceRedirects(), delegateQueue: nil)
    }
    deinit { http.invalidateAndCancel(); eventHTTP.invalidateAndCancel() }
    func openEvents(device: DeviceCredential) async throws -> any ForegroundEventSocket {
        var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)!
        components.scheme = endpoint.scheme == "https" ? "wss" : "ws"
        components.path = "/v1/events"
        let token = try await authentication.accessToken(for: userID, rejected: nil)
        try Task.checkCancellation()
        var request = URLRequest(url: components.url!)
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
        request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
        request.setValue("1", forHTTPHeaderField:"X-Vipi-Chat-Events")
        return NativeEventSocket(task: eventHTTP.webSocketTask(with: request)) { [authentication, userID] in
            _ = try await authentication.accessToken(for: userID, rejected: token)
        }
    }
    func request<T: Decodable>(_ method: String, _ path: String, body: Data? = nil, device: DeviceCredential? = nil, query: [String: String] = [:], as type: T.Type = T.self) async throws -> T {
        guard path.hasPrefix("/v1/"), !path.contains(".."), !path.contains("?"), !path.contains("#"), let url = URL(string: path, relativeTo: endpoint)?.absoluteURL else { throw ServiceFailure(status: 0, code: "invalid_request") }
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        components.queryItems = query.isEmpty ? nil : query.sorted(by: { $0.key < $1.key }).map { URLQueryItem(name: $0.key, value: $0.value) }
        guard let requestURL = components.url else { throw ServiceFailure(status: 0, code: "invalid_request") }
        var token = try await authentication.accessToken(for: userID, rejected: nil)
        for attempt in 0...1 {
            var request = URLRequest(url: requestURL); request.httpMethod = method; request.httpBody = body
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            if device != nil, acceptsGroupEnvelopes, GroupsUpgrade.isEnvelopeRequest(method: method, path: path) {
                request.setValue(String(GroupsUpgrade.protocolVersion), forHTTPHeaderField: "X-Vipi-Group-Protocol")
            }
            if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
            if let device {
                request.setValue(device.id.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
                request.setValue(device.secret, forHTTPHeaderField: "X-Vipi-Device-Secret")
            }
            let (stream, response) = try await http.bytes(for: request)
            guard let response = response as? HTTPURLResponse, response.expectedContentLength <= 12_000_000 else { throw ServiceFailure(status: 0, code: "invalid_response") }
            var data = Data()
            for try await byte in stream {
                guard data.count < 12_000_000 else { throw ServiceFailure(status: 0, code: "response_too_large") }
                data.append(byte)
            }
            if (200...299).contains(response.statusCode) { return try JSONDecoder().decode(T.self, from: data) }
            let code = (try? JSONDecoder().decode(ServiceErrorBody.self, from: data).error) ?? "service_unavailable"
            if attempt == 0, response.statusCode == 401, code == "sign_in_required" { token = try await authentication.accessToken(for: userID, rejected: token) }
            else { throw ServiceFailure(status: response.statusCode, code: code) }
        }
        throw AuthenticationManager.SessionFailure.signInRequired
    }
}
